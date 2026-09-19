#!/usr/bin/env python3
"""Fit the global gauge needed to lift predicted depths with known cameras."""

import numpy as np


def fit_camera_similarity(source, target):
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError("source and target must both be Nx3")
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    xs = source - source_mean
    xt = target - target_mean
    covariance = xt.T @ xs / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    sign = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        sign[-1] = -1
    rotation = u @ np.diag(sign) @ vt
    source_variance = np.sum(xs * xs) / len(source)
    if source_variance <= 0:
        raise ValueError("source camera centers have zero variance")
    scale = float(np.sum(singular * sign) / source_variance)
    translation = target_mean - scale * (rotation @ source_mean)
    fitted = scale * (source @ rotation.T) + translation
    residual = np.linalg.norm(fitted - target, axis=1)
    return {
        "scale": scale,
        "rotation": rotation,
        "translation": translation,
        "residual_median": float(np.median(residual)),
        "residual_p95": float(np.percentile(residual, 95)),
        "residual_max": float(residual.max()),
    }
