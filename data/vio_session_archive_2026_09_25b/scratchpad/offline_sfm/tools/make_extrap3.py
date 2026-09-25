#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 加计前移轮] make_extrap2.py 的参数化版本:用法 make_extrap3.py <scene> <asrun 标签> <臂后缀>
(如 13f5 13f5_as16_td-6 16 ⇒ 臂 F16 / X16 / B16;来源 asrun/<标签>.*;输出 extrap3/<标签>_dense.json、
feeds/<scene>_{e,p}<相位>_{F,X,B}<后缀>.jsonl、feeds/<标签>_selection.json)。选帧规则、换算、外推调用与 make_extrap2 逐句相同;
不写 ARKit 臂(照片组若与上一轮相同,ARKit 结果直接沿用)。以下为 make_extrap2 原注释。
[offline_sfm 新引擎轮] 新引擎(xrslam feat/okvis2-preint@4e8dda2)下的 12MP 外推模拟与喂帧。

唯一来源 = 新引擎回放 newrun/<scene>_new_r1(单线程 --pace 0,--cam-delay-ms 20 实拍顺序,--td-extra-ms -5 仅限本实验;
两次回放逐位一致):
  前端 FN  = keyed.csv(XRSLAM_RESULT_CAMERA_POSE,TRACKING_SUCCESS 门;实拍顺序下 = 官方 predict_pose 在该帧时刻给的位姿)
  后端首次 = backend.csv kind 1 第一条(body 位姿 + v bg ba);后端定稿 = kind 2,收尾仍在窗口的帧取 kind 3(eval3 同规则)
