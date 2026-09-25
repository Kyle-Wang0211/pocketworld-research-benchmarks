#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 2026-09-25] 同一组照片、四种设备位姿的喂帧文件。

照片 = 录制视频帧(1920x1440 luma8),只取后端帧(同一次引擎回放 <scene>_tap_r1 里有
「首次后端估计」和「定稿值」的帧),四个臂照片逐张相同,只换 arkitCamFromWorld*。

位姿来源(全部按录制帧 t_ns 整数相等键控,不插值、不平滑):
  A  ARKit      录制 arkit_poses.tum(world_from_camera,ARKit 相机轴,y 朝上重力世界)
  F  XRSLAM 前端 <tag>.keyed.csv = XRSLAM_RESULT_CAMERA_POSE(TRACKING_SUCCESS 门)
  B1 后端首次    <tag>.backend.csv kind 1 的第一条
  B2 后端定稿    kind 2(离窗定稿);收尾仍在窗口的帧取 kind 3 整窗快照
     (B1/B2 规则与集成 agent 的 eval3.py load_backend 逐字相同)
XRSLAM 相机位姿 = body 位姿 × 相机→body 外参(XRSLAMManager::GetResultCameraPose),
OpenCV 相机轴、z 朝上世界(重力 (0,0,-g))。换成产品 ABI 的口径照抄 09-23
prep_inputs.py(研究仓 data/vio-session-archive-20260923 .../sfmB/tools/prep_inputs.py,
每一步的出处见该文件头):
  R_wc_ark = M · R_wc_cv · diag(1,-1,-1),C' = M · C,M = Rx90ᵀ(z 朝上 → y 朝上);
  CamFromWorld:R_w2c = R_wcᵀ,t = −R_w2c · C。
(09-23 从 body 位姿起算,多一步 T_WC = T_WB·T_BC;这里引擎已经给了相机位姿,那一步省去。)

device_pose_trusted(fixA 判据,pocketworld fixA device_pose_trust.dart):
  ARKit 臂:该帧 intrinsics.jsonl arkit_tracking == "normal"(且位姿非零);
  XRSLAM 三臂:该帧引擎状态 XRSLAM_RESULT_STATE == TRACKING_SUCCESS 且四元数非退化
  = 该帧出现在 keyed.csv(pwvi_runner.cpp 的 keyed 门)。三臂同一次回放 ⇒ 同一组信任位。

拍照节奏:产品快门是运动驱动的(auto_capture_governor.dart:stella keyframe_inserter
+ 0.12×场景深度最小距离 + 快门回压),离线无法逐项复刻;用真机统计的节奏近似:
研究仓 data/sfm-device-align-20260924 step1_phone_scale/results.tsv 里 2026-09 的 43 场
真机采集(自动快门时代),每场「喂入帧设备时间戳相邻差的中位数」再取中位 = 1.45 s
(四分位 1.28–1.78 s;每场中位 22 张)。快门起点 = 两个追踪器都就绪的第一个后端帧
(产品自动快门在追踪非 normal 时不开火,fixA「自动快门的 tracking 硬闸」),
之后每 1.45 s 取第一个 t ≥ 网格时刻的后端帧(只选帧,不插值)。为了把「照片组运气」
和「位姿差别」分开,同一场取 3 个相位(网格起点偏移 0、1/3、2/3 间隔)各成一组照片。

