# ⚠️ 本文件是 vendored `diffmvs/models/conv3d_as_2d.py` 的**副本**。
# `tools/python/diffmvs/` 被 .gitignore 排除(vendored 不入库),所以正本无法提交。
# 使用前拷回去:
#   cp experiments/.../tools/vendored_models_conv3d_as_2d.py \
#      tools/python/diffmvs/models/conv3d_as_2d.py
# 调用:from models.conv3d_as_2d import convert_ ; convert_(model)
"""把 3D 卷积改写成等价的**单次** 2D 卷积。权重重排,不重训。

为什么(08-17 实测,两个无关后端给出同一个数):

    Conv3d(4→8,k3) on [1,4,48,72,96]      PyTorch/MPS   CoreML CPU+GPU
      原生 Conv3d                            3.12 ms        14.72 ms
      本文件的融合 Conv2d                     0.78 ms         3.71 ms
                                            3.98×          3.97×

  Conv3d 在 MPS 上只跑到本机 matmul 峰值的 3.6%(184 vs 5077 GFLOPS),
  同 FLOP 的 Conv2d 是它的 7.19× —— **Conv3d 在哪家后端都是二等公民**,
  三端(苹果/安卓/鸿蒙)的移动后端对 Conv2d 的优化投入都远高于它。

  ⚰️ 试过但更慢的写法:拆成 3 次 Conv2d 再相加 = **0.73×**(比原生还慢)。
     permute/cat 的搬运把收益全吃掉 ⇒ **必须是单次 conv 才赢。**

  副产品:CoreML **根本转不了** `ConvTranspose3d` 的 `output_padding`
  (`module.py` 里 `EXPORT_MODE` + `_convT3d_export` 就是为绕它写的,
   而且注释记着上一版绕错、把尾部边界置零 ⇒ 约 8% 深度偏差、p90 42%)。
  改成 2D 之后这一整套特判可以整块删掉。

⚠️ 数值等价、**非逐比特** —— 浮点加法结合律不同,实测最大相对差约 5e-07(fp32 舍入量级)。
   作为参照:本模型自身的扩散噪声让同输入两跑有 21.5% 的像素相对差 >1%,
   比这高**七个数量级**。

⚠️ 只处理本模型实际用到的形状:k=(3,3,3)、pad=(1,1,1)、stride ∈ {1,2}、
   ConvTranspose 的 output_padding=(1,1,1)。其它形状**直接抛异常**,不静默走错路径。
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def _stack_depth(x, step=1):
    """[B,C,D,H,W] → [B,3C,ceil(D/step),H,W],通道维依次是 D-1 / D / D+1(越界补零)。

    这是把深度维的 k=3 卷积核折进通道维的关键一步:折完之后
    Conv2d(3C→Cout, k=3) 与原 Conv3d(C→Cout, k=(3,3,3)) 的乘加**完全相同**。

    🔴 step=2 必须在**切片时**就抽稀,不能先堆满再 `[::2]`。
       踩过:先堆后抽的版本把一半搬运白做了,stride=2 的层反而慢 3 倍(0.33×)。
       这类改写的成败全在"物化了多少字节",不在 FLOP。
    """
    xp = F.pad(x, (0, 0, 0, 0, 1, 1))          # 只在深度维补 1,对应 padding=(1,·,·)
    D = x.shape[2]
    return torch.cat([xp[:, :, 0:D:step],
                      xp[:, :, 1:D + 1:step],
                      xp[:, :, 2:D + 2:step]], dim=1)


class Conv3dAs2d(nn.Module):
    """等价替换 nn.Conv3d(k=3, pad=1, stride ∈ {1,2})。"""

    def __init__(self, c3: nn.Conv3d):
        super().__init__()
        if tuple(c3.kernel_size) != (3, 3, 3) or tuple(c3.padding) != (1, 1, 1):
            raise ValueError(f"只支持 k=3/pad=1,收到 k={c3.kernel_size} p={c3.padding}")
        sd, sh, sw = c3.stride
        if sd not in (1, 2) or (sh, sw) != (sd, sd):
            raise ValueError(f"只支持三轴同 stride∈{{1,2}},收到 {c3.stride}")
        self.sd = sd
        self.cin, self.cout = c3.in_channels, c3.out_channels
        # [Cout,Cin,kd,kh,kw] → [Cout,kd*Cin,kh,kw];kd 的顺序必须与 _stack_depth 一致
        w = c3.weight.detach().permute(0, 2, 1, 3, 4).reshape(
            self.cout, 3 * self.cin, 3, 3).contiguous()
        self.conv = nn.Conv2d(3 * self.cin, self.cout, 3, stride=sd, padding=1,
                              bias=c3.bias is not None)
        with torch.no_grad():
            self.conv.weight.copy_(w)
            if c3.bias is not None:
                self.conv.bias.copy_(c3.bias.detach())

    def forward(self, x):
        B, _, D, H, W = x.shape
        # stride=2 时 out[d] 吃 in[2d-1, 2d, 2d+1] ⇒ 切片阶段直接按 2 抽稀
        s = _stack_depth(x, step=self.sd)
        Do = s.shape[2]
        s = s.permute(0, 2, 1, 3, 4).reshape(B * Do, 3 * self.cin, H, W)
        y = self.conv(s)
        return y.reshape(B, Do, self.cout, y.shape[-2], y.shape[-1]).permute(0, 2, 1, 3, 4)


class ConvT3dAs2d(nn.Module):
    """等价替换 nn.ConvTranspose3d(k=3, stride=2, pad=1, output_padding=1)。

    深度维推导(out 长度 = 2*D_in):
        out[o] = Σ_{d,k : 2d-1+k = o} w[:,:,k] · in[d]
        o 偶 ⇒ 仅 k=1 命中:   out[2d]   = w₁ · in[d]
        o 奇 ⇒ k=0 与 k=2 命中:out[2d+1] = w₀ · in[d+1] + w₂ · in[d]
    ⇒ 三个深度切片并进**输出通道**做一次 ConvTranspose2d,再按上式交织。
    """

    def __init__(self, ct: nn.ConvTranspose3d):
        super().__init__()
        if (tuple(ct.kernel_size) != (3, 3, 3) or tuple(ct.stride) != (2, 2, 2)
                or tuple(ct.padding) != (1, 1, 1) or tuple(ct.output_padding) != (1, 1, 1)):
            raise ValueError(f"只支持 k=3/s=2/p=1/op=1,收到 k={ct.kernel_size} "
                             f"s={ct.stride} p={ct.padding} op={ct.output_padding}")
        self.cin, self.cout = ct.in_channels, ct.out_channels
        # ConvTranspose 权重是 [Cin,Cout,kd,kh,kw];把 kd 并进输出通道 → [Cin,3*Cout,kh,kw]
        w = ct.weight.detach().permute(0, 2, 1, 3, 4).reshape(
            self.cin, 3 * self.cout, 3, 3).contiguous()
        self.conv = nn.ConvTranspose2d(self.cin, 3 * self.cout, 3, stride=2,
                                       padding=1, output_padding=1, bias=False)
        with torch.no_grad():
            self.conv.weight.copy_(w)
        # bias 是按输出通道加的,深度交织后每个输出位置只加一次 ⇒ 留到最后加
        self.bias = nn.Parameter(ct.bias.detach().clone()) if ct.bias is not None else None

    def forward(self, x):
        B, _, D, H, W = x.shape
        s = x.permute(0, 2, 1, 3, 4).reshape(B * D, self.cin, H, W)
        y = self.conv(s)                                  # [B*D, 3*Cout, 2H, 2W]
        Ho, Wo = y.shape[-2], y.shape[-1]
        y = y.reshape(B, D, 3, self.cout, Ho, Wo).permute(0, 3, 1, 2, 4, 5)
        y0, y1, y2 = y[:, :, :, 0], y[:, :, :, 1], y[:, :, :, 2]   # 各 [B,Cout,D,Ho,Wo]

        even = y1                                          # out[2d] = w₁·in[d]
        # out[2d+1] = w₀·in[d+1] + w₂·in[d];d+1 越界处 w₀ 项为 0
        odd = y2 + F.pad(y0[:, :, 1:], (0, 0, 0, 0, 0, 1))

        out = torch.stack([even, odd], dim=3).reshape(B, self.cout, 2 * D, Ho, Wo)
        if self.bias is not None:
            out = out + self.bias.view(1, -1, 1, 1, 1)
        return out


def should_fuse(m) -> bool:
    """🔴 **不是一刀全改** —— 逐层实测(M3/MPS,真实层配置与真实输入形状):

        层                   原生      融合    提速
        pvw.0     4→8  s1   3.00ms   1.09ms  2.75×  ✅
        pvw.1     8→1  s1   2.97ms   3.67ms  0.81×  ⬜ 变慢
        cr.conv0  4→8  s1   2.92ms   1.01ms  2.91×  ✅
        cr.conv1  8→8  s1   3.01ms   2.03ms  1.48×  ✅
        cr.conv2  8→16 s2   0.41ms   1.29ms  0.32×  ⬜ 变慢
        cr.conv3 16→16 s1   0.78ms   0.48ms  1.62×  ✅
        cr.conv4 16→32 s2   0.14ms   0.44ms  0.32×  ⬜ 变慢
        cr.conv5 32→32 s1   0.25ms   0.17ms  1.48×  ✅
        cr.conv6 32→16 cT   1.71ms   0.36ms  4.75×  ✅ 最大赢家
        cr.conv7 16→8  cT   6.57ms   1.07ms  6.16×  ✅ 最大赢家
        cr.prob   8→1  s1   2.94ms   3.68ms  0.80×  ⬜ 变慢
        ───────────────────────────────────────────
        全 3D 24.69ms | 全 2D 15.28ms(1.62×) | **逐层取优 12.66ms(1.95×)**

    两条败因,都不是 FLOP 而是**物化了多少字节**:
      · `Cout=1`:卷积本身极便宜,但融合仍要物化 3×Cin 的堆叠张量 ⇒ 不划算
      · `stride=2`:原生 Conv3d 只产出 1/8 体积、本来就快,融合白搭一次搬运

    ⇒ 判据:**转置卷积一律融合;普通卷积只在 stride=1 且 Cout>1 时融合。**
    ⚠️ 这张表量自 MPS。CoreML CPU+GPU 上单层实测比值一致(3.97× vs 3.98×),
       但**逐层取舍未在 CoreML 上复核** —— 换后端应重跑本表。
    """
    if isinstance(m, nn.ConvTranspose3d):
        return True
    return tuple(m.stride) == (1, 1, 1) and m.out_channels > 1


def convert_(module: nn.Module, policy=should_fuse) -> int:
    """就地把 module 里**划算的** 3D 卷积换成 2D 等价版,返回替换个数。

    只换卷积本身,周围的 BN3d/ReLU 原样保留 ⇒ 输入输出形状不变,爆炸半径最小。
    传 `policy=lambda m: True` 可强制全改(用于复现上表的"全 2D"一行)。
    """
    n = 0
    for name, child in list(module.named_children()):
        if isinstance(child, (nn.Conv3d, nn.ConvTranspose3d)):
            if policy(child):
                setattr(module, name,
                        (ConvT3dAs2d if isinstance(child, nn.ConvTranspose3d)
                         else Conv3dAs2d)(child))
                n += 1
        else:
            n += convert_(child, policy)
    return n
