#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""插桩日志:ba/bg 时间序列、跟踪/内点/拒绝计数,与 2 s 窗尺度误差对照。"""
import json
import sys

import numpy as np

sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob  # noqa: E402
from corr import spearman  # noqa: E402


def load_log(tag):
    ev = {}
    for ln in open(wob.W + '/runs/%s.jsonl' % tag):
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        ev.setdefault(d['ev'], []).append(d)
    return ev


def per_window(sc, tag, win=2.0):
    ev = load_log(tag)
    L = ev['latest']
    t = np.array([d['t'] for d in L])
    ba = np.array([d['ba'] for d in L]); bg = np.array([d['bg'] for d in L])
    ft = ev['ft']
    tf = np.array([d['t'] for d in ft])
    ntot = np.array([d['n_total'] for d in ft]); ncur = np.array([d['n_curr'] for d in ft])
    nout = np.array([d['n_out'] for d in ft]); flow = np.array([d['flow'] for d in ft])
    lo = ev['loc']
    tl = np.array([d['t'] for d in lo]); nin3 = np.array([d['in3'] for d in lo]); nn = np.array([d['n'] for d in lo])
    medpx = np.array([d['med_px'] for d in lo])
    wv = ev['win']
    tw = np.array([d['t'] for d in wv]); rej = np.array([d['rej_rpe'] for d in wv]); evl = np.array([d['eval'] for d in wv])
    ntrk = np.array([d['ntrk'] for d in wv])
    xr = wob.load_xr_mac(tag)
    ark = wob.load_arkit(sc)
    J = wob.join(xr, ark)
    kg = wob.k_sim3(J['X'], J['Y'])
    rows = []
    for w in wob.windows(J, win, win):
        # 引擎时间 ≈ 帧时间 + ~7.5 ms;窗口 2 s,忽略
        m = (t >= w['t0']) & (t < w['t1'])
        mf = (tf >= w['t0']) & (tf < w['t1'])
        ml = (tl >= w['t0']) & (tl < w['t1'])
        mw = (tw >= w['t0']) & (tw < w['t1'])
        if m.sum() < 3:
            continue
        rows.append(dict(
            tc=w['tc'], e=w['k_sim3'] / kg - 1,
            ba_range=float(np.linalg.norm(ba[m].max(0) - ba[m].min(0))),
            ba_tv=float(np.linalg.norm(np.diff(ba[m], axis=0), axis=1).sum()),
            bg_tv_dps=float(np.degrees(np.linalg.norm(np.diff(bg[m], axis=0), axis=1).sum())),
            n_total=float(ntot[mf].mean()), n_curr=float(ncur[mf].mean()), n_out=float(nout[mf].mean()),
            flow=float(np.median(flow[mf])),
            in3_frac=float((nin3[ml] / np.maximum(nn[ml], 1)).mean()), loc_med_px=float(np.median(medpx[ml])),
            rej_frac=float(rej[mw].sum() / max(evl[mw].sum(), 1)), ntrk=float(ntrk[mw].mean()) if mw.any() else np.nan))
    return rows, ba, t


if __name__ == '__main__':
    allr = []
    for a in sys.argv[1:] or ['13f5:13f5_log_r1', '6d18:6d18_log_r1', '7353:7353_log_r1', 'fb5d:fb5d_log_r1']:
        sc, tag = a.split(':')
        rows, ba, t = per_window(sc, tag)
        allr += rows
        e = np.array([r['e'] for r in rows])
        dba = np.linalg.norm(np.diff(ba, axis=0), axis=1) / np.diff(t)
        print('== %s  ba 整段范围 %s m/s²  ba 变化率中位 %.3f m/s³  p90 %.3f' % (
            sc, np.round(ba.max(0) - ba.min(0), 3), np.median(dba), np.percentile(dba, 90)))
        for k in ['ba_range', 'ba_tv', 'bg_tv_dps', 'n_total', 'n_curr', 'n_out', 'flow', 'in3_frac', 'loc_med_px', 'rej_frac', 'ntrk']:
            x = np.array([r[k] for r in rows]); f = np.isfinite(x)
            print('   %-11s 均值 %8.3f   spearman(|e|) %+.2f  spearman(e) %+.2f' % (k, np.nanmean(x), spearman(x[f], np.abs(e[f])), spearman(x[f], e[f])))
    e = np.array([r['e'] for r in allr])
    print('== 合并 %d 窗' % len(allr))
    for k in ['ba_range', 'ba_tv', 'bg_tv_dps', 'n_total', 'n_curr', 'n_out', 'flow', 'in3_frac', 'loc_med_px', 'rej_frac', 'ntrk']:
        x = np.array([r[k] for r in allr]); f = np.isfinite(x)
        print('   %-11s spearman(|e|) %+.2f  spearman(e) %+.2f' % (k, spearman(x[f], np.abs(e[f])), spearman(x[f], e[f])))
