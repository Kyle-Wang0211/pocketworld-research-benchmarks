# -*- coding: utf-8 -*-
"""第二处性能改写: 不要把同样的 4 个小矩阵逆算 28 遍, 也别每次在 CPU 建 meshgrid。

profile (stage4, batch4×7源 = 28 次 reproject, 整个 ξ 165.8 ms):
    4× torch.linalg.inv (3x3/4x4)   3.119 ms/次 × 28 = 87.3 ms  = 54%
    CPU 建 meshgrid + 搬显存         0.606 ms/次 × 28 = 17.0 ms  = 10%
    grid_sample 本体                0.103 ms/次 × 28 =  2.9 ms  = 1.8%
cuSOLVER 在 3×3 上的固定开销就是这么贵; 而参考视图那两个逆在 28 次里根本没变过。

两处都是【数值恒等】的重复计算消除, 不改算法:
  A) generate_geometric_weights 里对整批 p_mats 一次性批量求逆 (2 次调用替代 112 次)
  B) meshgrid 按 (W,H,device) 缓存在显存
均由 GPU_REMAP 开关控制, 关掉时逐字走上游原路径。
"""
import io, hashlib, re

P = "/root/diffmvs_gc/models/geo_weights.py"

NEW_REPROJECT = '''    # project the reference point cloud into the source view, then project back
    def reproject_with_depth(self, depth_ref, intrinsics_ref, extrinsics_ref, depth_src, intrinsics_src, extrinsics_src, invs=None):
        width, height = depth_ref.shape[1], depth_ref.shape[0]
        ## step1. project reference pixels to the source view
        # reference view x, y
        if GPU_REMAP:
            # PocketWorld: 同一 (W,H) 的网格是常量, 从显存缓存拿 (上游每次在 CPU 建再搬)
            x_ref, y_ref = _meshgrid_cached(width, height, depth_ref.device, True)
        else:
            x_ref, y_ref = torch.meshgrid(torch.arange(0, width), torch.arange(0, height), indexing='xy')
            x_ref, y_ref = x_ref.reshape([-1]), y_ref.reshape([-1])

        # PocketWorld: 四个小矩阵逆由调用方一次性批量算好传进来; 不传则逐字走上游
        if invs is None:
            inv_K_ref, inv_E_ref = torch.linalg.inv(intrinsics_ref), torch.linalg.inv(extrinsics_ref)
            inv_K_src, inv_E_src = torch.linalg.inv(intrinsics_src), torch.linalg.inv(extrinsics_src)
        else:
            inv_K_ref, inv_E_ref, inv_K_src, inv_E_src = invs

        # reference 3D space
        xyz_ref = torch.matmul(inv_K_ref,
                            torch.vstack((x_ref.to(device='cuda'),
                                          y_ref.to(device='cuda'),
                                          torch.ones_like(x_ref, device=torch.device('cuda')))) * depth_ref.reshape([-1]))
        # source 3D space
        xyz_src = torch.matmul(torch.matmul(extrinsics_src, inv_E_ref),
                            torch.vstack((xyz_ref.to(device='cuda'),
                                          torch.ones_like(x_ref, device=torch.device('cuda')))))[:3]
        # source view x, y
        K_xyz_src = torch.matmul(intrinsics_src, xyz_src)
        xy_src = K_xyz_src[:2] / K_xyz_src[2:3]

        ## reproject the source view points with source view depth estimation
        # find the depth estimation of the source view
        if GPU_REMAP:
            # --- PocketWorld 改写: 同一件事全部留在显存里 ---
            x_src = xy_src[0].reshape([height, width])
            y_src = xy_src[1].reshape([height, width])
            sampled_depth_src = _remap_bilinear_gpu(
                depth_src.reshape(height, width), x_src, y_src)
        else:
            x_src = xy_src[0].reshape([height, width]).cpu().detach().numpy()
            y_src = xy_src[1].reshape([height, width]).cpu().detach().numpy()
            sampled_depth_src = cv2.remap(np.squeeze(depth_src.cpu().detach().numpy()),
                                          x_src,
                                          y_src,
                                          interpolation=cv2.INTER_LINEAR)
            sampled_depth_src = torch.from_numpy(sampled_depth_src)

        # source 3D space
        # NOTE that we should use sampled source-view depth_here to project back
        xyz_src = torch.matmul(inv_K_src,
                               torch.vstack((xy_src, torch.ones_like(x_ref, device=torch.device('cuda')))) * sampled_depth_src.reshape([-1]).to(device='cuda'))
        # reference 3D space
        xyz_reprojected = torch.matmul(torch.matmul(extrinsics_ref, inv_E_src),
                                    torch.vstack((xyz_src.to(device='cuda'),
                                                  torch.ones_like(x_ref, device=torch.device('cuda')))))[:3]
        # source view x, y, depth
        depth_reprojected = xyz_reprojected[2].reshape([height, width])
        K_xyz_reprojected = torch.matmul(intrinsics_ref, xyz_reprojected)
        xy_reprojected = K_xyz_reprojected[:2] / K_xyz_reprojected[2:3]
        x_reprojected = xy_reprojected[0].reshape([height, width])
        y_reprojected = xy_reprojected[1].reshape([height, width])

        ## put back to cuda
        if not GPU_REMAP:
            x_src = torch.from_numpy(x_src)
            y_src = torch.from_numpy(y_src)

        return depth_reprojected, x_reprojected, y_reprojected, x_src, y_src
'''