用法:make_feeds.py <scene 13f5|6d18|7353> [间隔秒 默认 1.45] [相位数 默认 3] [前缀 默认 p]
补充密节奏:make_feeds.py <scene> 0.25 1 q —— 0.25 s = 产品调速器防抖下限
(auto_capture_governor.dart kStellaMinIntervalSec 之外的 0.25 s 防抖地板,09-23 prep_inputs.py S_deb 同口径)。
"""
import csv, json, os, subprocess, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
OUT = SP + '/offline_sfm'
MV = os.path.expanduser('~/Developer/arloopbench_builds/unified_official_xrslam_rec30_expmid_backendpose_20260925/mac_verify')
RECS = {
    '13f5': '~/Developer/viobench-recordings/run-13f53d2f-5935-4b1a-a499-4dc8367ea935',
    '6d18': '~/Developer/viobench-recordings/run-6d187dff-403a-4882-b692-7bdc6c3cfa2a',
    '7353': '~/Developer/viobench-recordings/run-73538ad6-8418-4eaf-8b75-a63c9d32af46',
}
W, H = 1920, 1440
INTERVAL_S = 1.45
N_PHASES = 3

F = np.diag([1., -1., -1.])
RX90 = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])  # prep_inputs.py(= ate.py:161)
M_ZUP_TO_YUP = RX90.T


def q2R(w, x, y, z):  # prep_inputs.py 原样
    n = np.sqrt(w*w + x*x + y*y + z*z); w, x, y, z = w/n, x/n, y/n, z/n
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def R2q(R):  # prep_inputs.py 原样(wxyz, w>=0)
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2; w = 0.25*s
        x = (R[2, 1]-R[1, 2])/s; y = (R[0, 2]-R[2, 0])/s; z = (R[1, 0]-R[0, 1])/s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0+R[0, 0]-R[1, 1]-R[2, 2])*2; w = (R[2, 1]-R[1, 2])/s
        x = 0.25*s; y = (R[0, 1]+R[1, 0])/s; z = (R[0, 2]+R[2, 0])/s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0+R[1, 1]-R[0, 0]-R[2, 2])*2; w = (R[0, 2]-R[2, 0])/s
        x = (R[0, 1]+R[1, 0])/s; y = 0.25*s; z = (R[1, 2]+R[2, 1])/s
    else:
        s = np.sqrt(1.0+R[2, 2]-R[0, 0]-R[1, 1])*2; w = (R[1, 0]-R[0, 1])/s
        x = (R[0, 2]+R[2, 0])/s; y = (R[1, 2]+R[2, 1])/s; z = 0.25*s
    q = np.array([w, x, y, z]); q /= np.linalg.norm(q)
    return q if q[0] >= 0 else -q


def t_ns_of(s):  # TUM 秒串 → 整数纳秒(lidar_ruler._tum_rows 同法)
    sec, _, frac = s.partition('.')
    return int(sec) * 1_000_000_000 + int((frac + '000000000')[:9]) if frac else int(sec) * 10**9


def load_backend(p):  # eval3.py load_backend 逐字规则
    first, final, window = {}, {}, {}
    for r in csv.DictReader(open(p)):
        t = int(r['t_ns'])
        if t < 0:
            continue
        c = (q2R(float(r['qw']), float(r['qx']), float(r['qy']), float(r['qz'])),
             np.array([float(r['tx']), float(r['ty']), float(r['tz'])]))
        if r['kind'] == '1':
            first.setdefault(t, c)
        elif r['kind'] == '2':
            final[t] = c
        elif r['kind'] == '3':
            window[t] = c
    fin = dict(window); fin.update(final)
    return first, fin


def xr_to_ark(Rwc_cv, C):  # XRSLAM 相机位姿 → ARKit 相机轴、y 朝上世界的 world_from_camera
    return M_ZUP_TO_YUP @ Rwc_cv @ F, M_ZUP_TO_YUP @ C


def vang(a, b):
    return float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1))))


def main():
    scene = sys.argv[1]
    global INTERVAL_S, N_PHASES
    if len(sys.argv) > 2: INTERVAL_S = float(sys.argv[2])
    if len(sys.argv) > 3: N_PHASES = int(sys.argv[3])
    PFX = sys.argv[4] if len(sys.argv) > 4 else 'p'
    rec = os.path.expanduser(RECS[scene])
    tag = f'{scene}_tap_r1'
    # 帧
    idx_of_t, t_of_idx = {}, {}
    for ln in list(open(rec + '/camera_index.csv'))[1:]:
        a, b = ln.strip().split(',')
        idx_of_t[int(a)] = int(b); t_of_idx[int(b)] = int(a)
    # 逐帧内参 + ARKit 追踪状态
    K, trk = {}, {}
    for ln in open(rec + '/intrinsics.jsonl'):
        j = json.loads(ln)
        t = int(round(j['t'] * 1e9))
        K[t] = j['intrinsics_fxfycxcy']; trk[t] = j.get('arkit_tracking')
    def near(dct, t, tol=500_000):
        best = min(dct, key=lambda k: abs(k - t))
        return dct[best] if abs(best - t) <= tol else None
    # ARKit
    ark = {}
    for ln in open(rec + '/arkit_poses.tum'):
        f = ln.split()
        if len(f) < 8 or ln.startswith('#'):
            continue
        t = t_ns_of(f[0])
        C = np.array([float(v) for v in f[1:4]])
        qx, qy, qz, qw = [float(v) for v in f[4:8]]
        ark[t] = (q2R(qw, qx, qy, qz), C)
    # XRSLAM
    front = {}
    for r in csv.DictReader(open(f'{MV}/runs/{tag}.keyed.csv')):
        front[int(r['t_ns'])] = (q2R(float(r['qw']), float(r['qx']), float(r['qy']), float(r['qz'])),
                                 np.array([float(r['tx']), float(r['ty']), float(r['tz'])]))
    bfirst, bfinal = load_backend(f'{MV}/runs/{tag}.backend.csv')

    def trusted_A(t):
        st = near(trk, t)
        return st == 'normal' and t in ark and np.abs(ark[t][1]).sum() > 0

    def trusted_X(t):
        return t in front

    cands = sorted(t for t in bfirst if t in bfinal and t in idx_of_t)
    t_ready = next(t for t in cands if trusted_A(t) and trusted_X(t))
    t_end = cands[-1]
    phases = {}
    for ph in range(N_PHASES):
        g = t_ready + int(round(ph * INTERVAL_S / N_PHASES * 1e9))
        sel = []
        while g <= t_end:
            nxt = next((t for t in cands if t >= g and (not sel or t > sel[-1])), None)
            if nxt is None:
                break
            sel.append(nxt)
            g += int(round(INTERVAL_S * 1e9))
        phases[ph] = sel
    # JPEG(各相位的并集,一次编好)
    jdir = f'{OUT}/jpeg/{scene}'
    os.makedirs(jdir, exist_ok=True)
    need = sorted({idx_of_t[t] for s in phases.values() for t in s})
    todo = [i for i in need if not os.path.exists(f'{jdir}/f{i:06d}.jpg')]
    if todo:
        subprocess.run([f'{OUT}/build/luma_to_jpeg', rec + '/frames.bin', str(W), str(H), jdir] +
                       [str(i) for i in todo], check=True, stdout=subprocess.DEVNULL)
    # 喂帧文件
    os.makedirs(f'{OUT}/feeds', exist_ok=True)
    arms = {
        'A': lambda t: (ark[t] if t in ark else None, trusted_A(t)),
        'F': lambda t: (xr_to_ark(*front[t]) if t in front else None, trusted_X(t)),
        'B1': lambda t: (xr_to_ark(*bfirst[t]), trusted_X(t)),
        'B2': lambda t: (xr_to_ark(*bfinal[t]), trusted_X(t)),
    }
    rep = {'scene': scene, 'tag': tag, 'interval_s': INTERVAL_S, 'n_phases': N_PHASES,
           'backend_candidates': len(cands), 't_ready_frame': idx_of_t[t_ready],
           'first_backend_frame': idx_of_t[cands[0]], 'last_backend_frame': idx_of_t[t_end], 'phases': {}}
    for ph, sel in phases.items():
        pr = {'frames': [idx_of_t[t] for t in sel], 'n': len(sel),
              'span_s': (sel[-1] - sel[0]) * 1e-9, 'gaps_s': [round((b - a) * 1e-9, 3) for a, b in zip(sel, sel[1:])]}
        tilt = {}
        for arm, fn in arms.items():
            n_tr = 0
            with open(f'{OUT}/feeds/{scene}_{PFX}{ph}_{arm}.jsonl', 'w') as fo:
                for t in sel:
                    i = idx_of_t[t]
                    pose, tr = fn(t)
                    if pose is None:  # 该臂这一帧没有位姿 ⇒ 只能不可信,位姿值核不会用
                        Rwc, C = np.eye(3), np.zeros(3); tr = False
                    else:
                        Rwc, C = pose
                    n_tr += int(bool(tr))
                    Rw2c = Rwc.T
                    k = near(K, t, 1000)
                    fo.write(json.dumps({'frameIndex': i, 'jpeg': f'{jdir}/f{i:06d}.jpg', 't': t * 1e-9,
                                         'w': W, 'h': H, 'fxfycxcy': k,
                                         'arkitCamFromWorldQwxyz': R2q(Rw2c).tolist(),
                                         'arkitCamFromWorldTxyz': (-Rw2c @ C).tolist(),
                                         'devicePoseTrusted': bool(tr)}) + '\n')
            pr[f'trusted_{arm}'] = int(n_tr)
            if arm != 'A':  # 换算自检:相机系里的重力方向与 ARKit 的夹角(错一个轴会炸到几十度)
                g = [vang((ark[t][0] @ F).T @ np.array([0, -1., 0]), (fn(t)[0][0] @ F).T @ np.array([0, -1., 0]))
                     for t in sel if fn(t)[0] is not None and t in ark]
                tilt[arm] = {'median_deg': float(np.median(g)), 'max_deg': float(np.max(g))}
        pr['gravity_in_cam_vs_arkit'] = tilt
        rep['phases'][ph] = pr
    json.dump(rep, open(f'{OUT}/feeds/{scene}_{PFX}_selection.json', 'w'), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in rep.items() if k != 'phases'}, ensure_ascii=False))
    for ph, pr in rep['phases'].items():
        print(f"  相位{ph}: {pr['n']} 张, 跨度 {pr['span_s']:.1f} s, 可信 A/F/B1/B2 = "
              f"{pr['trusted_A']}/{pr['trusted_F']}/{pr['trusted_B1']}/{pr['trusted_B2']}, "
              f"重力夹角(对 ARKit) {json.dumps(pr['gravity_in_cam_vs_arkit'])}")


if __name__ == '__main__':
    main()
