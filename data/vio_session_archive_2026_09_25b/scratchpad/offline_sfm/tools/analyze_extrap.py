#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 外推轮] 外推位姿本身的质量与时效(只读)。
1) 对陀螺仪:wobble/tools/gyrofit.py 的 fit / increments / GyroInt 原样调用(幅度比 g、抖动 °/增量)。
2) 对 ARKit 的位置误差,按外推长度 33 / 67 ms 分组:
   a. 整体:该臂在全部非后端帧上的相机中心对 ARKit 做 Umeyama Sim3,逐帧残差;
   b. 局部:从起点后端帧 b 到拍照帧 p 的位移,对 ARKit 同一对帧的位移(经 a 的 s·R 转到同一系)之差 ——
      去掉整条轨迹的漂移,只剩外推这一段的误差。前端臂用它自己在 b 帧的输出作起点。
   ARKit 位姿按录制帧 t_ns 键控;XRSLAM 时刻 = PTS + 曝光/2 + 3 ms,两边相差约 7.5 ms 的整体相位,各臂相同。
3) 时效:外推要等起点后端帧的定稿状态。
   a. 同一次运行(日志):kf_final 那一行之前最后一个前端 ft 事件的帧时刻 ≈ 定稿产出时的喂入进度;
   b. 另一次运行(bkpose <scene>_tap2_r2.backend.csv,接口层每喂一帧就取一次事件的 fed_t_at_drain):
      后端帧时刻逐位相同,时序可比,轨迹不同不影响时效。
   延迟 = 可用时刻 − 拍照时刻。
