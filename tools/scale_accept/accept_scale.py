#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""±5% 绝对尺度验收台架(离线,只读 .tum,不录制、不开摄像头)。

产品负责人 2026-09-22 定的容差:**估算型,真实尺寸 ±5%**。本脚本回答一个
且只有一个问题:**我们的 VIO 轨迹相对 ARKit 参照的整体尺度,偏差是否 ≤5%。**

────────────────────────────────────────────────────────────────────────
为什么指标是「Sim3 对齐求出的尺度因子 s」而不是 ate.py 打印的「尺度偏差」
────────────────────────────────────────────────────────────────────────
两者数学上是同一个量(ate.py 的「尺度偏差」就是 `abs(1-s)*100`),但读法必须
改:2026-09-22 的 td 二维扫描已证明该统计量**随 td 非单调、存在假极小**
(+20 ms 处 0.21% 比真值点还低,而同点 ATE 已烂 3.7 倍)。所以:
  * 它**不能**用来挑参数(挑参数必须用 ATE);
  * 但在参数**已经定死**之后,它就是「整体尺度」本身,正是 ±5% 容差要管的量。
本脚本因此固定参数、只报尺度,并同时打印 SE3−Sim3 的 ATE 差(= 释放尺度这
一个自由度买到的 ATE 改善,即「尺度对总误差的贡献」),以免单看一个数。

────────────────────────────────────────────────────────────────────────
🔴 参照是 ARKit,不是真值
────────────────────────────────────────────────────────────────────────
ARKit 位姿本身带约 **3.5%** 的尺度不确定度(2026-09-20 尺子分析:我们用来锚
定的那把尺自带 3.45%;同日 COLMAP 仲裁另测得 ARKit 自身 ATE 量级 ~11 mm)。
因此本脚本输出的「通过 ±5%」只能读成:
    **与 ARKit 的尺度差 ≤5%**,不是「与真实尺寸的差 ≤5%」。
真实尺寸的验收必须用外部尺子(卷尺 / 标定板),本脚本做不到,也不假装能做。

────────────────────────────────────────────────────────────────────────
为什么要分段
────────────────────────────────────────────────────────────────────────
估算型容差看的是**最坏段**不是均值。2026-09-20 已实测同一场四段的尺度偏差
跨度 0.73%–10.80% —— 全程 Sim3 的单个 s 会把这种段间不一致平均掉。本脚本按
**时间**把配对好的样本切成 N 段(默认 4),每段独立做一次 Sim3,报每段
|1−s| 与段间极差。

────────────────────────────────────────────────────────────────────────
对齐算法的出处:零自研,直接复用 ate.py
────────────────────────────────────────────────────────────────────────
本脚本**不实现任何对齐算法**。它把 `~/Developer/viobench-recordings/ate.py`
的源码读进来,exec 掉「函数定义段」(命令行解析之前的部分),直接拿它的
`load()` / `umeyama()` / `align_position_yaw()`。ate.py 里的 posyaw 已经是
rpg_trajectory_evaluation@8c8ceec 的逐行移植,Sim3 用的是 Umeyama 1991:
  S. Umeyama, "Least-squares estimation of transformation parameters between
  two point patterns", IEEE TPAMI 13(4):376-380, 1991.
  https://doi.org/10.1109/34.88573
  Zhang & Scaramuzza, "A Tutorial on Quantitative Trajectory Evaluation for
  Visual(-Inertial) Odometry", IROS 2018.
  https://github.com/uzh-rpg/rpg_trajectory_evaluation (commit 8c8ceec)

唯一从 ate.py **抄进本文件**的是它的时间配对那 4 行(在 ate.py 里是顶层代
码,不是函数,没法 import),见 `associate()`,逐字对照并在注释里标了来源。
为防止抄漏,`--selfcheck`(默认开)会把 ate.py 当子进程跑一遍同一对轨迹,
断言本脚本算出的 Sim3 ATE / 尺度偏差 / SE3 ATE 与它打印的三个数**逐位一致**
(容差 0.005,即它打印精度的一半)。对不上就直接报错退出。

用法:
    ./accept_scale.py \
        --pair phone1 EST.tum REF.tum \
        --pair phone2 EST.tum REF.tum \
        --ref-y-up
