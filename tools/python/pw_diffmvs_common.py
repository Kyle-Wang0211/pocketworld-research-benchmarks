"""Shared helpers for the PocketWorld DiffMVS desktop validation.

Builds the cvg/diffmvs model (DiffMVS-light or CasDiffMVS) with the exact
hyper-params from the repo's test scripts, loads a checkpoint, and exposes a
device-agnostic (MPS / CPU) inference helper. test.py is NOT reused because it
hardcodes .cuda()/cuda.synchronize() and the DTU file format; we feed tensors
straight from PocketWorld's npz windows instead.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch

DIFFMVS_DIR = Path(__file__).resolve().parent / "diffmvs"
sys.path.insert(0, str(DIFFMVS_DIR))
CKPT_DIR = DIFFMVS_DIR / "checkpoints_unz"

from models import CasDiffMVS  # noqa: E402  (the class implements both variants)


def pick_device(prefer: str = "mps") -> torch.device:
    if prefer == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    if prefer == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


# Exact args from scripts/test/test_dtu_*.sh
def _args_diffmvs() -> SimpleNamespace:
    return SimpleNamespace(
        method="diffmvs", numdepth_initial=48, numdepth=384,
        scale=[0.0, 0.5, 0.0], sampling_timesteps=[0, 1, 1], ddim_eta=[0, 1, 0],
        timesteps=[1000, 1000, 1000],
        stage_iters=[1, 4, 0], cost_dim_stage=[4, 4, 0], CostNum=[0, 6, 0],
        hidden_dim=[0, 32, 0], context_dim=[32, 32, 0], unet_dim=[0, 16, 8],
        min_radius=0.25, max_radius=4,
    )


def _args_casdiffmvs() -> SimpleNamespace:
    return SimpleNamespace(
        method="casdiffmvs", numdepth_initial=48, numdepth=384,
        scale=[0.0, 0.5, 0.1], sampling_timesteps=[0, 1, 1], ddim_eta=[0, 1, 1],
        timesteps=[1000, 1000, 1000],
        stage_iters=[1, 3, 3], cost_dim_stage=[4, 4, 4], CostNum=[0, 4, 4],
        hidden_dim=[0, 32, 20], context_dim=[32, 32, 16], unet_dim=[0, 16, 8],
        min_radius=0.125, max_radius=8,
    )


def build_model(method: str, device: torch.device):
    args = _args_diffmvs() if method == "diffmvs" else _args_casdiffmvs()
    ckpt = CKPT_DIR / (f"{method}_dtu.ckpt")
    model = CasDiffMVS(args, test=True)
    state = torch.load(ckpt, map_location="cpu")
    model.load_state_dict(state["model"], strict=False)
    model.eval().to(device)
    return model, args


def make_proj_matrices(K33: np.ndarray, w2c44: np.ndarray) -> dict:
    """K33: (N,3,3) intrinsics at full res, w2c44: (N,4,4). Returns the
    per-stage proj dict (each (1,N,2,4,4)) exactly as datasets/mvs.py builds it."""
    N = K33.shape[0]
    proj = np.zeros((N, 2, 4, 4), np.float32)
    proj[:, 0] = w2c44
    proj[:, 1, :3, :3] = K33
    out = {}
    for st, f in (("stage1", 0.125), ("stage2", 0.25), ("stage3", 0.5), ("stage4", 1.0)):
        p = proj.copy()
        p[:, 1, :2, :] = proj[:, 1, :2, :] * f
        out[st] = torch.from_numpy(p[None]).float()  # (1,N,2,4,4)
    return out


def depth_values_tensor(depth_min: float, depth_max: float, numdepth: int = 384) -> torch.Tensor:
    dv = np.linspace(1.0 / depth_max, 1.0 / depth_min, numdepth, dtype=np.float32)
    return torch.from_numpy(dv[None])  # (1, numdepth)


@torch.no_grad()
def run_inference(model, imgs_np, proj_ms, depth_values, device):
    """imgs_np: list of (3,H,W) float32 [0,1] RGB. Returns (depth HxW, conf HxW, dt)."""
    imgs = [torch.from_numpy(im[None]).float().to(device) for im in imgs_np]  # each (1,3,H,W)
    proj = {k: v.to(device) for k, v in proj_ms.items()}
    dv = depth_values.to(device)
    if device.type == "mps":
        torch.mps.synchronize()
    t0 = time.time()
    out = model(imgs, proj, dv)
    if device.type == "mps":
        torch.mps.synchronize()
    dt = time.time() - t0
    depth = out["depth"][-1][0].detach().float().cpu().numpy()
    conf = out["photometric_confidence"][-1][0].detach().float().cpu().numpy()
    return depth, conf, dt
