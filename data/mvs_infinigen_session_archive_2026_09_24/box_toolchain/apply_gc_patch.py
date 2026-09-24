# -*- coding: utf-8 -*-
"""把 GC-MVSNet (WACV 2024 / Neurocomputing 2025, MIT) 的训练期几何一致性权重接进 CasDiffMVS。

上游 = github.com/vkvats/GC-MVSNet @ MIT
  models/geo_weights.py  md5 45f5e3d5f3deba422b26f667c8ac81c4  ← 逐字节拷入, 不改
  models/geo_utils.py    md5 fc2451a49ef92a5ef0d9f071b009688e  ← 同上
  (与 GC-MVSNet-PlusPlus 的同名文件 diff 为空, 两版一致)

本脚本只改三个文件, 每处都抄上游的【位置】而不只是常量:
  datasets/blend.py  ← 对照上游 datasets/bld_train.py:88-95 (read_src_depth) 与 :158/:178
  models/loss.py     ← 对照上游 models/loss.py:geo_loss 里 ξ 乘进逐像素损失的那一步
  train.py           ← 对照上游 train.py:186/:200 (src_depths 取出并传给 loss)

🔴 默认关闭 (--gc_weight 0)。关闭时 loss.py 走的是与改动前【逐字符相同】的原分支。
"""
import io, os, sys, hashlib

ROOT = "/root/diffmvs_gc"


def patch(relpath, edits):
    """🔴 官方这几个文件是 CRLF (blend.py/loss.py/train.py 实测 100% 行带 \\r)。
    按字节读、在内存里归一成 \\n 匹配锚点、写回前换回原线尾 —— 否则整份文件每行都变,
    diff 看不出真实改动量, 也和 09-14 那次 '补丁 11 行加 2 行删(CRLF 保留)' 的纪律冲突。"""
    p = os.path.join(ROOT, relpath)
    raw = io.open(p, "rb").read()
    before = hashlib.md5(raw).hexdigest()
    crlf = b"\r\n" in raw
    src = raw.decode("utf-8")
    if crlf:
        src = src.replace("\r\n", "\n")
    for i, (old, new) in enumerate(edits):
        n = src.count(old)
        assert n == 1, "%s edit#%d: 锚点出现 %d 次 (必须恰好 1 次)\n---\n%s\n---" % (relpath, i, n, old[:400])
        src = src.replace(old, new)
    if crlf:
        src = src.replace("\n", "\r\n")
    out = src.encode("utf-8")
    io.open(p, "wb").write(out)
    print("  %-22s %s -> %s  (%d 处, 线尾 %s)" % (
        relpath, before[:8], hashlib.md5(out).hexdigest()[:8], len(edits), "CRLF" if crlf else "LF"))


# ---------------------------------------------------------------- datasets/blend.py
patch("datasets/blend.py", [
    # 1) 构造参数, 默认 False => 不传就完全是原行为
    ("""        ndepths = 384,
    ):
        super(MVSDataset, self).__init__()
        self.datapath = datapath""",
     """        ndepths = 384,
        gc_src_depth = False,
    ):
        super(MVSDataset, self).__init__()
        self.gc_src_depth = gc_src_depth
        self.datapath = datapath"""),

    # 2) read_src_depth: 逐项对照上游 bld_train.py:88-95。上游三档 (w//4, w//2, w) 用 INTER_NEAREST;
    #    我们四档, 多一档 w//8, 用同一个 resize 写法与同一个插值 —— 沿上游代码形状外推分辨率, 不引入新常数。
    ("""    def read_depth(self, filename):
        # read pfm depth file
        depth_image = np.array(read_pfm(filename)[0], dtype=np.float32)
        return depth_image""",
     """    def read_depth(self, filename):
        # read pfm depth file
        depth_image = np.array(read_pfm(filename)[0], dtype=np.float32)
        return depth_image

    def read_src_depth(self, filename, s1, s2, s3, s4):
        \"\"\"源视图【真值】深度, 四档分辨率。抄 GC-MVSNet datasets/bld_train.py:88-95
        (上游三档 w//4 / w//2 / w, 全部 INTER_NEAREST);我们的 stage1 = w//8 是
        CasDiffMVS 多出来的一档, 用同一写法同一插值补齐。\"\"\"
        depth_hr = np.array(read_pfm(filename)[0], dtype=np.float32)
        h, w = depth_hr.shape
        s1.append(cv2.resize(depth_hr, (w // 8, h // 8), interpolation=cv2.INTER_NEAREST))
        s2.append(cv2.resize(depth_hr, (w // 4, h // 4), interpolation=cv2.INTER_NEAREST))
        s3.append(cv2.resize(depth_hr, (w // 2, h // 2), interpolation=cv2.INTER_NEAREST))
        s4.append(depth_hr)
        return s1, s2, s3, s4"""),

    # 3) 循环前初始化四个列表
    ("""        depth_ms = {}
        mask_ms = {}
        for i, vid in enumerate(view_ids):""",
     """        depth_ms = {}
        mask_ms = {}
        src_s1, src_s2, src_s3, src_s4 = [], [], [], []
        for i, vid in enumerate(view_ids):"""),

    # 4) else 分支 —— 位置同上游 bld_train.py:158 (i != 0 时读源深度)
    ("""                    "stage4": np.array((depth_ms["stage4"] >= depth_min) & (depth_ms["stage4"] <= depth_max), dtype=np.float32),
                }
""",
     """                    "stage4": np.array((depth_ms["stage4"] >= depth_min) & (depth_ms["stage4"] <= depth_max), dtype=np.float32),
                }
            elif self.gc_src_depth:
                src_s1, src_s2, src_s3, src_s4 = self.read_src_depth(
                    depth_filename, src_s1, src_s2, src_s3, src_s4)
"""),

    # 5) 返回值多带一项 —— 键名同上游 "src_depths"
    ("""        return {
            "imgs": imgs,
            "proj_matrices": proj_matrices_ms,
            "depth": depth_ms,
            "depth_values": depth_values,
            "mask": mask_ms,
        }""",
     """        out = {
            "imgs": imgs,
            "proj_matrices": proj_matrices_ms,
            "depth": depth_ms,
            "depth_values": depth_values,
            "mask": mask_ms,
        }
        if self.gc_src_depth:
            out["src_depths"] = {"stage1": src_s1, "stage2": src_s2,
                                 "stage3": src_s3, "stage4": src_s4}
        return out"""),
])

