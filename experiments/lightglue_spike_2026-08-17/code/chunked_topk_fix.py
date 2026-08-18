"""修好上游的分块 TopK,让它在 MPS 上也正确 —— 而不是像我 08-17 早上那样整个关掉。

背景:上游 `lightglue_dynamo/models/raco.py::_chunked_topk` 是为压 TensorRT 的 TopK
延迟写的,fabio-sim 实测**检测器 39.5ms → 4.1ms(9.6×)**,且数学等价于全局 TopK。
我早上发现它在 MPS 上会整块返回 −inf(关键点全落第 0 行、匹配恒为 0、零报错),
当时的处置是 `topk_chunk_size=None` 走回退 —— **把 9.6× 的优化连同 bug 一起扔了**。

真凶定位(08-17 二次排查,三步收窄):
  1. `pad=finfo.min` 时 topk 返回 **−3.4e38 本身**(即选中了填充值)⇒ 不是 −inf 的锅,
     是 topk 把填充区当成了有效数据。
  2. 截断到整块、**完全不 pad** 时,MPS 上 3D 批量 topk / 2D 直接 topk / 逐块循环
     **三种写法全部正确** ⇒ 不是 3D 批量 topk 的锅。
  3. ⇒ 真凶就是 **`F.pad`**:MPS 上 pad 出来的张量 reshape 之后,内存布局/尺寸元数据
     是错的,topk 读到了填充区外的垃圾。`.contiguous()` 也救不回来。

修法:不用 `F.pad`,直接 `new_full` 出目标形状再切片拷贝。CPU/MPS/CUDA 全部逐条正确。
"""
import torch


def chunked_topk(scores: torch.Tensor, count: int, chunk_size: int | None):
    """等价于 scores.topk(count),但按块做以压低单次 TopK 的规模。

    scores: [b, n];返回 (values, indices),与 torch.topk 同语义(indices 指向原始位置)。
    """
    if chunk_size is None or chunk_size >= scores.shape[-1]:
        top = scores.topk(count)
        return top.values, top.indices
    if chunk_size < count:
        raise ValueError(f"chunk_size({chunk_size}) 必须 ≥ count({count})")

    b, n = scores.shape
    n_chunk = (n + chunk_size - 1) // chunk_size
    # 🔴 不能用 F.pad:MPS 上它产出的张量 reshape 后 topk 会读到填充区外的垃圾
    buf = scores.new_full((b, n_chunk * chunk_size), -float("inf"))
    buf[:, :n] = scores
    chunks = buf.view(b, n_chunk, chunk_size)

    local_v, local_i = chunks.topk(count, dim=-1, sorted=False)
    offs = torch.arange(n_chunk, device=scores.device,
                        dtype=local_i.dtype).reshape(1, -1, 1)
    local_i = (local_i + offs * chunk_size).flatten(1)
    values, order = local_v.flatten(1).topk(count, dim=-1)
    return values, local_i.gather(1, order)


def patch(raco_module):
    """就地替换上游的 _chunked_topk;返回原实现以便还原。"""
    orig = raco_module._chunked_topk
    raco_module._chunked_topk = chunked_topk
    return orig
