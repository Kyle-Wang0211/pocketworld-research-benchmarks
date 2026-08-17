"""把 LightGlue 的注意力改成按查询行分块 —— 无损降低峰值内存。

为什么必须做:MPS 上 LightGlue 走 F.scaled_dot_product_attention,会把 N×N
注意力矩阵整个物化。9 层 ×(self+cross)累计下来,8192 点 fp16 就要 6.3GB、
12288 要 11.9GB、16384 直接 OOM。而 iPhone 的 jetsam 预算只有 2–3GB
(我们自己的记录:2903MB 就撞线)⇒ 不解决这个,连 8192 都上不了手机。

原理:softmax 沿 key 维归一化,**各查询行之间完全独立**,所以按查询行分块
计算再拼接,与全矩阵计算**数学等价**。峰值从 O(N²) 降到 O(chunk×N)。
每块内部仍调用原 SDPA 内核 ⇒ 数值路径不变,不是重新实现的近似。

不做 online softmax(FlashAttention 那套),因为我们保留完整 key 维度,
不需要跨块合并归一化 —— 更简单,也更容易证明等价。
"""
import torch
import torch.nn.functional as F


def make_chunked_forward(chunk_size: int):
    def forward(self, q, k, v, mask=None):
        if q.shape[-2] == 0 or k.shape[-2] == 0:
            return q.new_zeros((*q.shape[:-1], v.shape[-1]))
        n = q.shape[-2]
        kc, vc = k.contiguous(), v.contiguous()
        if n <= chunk_size:
            out = F.scaled_dot_product_attention(q.contiguous(), kc, vc, attn_mask=mask)
            return out if mask is None else out.nan_to_num()
        parts = []
        for i in range(0, n, chunk_size):
            qi = q[..., i:i + chunk_size, :].contiguous()
            mi = None if mask is None else mask[..., i:i + chunk_size, :]
            parts.append(F.scaled_dot_product_attention(qi, kc, vc, attn_mask=mi))
        out = torch.cat(parts, dim=-2)
        return out if mask is None else out.nan_to_num()
    return forward


def patch(lightglue_module, chunk_size: int = 1024):
    """就地替换 Attention.forward;返回原实现以便还原。"""
    cls = lightglue_module.Attention
    orig = cls.forward
    cls.forward = make_chunked_forward(chunk_size)
    return orig


def unpatch(lightglue_module, orig):
    lightglue_module.Attention.forward = orig
