#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 2026-09-25] 一次出货核运行的评分(只读)。

输入:runs/<feed>_r<rep>/{run.log, delivered_poses.txt, sfm_match_fail.jsonl, tracks.txt}
      + feeds/<feed>.jsonl(喂入的设备位姿与内参)+ 录制 ARKit 位姿。
输出:同目录 metrics.json。

指标:
  注册:run.log RESULT 的 n_reg / fed(get_poses 只返回模型里的帧)。
  交付 Sim3(补丁 B):核自己写的 device_alignment_v1 一行(status / 对数 / 内点 / 阈值 /
      centre_err 中位与最大);另用交付相机中心与该臂喂入的设备中心逐帧距离算 RMS
      (补丁 B 的误差就是「变换后投影中心 − 设备位置」,这里核对中位 / 最大与核一致)。
  交付尺度:交付相机中心(X)对 ARKit 相机中心(Y),scale_eval.estimators(09-24 真值审计
      规范估计器;Umeyama Sim3,k = 1/s,即交付轨迹长度 / ARKit 长度,k>1 ⇒ 交付偏大);
      ATE = 同一 Sim3 后的 RMS。与集成 agent eval3.py 同一个估计器。
      链到 LiDAR:k_L = k × k_ARKit(米尺报告 trajectories.arkit.estimate.k,同一场)。
      另给「喂入位姿本身」在同一组照片上对 ARKit 的 k,看核有没有改动尺度。
  重投影误差:tracks.txt 的每条观测,用交付位姿(COLMAP CamFromWorld,OpenCV 相机轴)与
      该帧喂入内参投影,取像素误差的均值 / 中位。
