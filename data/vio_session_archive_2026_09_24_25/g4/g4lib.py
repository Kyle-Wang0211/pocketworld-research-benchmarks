# -*- coding: utf-8 -*-
"""G4 调查用的共享框架:直接 import 台架尺子 lidar_ruler.py,复用它的 Scene / 帧对 / 匹配 / pair_measure,
不改尺子一行。只在 scratchpad 里用。"""
import os, sys, json, pickle, types, csv
import numpy as np

RULER = os.path.expanduser('~/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler')
sys.path.insert(0, RULER)
import lidar_ruler as LR  # noqa
import cv2  # noqa

REC = os.path.expanduser('~/Developer/viobench-recordings')
WS = os.path.dirname(os.path.abspath(__file__))

RUNS = {
    '13f5': dict(sub=f'{REC}/run-13f53d2f-5935-4b1a-a499-4dc8367ea935/ruler_subset',
                 rep=f'{REC}/replay_13f53d2f_pfk-on_paced_20260925_095720_expmid',
                 report=f'{REC}/run-13f53d2f-5935-4b1a-a499-4dc8367ea935/lidar_ruler_expmid/lidar_ruler_report.json'),
    '6d18': dict(sub=f'{REC}/run-6d187dff-403a-4882-b692-7bdc6c3cfa2a/ruler_subset',
                 rep=f'{REC}/replay_6d187dff_pfk-on_paced_20260925_103521_expmid_default',
                 report=f'{REC}/run-6d187dff-403a-4882-b692-7bdc6c3cfa2a/lidar_ruler_p90/lidar_ruler_report.json'),
    '7353': dict(sub=f'{REC}/run-73538ad6-8418-4eaf-8b75-a63c9d32af46/ruler_subset',
                 rep=f'{REC}/replay_73538ad6_pfk-on_paced_20260925_103413_expmid_default',
                 report=f'{REC}/run-73538ad6-8418-4eaf-8b75-a63c9d32af46/lidar_ruler_p90/lidar_ruler_report.json'),
}


def default_args(**kw):
    a = dict(detector='sift', features=4000, ratio=0.8, pairs=90, pair_dt=0.33, depth_tol_ms=0.5,
             min_points=20, min_pairs=8, min_baseline=0.02, max_reproj_px=2.0, min_angle_deg=1.0,
             min_confidence=2, max_between=0.15, max_within=0.25, seed=20260924)
    a.update(kw)
    return types.SimpleNamespace(**a)


class Run:
    """一场录制:Scene + ARKit/XRSLAM 位姿(尺子同一函数)+ 帧对 + 匹配(缓存到 pickle)。"""

    def __init__(self, key, args=None):
        self.key = key
        cfg = RUNS[key]
        self.cfg = cfg
        self.args = args or default_args()
        self.scene = LR.Scene(cfg['sub'], self.args)
        self.frame_ts = [t for t, _ in self.scene.ts]
        self.ark, self.ark_prov = LR.arkit_poses(cfg['sub'], os.path.join(cfg['sub'], 'arkit_poses.tum'), self.frame_ts)
        self.xr_csv = os.path.join(cfg['rep'], 'poses_camera_by_recording_frame.csv')
        self.xr, self.xr_prov = LR.xrslam_camera_by_frame(self.xr_csv, self.frame_ts)
        trajs = {'arkit': self.ark, 'xr': self.xr}
        usable = [f for f in self.scene.frames if all(f['t_ns'] in tj for tj in trajs.values())]
        self.usable = usable
        pairs = self.scene.select_pairs(usable)
        cache = os.path.join(WS, f'cache_matches_{key}.pkl')
        if os.path.exists(cache):
            m = pickle.load(open(cache, 'rb'))
            assert [(p[0], p[1]) for p in m] == [(fa['t_ns'], fb['t_ns']) for fa, fb in pairs]
            self.matched = [(fa, fb, pa, pb) for (fa, fb), (_, _, pa, pb) in zip(pairs, m)]
        else:
            self.matched = [(fa, fb) + self.scene.matches(fa, fb) for fa, fb in pairs]
            pickle.dump([(fa['t_ns'], fb['t_ns'], pa, pb) for fa, fb, pa, pb in self.matched], open(cache, 'wb'))
        self._depth_cache = {}

    def depths(self, off=0, perm=None):
        key = ('perm' if perm is not None else off)
        if key not in self._depth_cache:
            self._depth_cache[key] = [self.scene.depth_of(fa, offset_rows=off, perm=perm) for fa, _, _, _ in self.matched]
        return self._depth_cache[key]

    def measure(self, poses, off=0, depths=None, args=None):
        args = args or self.args
        dd = depths if depths is not None else self.depths(off)
        out = []
        for (fa, fb, pa, pb), d in zip(self.matched, dd):
            if fa['t_ns'] not in poses or fb['t_ns'] not in poses:
                out.append({'t_a': fa['t_ns'] / 1e9, 'skipped': 'no_pose'})
                continue
            out.append(LR.pair_measure(self.scene, fa, fb, pa, pb, poses[fa['t_ns']], poses[fb['t_ns']], d, args))
        return out

    def curve(self, poses, offs=(-2, -1, 0, 1, 2)):
        """返回 {off: per-pair list}(尺子 run_all 同式:深度帧偏移 off 行)。"""
        return {o: self.measure(poses, off=o) for o in offs}