用法:analyze_extrap.py 13f5 6d18 7353
"""
import csv, json, os, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
O = SP + '/offline_sfm'
sys.path.insert(0, SP + '/wobble/tools')
import gyrofit as GF  # noqa: E402
import wob  # noqa: E402
sys.path.insert(0, O + '/tools')
import make_feeds as MF  # noqa: E402
MVR = os.path.expanduser('~/Developer/arloopbench_builds/unified_official_xrslam_rec30_expmid_backendpose_20260925/mac_verify')
GRID = np.arange(-0.03, 0.0301, 0.0005)


def qR(q):  # [x y z w] → R
    return MF.q2R(q[3], q[0], q[1], q[2])


def umeyama(X, Y):
    s, R, t = wob.umeyama(X, Y)
    return s, R, t


def stats(v):
    v = np.asarray(v, float)
    return {'n': int(v.size), 'median': float(np.median(v)), 'p95': float(np.percentile(v, 95)), 'max': float(v.max()),
            'mean': float(v.mean())}


def main():
    res = {}
    for scene in sys.argv[1:]:
        D = json.load(open(f'{O}/extrap/{scene}_dense.json'))
        rows = D['rows']
        tag = f'{scene}_log_r1'
        # 后端帧轨迹(上一轮口径):kf_final / latest,按 gyrofit.backend_traj 原样取
        G = GF.GyroInt(scene)
        ark = wob.load_arkit(scene)
        arkC = dict(zip(ark['tns'].tolist(), ark['P']))
        xr = wob.load_xr_mac(tag)
        out = {}
        out['ARKit(全速率)'] = GF.fit(G, *GF.increments(ark['tns'], wob.qmat(ark['Q']) @ GF.D), GRID)
        out['前端(全速率)'] = GF.fit(G, *GF.increments(xr['tns'], wob.qmat(xr['Q'])), GRID)
        nb_tns = np.array([r['tns'] for r in rows], dtype=np.int64)
        sel = np.isin(xr['tns'], nb_tns)
        out['前端@非后端帧'] = GF.fit(G, *GF.increments(xr['tns'][sel], wob.qmat(xr['Q'][sel])), GRID)
        tk, Rk, Pk = GF.backend_traj(tag, 'kf_final')
        tl, Rl, Pl = GF.backend_traj(tag, 'latest')
        out['后端帧定稿(10Hz,上一轮)'] = GF.fit(G, *GF.increments(tk, Rk, 0.4), GRID)
        out['后端帧首次(10Hz)'] = GF.fit(G, *GF.increments(tl, Rl, 0.4), GRID)
        for arm, name in (('X2', '定稿+外推'), ('X1', '首次+外推')):
            rr = [r for r in rows if arm in r]
            t = np.array([r['tns'] for r in rr], dtype=np.int64)
            R = np.array([qR(r[arm]['q_xyzw']) for r in rr])
            out[f'{name}@非后端帧'] = GF.fit(G, *GF.increments(t, R), GRID)
            # 同一起点内的增量(纯 IMU 外推)与跨起点增量(换了后端帧)分开
            t0, t1, th = GF.increments(t, R)
            bmap = {r['tns']: r['b'] for r in rr}
            same = np.array([bmap[int(round(a * 1e9))] == bmap[int(round(b * 1e9))] if int(round(a * 1e9)) in bmap and int(round(b * 1e9)) in bmap else False
                             for a, b in zip(t0, t1)])
            if same.sum() > 20:
                out[f'{name}@非后端帧:同起点增量'] = GF.fit(G, t0[same], t1[same], th[same], GRID)
                out[f'{name}@非后端帧:跨起点增量'] = GF.fit(G, t0[~same], t1[~same], th[~same], GRID)
            # 拼接:后端帧用该状态本身的位姿,非后端帧用外推 → 全速率
            tb, Rb = (tk, Rk) if arm == 'X2' else (tl, Rl)
            # backend_traj 给的是 body 旋转,外推给的是相机旋转 ⇒ 后端帧也换到相机系(右乘 q_cb,常量)
            q_cb = np.array([-0.7071068, 0.7071068, 0.0, 0.0])
            Rcb = qR(q_cb / np.linalg.norm(q_cb))
            tt = np.concatenate([tb, t]); RR = np.concatenate([Rb @ Rcb, R])
            out[f'{name}拼接(后端帧+非后端帧,全速率)'] = GF.fit(G, *GF.increments(tt, RR), GRID)
        # 位置误差
        pos = {}
        kfC = {}
        for ln in open(f'{SP}/wobble/runs/{tag}.jsonl'):
            if '"kf_final"' in ln:
                d = json.loads(ln); kfC['%.9f' % d['t']] = np.array(d['pc'])
        latC = {}
        q_cb = np.array([-0.7071068, 0.7071068, 0.0, 0.0]) / np.linalg.norm([-0.7071068, 0.7071068, 0.0, 0.0])
        p_cb = np.array([0.03290364, -0.00696553, -0.00286231])
        for ln in open(f'{SP}/wobble/runs/{tag}.jsonl'):
            if '"ev":"latest"' in ln:
                d = json.loads(ln); k = '%.9f' % d['t']
                if k not in latC:
                    latC[k] = np.array(d['p']) + qR(d['q']) @ p_cb
        mp = {l.split()[0]: int(l.split()[1]) for l in open(f'{SP}/wobble/runs/{tag}.map')}
        xrC = dict(zip(xr['tns'].tolist(), xr['P']))
        for arm in ('F', 'X2', 'X1'):
            rr = [r for r in rows if arm in r and r['tns'] in arkC]
            X = np.array([r[arm]['C'] for r in rr]).T
            Y = np.array([arkC[r['tns']] for r in rr]).T
            s, R, t = umeyama(X, Y)
            e_abs = np.linalg.norm(s * R @ X + t.reshape(3, 1) - Y, axis=0)
            e_loc, dts, disp = [], [], []
            for j, r in enumerate(rr):
                tb_ns = mp.get(r['b'])
                if tb_ns is None or tb_ns not in arkC:
                    e_loc.append(np.nan); dts.append(r['dt_ms']); disp.append(np.nan); continue
                if arm == 'X2':
                    Cb = kfC.get(r['b'])
                elif arm == 'X1':
                    Cb = latC.get(r['b'])
                else:
                    Cb = xrC.get(tb_ns)
                if Cb is None:
                    e_loc.append(np.nan); dts.append(r['dt_ms']); disp.append(np.nan); continue
                dx = s * R @ (np.array(r[arm]['C']) - Cb)
                da = arkC[r['tns']] - arkC[tb_ns]
                e_loc.append(np.linalg.norm(dx - da)); dts.append(r['dt_ms']); disp.append(np.linalg.norm(da))
            e_loc = np.array(e_loc); dts = np.array(dts); disp = np.array(disp)
            pa = {}
            for lab, m in (('33ms', dts < 50), ('67ms', dts >= 50)):
                ok = m & np.isfinite(e_loc)
                pa[lab] = {'整体残差_mm': stats(1e3 * e_abs[m]), '局部位移误差_mm': stats(1e3 * e_loc[ok]),
                           'ARKit位移_mm': stats(1e3 * disp[ok])}
            pa['整体_sim3_k'] = float(1 / s); pa['整体_ATE_cm'] = float(100 * np.sqrt((e_abs ** 2).mean()))
            if arm != 'F':
                lags = np.array([r[arm]['lag_ms'] for r in rr])
                pa['末样本距拍照时刻_ms'] = stats(lags)
            pos[arm] = pa
        # 后端帧定稿(上一轮口径)在后端帧上的整体残差,作对照
        kt = [k for k in kfC if k in mp and mp[k] in arkC]
        X = np.array([kfC[k] for k in kt]).T; Y = np.array([arkC[mp[k]] for k in kt]).T
        s, R, t = umeyama(X, Y)
        pos['后端帧定稿@后端帧'] = {'整体残差_mm': stats(1e3 * np.linalg.norm(s * R @ X + t.reshape(3, 1) - Y, axis=0)),
                              '整体_ATE_cm': float(100 * np.sqrt(((s * R @ X + t.reshape(3, 1) - Y) ** 2).sum(0).mean()))}
        # 时效
        tim = {}
        photos = set()
        sel = json.load(open(f'{O}/feeds/{scene}_e_selection.json'))
        for p in sel['phases'].values():
            photos |= set(p['rec_frames'])
        drain = {}
        p2 = f'{SP}/bkpose/runs/{scene}_tap2_r2.backend.csv'
        for r in csv.DictReader(open(p2)):
            if r['kind'] == '2' and r['t_ns'] != '-1':
                drain['%.9f' % float(r['engine_t'])] = float(r['fed_t_at_drain'])
        for lab, rs in (('全部非后端帧', [r for r in rows if r['has_final']]),
                        ('照片', [r for r in rows if r['has_final'] and r['rec'] in photos])):
            a = [1e3 * (r['ft_at_final_emit'] - float(r['k'])) for r in rs if r['ft_at_final_emit'] is not None]
            b = [1e3 * (drain[r['b']] - float(r['k'])) for r in rs if r['b'] in drain]
            tim[lab] = {'日志(同一次运行)_ms': stats(a), 'tap2_r2 接口取事件_ms': stats(b)}
        res[scene] = {'gyrofit': out, 'position': pos, 'timeliness': tim}
        print(f'==== {scene}')
        for k, v in out.items():
            print(f"  {k:28s} s {v['s_ms']:+6.2f} ms  幅度比 g {v['g']:.4f}  抖动 {v['jitter_deg']:.3f}°/增量  n {v['n']}")
        for arm, pa in pos.items():
            if arm == '后端帧定稿@后端帧':
                print(f"  位置 {arm}: 整体残差中位 {pa['整体残差_mm']['median']:.1f} mm,ATE {pa['整体_ATE_cm']:.2f} cm")
                continue
            print(f"  位置 {arm}: k {100*(pa['整体_sim3_k']-1):+.2f}% ATE {pa['整体_ATE_cm']:.2f} cm | " +
                  ' | '.join(f"{lab}: 整体残差 中位 {pa[lab]['整体残差_mm']['median']:.1f}/p95 {pa[lab]['整体残差_mm']['p95']:.1f} mm,"
                             f"局部位移误差 中位 {pa[lab]['局部位移误差_mm']['median']:.2f}/p95 {pa[lab]['局部位移误差_mm']['p95']:.2f}/最大 {pa[lab]['局部位移误差_mm']['max']:.2f} mm"
                             f"(ARKit 位移中位 {pa[lab]['ARKit位移_mm']['median']:.1f} mm, n {pa[lab]['局部位移误差_mm']['n']})"
                             for lab in ('33ms', '67ms')) +
                  (f" | 末样本距拍照 中位 {pa['末样本距拍照时刻_ms']['median']:.1f} ms" if '末样本距拍照时刻_ms' in pa else ''))
        for lab, v in tim.items():
            for src, st in v.items():
                print(f"  时效 {lab} {src}: 中位 {st['median']:.0f} ms, p95 {st['p95']:.0f}, 最大 {st['max']:.0f} (n {st['n']})")
    json.dump(res, open(f'{O}/extrap_quality.json', 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
