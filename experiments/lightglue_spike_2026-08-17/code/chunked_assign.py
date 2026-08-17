"""把 LightGlue 的分配矩阵改成分块计算 —— 第二处 O(N²) 的无损消除。

背景:分块注意力解决了 9 层注意力的 N×N 物化后,剩下的峰值全在这里。
`sigmoid_log_double_softmax` 一次造出 5 个 M×N 张量(sim/scores0/scores1/
certainties/scores),16384 档 fp16 下每个 537MB ⇒ 实测活跃峰值 2.82GB。
这是 8192 能进手机(0.76GB)而 16384 进不去(撞 jetsam 2.9GB 线)的唯一原因。

数学展开(这是能分块的根据):
    scores0 = log_softmax(sim, dim=行内)  = sim[i,j] − rowLSE[i]
    scores1 = log_softmax(sim, dim=列内)  = sim[i,j] − colLSE[j]
    S[i,j]  = scores0 + scores1 + certainties
            = 2·sim[i,j] − rowLSE[i] − colLSE[j] + logsig(z0[i]) + logsig(z1[j])

rowLSE 只需该行(块内即可得),colLSE 需跨全部行 ⇒ 走两遍:
  第一遍:按行分块累计每列的 logsumexp(流式 max/sum,数值稳定)
  第二遍:重算 sim 块,组装 S 块,取行 max/argmax,并滚动更新列 max/argmax
峰值从 O(M·N) 降到 O(chunk·N)。代价是 sim 算两遍(一次 M×N×D 矩乘),
相对 9 层注意力可以忽略。

LSE 与比较全程用 fp32 累计,避免 fp16 在 logsumexp 上失稳。
"""
import torch
import torch.nn.functional as F


class LazyAssign:
    """占位:把真正的计算推迟到 filter 阶段,从而跳过整张矩阵的物化。"""

    def __init__(self, module, desc0, desc1):
        self.module, self.desc0, self.desc1 = module, desc0, desc1


def _sim_block(mdesc0_blk, mdesc1):
    return torch.einsum("bmd,bnd->bmn", mdesc0_blk, mdesc1)


def chunked_filter(mod, desc0, desc1, th: float, chunk: int):
    """等价于 filter_matches(sigmoid_log_double_softmax(...)),但不物化 M×N。"""
    mdesc0, mdesc1 = mod.final_proj(desc0), mod.final_proj(desc1)
    d = mdesc0.shape[-1]
    mdesc0 = mdesc0 / d ** 0.25
    mdesc1 = mdesc1 / d ** 0.25
    z0 = mod.matchability(desc0)          # [b,m,1]
    z1 = mod.matchability(desc1)          # [b,n,1]
    ls0 = F.logsigmoid(z0.squeeze(-1)).float()   # [b,m]
    ls1 = F.logsigmoid(z1.squeeze(-1)).float()   # [b,n]

    b, m, _ = mdesc0.shape
    n = mdesc1.shape[1]
    dev = mdesc0.device

    # ---- 第一遍:行 LSE + 流式列 LSE ----
    row_lse = torch.empty(b, m, device=dev, dtype=torch.float32)
    col_max = torch.full((b, n), -float("inf"), device=dev, dtype=torch.float32)
    col_sum = torch.zeros(b, n, device=dev, dtype=torch.float32)
    for i in range(0, m, chunk):
        sim = _sim_block(mdesc0[:, i:i + chunk], mdesc1).float()   # [b,c,n]
        row_lse[:, i:i + chunk] = torch.logsumexp(sim, dim=2)
        blk_max = sim.max(dim=1).values                            # [b,n]
        new_max = torch.maximum(col_max, blk_max)
        col_sum = col_sum * torch.exp(col_max - new_max) + \
            torch.exp(sim - new_max[:, None, :]).sum(dim=1)
        col_max = new_max
        del sim
    col_lse = col_max + torch.log(col_sum)

    # ---- 第二遍:行 max/argmax,滚动更新列 max/argmax ----
    row_val = torch.empty(b, m, device=dev, dtype=torch.float32)
    row_idx = torch.empty(b, m, device=dev, dtype=torch.long)
    colb_val = torch.full((b, n), -float("inf"), device=dev, dtype=torch.float32)
    colb_idx = torch.zeros(b, n, device=dev, dtype=torch.long)
    for i in range(0, m, chunk):
        c = min(chunk, m - i)
        sim = _sim_block(mdesc0[:, i:i + c], mdesc1).float()
        S = 2.0 * sim - row_lse[:, i:i + c, None] - col_lse[:, None, :] \
            + ls0[:, i:i + c, None] + ls1[:, None, :]
        rv, ri = S.max(dim=2)
        row_val[:, i:i + c], row_idx[:, i:i + c] = rv, ri
        cv, ci = S.max(dim=1)
        upd = cv > colb_val
        colb_idx = torch.where(upd, ci + i, colb_idx)
        colb_val = torch.where(upd, cv, colb_val)
        del sim, S

    # ---- 与 filter_matches 逐行等价的互检 ----
    m0, m1 = row_idx, colb_idx
    idx0 = torch.arange(m, device=dev)[None]
    idx1 = torch.arange(n, device=dev)[None]
    mutual0 = idx0 == m1.gather(1, m0)
    mutual1 = idx1 == m0.gather(1, m1)
    zero = row_val.new_tensor(0)
    mscores0 = torch.where(mutual0, row_val.exp(), zero)
    mscores1 = torch.where(mutual1, mscores0.gather(1, m1), zero)
    valid0 = mutual0 & (mscores0 > th)
    valid1 = mutual1 & valid0.gather(1, m1)
    m0 = torch.where(valid0, m0, torch.full_like(m0, -1))
    m1 = torch.where(valid1, m1, torch.full_like(m1, -1))
    return m0, m1, mscores0.to(desc0.dtype), mscores1.to(desc0.dtype)


def patch(lightglue_module, chunk: int = 1024):
    """让 MatchAssignment 返回占位、filter_matches 走分块路径。返回原实现以便还原。"""
    orig_assign = lightglue_module.MatchAssignment.forward
    orig_filter = lightglue_module.filter_matches

    def lazy_forward(self, desc0, desc1):
        return LazyAssign(self, desc0, desc1), None

    def filter_dispatch(scores, th):
        if isinstance(scores, LazyAssign):
            return chunked_filter(scores.module, scores.desc0, scores.desc1, th, chunk)
        return orig_filter(scores, th)

    lightglue_module.MatchAssignment.forward = lazy_forward
    lightglue_module.filter_matches = filter_dispatch
    return orig_assign, orig_filter


def unpatch(lightglue_module, saved):
    lightglue_module.MatchAssignment.forward, lightglue_module.filter_matches = saved