MG_HELPER = '''

_MG = {}


def _meshgrid_cached(W, H, device, flat):
    """上游每次 reproject 都在 CPU 建一次 meshgrid 再搬显存 (实测 0.606 ms × 28 次/ξ)。
    同一 (W,H) 是常量, 缓存在显存。dtype 与上游一致 (arange 默认 int64)。"""
    key = (W, H, str(device), flat)
    if key not in _MG:
        x, y = torch.meshgrid(torch.arange(0, W, device=device),
                              torch.arange(0, H, device=device), indexing='xy')
        _MG[key] = (x.reshape([-1]), y.reshape([-1])) if flat else (x, y)
    return _MG[key]'''

raw = io.open(P, "rb").read()
before = hashlib.md5(raw).hexdigest()
crlf = b"\r\n" in raw
lines = raw.decode("utf-8").replace("\r\n", "\n").split("\n")


def one(pred, what):
    h = [i for i, l in enumerate(lines) if pred(l)]
    assert len(h) == 1, "%s: 命中 %d 行 %s" % (what, len(h), h)
    return h[0]


# --- 0) meshgrid 缓存加进 helper 块 ---
k = one(lambda l: l.startswith("GPU_REMAP = False"), "GPU_REMAP")
lines[k + 1:k + 1] = MG_HELPER.split("\n")

# --- 1) 整段替换 reproject_with_depth (从它上面那行注释, 到下一个同级 def) ---
i0 = one(lambda l: l.strip() == "# project the reference point cloud into the source view, then project back", "reproject 注释")
i1 = next(i for i in range(i0 + 2, len(lines)) if lines[i].startswith("    def "))
old_n = i1 - i0
lines[i0:i1] = NEW_REPROJECT.rstrip("\n").split("\n") + [""]
print("reproject_with_depth: 替换 %d 行 -> %d 行" % (old_n, len(NEW_REPROJECT.rstrip("\n").split("\n")) + 1))

# --- 2) 两个 *_mask 方法: 加 invs 形参并透传, meshgrid 走缓存 ---
for name in ("geometric_consistency_mask", "geometric_inconsistency_mask"):
    i = one(lambda l, n=name: l.strip().startswith("def %s(self, depth_ref" % n), name + " 签名")
    assert lines[i].rstrip().endswith("stage_idx):"), lines[i]
    lines[i] = lines[i].rstrip()[:-2] + ", invs=None):"