"""
import hashlib, json, os, re, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
O = SP + '/offline_sfm'
LR_DIR = os.path.expanduser('~/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler')
sys.path.insert(0, LR_DIR)
import lidar_ruler as LR  # noqa: E402
SE = LR._load_scale_eval()
MV = os.path.expanduser('~/Developer/arloopbench_builds/unified_official_xrslam_rec30_expmid_backendpose_20260925/mac_verify')
RECS = {
    '13f5': '~/Developer/viobench-recordings/run-13f53d2f-5935-4b1a-a499-4dc8367ea935',
    '6d18': '~/Developer/viobench-recordings/run-6d187dff-403a-4882-b692-7bdc6c3cfa2a',
    '7353': '~/Developer/viobench-recordings/run-73538ad6-8418-4eaf-8b75-a63c9d32af46',
}
_ark_cache = {}


def k_arkit_lidar(scene):
    d = json.load(open(f'{MV}/ruler/{scene}/lidar_ruler_report.json'))
    return d['trajectories']['arkit']['estimate']['k']


def arkit_centres(scene):
    if scene not in _ark_cache:
        rec = os.path.expanduser(RECS[scene])
        frame_ts = [int(l.split(',')[0]) for l in open(rec + '/camera_index.csv').read().split('\n')[1:] if l]
        idx = {int(l.split(',')[0]): int(l.split(',')[1]) for l in open(rec + '/camera_index.csv').read().split('\n')[1:] if l}
        ark, _ = LR.arkit_poses(rec, rec + '/arkit_poses.tum', frame_ts)  # 去零平移、只留 normal
        _ark_cache[scene] = {idx[t]: v[1] for t, v in ark.items()}
    return _ark_cache[scene]


def q2R(w, x, y, z):
    n = np.sqrt(w*w + x*x + y*y + z*z); w, x, y, z = w/n, x/n, y/n, z/n
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else None


def analyze(run_dir):
    name = os.path.basename(run_dir.rstrip('/'))
    m = re.match(r'(\w{4})_[pqe](\d)_(A|F|B1|B2|X1|X2|FN|XN|BN|AN|F16|X16|B16|F21|X21|B21)_r(\d+)$', name)
    feedname = name.rsplit('_r', 1)[0]
    scene = m.group(1)
    feed = [json.loads(l) for l in open(f'{O}/feeds/{feedname}.jsonl')]
    fed_C, K = {}, {}
    for g in feed:
        R = q2R(*g['arkitCamFromWorldQwxyz']); t = np.array(g['arkitCamFromWorldTxyz'])
        fed_C[g['frameIndex']] = -R.T @ t
        K[g['frameIndex']] = g['fxfycxcy']
    log = open(f'{run_dir}/run.log').read()
    res = re.search(r'RESULT finalize=(\w+) fed=(\d+) rejected=(\d+) n_reg=(\d+)/(\d+) cloud_points=(\d+) n_obs=(\d+)', log)
    out = {'run': name, 'scene': scene, 'phase': int(m.group(2)), 'arm': m.group(3), 'rep': int(m.group(4)),
           'n_photos': len(feed)}
    if not res:
        out['error'] = 'no RESULT'
        return out
    out.update(finalize=res.group(1), fed=int(res.group(2)), n_reg=int(res.group(4)), n_points=int(res.group(6)),
               n_obs=int(res.group(7)))
    reg = re.search(r'REG_EVIDENCE untrusted_fed=(\d+) untrusted_registered=(\d+) .* unregistered_delivered=(\d+)', log)
    if reg:
        out['untrusted_fed'] = int(reg.group(1)); out['unregistered_delivered'] = int(reg.group(3))
    da = None
    for l in open(f'{run_dir}/sfm_match_fail.jsonl'):
        if '"device_alignment_v1"' in l:
            da = json.loads(l)
    if da:
        out['align'] = {k: da[k] for k in ('status', 'applied', 'n_pairs', 'inliers_all', 'max_error_m', 'scale')}
        out['align']['centre_err_median_m'] = da['centre_err_m']['median']
        out['align']['centre_err_max_m'] = da['centre_err_m']['max']
        out['align']['rot_err_median_deg'] = da['rot_err_deg']['median']
        out['align']['outlier_frame_ids'] = da['outlier_frame_ids']
    # 交付位姿
    dp = {}
    for l in open(f'{run_dir}/delivered_poses.txt'):
        f = l.split()
        fid, fi, regd = int(f[0]), int(f[1]), int(f[2])
        if not regd:
            continue
        R = q2R(*[float(v) for v in f[3:7]]); t = np.array([float(v) for v in f[7:10]])
        dp[fid] = (fi, R, t, -R.T @ t)
    out['registered_frames'] = sorted(v[0] for v in dp.values())
    # 交付中心 − 喂入设备中心(补丁 B 的误差口径)
    e = np.array([np.linalg.norm(v[3] - fed_C[v[0]]) for v in dp.values()])
    out['centre_err_rms_m'] = float(np.sqrt((e ** 2).mean()))
    out['centre_err_median_m_recomputed'] = float(np.median(e))
    out['centre_err_max_m_recomputed'] = float(e.max())
    # 尺度 / ATE:交付中心对 ARKit 中心
    ark = arkit_centres(scene)
    fis = sorted(v[0] for v in dp.values() if v[0] in ark)
    byfi = {v[0]: v[3] for v in dp.values()}
    X = np.array([byfi[i] for i in fis]).T
    Y = np.array([ark[i] for i in fis]).T
    r = SE['estimators'](X, Y)
    kA = k_arkit_lidar(scene)
    out['vs_arkit'] = {'n': len(fis), 'k': r['k_sim3_fwd'], 'k_pct': 100 * (r['k_sim3_fwd'] - 1), 'ate_cm': r['ate_sim3_cm']}
    out['vs_lidar_chained'] = {'k_arkit_vs_lidar': kA, 'k': r['k_sim3_fwd'] * kA, 'k_pct': 100 * (r['k_sim3_fwd'] * kA - 1)}
    # 并列口径:剔除核自己闸判的离群帧(device_alignment_v1.outlier_frame_ids,frame_id)后再算一次;
    # 只用核的原生判定,不另设阈值。无离群帧时与上面相同。
    outl = set(out.get('align', {}).get('outlier_frame_ids') or [])
    keep = [fid for fid, v in dp.items() if v[0] in ark and fid not in outl]
    fis2 = sorted(dp[f][0] for f in keep)
    X2 = np.array([byfi[i] for i in fis2]).T; Y2 = np.array([ark[i] for i in fis2]).T
    r2 = SE['estimators'](X2, Y2)
    out['vs_arkit_excl_core_outliers'] = {'n': len(fis2), 'k_pct': 100 * (r2['k_sim3_fwd'] - 1), 'ate_cm': r2['ate_sim3_cm'],
                                          'kL_pct': 100 * (r2['k_sim3_fwd'] * kA - 1)}
    # 喂入位姿本身(同一组已注册帧)对 ARKit
    Xi = np.array([fed_C[i] for i in fis]).T
    ri = SE['estimators'](Xi, Y)
    out['input_vs_arkit'] = {'k': ri['k_sim3_fwd'], 'k_pct': 100 * (ri['k_sim3_fwd'] - 1), 'ate_cm': ri['ate_sim3_cm']}
    # 重投影误差
    errs = []
    if os.path.exists(f'{run_dir}/tracks.txt'):
        P = None
        for l in open(f'{run_dir}/tracks.txt'):
            if l.startswith('P '):
                f = l.split(); P = np.array([float(f[1]), float(f[2]), float(f[3])])
                continue
            f = l.split(); fid = int(f[0])
            if fid not in dp:
                continue
            fi, R, t, _ = dp[fid]
            pc = R @ P + t
            fx, fy, cx, cy = K[fi]
            u = fx * pc[0] / pc[2] + cx; v = fy * pc[1] / pc[2] + cy
            errs.append(np.hypot(u - float(f[1]), v - float(f[2])))
    errs = np.array(errs)
    out['reproj_px_mean'] = float(errs.mean()) if errs.size else None
    out['reproj_px_median'] = float(np.median(errs)) if errs.size else None
    out['sha_delivered_poses'] = sha(f'{run_dir}/delivered_poses.txt')
    out['sha_tracks'] = sha(f'{run_dir}/tracks.txt')
    cmd = open(f'{run_dir}/cmd.txt').read()
    la = re.findall(r'loadavg=\{ ([\d.]+)', cmd)
    out['loadavg1_start'] = float(la[0]) if la else None
    json.dump(out, open(f'{run_dir}/metrics.json', 'w'), indent=1, ensure_ascii=False)
    return out


if __name__ == '__main__':
    for d in sys.argv[1:]:
        o = analyze(d)
        a = o.get('align', {})
        print(f"{o['run']}: 注册 {o.get('n_reg')}/{o['n_photos']} 点 {o.get('n_points')} 闸 {a.get('status')} "
              f"残差 RMS {1e3*o.get('centre_err_rms_m', float('nan')):.1f} mm 中位 {1e3*a.get('centre_err_median_m', float('nan')):.1f}"
              f"(复算 {1e3*o.get('centre_err_median_m_recomputed', float('nan')):.1f}) 最大 {1e3*a.get('centre_err_max_m', float('nan')):.1f}"
              f"(复算 {1e3*o.get('centre_err_max_m_recomputed', float('nan')):.1f}) mm | 对 ARKit k {o['vs_arkit']['k_pct']:+.2f}% "
              f"ATE {o['vs_arkit']['ate_cm']:.2f} cm | 链到 LiDAR {o['vs_lidar_chained']['k_pct']:+.2f}% | 喂入 k {o['input_vs_arkit']['k_pct']:+.2f}% "
              f"| 重投影 {o['reproj_px_mean']:.3f} px")
