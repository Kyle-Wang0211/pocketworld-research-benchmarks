#!/usr/bin/env python3.11
"""
烟测(步骤5):
  1) 用官方训练 dataloader datasets/blend.py::MVSDataset (--dataset=blend 对应的类)
     真实加载 tartanground2mvsnet.py 的转换产物,跑通 __getitem__,打印张量形状与
     深度合法性。
  2) 用 casdiffmvs_mvgZeroDTU.ckpt 对同一个 batch 做一次前向推理,确认端到端
     无形状/单位爆炸。

模型构造参数取自仓库自带的 scripts/test/test_tank_casdiffmvs.sh (CasDiffMVS 在
BlendedMVS 系checkpoint上的官方测试recipe,唯一一份公开的“非DTU”测试超参),
因为这个具体的 mvgZeroDTU.ckpt 没有专属测试脚本 —— 这是本次烟测唯一的“非直接
来自官方脚本”的假设,报告里会明确标注,不冒充是官方为这个 ckpt 写定的配方。
"""
import argparse
import sys
import time

import numpy as np
import torch

DIFFMVS_DIR = "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs"
sys.path.insert(0, DIFFMVS_DIR)

from datasets import find_dataset_def  # noqa: E402
from models import CasDiffMVS  # noqa: E402

CKPT = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/casdiffmvs_mvgZeroDTU.ckpt"


def build_args():
    # 取自 scripts/test/test_tank_casdiffmvs.sh 的模型结构超参(与 BlendedMVS
    # 训练时一致,唯一改动是把 sampling_timesteps/ddim_eta 设成官方测试脚本自带值)
    ap = argparse.Namespace(
        numdepth_initial=96,
        numdepth=384,
        ddim_eta=[0, 1, 1],
        scale=[0.0, 0.125, 0.025],
        timesteps=[1000, 1000, 1000],
        sampling_timesteps=[0, 1, 1],
        hidden_dim=[0, 32, 20],
        context_dim=[32, 32, 16],
        stage_iters=[1, 3, 3],
        cost_dim_stage=[4, 4, 4],
        CostNum=[0, 4, 4],
        unet_dim=[0, 16, 8],
        min_radius=0.125,
        max_radius=8,
    )
    return ap


def main():
    device = torch.device("cpu")  # smoke test 只求端到端不爆炸,cpu 最稳妥

    MVSDataset = find_dataset_def("blend")
    dataset = MVSDataset(
        datapath="/Users/kaidongwang/Developer/tartanground_b_line/converted",
        listfile="/Users/kaidongwang/Developer/tartanground_b_line/converted/lists/train.txt",
        mode="test",     # 确定性 src 选择: src_views[:nviews-1]
        nviews=9,        # 与 train_casdiffmvs.sh 的 BlendedMVS 段 trainviews=9 对齐
        ndepths=384,
    )
    print(f"[dataset] len(metas) = {len(dataset)}")
    assert len(dataset) > 0, "没有任何 ref_view 凑够 nviews-1 个 src —— 数据集太稀疏"

    sample = dataset[0]
    imgs = sample["imgs"]
    proj = sample["proj_matrices"]
    depth_ms = sample["depth"]
    depth_values = sample["depth_values"]
    mask_ms = sample["mask"]

    print(f"[getitem] imgs: {len(imgs)} views, each shape={imgs[0].shape} dtype={imgs[0].dtype}")
    for k in ["stage1", "stage2", "stage3", "stage4"]:
        print(f"[getitem] proj_matrices[{k}] shape={proj[k].shape}")
        print(f"[getitem] depth[{k}] shape={depth_ms[k].shape} "
              f"range=[{np.nanmin(depth_ms[k]):.3f}, {np.nanmax(depth_ms[k]):.3f}] "
              f"valid_ratio={mask_ms[k].mean():.3f}")
    print(f"[getitem] depth_values(disparity 空间线性采样) shape={depth_values.shape} "
          f"range=[{depth_values.min():.6f}, {depth_values.max():.6f}]")
    implied_depth_min = 1.0 / depth_values.max()
    implied_depth_max = 1.0 / depth_values.min()
    print(f"[getitem] 反推 depth_min={implied_depth_min:.3f} depth_max={implied_depth_max:.3f} "
          f"(应与 cam.txt 深度行一致且为正、非 nan/inf)")

    # 手工组 batch(batch_size=1),复刻 test.py 里 DataLoader 默认 collate 之后
    # 传给 model() 的张量形状: imgs 是长度=nviews 的 list,每个 [B,3,H,W]
    imgs_b = [torch.from_numpy(np.expand_dims(im, 0)).float() for im in imgs]
    proj_b = {k: torch.from_numpy(np.expand_dims(v, 0)).float() for k, v in proj.items()}
    depth_values_b = torch.from_numpy(np.expand_dims(depth_values, 0)).float()

    args = build_args()
    model = CasDiffMVS(args, test=True)
    print(f"[model] loading checkpoint {CKPT}")
    state_dict = torch.load(CKPT, map_location="cpu")
    missing, unexpected = model.load_state_dict(state_dict["model"], strict=False)
    print(f"[model] missing keys: {len(missing)}, unexpected keys: {len(unexpected)}")
    if len(missing) > 0:
        print("  missing[:10] =", missing[:10])
    if len(unexpected) > 0:
        print("  unexpected[:10] =", unexpected[:10])
    model.to(device)
    model.eval()

    t0 = time.time()
    with torch.no_grad():
        outputs = model(imgs_b, proj_b, depth_values_b)
    dt = time.time() - t0
    print(f"[forward] 完成, 用时 {dt:.1f}s")

    depth_out = outputs["depth"]
    print(f"[forward] depth 输出层数 = {len(depth_out)}")
    for i, d in enumerate(depth_out):
        d_np = d.detach().cpu().numpy()
        finite = np.isfinite(d_np)
        print(f"  stage_out[{i}] shape={d_np.shape} "
              f"finite_ratio={finite.mean():.4f} "
              f"range(finite)=[{d_np[finite].min():.3f}, {d_np[finite].max():.3f}]" if finite.any()
              else f"  stage_out[{i}] 全部非有限值!")

    final_depth = depth_out[-1].detach().cpu().numpy()
    conf = outputs.get("photometric_confidence")
    if isinstance(conf, torch.Tensor):
        conf_np = conf.detach().cpu().numpy()
        print(f"[forward] photometric_confidence shape={conf_np.shape} "
              f"range=[{conf_np.min():.4f}, {conf_np.max():.4f}]")
    elif isinstance(conf, list):
        for i, c in enumerate(conf):
            c_np = c.detach().cpu().numpy()
            print(f"[forward] photometric_confidence[{i}] shape={c_np.shape} "
                  f"range=[{c_np.min():.4f}, {c_np.max():.4f}]")

    sane = (
        np.isfinite(final_depth).mean() > 0.5
        and final_depth[np.isfinite(final_depth)].min() >= 0
        and final_depth[np.isfinite(final_depth)].max() < implied_depth_max * 3
    )
    print(f"[verdict] 端到端无形状/单位爆炸 = {sane} "
          f"(最终深度范围应大致落在 cam.txt 的 depth_min/depth_max 数量级内)")


if __name__ == "__main__":
    main()