# 这两个方法里各有一处 [H,W] 形状的 meshgrid
# 只取缩进恰好 8 空格的那两处 (两个 mask 方法里的); 12 空格那处是上面新写的 else 分支
mg = [i for i, l in enumerate(lines)
      if l == "        x_ref, y_ref = torch.meshgrid(torch.arange(0, width), torch.arange(0, height), indexing='xy')"]
assert len(mg) == 2, "两个 mask 方法里的 meshgrid 应为 2 处, 实际 %d" % len(mg)
for i in reversed(mg):
    lines[i:i + 1] = [
        "        if GPU_REMAP:",
        "            x_ref, y_ref = _meshgrid_cached(width, height, depth_ref.device, False)",
        "        else:",
        "            x_ref, y_ref = torch.meshgrid(torch.arange(0, width), torch.arange(0, height), indexing='xy')",
    ]

# 透传 invs 到 reproject_with_depth 的两处调用
calls = [i for i, l in enumerate(lines) if l.strip().startswith("depth_reprojected, x2d_reprojected, y2d_reprojected, x2d_src, y2d_src = self.reproject_with_depth(")]
assert len(calls) == 2, "reproject 调用应为 2 处, 实际 %d" % len(calls)
for i in reversed(calls):
    j = next(j for j in range(i, i + 12) if lines[j].rstrip().endswith("extrinsics_src)"))
    lines[j] = lines[j].rstrip()[:-1] + ", invs)"

# --- 3) generate_geometric_weights: 批量预算逆 + 传下去 ---
i = one(lambda l: l.strip() == "batch_size, _, _ = depth_est.shape", "gw 开头")
lines[i + 1:i + 1] = [
    "        # PocketWorld: 整批一次性求逆 (2 次批量调用替代 4×batch×src 次), 数值与逐次求逆恒等",
    "        if GPU_REMAP:",
    "            _iK = torch.linalg.inv(p_mats[:, :, 1, :3, :3])",
    "            _iE = torch.linalg.inv(p_mats[:, :, 0, :4, :4])",
]
# 在 src 循环里组装 invs: 插在 src_intrinsics 取出之后
i = one(lambda l: l.strip() == "src_intrinsics = p_mats[batch_idx, src_idx + 1, 1, :3, :3]", "src 内参取出")
lines[i + 1:i + 1] = [
    "                invs = ((_iK[batch_idx, 0], _iE[batch_idx, 0],",
    "                         _iK[batch_idx, src_idx + 1], _iE[batch_idx, src_idx + 1])",
    "                        if GPU_REMAP else None)",
]
# 三处 mask 调用补上 invs
for pat in ("stage_idx)",):
    pass
ends = [i for i, l in enumerate(lines)
        if l.strip() == "stage_idx)" or l.strip() == "stage_idx)  " or l.rstrip().endswith("                                                           stage_idx)")]
# 更稳的做法: 找 mask_in/dist_in 的三处调用, 把结尾的 stage_idx) 换成 stage_idx, invs)
targets = []
for i, l in enumerate(lines):
    if ("= self.geometric_consistency_mask(" in l or "= self.geometric_inconsistency_mask(" in l) and "def " not in l:
        j = next(j for j in range(i, i + 8) if lines[j].rstrip().endswith("stage_idx)"))
        targets.append(j)
assert len(targets) == 3, "generate_geometric_weights 里应有 3 处 mask 调用, 实际 %d" % len(targets)
for j in reversed(targets):
    lines[j] = lines[j].rstrip()[:-1] + ", invs)"

s = "\n".join(lines)
if crlf:
    s = s.replace("\n", "\r\n")
out = s.encode("utf-8")
io.open(P, "wb").write(out)
print("geo_weights.py  %s -> %s" % (before[:8], hashlib.md5(out).hexdigest()[:8]))