# ---------------------------------------------------------------- models/loss.py
patch("models/loss.py", [
    ("""import torch
import numpy as np
import torch.nn.functional as F
from .module import depth_to_disp
""",
     """import torch
import numpy as np
import torch.nn.functional as F
from .module import depth_to_disp

# CasDiffMVS 有四档 (stage1 w//8 / stage2 w//4 / stage3 w//2 / stage4 w),
# GC-MVSNet 只有三档 (w//4 / w//2 / w) 各带一组阈值。按【分辨率对应】取上游档位:
#   我们 stage2 (w//4) = 上游 stage1 -> idx 0   阈值 dist 1    / rdd 0.01
#   我们 stage3 (w//2) = 上游 stage2 -> idx 1   阈值 dist 0.5  / rdd 0.005
#   我们 stage4 (w)    = 上游 stage3 -> idx 2   阈值 dist 0.25 / rdd 0.0025
# 我们 stage1 (w//8) 在上游【没有对应档】。按"禁止自研"铁律不外推阈值, 该档不加权 (ξ≡1)。
_GC_STAGE_IDX = {1: None, 2: 0, 3: 1, 4: 2}
"""),

    ("""    loss_rate=0.8,
    iters=[1,3,3],
):""",
     """    loss_rate=0.8,
    iters=[1,3,3],
    geo_obj=None,
    proj_mats=None,
    src_depths=None,
):"""),

    ("""    conf_iter = 0
    for i, depth_esti in enumerate(inputs):
        depth_est = depth_to_disp(depth_esti, depth_min, depth_max)
""",
     """    conf_iter = 0
    for i, depth_esti in enumerate(inputs):
        # ξ 用【米制】深度算 (depth_esti 就是米制, depth_to_disp 之前), 与上游一致;
        # 算出来的权重再乘到归一化逆深度上的逐像素损失。全程 no_grad: 上游 geo_weights.py
        # 内部就有 .cpu().detach().numpy()+cv2.remap, ξ 本来就是权重不是可导路径。
        xi = None
        if geo_obj is not None:
            gidx = _GC_STAGE_IDX[stage_id[i]]
            if gidx is not None:
                sk = "stage{}".format(stage_id[i])
                with torch.no_grad():
                    xi = geo_obj.generate_geometric_weights(
                        torch.zeros_like(depth_esti),   # 上游 photo_mask 是死代码(赋值后从不被读),
                        depth_esti,                     # 传什么都不影响结果, 传零张量保证确定性
                        proj_mats[sk], src_depths[sk], gidx)[0]
                xi = xi.to(depth_esti.dtype)

        depth_est = depth_to_disp(depth_esti, depth_min, depth_max)
"""),

    ("""        if conf_flag[i]:
            # there is estimated confidence from diffusion model
            confidence = confs[conf_iter]
            conf_iter = conf_iter + 1
            uncertainty = 1 - confidence
            uncertainty = torch.clamp(uncertainty, min=1e-6)
            depth_loss = torch.abs(depth_est - depth_gt)
            depth_loss = depth_loss / uncertainty + args.conf_weight * torch.log(uncertainty)
            depth_loss = torch.mean(depth_loss[mask])
        else:
            depth_loss = F.l1_loss(depth_est[mask], depth_gt[mask], reduction='mean')""",
     """        if xi is None:
            # ↓↓↓ 与改动前【逐字符相同】的原分支, --gc_weight 0 时走这里 ↓↓↓
            if conf_flag[i]:
                # there is estimated confidence from diffusion model
                confidence = confs[conf_iter]
                conf_iter = conf_iter + 1
                uncertainty = 1 - confidence
                uncertainty = torch.clamp(uncertainty, min=1e-6)
                depth_loss = torch.abs(depth_est - depth_gt)
                depth_loss = depth_loss / uncertainty + args.conf_weight * torch.log(uncertainty)
                depth_loss = torch.mean(depth_loss[mask])
            else:
                depth_loss = F.l1_loss(depth_est[mask], depth_gt[mask], reduction='mean')
        else:
            # 位置同上游 models/loss.py:geo_entropy_loss —— ξ 乘在【逐像素】损失图上, 再按 mask 取均值
            if conf_flag[i]:
                confidence = confs[conf_iter]
                conf_iter = conf_iter + 1
                uncertainty = torch.clamp(1 - confidence, min=1e-6)
                loss_map = torch.abs(depth_est - depth_gt) / uncertainty \\
                           + args.conf_weight * torch.log(uncertainty)
            else:
                loss_map = torch.abs(depth_est - depth_gt)
            depth_loss = torch.mean((xi * loss_map)[mask])"""),
])