"""

import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np

DEFAULT_ATE_PY = os.path.expanduser("~/Developer/viobench-recordings/ate.py")

# ARKit 参照自身的尺度不确定度(见文件头)。只用于报告里的提醒文字,
# 不参与任何判定 —— 判定就是裸的 |1−s| ≤ tol。
ARKIT_SCALE_UNCERTAINTY_PCT = 3.5


# --------------------------------------------------------------------------
# 复用 ate.py 的函数段(不重新实现)
# --------------------------------------------------------------------------
def load_ate_module(ate_py_path):
    """exec ate.py 中命令行解析之前的部分,拿到它的 load/umeyama/align_position_yaw。

    ate.py 是个脚本不是模块:顶层有 `ARGS=[...sys.argv...]` 和紧跟的文件读取,
    直接 import 会立刻炸。这里在 `ARGS=` 那一行处截断,只 exec 前半段 ——
    前半段纯粹是 import + 函数定义,没有副作用。
    """
    with open(ate_py_path, "r", encoding="utf-8") as fh:
        src = fh.read()
    marker = "ARGS=[a for a in sys.argv"
    cut = src.find(marker)
    if cut < 0:
        raise RuntimeError(
            "在 %s 里找不到命令行解析起点 %r —— ate.py 结构变了,"
            "请先核对再改本脚本的截断点。" % (ate_py_path, marker)
        )
    ns = {"__name__": "_ate_funcs", "__file__": ate_py_path}
    exec(compile(src[:cut], ate_py_path, "exec"), ns)  # noqa: S102
    for need in ("load", "umeyama", "align_position_yaw"):
        if need not in ns:
            raise RuntimeError("ate.py 里没有 %s()" % need)
    return ns


def associate(te, Pe, tr, Pr, max_dt=0.010):
    """时间配对。逐字抄自 ate.py 顶层(`idx=np.clip(...)` 起那 4 行)。

    ate.py 原文:
        idx=np.clip(np.searchsorted(tr,te),1,len(tr)-1)
        l=np.abs(te-tr[idx-1]); r=np.abs(te-tr[idx])
        pick=np.where(l<r,idx-1,idx); ok=np.minimum(l,r)<0.010
        X=Pe[ok].T; Y=Pr[pick[ok]].T
    """
    idx = np.clip(np.searchsorted(tr, te), 1, len(tr) - 1)
    l = np.abs(te - tr[idx - 1])
    r = np.abs(te - tr[idx])
    pick = np.where(l < r, idx - 1, idx)
    ok = np.minimum(l, r) < max_dt
    X = Pe[ok].T
    Y = Pr[pick[ok]].T
    return te[ok], X, Y


# --------------------------------------------------------------------------
# 评分
# --------------------------------------------------------------------------
def rmse(v):
    return float(np.sqrt((v ** 2).mean()))


def score_block(ate, X, Y):
    """对一段(或全程)配对样本做 Sim3 + SE3,返回尺度因子与两个 ATE。

    X = 估计(XRSLAM),Y = 参照(ARKit),都是 3xN。
    ate.py 的约定:umeyama(X,Y) 解的是 Y ≈ s·R·X + t,
    所以 s = 参照尺度 / 估计尺度;s>1 表示我们的轨迹「偏小」。
    """
    s, R, t = ate["umeyama"](X, Y)
    e_sim3 = np.linalg.norm((s * R @ X + t) - Y, axis=0)
    _, R1, t1 = ate["umeyama"](X, Y, False)
    e_se3 = np.linalg.norm((R1 @ X + t1) - Y, axis=0)
    return {
        "n": int(X.shape[1]),
        "scale_factor": float(s),
        "scale_dev_pct": float(abs(1.0 - s) * 100.0),
        "ate_sim3_cm": rmse(e_sim3) * 100.0,
        "ate_se3_cm": rmse(e_se3) * 100.0,
    }


def segment_bounds(t, n_seg):
    """按**时间**等分成 n_seg 段,返回每段的 (t0, t1) 闭开区间(最后一段闭)。"""
    t0, t1 = float(t[0]), float(t[-1])
    edges = np.linspace(t0, t1, n_seg + 1)
    out = []
    for k in range(n_seg):
        out.append((float(edges[k]), float(edges[k + 1])))
    return out


def evaluate_pair(ate, name, est_path, ref_path, n_seg, tol_pct, min_seg_pairs):
    te, Pe = ate["load"](est_path)
    tr, Pr = ate["load"](ref_path)
    if len(te) == 0 or len(tr) == 0:
        raise RuntimeError("%s: 轨迹为空 (est %d 行 / ref %d 行)" % (name, len(te), len(tr)))
    t, X, Y = associate(te, Pe, tr, Pr)
    if X.shape[1] < 3:
        raise RuntimeError("%s: 时间配对后只剩 %d 个样本,无法对齐" % (name, X.shape[1]))

    whole = score_block(ate, X, Y)
    whole["duration_s"] = float(t[-1] - t[0])
    whole["pass"] = bool(whole["scale_dev_pct"] <= tol_pct)
    # 释放「尺度」这一个自由度买到的 ATE 改善 = 尺度对总误差的贡献。
    whole["scale_contrib_cm"] = whole["ate_se3_cm"] - whole["ate_sim3_cm"]

    segs = []
    for k, (a, b) in enumerate(segment_bounds(t, n_seg)):
        m = (t >= a) & (t <= b if k == n_seg - 1 else t < b)
        if int(m.sum()) < min_seg_pairs:
            segs.append({"index": k + 1, "t0": a, "t1": b, "n": int(m.sum()),
                         "skipped": True})
            continue
        sc = score_block(ate, X[:, m], Y[:, m])
        sc.update({"index": k + 1, "t0": a, "t1": b, "skipped": False})
        sc["pass"] = bool(sc["scale_dev_pct"] <= tol_pct)
        segs.append(sc)

    live = [s for s in segs if not s["skipped"]]
    seg_summary = None
    if live:
        devs = [s["scale_dev_pct"] for s in live]
        facs = [s["scale_factor"] for s in live]
        seg_summary = {
            "n_segments_scored": len(live),
            "dev_min_pct": min(devs),
            "dev_max_pct": max(devs),
            "dev_spread_pp": max(devs) - min(devs),
            "factor_min": min(facs),
            "factor_max": max(facs),
            # 段间尺度极差(相对):最大段尺度 / 最小段尺度 − 1。
            "factor_spread_pct": (max(facs) / min(facs) - 1.0) * 100.0,
            "worst_segment_pass": bool(max(devs) <= tol_pct),
        }

    return {
        "name": name,
        "est": est_path,
        "ref": ref_path,
        "whole": whole,
        "segments": segs,
        "segment_summary": seg_summary,
    }


# --------------------------------------------------------------------------
# 自证:与 ate.py 子进程逐位对表
# --------------------------------------------------------------------------
_ATE_LINE = re.compile(
    r"配对\s+(\d+)\s*\|\s*Sim3 ATE\s+([\d.]+)\s*cm\s*\|\s*尺度偏差\s+([\d.]+)%"
    r"\s*\|\s*SE3 ATE\s+([\d.]+)\s*cm"
)


def selfcheck(ate_py, est, ref, whole, ref_y_up, tol=0.005):
    """把 ate.py 当子进程跑同一对轨迹,断言三个数与本脚本一致。

    对不上 => 本脚本的配对/对齐与既有台架口径分了家,直接失败,不静默。
    """
    cmd = [sys.executable, ate_py, est, ref]
    if ref_y_up:
        cmd.append("--ref-y-up")
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    m = None
    for ln in (out.stdout or "").splitlines():
        m = _ATE_LINE.search(ln) or m
    if m is None:
        return False, "ate.py 输出里没匹配到结果行:\n%s\n%s" % (out.stdout, out.stderr)
    got = (int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
    mine = (whole["n"], whole["ate_sim3_cm"], whole["scale_dev_pct"], whole["ate_se3_cm"])
    if got[0] != mine[0]:
        return False, "配对数不一致: ate.py=%d 本脚本=%d" % (got[0], mine[0])
    for label, a, b in zip(("Sim3 ATE", "尺度偏差", "SE3 ATE"), got[1:], mine[1:]):
        if abs(a - b) > tol:
            return False, "%s 不一致: ate.py=%.4f 本脚本=%.4f" % (label, a, b)
    return True, "与 ate.py 一致 (配对 %d / Sim3 %.2f / 尺度 %.2f%% / SE3 %.2f)" % got


# --------------------------------------------------------------------------
def fmt_report(results, tol_pct, n_seg, selfchecks):
    L = []
    L.append("=" * 78)
    L.append("±%.0f%% 绝对尺度验收 —— 判定量 = Sim3 对齐解出的尺度因子 s 与 1 的偏差" % tol_pct)
    L.append("🔴 参照是 ARKit,**不是真值**。ARKit 自带约 %.1f%% 尺度不确定度,"
             % ARKIT_SCALE_UNCERTAINTY_PCT)
    L.append("   所以「通过」只能读成「与 ARKit 的尺度差 ≤%.0f%%」,不是「与真实尺寸差 ≤%.0f%%」。"
             % (tol_pct, tol_pct))
    L.append("=" * 78)
    L.append("")
    L.append("【全程】")
    hdr = ("%-10s %6s %8s %10s %9s %10s %9s %9s %6s"
           % ("场次", "配对", "时长s", "尺度因子s", "|1-s|%", "Sim3 ATE", "SE3 ATE", "尺度贡献", "≤%d%%" % tol_pct))
    L.append(hdr)
    L.append("-" * len(hdr))
    for r in results:
        w = r["whole"]
        L.append("%-10s %6d %8.2f %10.6f %9.2f %8.2fcm %7.2fcm %7.2fcm %6s"
                 % (r["name"], w["n"], w["duration_s"], w["scale_factor"],
                    w["scale_dev_pct"], w["ate_sim3_cm"], w["ate_se3_cm"],
                    w["scale_contrib_cm"], "通过" if w["pass"] else "不通过"))
    L.append("")
    L.append("【按时间等分 %d 段,每段独立 Sim3】(估算型容差看最坏段,不看均值)" % n_seg)
    hdr2 = ("%-10s %3s %6s %10s %9s %10s %6s"
            % ("场次", "段", "配对", "尺度因子s", "|1-s|%", "Sim3 ATE", "≤%d%%" % tol_pct))
    L.append(hdr2)
    L.append("-" * len(hdr2))
    for r in results:
        for s in r["segments"]:
            if s["skipped"]:
                L.append("%-10s %3d %6d %10s %9s %10s %6s"
                         % (r["name"], s["index"], s["n"], "-", "-", "-", "样本不足"))
                continue
            L.append("%-10s %3d %6d %10.6f %9.2f %8.2fcm %6s"
                     % (r["name"], s["index"], s["n"], s["scale_factor"],
                        s["scale_dev_pct"], s["ate_sim3_cm"],
                        "通过" if s["pass"] else "不通过"))
        ss = r["segment_summary"]
        if ss:
            L.append("%-10s     段间: |1-s| %.2f%%–%.2f%% (极差 %.2f pp) | "
                     "尺度因子 %.6f–%.6f (相对极差 %.2f%%) | 最坏段 %s"
                     % (r["name"], ss["dev_min_pct"], ss["dev_max_pct"],
                        ss["dev_spread_pp"], ss["factor_min"], ss["factor_max"],
                        ss["factor_spread_pct"],
                        "通过" if ss["worst_segment_pass"] else "不通过"))
        L.append("")
    if selfchecks:
        L.append("【自证:与 ate.py 子进程对表】")
        for name, ok, msg in selfchecks:
            L.append("  %-10s %s %s" % (name, "✓" if ok else "✗", msg))
        L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="±5% 绝对尺度验收(离线;对齐算法复用 ate.py,零自研)")
    ap.add_argument("--pair", nargs=3, action="append", metavar=("NAME", "EST", "REF"),
                    required=True, help="一场:名字 估计轨迹.tum 参照轨迹.tum")
    ap.add_argument("--ref-y-up", action="store_true",
                    help="参照是 ARKit(y-up)。只影响自证时传给 ate.py 的参数;"
                         "Sim3/SE3 的尺度因子本身对刚体换轴不变。")
    ap.add_argument("--segments", type=int, default=4, help="按时间等分的段数(默认 4)")
    ap.add_argument("--tol", type=float, default=5.0, help="容差百分比(默认 5.0)")
    ap.add_argument("--min-seg-pairs", type=int, default=10,
                    help="一段少于这么多配对就跳过不评(默认 10)")
    ap.add_argument("--ate-py", default=DEFAULT_ATE_PY, help="ate.py 路径")
    ap.add_argument("--no-selfcheck", action="store_true", help="关掉与 ate.py 的对表")
    ap.add_argument("--json", help="同时把结构化结果写到这个文件")
    a = ap.parse_args(argv)

    ate = load_ate_module(a.ate_py)

    results, selfchecks = [], []
    for name, est, ref in a.pair:
        est = os.path.expanduser(est)
        ref = os.path.expanduser(ref)
        r = evaluate_pair(ate, name, est, ref, a.segments, a.tol, a.min_seg_pairs)
        results.append(r)
        if not a.no_selfcheck:
            ok, msg = selfcheck(a.ate_py, est, ref, r["whole"], a.ref_y_up)
            selfchecks.append((name, ok, msg))

    report = fmt_report(results, a.tol, a.segments, selfchecks)
    print(report)

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({
                "tolerance_pct": a.tol,
                "segments": a.segments,
                "reference_is_arkit_not_ground_truth": True,
                "arkit_scale_uncertainty_pct": ARKIT_SCALE_UNCERTAINTY_PCT,
                "results": results,
                "selfcheck": [{"name": n, "ok": o, "detail": m} for n, o, m in selfchecks],
            }, fh, ensure_ascii=False, indent=2)

    failed_selfcheck = [n for n, o, _ in selfchecks if not o]
    if failed_selfcheck:
        print("\n🔴 自证失败(与 ate.py 口径分家):%s" % ", ".join(failed_selfcheck),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
