#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 2026-09-25 外推轮] 模拟 12MP 静态照:拍照时刻落在非后端帧上,位姿由「之前最近一个后端帧的
状态 + XRSLAM 官方 IMU 外推(引擎 propagate_state,经 build/xr_propagate)」给出。

唯一来源 = wobble 插桩回放 <scene>_log_r1(同一次运行):
  前端对外位姿 F   = <scene>_log_r1.cam.tum(XRSLAM_RESULT_CAMERA_POSE,每个喂入帧)
  后端首次状态     = 日志 `latest` 事件(该帧自己那次后端 track 刚结束时:p q v ba bg)
  后端定稿状态     = 日志 `kf_final` 事件(关键帧边缘化前:p q pc v bg ba)
  13f5 / 7353:这次运行与 bkpose tap_r1 逐帧一致(match_log_to_tap.py:定稿位置差 ≤5e-9 m,cam.tum sha 相同);
  6d18:日志运行与 tap_r1 从 268477.59 s 起分叉(最大 2.9 mm),是另一次运行,但四个 XRSLAM 量同出这一次。
136 字节的后端出口记录只有位姿,没有 v / bg / ba,所以状态只能来自这份日志。

臂(同一组非后端帧照片,只换位姿):
  A  ARKit;F 前端对外输出;X2 = 后端定稿 + 官方外推(主角);X1 = 后端首次 + 官方外推。
  X 臂的起点 = 拍照时刻之前最近的后端帧 b;若 b 没有 kf_final(子帧 / 收尾窗口帧),该帧不作照片候选
  (不回退到更早的后端帧,避免外推长度超出 0–100 ms)。数目写进选帧报告。
