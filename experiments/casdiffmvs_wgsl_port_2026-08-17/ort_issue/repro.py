#!/usr/bin/env python3
"""Minimal repro: WebGPU EP produces non-finite values with ORT_ENABLE_EXTENDED.

    pip install onnxruntime-webgpu   # or a source build with --use_webgpu
    python repro.py

Expected: all four optimization levels agree with the CPU EP.
Actual:   ORT_ENABLE_EXTENDED and ORT_ENABLE_ALL produce ~0.4% non-finite values.
"""
import numpy as np
import onnxruntime as ort

x = np.load("input_small.npz")["ctx"].astype(np.float32)   # (1, 36, 288, 384)
# 输入已四舍五入到 1 位小数并以 fp16 存储 —— 实测触发率不变(0.414%),仅为缩小附件。
levels = [
    ("ORT_DISABLE_ALL",      ort.GraphOptimizationLevel.ORT_DISABLE_ALL),
    ("ORT_ENABLE_BASIC",     ort.GraphOptimizationLevel.ORT_ENABLE_BASIC),
    ("ORT_ENABLE_EXTENDED",  ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED),
    ("ORT_ENABLE_ALL",       ort.GraphOptimizationLevel.ORT_ENABLE_ALL),
]

def run(providers, level):
    so = ort.SessionOptions()
    so.graph_optimization_level = level
    s = ort.InferenceSession("model.onnx", so, providers=providers)
    return s.run(["hidden"], {"ctx": x})[0]

ref = run(["CPUExecutionProvider"], ort.GraphOptimizationLevel.ORT_DISABLE_ALL)
print(f"{'graph_optimization_level':<24}{'non-finite %':>14}{'max |diff| vs CPU':>20}")
for name, lv in levels:
    w = run(["WebGpuExecutionProvider", "CPUExecutionProvider"], lv)
    nf = 100.0 * (~np.isfinite(w)).mean()
    d = np.nanmax(np.abs(np.where(np.isfinite(w), w, np.nan) - ref))
    print(f"{name:<24}{nf:13.3f}%{d:20.3e}")