def between_iqr(ratios):
    r = np.asarray(ratios, float)
    if len(r) == 0:
        return np.nan
    s = np.median(r)
    q1, q3 = np.percentile(r, [25, 75])
    return (q3 - q1) / s


def ratios_of(per_pair):
    return np.array([p.get('scale_to_metric', np.nan) for p in per_pair])


def g4_from_curve(curve_ratios):
    """curve_ratios: {off: array(n_pairs) with nan for invalid}. 尺子同式:每个偏移只用该偏移下有效的帧对。"""
    c = {o: between_iqr(r[np.isfinite(r)]) for o, r in curve_ratios.items()}
    fin = {o: v for o, v in c.items() if np.isfinite(v)}
    return c, (min(fin, key=fin.get) if fin else None)


# ────────── 位姿工具 ──────────

def rot_log(R):
    """SO(3) log → 旋转向量(弧度)。"""
    c = (np.trace(R) - 1) / 2
    c = np.clip(c, -1, 1)
    th = np.arccos(c)
    if th < 1e-9:
        return np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / 2
    return th / (2 * np.sin(th)) * np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])


def rot_exp(w):
    th = np.linalg.norm(w)
    if th < 1e-12:
        return np.eye(3)
    k = w / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def rmat_to_quat(R):
    """→ (x,y,z,w)。"""
    q = np.empty(4)
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        q[3] = 0.25 * s
        q[0] = (R[2, 1] - R[1, 2]) / s
        q[1] = (R[0, 2] - R[2, 0]) / s
        q[2] = (R[1, 0] - R[0, 1]) / s
    else:
        i = np.argmax(np.diag(R))
        if i == 0:
            s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
            q[3] = (R[2, 1] - R[1, 2]) / s; q[0] = 0.25 * s; q[1] = (R[0, 1] + R[1, 0]) / s; q[2] = (R[0, 2] + R[2, 0]) / s
        elif i == 1:
            s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
            q[3] = (R[0, 2] - R[2, 0]) / s; q[0] = (R[0, 1] + R[1, 0]) / s; q[1] = 0.25 * s; q[2] = (R[1, 2] + R[2, 1]) / s
        else:
            s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
            q[3] = (R[1, 0] - R[0, 1]) / s; q[0] = (R[0, 2] + R[2, 0]) / s; q[1] = (R[1, 2] + R[2, 1]) / s; q[2] = 0.25 * s
    return q / np.linalg.norm(q)


class Interp:
    """按时间插值位姿(旋转走 SO(3) 测地线,中心线性)。输入 {t_ns: (R, C)}。"""

    def __init__(self, poses):
        self.t = np.array(sorted(poses), dtype=np.int64)
        self.R = [poses[t][0] for t in self.t]
        self.C = np.array([np.asarray(poses[t][1], float) for t in self.t])

    def __call__(self, t):
        i = np.searchsorted(self.t, t)
        if i <= 0 or i >= len(self.t):
            return None
        t0, t1 = self.t[i - 1], self.t[i]
        if t1 - t0 > 60_000_000:      # 两个样本间隔 > 60 ms(缺帧)⇒ 不插
            return None
        a = (t - t0) / (t1 - t0)
        R0, R1 = self.R[i - 1], self.R[i]
        R = R0 @ rot_exp(a * rot_log(R0.T @ R1))
        C = (1 - a) * self.C[i - 1] + a * self.C[i]
        return R, C


def all_arkit(run):
    """整段 ARKit(不是只在子集帧):尺子同一函数,frame_ts 用 tum 自己的时间。"""
    rows = LR._tum_rows(os.path.join(run.cfg['sub'], 'arkit_poses.tum'))
    ts = [t for t, _, _ in rows]
    p, _ = LR.arkit_poses(run.cfg['sub'], os.path.join(run.cfg['sub'], 'arkit_poses.tum'), ts)
    return p


def all_xr(run):
    by_t = {}
    with open(run.xr_csv) as f:
        for r in csv.DictReader(f):
            q = [float(r[k]) for k in ('qx', 'qy', 'qz', 'qw')]
            by_t[int(r['t_ns'])] = (LR.quat_to_rmat(*q), np.array([float(r['tx']), float(r['ty']), float(r['tz'])]))
    return by_t


def sim3_align(src, ref, common=None):
    """把 src 的世界系对齐到 ref(Umeyama,中心)。返回 (s, R, t) 使 ref ≈ s R src + t。"""
    common = common or sorted(set(src) & set(ref))
    X = np.array([src[t][1] for t in common]).T
    Y = np.array([ref[t][1] for t in common]).T
    s, R, t, ate = LR.SE['sim3'](X, Y)
    return s, R, t.reshape(3), ate
