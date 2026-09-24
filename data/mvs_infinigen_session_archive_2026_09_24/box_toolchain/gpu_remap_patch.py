# -*- coding: utf-8 -*-
"""把 GC-MVSNet geo_weights.py 里唯一那处 cv2.remap 换成 GPU 上的 grid_sample。

为什么非改不可: 实测每步 +442 ms (方案B 3 次 ξ/步), 14.4 h/epoch -> 32.8 h/epoch (2.3×)。
瓶颈是 reproject_with_depth 里的 GPU->CPU->cv2.remap->GPU 往返: 上游 batch1×2源×3档=6 次/步,
我们 batch4×7源×3档=84 次/步。

🔴 这是【改写上游代码】, 不是复制。所以:
  1) 原路径一行不删, 用模块级开关 GPU_REMAP 切换, 随时可跑对照
  2) 必须过等价闸才允许打开
  3) 等价判据不是"逐位相同": cv2.remap 在 INTER_LINEAR 下把亚像素位置量化到 1/32 像素
     (OpenCV INTER_BITS=5), grid_sample 是全精度浮点 => 本来就不可能逐位相等。
     判据取【最终布尔掩码的逐像素一致率】与 ξ 的最大绝对差。

grid_sample(align_corners=True) 的坐标约定: -1 = 第 0 个像素中心, +1 = 第 W-1 个像素中心,
与 cv2.remap"整数坐标落在像素中心"一致; padding_mode='zeros' 对应 BORDER_CONSTANT(0)。

🔴 定位方式: 按【行号】不按字符串。这个仓库的源文件行尾带空格, 前两次字符串锚点都因此失配。
"""
import io, hashlib

P = "/root/diffmvs_gc/models/geo_weights.py"

HELPER = '''# ======================= PocketWorld 改写: GPU 版 remap =======================
# 上游这一处是 GPU->CPU->cv2.remap->GPU 往返, 在我们 batch4×7源 的规模下是主要开销。
# GPU_REMAP=False 时逐字走上游原路径(下面 if/else 的 else 分支), 原代码一行未删。
GPU_REMAP = False


def _remap_bilinear_gpu(src, x_map, y_map):
    """等价于 cv2.remap(src, x_map, y_map, cv2.INTER_LINEAR) + BORDER_CONSTANT(0)。
    src [H,W] cuda float; x_map/y_map [H,W] cuda float(像素坐标, 整数=像素中心)。"""
    H, W = src.shape[-2], src.shape[-1]
    gx = x_map * (2.0 / (W - 1)) - 1.0
    gy = y_map * (2.0 / (H - 1)) - 1.0
    grid = torch.stack((gx, gy), dim=-1).unsqueeze(0)
    out = torch.nn.functional.grid_sample(
        src.reshape(1, 1, H, W).float(), grid,
        mode='bilinear', padding_mode='zeros', align_corners=True)
    return out.reshape(H, W)
# =============================================================================

'''

NEW_REMAP = '''        if GPU_REMAP:
            # --- PocketWorld 改写: 同一件事全部留在显存里 ---
            x_src = xy_src[0].reshape([height, width])
            y_src = xy_src[1].reshape([height, width])
            sampled_depth_src = _remap_bilinear_gpu(
                depth_src.reshape(height, width), x_src, y_src)
        else:
'''

raw = io.open(P, "rb").read()
before = hashlib.md5(raw).hexdigest()
crlf = b"\r\n" in raw
lines = raw.decode("utf-8").replace("\r\n", "\n").split("\n")


def find_one(pred, what):
    hits = [i for i, l in enumerate(lines) if pred(l)]
    assert len(hits) == 1, "%s: 命中 %d 行 %s" % (what, len(hits), hits)
    return hits[0]


# --- 1) remap 块: 从 "x_src = xy_src[0]" 到 "sampled_depth_src = torch.from_numpy" ---
i0 = find_one(lambda l: l.strip().startswith("x_src = xy_src[0].reshape([height, width]).cpu()"), "remap 块起点")
i1 = find_one(lambda l: l.strip() == "sampled_depth_src = torch.from_numpy(sampled_depth_src)", "remap 块终点")
assert i1 > i0, (i0, i1)
block = lines[i0:i1 + 1]
assert any("cv2.remap" in l for l in block), "块里没有 cv2.remap"
print("remap 块 = 第 %d-%d 行, 共 %d 行" % (i0 + 1, i1 + 1, len(block)))
lines[i0:i1 + 1] = NEW_REMAP.rstrip("\n").split("\n") + ["    " + l for l in block]

# --- 2) 结尾那两行 from_numpy 只在 CPU 路径下做 ---
j0 = find_one(lambda l: l.strip() == "x_src = torch.from_numpy(x_src)", "putback x")
j1 = find_one(lambda l: l.strip() == "y_src = torch.from_numpy(y_src)", "putback y")
assert j1 == j0 + 1, (j0, j1)
lines[j0:j1 + 1] = ["        if not GPU_REMAP:",
                    "            x_src = torch.from_numpy(x_src)",
                    "            y_src = torch.from_numpy(y_src)"]

# --- 3) helper 插在 class 之前 ---
k = find_one(lambda l: l.startswith("class GeometricWeights:"), "class 锚点")
lines[k:k] = HELPER.rstrip("\n").split("\n") + [""]

s = "\n".join(lines)
if crlf:
    s = s.replace("\n", "\r\n")
out = s.encode("utf-8")
io.open(P, "wb").write(out)
print("geo_weights.py  %s -> %s  (上游 md5 45f5e3d5…, 已偏离; 开关默认 False)"
      % (before[:8], hashlib.md5(out).hexdigest()[:8]))