# ---------------------------------------------------------------- train.py
patch("train.py", [
    # 1) 参数。默认值全部照抄上游 train.py 的 argparse 默认 + train.sh 的实际取值。
    ("""parser.add_argument('--max_radius', type=float, default=2,""",
     """# ---- GC-MVSNet (WACV2024/Neurocomputing2025, MIT) 训练期几何一致性权重 ----
# 默认值 = 上游 train.sh 实际跑的那组; photo_mask_thresh 上游 train.sh 未覆盖, 用其 argparse 默认 0.9
parser.add_argument('--gc_weight', type=int, default=0,
                    help='>0: 开启 GC-MVSNet 训练期几何一致性权重 (只作用于训练, 不作用于验证)')
parser.add_argument('--mask_type', type=str, default='joint_inconsistency_mask')
parser.add_argument('--cons2incon_type', type=str, default='average')
parser.add_argument('--avg_weight_gap', type=str, default='0.2')   # 0.2 => ξ∈[1,3] (上游 train.sh)
parser.add_argument('--dist_thresh', type=str, default='1,0.5,0.25')
parser.add_argument('--relative_depth_diff_min_thresh', type=str, default='0.01,0.005,0.0025')
parser.add_argument('--geo_mask_sum_thresh', type=float, default=8)
parser.add_argument('--photo_mask_thresh', type=float, default=0.9)
parser.add_argument('--max_radius', type=float, default=2,"""),

    # 2) 数据集要吐源真值深度 (只有训练集要; 验证集保持原样, 这样 epoch_eval 的数与基线可比)
    ("""    train_dataset = MVSDataset(args.trainpath, args.trainlist, "train",
                               args.trainviews, args.numdepth)""",
     """    train_dataset = MVSDataset(args.trainpath, args.trainlist, "train",
                               args.trainviews, args.numdepth,
                               gc_src_depth=bool(args.gc_weight))"""),

    # 3) 建 GeometricWeights 对象
    ("""    model_loss = compute_inverse_loss""",
     """    model_loss = compute_inverse_loss
    if args.gc_weight:
        from models.geo_weights import GeometricWeights
        args.GEO_OBJ = GeometricWeights(args)
        print('[GC] on | mask_type', args.mask_type, '| cons2incon', args.cons2incon_type,
              '| gap', args.avg_weight_gap, '| dist', args.dist_thresh,
              '| rdd', args.relative_depth_diff_min_thresh)
    else:
        args.GEO_OBJ = None"""),

    # 4) 只在 train_sample 里传 —— 位置同上游 train.py:186/:200。test_sample_depth 不传:
    #    验证损失必须与正在跑的基线同口径, 否则 epoch_eval 的逐域曲线不可比。
    #    锚点用带右括号的这一串: test_sample_depth 里同样的参数后面是换行的 ), 所以此串唯一
    #    (已实测 grep -c == 1), 也绕开了原文件的行尾空格。
    ("""loss_rate=0.9, iters=args.stage_iters)""",
     """loss_rate=0.9, iters=args.stage_iters,
                                       geo_obj=getattr(args, 'GEO_OBJ', None),
                                       proj_mats=sample_cuda["proj_matrices"],
                                       src_depths=sample_cuda.get("src_depths"))"""),
])

print("补丁全部应用完成")
