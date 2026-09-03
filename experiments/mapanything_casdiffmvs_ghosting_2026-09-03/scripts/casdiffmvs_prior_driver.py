#!/usr/bin/env python3
"""CasDiffMVS (upstream cvg/diffmvs) with an external per-view depth prior used
as the initialisation of the diffusion refinement (stage 1 input), everything
else identical to the official test.py path: same loader, same args, same seed,
same filter.py fusion.

Single variable vs the official run: `depth_predictions[-1]` entering stage 1 is
replaced by the prior (resized to the stage resolution, clamped to the view's
depth range). Where the prior is 0 (no MapAnything mask) the official coarse
depth is kept."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import types
from functools import partial
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

UP = "/root/casdiffmvs_official_20260903/diffmvs_upstream"
sys.path.insert(0, UP)
os.chdir(UP)
from datasets import find_dataset_def  # noqa: E402
from datasets.data_io import save_pfm, write_cam  # noqa: E402
from filter import filter_depth  # noqa: E402
from models import CasDiffMVS  # noqa: E402
from models.module import depth_to_disp, upsample_depth  # noqa: E402
from utils import set_random_seed, tensor2numpy, tocuda  # noqa: E402
import models.diffusion as diffusion_mod  # noqa: E402


def forward_with_prior(self, imgs, proj_matrices, depth_values, depth_gt_ms=None, prior_depth=None):
    """Verbatim copy of upstream CasDiffMVS.forward (test path) + prior hook at stage 1."""
    disp_min = depth_values[:, 0].float().view(-1, 1, 1, 1)
    disp_max = depth_values[:, -1].float().view(-1, 1, 1, 1)
    depth_max_ = 1.0 / disp_min
    depth_min_ = 1.0 / disp_max
    depth_interval = 1.0 / depth_values.size(1)
    self.scale_inv_depth = partial(diffusion_mod.disp_to_depth, min_depth=depth_min_, max_depth=depth_max_)
    features, confs, confidences, depth_predictions = [], [], [], []
    for img in imgs:
        features.append(self.feature(img))
    contexts = self.context(imgs[0])
    hook_info = {}
    for stage_idx in range(self.num_stage):
        inv_depth_gt = None
        if self.args.stage_iters[stage_idx] == 0:
            continue
        features_stage = [feat["stage{}".format(stage_idx + 1)] for feat in features]
        proj_matrices_stage = proj_matrices["stage{}".format(stage_idx + 1)].float()
        ref_feature = features_stage[0]
        context_stage = contexts["stage{}".format(stage_idx + 1)]
        B, _, H, W = ref_feature.size()
        if stage_idx == 0:
            depth_range_samples = torch.arange(0, self.numdepth_initial, device=ref_feature.device).view(1, -1, 1, 1)
            depth_range_samples = depth_range_samples / (self.numdepth_initial - 1.0)
            depth_range_samples = depth_range_samples.repeat(1, 1, H, W)
            depth_range_samples = self.scale_inv_depth(depth_range_samples)[1]
            context = torch.relu(context_stage)
            mask, inv_depth, init_depth, view_weights, conf = self.depthnet(features_stage, context, proj_matrices_stage, depth_values=depth_range_samples, scale_inv_depth=self.scale_inv_depth)
            depth_predictions.append(init_depth)
            confidences.append(F.interpolate(conf, scale_factor=2 ** (3 - stage_idx), mode="nearest").squeeze(1))
            inv_depth_up = upsample_depth(inv_depth, mask, ratio=2).unsqueeze(1)
            final_depth = self.scale_inv_depth(inv_depth_up)[1].squeeze(1)
            depth_predictions.append(final_depth)
        else:
            cur_depth = depth_predictions[-1].unsqueeze(1).detach()
            if prior_depth is not None and stage_idx == 1:
                # ---- prior hook: replace the stage-1 initialisation ----
                pr = F.interpolate(prior_depth, size=cur_depth.shape[-2:], mode="bilinear", align_corners=False)
                has = pr > 0
                pr = torch.clamp(pr, depth_min_.view(-1, 1, 1, 1) * 1.001, depth_max_.view(-1, 1, 1, 1) * 0.999)
                hook_info["prior_frac"] = float(has.float().mean())
                hook_info["rel_change_p50"] = float((torch.abs(pr - cur_depth) / cur_depth.clamp_min(1e-6))[has].median()) if has.any() else None
                cur_depth = torch.where(has, pr, cur_depth)
            inv_cur_depth = depth_to_disp(cur_depth, depth_min_, depth_max_)
            view_weights_stage = F.interpolate(view_weights, scale_factor=2 ** (stage_idx), mode="nearest")
            hidden_d, context = torch.split(context_stage, [self.hdim_stage[stage_idx], self.cdim_stage[stage_idx]], dim=1)
            hidden_d = self.hidden_init[stage_idx - 1](hidden_d)
            current_hidden_d = torch.tanh(hidden_d)
            context = torch.relu(context)
            inv_init_depth = None
            depth_cost_func = partial(self.GetCost, features=features_stage, proj_matrices=proj_matrices_stage, depth_interval=depth_interval * self.depth_interals_ratio[stage_idx], depth_max=depth_max_, depth_min=depth_min_, CostNum=self.CostNum[stage_idx], view_weights=view_weights_stage)
            mask, current_hidden_d, inv_depth_seqs, conf_seqs = self.update_block[stage_idx - 1](depth_cost_func, inv_cur_depth, current_hidden_d, context, gt_inv_depth=inv_depth_gt, inv_init_depth=inv_init_depth)
            depth_predictions.append(self.scale_inv_depth(inv_depth_seqs[-1])[1].squeeze(1))
            confidences.append(F.interpolate(conf_seqs[-1].unsqueeze(1), scale_factor=2 ** (3 - stage_idx), mode="nearest").squeeze(1))
            last_inv_depth = inv_depth_seqs[-1]
            inv_depth_up = upsample_depth(last_inv_depth, mask, ratio=self.up_ratio).unsqueeze(1)
            final_depth = self.scale_inv_depth(inv_depth_up)[1].squeeze(1)
            depth_predictions.append(final_depth)
    return {"depth": depth_predictions, "conf": confs, "photometric_confidence": confidences, "hook": hook_info}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testpath", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--loadckpt", required=True)
    ap.add_argument("--prior_dir", required=True)
    ap.add_argument("--num_view", type=int, default=10)
    ap.add_argument("--max_h", type=int, default=576)
    ap.add_argument("--max_w", type=int, default=768)
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--no_fusion", action="store_true")
    a = ap.parse_args()

    # official real-scene arguments (test_eth_casdiffmvs.sh), unchanged
    args = types.SimpleNamespace(method="casdiffmvs", numdepth_initial=48, numdepth=384, scale=[0.0, 0.125, 0.025], sampling_timesteps=[0, 1, 1], ddim_eta=[0, 1, 1], timesteps=[1000, 1000, 1000], stage_iters=[1, 3, 3], cost_dim_stage=[4, 4, 4], CostNum=[0, 4, 4], hidden_dim=[0, 32, 20], context_dim=[32, 32, 16], unet_dim=[0, 16, 8], min_radius=0.125, max_radius=8)
    set_random_seed(a.seed)
    MVSDataset = find_dataset_def("mvs")
    ds = MVSDataset(a.testpath, a.num_view, args.numdepth, dataset="general", scan=[""], max_h=a.max_h, max_w=a.max_w)
    loader = torch.utils.data.DataLoader(ds, 1, shuffle=False, num_workers=2, drop_last=False)
    model = CasDiffMVS(args, test=True)
    sd = torch.load(a.loadckpt, map_location="cpu")
    model.load_state_dict(sd["model"], strict=False)
    model.cuda().eval()
    model.forward = types.MethodType(forward_with_prior, model)

    out = Path(a.outdir)
    for d in ("depth_est", "cams", "images", "conf0", "conf1", "conf2"):
        (out / d).mkdir(parents=True, exist_ok=True)
    hooks, t0 = [], time.time()
    with torch.no_grad():
        for bi, sample in enumerate(loader):
            sc = tocuda(sample)
            fname = sample["filename"][0]  # e.g. "{}/00000000{}"
            import re
            vid = int(re.search(r"(\d{8})", fname.format("", "")).group(1))
            pp = Path(a.prior_dir) / f"{vid:08d}.npy"
            prior = torch.from_numpy(np.load(pp)).cuda()[None, None] if pp.exists() else None
            o = model(sc["imgs"], sc["proj_matrices"], sc["depth_values"], prior_depth=prior)
            hooks.append({"view": vid, **o["hook"]})
            o = tensor2numpy({k: v for k, v in o.items() if k != "hook"})
            cams = sample["proj_matrices"]["stage4"].numpy()
            imgs = sample["imgs"][0].numpy()
            depth_est = o["depth"][-1][0]
            save_pfm(str(out / "depth_est" / f"{vid:08d}.pfm"), depth_est)
            cam = cams[0, 0].copy()
            dmin = float(1.0 / sample["depth_values"][0, -1])
            dmax = float(1.0 / sample["depth_values"][0, 0])
            write_cam(str(out / "cams" / f"{vid:08d}_cam.txt"), cam, dmax, dmin)
            img = np.clip(np.transpose(imgs[0], (1, 2, 0)) * 255.0, 0, 255).astype(np.uint8)
            import cv2
            cv2.imwrite(str(out / "images" / f"{vid:08d}.jpg"), img[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 95])
            for k in range(3):
                save_pfm(str(out / f"conf{k}" / f"{vid:08d}.pfm"), o["photometric_confidence"][k][0])
            if bi % 20 == 0:
                print(f"view {vid} hook {o['hook'] if 'hook' in o else hooks[-1]}", flush=True)
    (out / "prior_hook_stats.json").write_text(json.dumps(hooks, indent=1) + "\n")
    print("inference seconds", round(time.time() - t0, 1), flush=True)
    if not a.no_fusion:
        filter_depth(a.testpath, str(out), str(out / "pc.ply"), 3, 1.0, 0.01, [0.3, 0.5, 0.5], "casdiffmvs", "general")
        print("fusion done", (out / "pc.ply").stat().st_size, flush=True)


if __name__ == "__main__":
    main()