选帧:起点同上一轮(两个追踪器都就绪的第一个后端帧,三场都是第 40 帧);1.45 s 网格 × 3 相位;
每个网格点取第一个 t ≥ 网格时刻、且起点后端帧有定稿状态的非后端喂入帧。
可信位:ARKit 臂按 arkit_tracking == normal;XRSLAM 三臂按该帧已初始化且有前端输出(同一次运行、同一组信任位)。
稠密外推:对全部非后端帧都外推(X1 / X2),供 gyrofit 与位置误差统计用。
用法:make_extrap.py <scene>
"""
import csv, json, os, subprocess, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
O = SP + '/offline_sfm'
sys.path.insert(0, O + '/tools')
import make_feeds as MF  # noqa: E402  (q2R / R2q / xr_to_ark / t_ns_of 与上一轮同一份)

INTERVAL_S, N_PHASES = 1.45, 3


def main():
    scene = sys.argv[1]
    rec = os.path.expanduser(MF.RECS[scene])
    tag = f'{scene}_log_r1'
    W = f'{SP}/wobble/runs/{tag}'
    # 喂入帧(按喂入顺序)与录制帧
    fed = [(l.split()[0], int(l.split()[1])) for l in open(W + '.map')]
    fed_idx = {k: i for i, (k, _) in enumerate(fed)}
    tns_of = dict(fed)
    idx_of_t, _ = {}, None
    for ln in list(open(rec + '/camera_index.csv'))[1:]:
        a, b = ln.strip().split(','); idx_of_t[int(a)] = int(b)
    # 日志事件(保留文件顺序,供时效估计)
    latest, kf, initp, order = {}, {}, {}, []
    last_ft = None
    for l in open(W + '.jsonl'):
        try:
            d = json.loads(l)
        except Exception:  # noqa: BLE001
            continue
        ev = d.get('ev')
        if ev == 'ft':
            last_ft = d['t']
        elif ev == 'latest':
            latest.setdefault('%.9f' % d['t'], d)
        elif ev == 'kf_final':
            k = '%.9f' % d['t']
            kf[k] = d; kf[k]['_ft_at_emit'] = last_ft
        elif ev == 'init_post':
            initp.setdefault('%.9f' % d['t'], d)
    backend = set(latest) | set(kf) | set(initp)
    bk_sorted = sorted(backend, key=float)
    # 前端对外输出(cam.tum,OpenCV 相机轴、z 朝上世界)
    front = {}
    for l in open(W + '.cam.tum'):
        f = l.split()
        if len(f) < 8:
            continue
        q = [float(x) for x in f[4:8]]
        if np.linalg.norm(q) < 0.5:
            continue
        front[f[0]] = (MF.q2R(q[3], q[0], q[1], q[2]), np.array([float(x) for x in f[1:4]]))
    # ARKit
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
    init_end = max(float(k) for k in initp) if initp else float(fed[0][0])
    def trusted_X(k):
        return k in front and float(k) > init_end
    # 非后端帧 + 起点后端帧
    nonbk = []
    for k, tn in fed:
        if k in backend or float(k) <= init_end:
            continue
        prev = [b for b in bk_sorted if float(b) < float(k)]
        if not prev:
            continue
        b = prev[-1]
        nonbk.append({'k': k, 'tns': tn, 'rec': idx_of_t[tn], 'fed': fed_idx[k], 'b': b, 'b_fed': fed_idx.get(b, -1),
                      'dt_ms': 1e3 * (float(k) - float(b)), 'has_final': b in kf, 'has_first': b in latest})
    # 稠密外推作业
    def job(tagp, st, k):
        v = [float(st['t'])] + st['p'] + st['q'] + st['v'] + st['bg'] + st['ba'] + [float(k)]
        return f'{tagp}|{k} ' + ' '.join('%.17g' % x for x in v)
    jobs = []
    for n in nonbk:
        if n['has_final']:
            jobs.append(job('X2', kf[n['b']], n['k']))
        if n['has_first']:
            jobs.append(job('X1', latest[n['b']], n['k']))
    os.makedirs(O + '/extrap', exist_ok=True)
    jp, op = f'{O}/extrap/{scene}.jobs', f'{O}/extrap/{scene}.prop'
    open(jp, 'w').write('\n'.join(jobs) + '\n')
    subprocess.run([f'{O}/build/xr_propagate', f'{SP}/bkpose/cfg/slam_config.yaml', f'{SP}/bkpose/cfg/dev_{scene}.yaml',
                    rec + '/imu.csv', jp, op], check=True)
    prop = {}
    for l in open(op):
        f = l.split(); arm, k = f[0].split('|')
        cp = np.array([float(x) for x in f[12:15]]); cq = [float(x) for x in f[15:19]]
        prop[(arm, k)] = {'R': MF.q2R(cq[3], cq[0], cq[1], cq[2]), 'C': cp, 't_last_imu': float(f[3]), 'n_imu': int(f[4]),
                          'q': cq}
    # 稠密表(相机位姿,引擎世界系 / OpenCV 相机轴 —— 与 cam.tum 同口径)
    dense = []
    for n in nonbk:
        row = dict(n)
        for arm in ('X2', 'X1'):
            p = prop.get((arm, n['k']))
            if p:
                row[arm] = {'C': p['C'].tolist(), 'q_xyzw': p['q'], 'lag_ms': 1e3 * (float(n['k']) - p['t_last_imu']),
                            'n_imu': p['n_imu']}
        if n['k'] in front:
            R, C = front[n['k']]
            row['F'] = {'C': C.tolist(), 'R': R.tolist()}
        row['ft_at_final_emit'] = kf[n['b']]['_ft_at_emit'] if n['has_final'] else None
        dense.append(row)
    json.dump({'scene': scene, 'source': tag, 'init_end': init_end, 'n_fed': len(fed), 'n_backend': len(backend),
               'backend_fed_idx_mod3': {str(m): sum(1 for b in backend if b in fed_idx and fed_idx[b] % 3 == m) for m in range(3)},
               'rows': dense}, open(f'{O}/extrap/{scene}_dense.json', 'w'), indent=0)
    # 选照片
    t_ready = None
    for b in bk_sorted:
        tn = tns_of.get(b)
        if tn and float(b) > init_end and trusted_A(tn) and trusted_X(b):
            t_ready = tn; break
    cand = [n for n in nonbk if n['tns'] >= t_ready]
    t_end = cand[-1]['tns']
    phases, skipped = {}, {}
    for ph in range(N_PHASES):
        g = t_ready + int(round(ph * INTERVAL_S / N_PHASES * 1e9)); sel = []; sk = 0
        while g <= t_end:
            first = next((n for n in cand if n['tns'] >= g and (not sel or n['tns'] > sel[-1]['tns'])), None)
            if first is None:
                break
            pick = next((n for n in cand if n['tns'] >= first['tns'] and n['has_final'] and n['has_first']
                         and n['k'] in front and trusted_A(n['tns'])), None)
            if pick is None:
                break
            if pick is not first:
                sk += 1
            sel.append(pick); g += int(round(INTERVAL_S * 1e9))
        phases[ph] = sel; skipped[ph] = sk
    # JPEG
    jdir = f'{O}/jpeg/{scene}'
    need = sorted({n['rec'] for s in phases.values() for n in s})
    todo = [i for i in need if not os.path.exists(f'{jdir}/f{i:06d}.jpg')]
    if todo:
        subprocess.run([f'{O}/build/luma_to_jpeg', rec + '/frames.bin', '1920', '1440', jdir] + [str(i) for i in todo],
                       check=True, stdout=subprocess.DEVNULL)
    rep = {'scene': scene, 'source': tag, 'interval_s': INTERVAL_S, 't_ready_rec_frame': idx_of_t[t_ready],
           'n_nonbackend': len(nonbk), 'n_nonbackend_without_final_start': sum(1 for n in nonbk if not n['has_final']),
           'phases': {}}
    arms = {
        'A': lambda n: (ark.get(n['tns']), trusted_A(n['tns'])),
        'F': lambda n: (MF.xr_to_ark(*front[n['k']]), trusted_X(n['k'])),
        'X2': lambda n: (MF.xr_to_ark(prop[('X2', n['k'])]['R'], prop[('X2', n['k'])]['C']), trusted_X(n['k'])),
        'X1': lambda n: (MF.xr_to_ark(prop[('X1', n['k'])]['R'], prop[('X1', n['k'])]['C']), trusted_X(n['k'])),
    }
    for ph, sel in phases.items():
        pr = {'rec_frames': [n['rec'] for n in sel], 'n': len(sel), 'skipped_to_next_for_missing_final': skipped[ph],
              'dt_ms': [round(n['dt_ms'], 1) for n in sel], 'fed_mod3': [n['fed'] % 3 for n in sel]}
        for arm, fn in arms.items():
            n_tr = 0
            with open(f'{O}/feeds/{scene}_e{ph}_{arm}.jsonl', 'w') as fo:
                for n in sel:
                    pose, tr = fn(n)
                    Rwc, C = pose
                    n_tr += int(bool(tr))
                    Rw2c = Rwc.T
                    fo.write(json.dumps({'frameIndex': n['rec'], 'jpeg': f"{jdir}/f{n['rec']:06d}.jpg", 't': n['tns'] * 1e-9,
                                         'w': 1920, 'h': 1440, 'fxfycxcy': near(K, n['tns'], 1000),
                                         'arkitCamFromWorldQwxyz': MF.R2q(Rw2c).tolist(),
                                         'arkitCamFromWorldTxyz': (-Rw2c @ C).tolist(),
                                         'devicePoseTrusted': bool(tr)}) + '\n')
            pr[f'trusted_{arm}'] = n_tr
        rep['phases'][ph] = pr
    json.dump(rep, open(f'{O}/feeds/{scene}_e_selection.json', 'w'), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in rep.items() if k != 'phases'}, ensure_ascii=False))
    print('  后端帧的喂入序号 mod 3 分布:', {str(m): sum(1 for b in backend if b in fed_idx and fed_idx[b] % 3 == m) for m in range(3)})
    for ph, pr in rep['phases'].items():
        print(f"  相位{ph}: {pr['n']} 张,因起点无定稿顺延 {pr['skipped_to_next_for_missing_final']} 次,外推长度 ms {sorted(set(pr['dt_ms']))},"
              f" 喂入序号 mod3 {sorted(set(pr['fed_mod3']))},可信 A/F/X2/X1 = {pr['trusted_A']}/{pr['trusted_F']}/{pr['trusted_X2']}/{pr['trusted_X1']}")


if __name__ == '__main__':
    main()
