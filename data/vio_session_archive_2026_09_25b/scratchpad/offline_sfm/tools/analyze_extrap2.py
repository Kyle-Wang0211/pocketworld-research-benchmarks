#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 新引擎轮] 新引擎外推位姿本身的质量与时效(只读),口径与 analyze_extrap.py(上一轮旧引擎)逐项相同,
并把上一轮 extrap_quality.json 的对应数字并排打印。
轨迹一律按录制帧 t_ns 键控、用相机旋转;gyrofit.py 的 GyroInt / increments / fit 原样调用。
时效(实拍顺序,单线程回放,无算力排队):
  FN(前端):回放里该帧的相机事件在 t+20 ms 投递(--cam-delay-ms 20),官方 predict_pose 当场给出 ⇒ 可用时刻 = t + 20 ms;
            另给「纯数据下限」= 拍照时刻之后第一个 IMU 样本到达(IMU 覆盖 t)所需时间。
  XN(定稿+外推):等起点后端帧的定稿事件;后端 CSV 的 fed_t_at_drain = 取到该事件时正在喂入的帧时刻,
            实拍顺序下该帧在 fed_t + 20 ms 投递 ⇒ 可用时刻 = fed_t_at_drain + 20 ms。
用法:analyze_extrap2.py 13f5 6d18 7353
"""
import json, os, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
O = SP + '/offline_sfm'
sys.path.insert(0, SP + '/wobble/tools')
import gyrofit as GF  # noqa: E402
import wob  # noqa: E402
sys.path.insert(0, O + '/tools')
import make_feeds as MF  # noqa: E402
GRID = np.arange(-0.03, 0.0301, 0.0005)
CAM_DELAY_MS = 20.0


def qR(q):
    return MF.q2R(q[3], q[0], q[1], q[2])


def stats(v):
    v = np.asarray([x for x in v if x is not None], float)
    return {'n': int(v.size), 'median': float(np.median(v)), 'p95': float(np.percentile(v, 95)), 'max': float(v.max()),
            'mean': float(v.mean())}


def main():
    prev = json.load(open(f'{O}/extrap_quality.json'))
    res = {}
    for scene in sys.argv[1:]:
        D = json.load(open(f'{O}/extrap2/{scene}_dense.json'))
        rows, brow = D['rows'], D['backend_rows']
        G = GF.GyroInt(scene)
        ark = wob.load_arkit(scene)
        arkC = dict(zip(ark['tns'].tolist(), ark['P']))
        out = {}
        out['ARKit(全速率)'] = GF.fit(G, *GF.increments(ark['tns'], wob.qmat(ark['Q']) @ GF.D), GRID)
        # 新前端全速率:keyed.csv(同一次运行)
        import csv
        kt, kR = [], []
        for r in csv.DictReader(open(f'{O}/newrun/{scene}_new_r1.keyed.csv')):
            kt.append(int(r['t_ns'])); kR.append(MF.q2R(float(r['qw']), float(r['qx']), float(r['qy']), float(r['qz'])))
        kt = np.array(kt, dtype=np.int64); kR = np.array(kR)
        out['前端(全速率)'] = GF.fit(G, *GF.increments(kt, kR), GRID)
        nb = np.array([r['tns'] for r in rows], dtype=np.int64)
        sel = np.isin(kt, nb)
        out['前端@非后端帧'] = GF.fit(G, *GF.increments(kt[sel], kR[sel]), GRID)
        bt = np.array([b['tns'] for b in brow], dtype=np.int64)
        bR = np.array([qR(b['q_xyzw']) for b in brow])
        out['后端帧定稿(10Hz)'] = GF.fit(G, *GF.increments(bt, bR, 0.4), GRID)
        bf = [b for b in brow if b['first_q_xyzw']]
        out['后端帧首次(10Hz)'] = GF.fit(G, *GF.increments(np.array([b['tns'] for b in bf], dtype=np.int64),
                                                        np.array([qR(b['first_q_xyzw']) for b in bf]), 0.4), GRID)
        for arm, name, bsrc in (('XN', '定稿+外推', 'q_xyzw'), ('XN1', '首次+外推', 'first_q_xyzw')):
            rr = [r for r in rows if arm in r]
            t = np.array([r['tns'] for r in rr], dtype=np.int64)
            R = np.array([qR(r[arm]['q_xyzw']) for r in rr])
            out[f'{name}@非后端帧'] = GF.fit(G, *GF.increments(t, R), GRID)
            t0, t1, th = GF.increments(t, R)
            bmap = {r['tns']: r['b'] for r in rr}
            key = lambda x: int(round(x * 1e9))
            same = np.array([bmap.get(key(a)) is not None and bmap.get(key(a)) == bmap.get(key(b)) for a, b in zip(t0, t1)])
            out[f'{name}@非后端帧:同起点增量'] = GF.fit(G, t0[same], t1[same], th[same], GRID)
            out[f'{name}@非后端帧:跨起点增量'] = GF.fit(G, t0[~same], t1[~same], th[~same], GRID)
            bb = [b for b in brow if b[bsrc]]
            tt = np.concatenate([np.array([b['tns'] for b in bb], dtype=np.int64), t])
            RR = np.concatenate([np.array([qR(b[bsrc]) for b in bb]), R])
            out[f'{name}拼接(后端帧+非后端帧,全速率)'] = GF.fit(G, *GF.increments(tt, RR), GRID)
        # 位置误差(同上一轮口径)
        pos = {}
        bC = {b['k']: np.array(b['C']) for b in brow}
        bC1 = {b['k']: np.array(b['first_C']) for b in brow if b['first_C']}
        fC = {}
        for r in csv.DictReader(open(f'{O}/newrun/{scene}_new_r1.keyed.csv')):
            fC['%.9f' % float(r['engine_t'])] = np.array([float(r[c]) for c in ('tx', 'ty', 'tz')])
        mp = {l.split()[0]: int(l.split()[1]) for l in open(f'{O}/newrun/{scene}_new_r1.map')}
        for arm in ('FN', 'XN', 'XN1'):
            rr = [r for r in rows if arm in r and r['tns'] in arkC]
            X = np.array([r[arm]['C'] for r in rr]).T
            Y = np.array([arkC[r['tns']] for r in rr]).T
            s, R, t = wob.umeyama(X, Y)
            e_abs = np.linalg.norm(s * R @ X + t.reshape(3, 1) - Y, axis=0)
            e_loc, dts, disp = [], [], []
            for r in rr:
                tb = mp.get(r['b'])
                Cb = {'XN': bC, 'XN1': bC1, 'FN': fC}[arm].get(r['b'])
                if tb is None or tb not in arkC or Cb is None:
                    e_loc.append(np.nan); dts.append(r['dt_ms']); disp.append(np.nan); continue
                dx = s * R @ (np.array(r[arm]['C']) - Cb); da = arkC[r['tns']] - arkC[tb]
                e_loc.append(np.linalg.norm(dx - da)); dts.append(r['dt_ms']); disp.append(np.linalg.norm(da))
            e_loc = np.array(e_loc); dts = np.array(dts); disp = np.array(disp)
            pa = {}
            for lab, m in (('33ms', dts < 50), ('67ms', dts >= 50)):
                ok = m & np.isfinite(e_loc)
                pa[lab] = {'整体残差_mm': stats(1e3 * e_abs[m]), '局部位移误差_mm': stats(1e3 * e_loc[ok]),
                           'ARKit位移_mm': stats(1e3 * disp[ok])}
            pa['整体_sim3_k'] = float(1 / s); pa['整体_ATE_cm'] = float(100 * np.sqrt((e_abs ** 2).mean()))
            if arm != 'FN':
                pa['外推终点距拍照时刻_ms'] = stats([r[arm]['end_gap_ms'] for r in rr])
            pos[arm] = pa
        kt2 = [b for b in brow if b['tns'] in arkC]
        X = np.array([b['C'] for b in kt2]).T; Y = np.array([arkC[b['tns']] for b in kt2]).T
        s, R, t = wob.umeyama(X, Y)
        e = np.linalg.norm(s * R @ X + t.reshape(3, 1) - Y, axis=0)
        pos['后端帧定稿@后端帧'] = {'整体_sim3_k': float(1 / s), '整体_ATE_cm': float(100 * np.sqrt((e ** 2).mean()))}
        # 时效
        photos = set()
        selj = json.load(open(f'{O}/feeds/{scene}_new_selection.json'))
        for p in selj['e'].values():
            photos |= set(p['rec_frames'])
        tim = {}
        for lab, rs in (('全部非后端帧', rows), ('照片', [r for r in rows if r['rec'] in photos])):
            tim[lab] = {
                'FN 回放实拍顺序_ms': stats([CAM_DELAY_MS for r in rs]),
                'FN 纯数据下限(IMU 覆盖拍照时刻)_ms': stats([r['imu_after_ms'] for r in rs]),
                'XN 等定稿_ms': stats([1e3 * (r['final_drain'] - float(r['k'])) + CAM_DELAY_MS for r in rs if r['final_drain'] is not None])}
        res[scene] = {'gyrofit': out, 'position': pos, 'timeliness': tim}
        pv = prev.get(scene, {})
        pmap = {'ARKit(全速率)': 'ARKit(全速率)', '前端(全速率)': '前端(全速率)', '前端@非后端帧': '前端@非后端帧',
                '后端帧定稿(10Hz)': '后端帧定稿(10Hz,上一轮)', '后端帧首次(10Hz)': '后端帧首次(10Hz)'}
        print(f'==== {scene}(新引擎,td −5 ms,实拍顺序;括号内为上一轮旧引擎 td 0、旧投递顺序)')
        for k, v in out.items():
            ov = pv.get('gyrofit', {}).get(pmap.get(k, k))
            old = f"(旧 g {ov['g']:.4f} 抖动 {ov['jitter_deg']:.3f}°)" if ov else ''
            print(f"  {k:28s} s {v['s_ms']:+6.2f} ms  幅度比 g {v['g']:.4f}  抖动 {v['jitter_deg']:.3f}°/增量  n {v['n']}  {old}")
        for arm, pa in pos.items():
            if arm == '后端帧定稿@后端帧':
                op = pv.get('position', {}).get('后端帧定稿@后端帧', {})
                print(f"  位置 {arm}: k {100*(pa['整体_sim3_k']-1):+.2f}% ATE {pa['整体_ATE_cm']:.2f} cm(旧 ATE {op.get('整体_ATE_cm', float('nan')):.2f})")
                continue
            oa = {'FN': 'F', 'XN': 'X2', 'XN1': 'X1'}[arm]
            op = pv.get('position', {}).get(oa, {})
            print(f"  位置 {arm}: k {100*(pa['整体_sim3_k']-1):+.2f}% ATE {pa['整体_ATE_cm']:.2f} cm(旧 {oa} ATE {op.get('整体_ATE_cm', float('nan')):.2f}) | " +
                  ' | '.join(f"{lab} 局部位移误差 中位 {pa[lab]['局部位移误差_mm']['median']:.2f}/p95 {pa[lab]['局部位移误差_mm']['p95']:.2f}/最大 {pa[lab]['局部位移误差_mm']['max']:.2f} mm"
                             f"(旧 {op.get(lab, {}).get('局部位移误差_mm', {}).get('median', float('nan')):.2f}/{op.get(lab, {}).get('局部位移误差_mm', {}).get('p95', float('nan')):.2f}/{op.get(lab, {}).get('局部位移误差_mm', {}).get('max', float('nan')):.2f})"
                             for lab in ('33ms', '67ms')) +
                  (f" | 外推终点距拍照 中位 {pa['外推终点距拍照时刻_ms']['median']:.2f} ms" if '外推终点距拍照时刻_ms' in pa else ''))
        for lab, v in tim.items():
            for src, st in v.items():
                print(f"  时效 {lab} {src}: 中位 {st['median']:.0f} ms, p95 {st['p95']:.0f}, 最大 {st['max']:.0f} (n {st['n']})")
    json.dump(res, open(f'{O}/extrap2_quality.json', 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