外推 = build/xr_propagate2(原样 #include 新 detail.cpp,调用 propagate_state_okvis2,按新 predict_pose 规则)。

两组照片(四臂照片逐张相同,只换位姿):
  e 组(非后端帧,外推 33 / 67 ms):选帧规则与上一轮 make_extrap.py 相同;新臂 FN(前端)、XN(定稿+外推)。
       若照片帧与上一轮 e 组逐张相同,上一轮的 A / F / X2 / X1(旧引擎)可直接配对。
  p 组(后端帧本身):选帧规则与第一轮 make_feeds.py 相同;新臂 FN、BN(新后端定稿,不外推)。
       若与第一轮 p 组逐张相同,第一轮的 A / F / B2(旧引擎)可直接配对。
可信位:ARKit 按 normal;XRSLAM 臂按该帧在 keyed.csv(TRACKING_SUCCESS)。
用法:make_extrap2.py <scene>
"""
import csv, json, os, subprocess, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
O = SP + '/offline_sfm'
sys.path.insert(0, O + '/tools')
import make_feeds as MF  # noqa: E402

INTERVAL_S, N_PHASES = 1.45, 3


def st_of(r):
    return {'t': float(r['engine_t']), 'p': [float(r[k]) for k in ('body_tx', 'body_ty', 'body_tz')],
            'q': [float(r[k]) for k in ('body_qx', 'body_qy', 'body_qz', 'body_qw')],
            'v': [float(r[k]) for k in ('vx', 'vy', 'vz')], 'bg': [float(r[k]) for k in ('bgx', 'bgy', 'bgz')],
            'ba': [float(r[k]) for k in ('bax', 'bay', 'baz')],
            'C': np.array([float(r[k]) for k in ('tx', 'ty', 'tz')]),
            'Rc': MF.q2R(float(r['qw']), float(r['qx']), float(r['qy']), float(r['qz'])),
            'drain': float(r['fed_t_at_drain'])}


def main():
    scene, tag, suf = sys.argv[1], sys.argv[2], sys.argv[3]
    rec = os.path.expanduser(MF.RECS[scene])
    W = f'{O}/asrun/{tag}'
    fed = [(l.split()[0], int(l.split()[1])) for l in open(W + '.map')]
    fed_idx = {k: i for i, (k, _) in enumerate(fed)}
    tns_of = dict(fed)
    idx_of_t = {}
    for ln in list(open(rec + '/camera_index.csv'))[1:]:
        a, b = ln.strip().split(','); idx_of_t[int(a)] = int(b)
    first, final, window = {}, {}, {}
    for r in csv.DictReader(open(W + '.backend.csv')):
        if r['t_ns'] == '-1':
            continue
        k = '%.9f' % float(r['engine_t'])
        if r['kind'] == '1':
            first.setdefault(k, st_of(r))
        elif r['kind'] == '2':
            final[k] = st_of(r)
        elif r['kind'] == '3':
            window[k] = st_of(r)
    fin = dict(window); fin.update(final)
    backend = set(first) | set(fin)
    bk_sorted = sorted(backend, key=float)
    front = {}
    for r in csv.DictReader(open(W + '.keyed.csv')):
        front['%.9f' % float(r['engine_t'])] = (MF.q2R(float(r['qw']), float(r['qx']), float(r['qy']), float(r['qz'])),
                                               np.array([float(r[c]) for c in ('tx', 'ty', 'tz')]))
    K, trk = {}, {}
    for ln in open(rec + '/intrinsics.jsonl'):
        j = json.loads(ln); t = int(round(j['t'] * 1e9)); K[t] = j['intrinsics_fxfycxcy']; trk[t] = j.get('arkit_tracking')
    def near(dct, t, tol=500_000):
        best = min(dct, key=lambda k: abs(k - t))
        return dct[best] if abs(best - t) <= tol else None
    ark = {}
    for ln in open(rec + '/arkit_poses.tum'):
        f = ln.split()
        if len(f) < 8 or ln.startswith('#'):
            continue
        qx, qy, qz, qw = [float(v) for v in f[4:8]]
        ark[MF.t_ns_of(f[0])] = (MF.q2R(qw, qx, qy, qz), np.array([float(v) for v in f[1:4]]))
    def trusted_A(tn):
        return near(trk, tn) == 'normal' and tn in ark and np.abs(ark[tn][1]).sum() > 0
    def trusted_X(k):
        return k in front
    # 非后端帧
    nonbk = []
    for k, tn in fed:
        if k in backend:
            continue
        prev = [b for b in bk_sorted if float(b) < float(k)]
        if not prev:
            continue
        b = prev[-1]
        nonbk.append({'k': k, 'tns': tn, 'rec': idx_of_t[tn], 'fed': fed_idx[k], 'b': b, 'b_fed': fed_idx.get(b, -1),
                      'dt_ms': 1e3 * (float(k) - float(b)), 'has_final': b in fin, 'final_is_window': b in window and b not in final,
                      'has_first': b in first})
    nonbk = [n for n in nonbk if n['k'] in front]  # 已初始化(有前端输出)
    def job(tagp, st, k):
        v = [st['t']] + st['p'] + st['q'] + st['v'] + st['bg'] + st['ba'] + [float(k)]
        return f'{tagp}|{k} ' + ' '.join('%.17g' % x for x in v)
    jobs = []
    for n in nonbk:
        if n['has_final']:
            jobs.append(job('XN', fin[n['b']], n['k']))
        if n['has_first']:
            jobs.append(job('XN1', first[n['b']], n['k']))
    os.makedirs(O + '/extrap3', exist_ok=True)
    jp, op = f'{O}/extrap3/{tag}.jobs', f'{O}/extrap3/{tag}.prop'
    open(jp, 'w').write('\n'.join(jobs) + '\n')
    subprocess.run([f'{O}/build/xr_propagate2', f'{SP}/preint/cfg/slam_config.yaml', f'{SP}/preint/cfg/dev_{scene}.yaml',
                    rec + '/imu.csv', jp, op], check=True)
    prop = {}
    for l in open(op):
        f = l.split(); arm, k = f[0].split('|')
        cp = np.array([float(x) for x in f[12:15]]); cq = [float(x) for x in f[15:19]]
        prop[(arm, k)] = {'R': MF.q2R(cq[3], cq[0], cq[1], cq[2]), 'C': cp, 't_end': float(f[3]), 'q': cq}
    # IMU 覆盖:拍照时刻之后第一个 IMU 样本(引擎时间轴)
    imu_t = np.array([float(l.split(',')[0]) * 1e-9 for l in list(open(rec + '/imu.csv'))[1:] if l.strip()])
    dense = []
    for n in nonbk:
        row = dict(n)
        for arm in ('XN', 'XN1'):
            p = prop.get((arm, n['k']))
            if p:
                row[arm] = {'C': p['C'].tolist(), 'q_xyzw': p['q'], 'end_gap_ms': 1e3 * (float(n['k']) - p['t_end'])}
        R, C = front[n['k']]
        row['FN'] = {'C': C.tolist(), 'q_xyzw': list(MF.R2q(R)[[1, 2, 3, 0]])}
        row['final_drain'] = fin[n['b']]['drain'] if n['has_final'] else None
        i = np.searchsorted(imu_t, float(n['k']))
        row['imu_after_ms'] = 1e3 * (imu_t[i] - float(n['k'])) if i < len(imu_t) else None
        dense.append(row)
    bk_rows = []
    for b in bk_sorted:
        if b not in fin or b not in fed_idx:
            continue
        s = fin[b]
        bk_rows.append({'k': b, 'tns': tns_of[b], 'C': s['C'].tolist(), 'q_xyzw': list(MF.R2q(s['Rc'])[[1, 2, 3, 0]]),
                        'body_q_xyzw': s['q'], 'first_C': first[b]['C'].tolist() if b in first else None,
                        'first_q_xyzw': list(MF.R2q(first[b]['Rc'])[[1, 2, 3, 0]]) if b in first else None,
                        'final_is_window': b in window and b not in final, 'drain': s['drain']})
    json.dump({'scene': scene, 'source': tag, 'rows': dense, 'backend_rows': bk_rows,
               'backend_fed_idx_mod3': {str(m): sum(1 for b in backend if b in fed_idx and fed_idx[b] % 3 == m) for m in range(3)}},
              open(f'{O}/extrap3/{tag}_dense.json', 'w'), indent=0)
    # 起点
    t_ready = None
    for b in bk_sorted:
        tn = tns_of.get(b)
        if tn and trusted_A(tn) and trusted_X(b):
            t_ready = tn; break
    jdir = f'{O}/jpeg/{scene}'
    rep = {'scene': scene, 'source': tag, 't_ready_rec_frame': idx_of_t[t_ready], 'e': {}, 'p': {}}
    def write_feed(name, sel, arms):
        out = {}
        for arm, fn in arms.items():
            n_tr = 0
            with open(f'{O}/feeds/{name}_{arm}.jsonl', 'w') as fo:
                for n in sel:
                    (Rwc, C), tr = fn(n)
                    n_tr += int(bool(tr)); Rw2c = Rwc.T
                    fo.write(json.dumps({'frameIndex': n['rec'], 'jpeg': f"{jdir}/f{n['rec']:06d}.jpg", 't': n['tns'] * 1e-9,
                                         'w': 1920, 'h': 1440, 'fxfycxcy': near(K, n['tns'], 1000),
                                         'arkitCamFromWorldQwxyz': MF.R2q(Rw2c).tolist(),
                                         'arkitCamFromWorldTxyz': (-Rw2c @ C).tolist(), 'devicePoseTrusted': bool(tr)}) + '\n')
            out[f'trusted_{arm}'] = n_tr
        return out
    # e 组:非后端帧
    cand = [n for n in nonbk if n['tns'] >= t_ready]
    t_end = cand[-1]['tns']
    for ph in range(N_PHASES):
        g = t_ready + int(round(ph * INTERVAL_S / N_PHASES * 1e9)); sel = []; sk = 0
        while g <= t_end:
            first_n = next((n for n in cand if n['tns'] >= g and (not sel or n['tns'] > sel[-1]['tns'])), None)
            if first_n is None:
                break
            pick = next((n for n in cand if n['tns'] >= first_n['tns'] and n['has_final'] and trusted_A(n['tns'])), None)
            if pick is None:
                break
            sk += pick is not first_n
            sel.append(pick); g += int(round(INTERVAL_S * 1e9))
        need = [n['rec'] for n in sel if not os.path.exists(f"{jdir}/f{n['rec']:06d}.jpg")]
        if need:
            subprocess.run([f'{O}/build/luma_to_jpeg', rec + '/frames.bin', '1920', '1440', jdir] + [str(i) for i in need],
                           check=True, stdout=subprocess.DEVNULL)
        pr = {'rec_frames': [n['rec'] for n in sel], 'n': len(sel), 'skipped': sk,
              'dt_ms': [round(n['dt_ms'], 1) for n in sel], 'start_is_window': sum(n['final_is_window'] for n in sel)}
        pr.update(write_feed(f'{scene}_e{ph}', sel, {
            'F' + suf: lambda n: (MF.xr_to_ark(*front[n['k']]), trusted_X(n['k'])),
            'X' + suf: lambda n: (MF.xr_to_ark(prop[('XN', n['k'])]['R'], prop[('XN', n['k'])]['C']), trusted_X(n['k']))}))
        old = [json.loads(l)['frameIndex'] for l in open(f'{O}/feeds/{scene}_e{ph}_AN.jsonl')]
        pr['same_frames_as_last_round'] = old == pr['rec_frames']
        rep['e'][ph] = pr
    # p 组:后端帧本身(第一轮 make_feeds.py 规则:1.45 s 网格上第一个 t ≥ 网格的后端帧)
    bcand = sorted([b for b in bk_sorted if b in fin and b in fed_idx and tns_of[b] >= t_ready], key=float)
    bt_end = tns_of[bcand[-1]]
    for ph in range(N_PHASES):
        g = t_ready + int(round(ph * INTERVAL_S / N_PHASES * 1e9)); sel = []
        while g <= bt_end:
            b = next((b for b in bcand if tns_of[b] >= g and (not sel or tns_of[b] > sel[-1]['tns'])), None)
            if b is None:
                break
            sel.append({'k': b, 'tns': tns_of[b], 'rec': idx_of_t[tns_of[b]]}); g += int(round(INTERVAL_S * 1e9))
        pr = {'rec_frames': [n['rec'] for n in sel], 'n': len(sel),
              'final_is_window': sum(1 for n in sel if n['k'] in window and n['k'] not in final)}
        pr.update(write_feed(f'{scene}_p{ph}', sel, {
            'F' + suf: lambda n: (MF.xr_to_ark(*front[n['k']]), trusted_X(n['k'])),
            'B' + suf: lambda n: (MF.xr_to_ark(fin[n['k']]['Rc'], fin[n['k']]['C']), trusted_X(n['k']))}))
        old = [json.loads(l)['frameIndex'] for l in open(f'{O}/feeds/{scene}_p{ph}_A.jsonl')]
        pr['same_frames_as_round1'] = old == pr['rec_frames']
        rep['p'][ph] = pr
    json.dump(rep, open(f'{O}/feeds/{tag}_selection.json', 'w'), indent=1, ensure_ascii=False)
    print(scene, '后端帧喂入序号 mod3:', {str(m): sum(1 for b in backend if b in fed_idx and fed_idx[b] % 3 == m) for m in range(3)},
          '起点帧', rep['t_ready_rec_frame'])
    for g in ('e', 'p'):
        for ph, pr in rep[g].items():
            print(f"  {g}{ph}: {pr['n']} 张,与上一轮同帧 {pr.get('same_frames_as_last_round', pr.get('same_frames_as_round1'))},"
                  f" 可信 {({k: v for k, v in pr.items() if k.startswith('trusted_')})},"
                  f" {'外推 ms ' + str(sorted(set(pr['dt_ms']))) + ' 顺延 ' + str(pr['skipped']) + ' 起点为收尾窗口 ' + str(pr['start_is_window']) if g == 'e' else '定稿为收尾窗口 ' + str(pr['final_is_window'])}")


if __name__ == '__main__':
    main()
