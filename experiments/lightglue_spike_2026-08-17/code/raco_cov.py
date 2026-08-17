"""把 RaCo 被丢掉的协方差头接回来 —— RaCo 的 "Co" 就是 covariance。

背景:`lightglue_dynamo/models/raco.py::_load_weights` 会把 checkpoint 里
`covariance_estimator_head.*` 那 5 个张量**过滤掉**(ONNX 导出用不上),于是
论文里那个"逐关键点空间不确定度"的头在我们这条线上一直是死的。

结构逐字抄自 cvg/RaCo 官方实现(不是猜的):
    Conv2d(128,64,3,pad=1,bias=False,padding_mode="reflect") → LeakyReLU
    Conv2d(64, 32,3,pad=1,bias=False,padding_mode="reflect") → LeakyReLU
    Conv2d(32, 32,3,pad=1,bias=False,padding_mode="reflect") → LeakyReLU
    Conv2d(32,  3,1,bias=True)
输出 3 通道 = Cholesky 元素 [L11, L21, L22];**只对 L11/L22 过 Softplus**
(保证对角正),L21 不加约束;Σ = L @ Lᵀ,L = [[L11,0],[L21,L22]]。

⚠️ 激活是 **LeakyReLU 不是 SELU**。RaCo 主干和 score/ranker 头用的都是 SELU,
   按"同一份网络应该一致"去推会推错 —— 这一处必须照抄官方源码。

用法:σ = sqrt(trace(Σ)/2),即该关键点定位误差的均方根半径(网络输入帧的像素)。
数值越小=定位越确定。我们拿它当**选点判据**:多取候选,只留 σ 最小的那批。
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def build_head(dim: int = 128) -> nn.Sequential:
    mods, c_in = [], dim
    for c_out in (64, 32, 32):
        mods += [nn.Conv2d(c_in, c_out, 3, stride=1, padding=1, bias=False,
                           padding_mode="reflect"),
                 nn.LeakyReLU(inplace=True)]
        c_in = c_out
    mods.append(nn.Conv2d(32, 3, 1, bias=True))
    return nn.Sequential(*mods)


def load_head(weights_path, dim: int = 128) -> nn.Sequential:
    head = build_head(dim)
    state = torch.load(weights_path, map_location="cpu", weights_only=True)
    sub = {k[len("covariance_estimator_head."):]: v for k, v in state.items()
           if k.startswith("covariance_estimator_head.")}
    if len(sub) != 5:
        raise RuntimeError(f"协方差头应有 5 个张量,实际 {len(sub)} —— 权重不对")
    missing, unexpected = head.load_state_dict(sub, strict=False)
    if missing or unexpected:
        raise RuntimeError(f"协方差头键不匹配 missing={missing} unexpected={unexpected}")
    return head.eval()


def dense_features(raco, image_normalized: torch.Tensor) -> torch.Tensor:
    """复算 RaCo 主干那张 128 通道多尺度特征图(score_head 与协方差头的共同输入)。

    直接调用 raco 自己的子模块,不改上游代码;与 `_candidate_keypoints` 里那段逐行一致。
    """
    x1 = raco.block1(image_normalized)
    x2 = raco.block2(raco.pool2(x1))
    x3 = raco.block3(raco.pool4(x2))
    x4 = raco.block4(raco.pool4(x3))
    return torch.cat(
        [raco.gate(raco.conv1(x1)),
         F.interpolate(raco.gate(raco.conv2(x2)), scale_factor=2,
                       mode="bilinear", align_corners=True),
         F.interpolate(raco.gate(raco.conv3(x3)), scale_factor=8,
                       mode="bilinear", align_corners=True),
         F.interpolate(raco.gate(raco.conv4(x4)), scale_factor=32,
                       mode="bilinear", align_corners=True)],
        dim=1,
    )


def cholesky_maps(head: nn.Sequential, feats: torch.Tensor) -> torch.Tensor:
    """[B,3,H,W]:对角过 Softplus,off-diagonal 不动(与官方一致)。"""
    m = head(feats)
    return torch.stack([F.softplus(m[:, 0]), m[:, 1], F.softplus(m[:, 2])], dim=1)


def sample_at(maps: torch.Tensor, kpts_px: torch.Tensor) -> torch.Tensor:
    """在关键点处双线性采样 [B,C,H,W] → [B,N,C]。kpts_px 是该图帧的像素坐标。"""
    b, c, h, w = maps.shape
    scale = torch.tensor([w - 1, h - 1], device=maps.device, dtype=maps.dtype)
    grid = (2.0 * kpts_px / scale - 1.0)[:, :, None, :]        # [B,N,1,2]
    out = F.grid_sample(maps, grid, mode="bilinear", align_corners=True)
    return out[..., 0].permute(0, 2, 1)                        # [B,N,C]


def sigma_from_cholesky(chol: torch.Tensor) -> torch.Tensor:
    """[B,N,3] → σ=[B,N],定位误差的均方根半径。

    Σ = L Lᵀ,trace(Σ) = L11² + L21² + L22² ⇒ σ = sqrt(trace/2)。
    用 trace 而不是最大特征值:各向同性的一个标量,且不受主轴朝向影响。
    """
    l11, l21, l22 = chol.unbind(-1)
    return torch.sqrt((l11 ** 2 + l21 ** 2 + l22 ** 2) / 2.0)


def covariance(chol: torch.Tensor) -> torch.Tensor:
    """[B,N,3] → Σ [B,N,2,2],需要完整矩阵时用(比如以后喂给 BA 当量测噪声)。"""
    l11, l21, l22 = chol.unbind(-1)
    z = torch.zeros_like(l11)
    L = torch.stack([torch.stack([l11, z], -1), torch.stack([l21, l22], -1)], -2)
    return L @ L.transpose(-1, -2)
