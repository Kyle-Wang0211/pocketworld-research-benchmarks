"""kornia 最小等价桩。

装 kornia 会引入第二份 libomp(OMP Error #15),官方给的 KMP_DUPLICATE_LIB_OK
绕法自带"可能静默产生错误结果"的警告 —— 质量臂不能接受。LightGlue 实际只用到
kornia 的三处,这里逐函数复刻:

  · color.grayscale_to_rgb / rgb_to_grayscale   ALIKED/SIFT/SuperPoint 的输入整形
  · geometry.transform.resize(side=...)         ImagePreprocessor 的在线缩放
  · feature.{HardNet,LAFDescriptor,...}         仅 DoGHardNet 用,我们不跑,占位即可

resize 逐行对齐 kornia 的 _side_to_image_size(注意是 int() 截断,不是四舍五入),
底层同样落到 F.interpolate(mode=bilinear, antialias=True)。
"""
import sys
import types

import torch
import torch.nn.functional as F


def grayscale_to_rgb(x: torch.Tensor) -> torch.Tensor:
    return x.repeat(1, 3, 1, 1) if x.shape[-3] == 1 else x


def rgb_to_grayscale(x: torch.Tensor) -> torch.Tensor:
    if x.shape[-3] == 1:
        return x
    w = torch.tensor([0.299, 0.587, 0.114], dtype=x.dtype, device=x.device)
    return (x * w.view(-1, 1, 1)).sum(-3, keepdim=True)


def _side_to_image_size(side_size: int, aspect_ratio: float, side: str = "short"):
    # 逐行照抄 kornia.geometry.transform.affwarp._side_to_image_size
    if side not in ("short", "long", "vert", "horz"):
        raise ValueError(f"side 非法: {side}")
    if side == "vert":
        return side_size, int(side_size * aspect_ratio)
    if side == "horz":
        return int(side_size / aspect_ratio), side_size
    if (side == "short") ^ (aspect_ratio < 1.0):
        return side_size, int(side_size * aspect_ratio)
    return int(side_size / aspect_ratio), side_size


def resize(input: torch.Tensor, size, side: str = "short",
           interpolation: str = "bilinear", align_corners=None,
           antialias: bool = False):
    if isinstance(size, int):
        h, w = input.shape[-2:]
        size = _side_to_image_size(size, w / h, side)
    return F.interpolate(input, size=size, mode=interpolation,
                         align_corners=align_corners, antialias=antialias)


def _install():
    color = types.ModuleType("kornia.color")
    color.grayscale_to_rgb = grayscale_to_rgb
    color.rgb_to_grayscale = rgb_to_grayscale

    transform = types.ModuleType("kornia.geometry.transform")
    transform.resize = resize
    geometry = types.ModuleType("kornia.geometry")
    geometry.transform = transform

    feature = types.ModuleType("kornia.feature")
    for n in ("HardNet", "LAFDescriptor", "DISK"):
        setattr(feature, n, type(n, (), {}))
    feature.laf_from_center_scale_ori = lambda *a, **k: (_ for _ in ()).throw(
        NotImplementedError("kornia 桩不支持 DoGHardNet"))

    k = types.ModuleType("kornia")
    k.color, k.geometry, k.feature = color, geometry, feature

    for name, mod in (("kornia", k), ("kornia.color", color),
                      ("kornia.geometry", geometry),
                      ("kornia.geometry.transform", transform),
                      ("kornia.feature", feature)):
        sys.modules.setdefault(name, mod)


_install()
