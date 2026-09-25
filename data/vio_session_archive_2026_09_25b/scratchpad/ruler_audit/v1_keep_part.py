
import argparse
import bisect
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
VENDORED = os.path.join(HERE, 'vendored')
sys.path.insert(0, VENDORED)

try:
    import cv2
except ImportError:  # pragma: no cover
    raise SystemExit('🔴 需要 OpenCV ≥ 4.4:用 /usr/bin/python3(cv2 4.13.0)')

import depth_ruler as DR                                   # noqa: E402  逐字复用(research @76b8d47)
from charuco_scale_arbiter import (                        # noqa: E402
    load_recording, load_intrinsics, load_tum, quat_to_rmat)

NOTICE = ('🔴 bench-only ruler:LiDAR 深度只用于研发期标定台架,永不进入产品代码、产品管线,'
          '也不作为任何产品方案的一部分')

D_ARKIT_TO_OPENCV = DR.D_ARKIT_TO_OPENCV          # diag(1,-1,-1)

# scale_eval.py(09-24 真值审计)用的设备 yaml 外参:cfg/dev_r6e2d.yaml,q_bc [-0.7071068, 0.7071068, 0, 0]
# (x,y,z,w)⇒ R_BC 如下;p_bc 米。没给 --xrslam-yaml 时才用它,且在报告里标出来。
R_BC_DEFAULT = np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
P_BC_DEFAULT = np.array([0.03290364, -0.00696553, -0.00286231])


# ═════════════════════════════════════════════════════════════════════════════════════════
# 规范估计器(scale_eval.py)的函数:原文件 vendored/ 下原样;它 import 时要 exec ate.py,
# 路径写死在 ~/Developer/viobench-recordings/ate.py —— 那台机器没有这份文件时换成 vendored/ate.py
# (两份逐字节相同,sha256 6583a967…)。只替换这一个路径常量,函数体不动。
# ═════════════════════════════════════════════════════════════════════════════════════════

def _load_scale_eval():
    src = open(os.path.join(VENDORED, 'scale_eval.py'), encoding='utf-8').read()
    ate = os.path.expanduser('~/Developer/viobench-recordings/ate.py')
    if not os.path.exists(ate):
        src = src.replace('ATE_PY = os.path.expanduser("~/Developer/viobench-recordings/ate.py")',
                          f'ATE_PY = {os.path.join(VENDORED, "ate.py")!r}')
    ns = {'__name__': 'scale_eval_vendored', '__file__': os.path.join(VENDORED, 'scale_eval.py')}
    exec(compile(src, os.path.join(VENDORED, 'scale_eval.py'), 'exec'), ns)
    return ns


SE = _load_scale_eval()


# ═════════════════════════════════════════════════════════════════════════════════════════
# 位姿:都变成「每个录制帧时间戳 t_ns → (R_wc 以 OpenCV 相机轴, 相机中心 C)」
# ═════════════════════════════════════════════════════════════════════════════════════════

def _tum_rows(path):
    """load_tum 的时间是秒(float);这里要逐行保留 9 位小数 ⇒ 按字符串解析成整数纳秒。"""
    out = []
    for ln in open(path):
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        f = ln.replace(',', ' ').split()
        if len(f) < 8:
            continue
        sec, _, frac = f[0].partition('.')
        t_ns = int(sec) * 1_000_000_000 + int((frac + '000000000')[:9]) if frac else int(sec) * 10**9
        out.append((t_ns, np.array([float(x) for x in f[1:4]]), [float(x) for x in f[4:8]]))
    return out


def tracking_by_t(recdir):
    """intrinsics.jsonl 的 arkit_tracking(本台架录制器 W6);老录制没有 ⇒ 空。"""
    out = {}
    p = os.path.join(recdir, 'intrinsics.jsonl')
    if not os.path.exists(p):
        return out
    for ln in open(p):
        ln = ln.strip()
        if not ln:
            continue
        d = json.loads(ln)
        if 'arkit_tracking' in d and 't' in d:
            out[int(round(float(d['t']) * 1e9))] = d['arkit_tracking']
    return out


def arkit_poses(recdir, path, frame_ts, tol_ns=500_000):
    """ARKit 相机位姿(x右/y上/z后)→ OpenCV 轴。时间戳就是 ARFrame.timestamp ⇒ 与帧精确相等。"""
    rows = _tum_rows(path)
    trk = tracking_by_t(recdir)
    keys = sorted(trk)
    stats = {'rows': len(rows), 'zero_translation_dropped': 0, 'not_normal_dropped': 0,
             'tracking_key_present': bool(trk)}
    by_t = {}
    for t_ns, p, q in rows:
        if np.abs(p).sum() == 0:                         # scale_eval.valid_ref_mask
            stats['zero_translation_dropped'] += 1
            continue
        if trk:
            i = bisect.bisect_left(keys, t_ns)
            state = None
            for j in (i - 1, i):
                if 0 <= j < len(keys) and abs(keys[j] - t_ns) <= tol_ns:
                    state = trk[keys[j]]
            if state != 'normal':
                stats['not_normal_dropped'] += 1
                continue
        R = quat_to_rmat(*q) @ D_ARKIT_TO_OPENCV
        by_t[t_ns] = (R, p)
    return _snap_to_frames(by_t, frame_ts, tol_ns), stats


def camera_poses_opencv(path, frame_ts, tol_ns=500_000):
    """通用:TUM 已是相机位姿、OpenCV 轴(合成数据 / 其它工具的输出)。"""
    by_t = {t: (quat_to_rmat(*q), p) for t, p, q in _tum_rows(path)}
    return _snap_to_frames(by_t, frame_ts, tol_ns), {'rows': len(by_t)}


def _snap_to_frames(by_t, frame_ts, tol_ns):
    keys = sorted(by_t)
    out = {}
    for t in frame_ts:
        i = bisect.bisect_left(keys, t)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(keys) and abs(keys[j] - t) <= tol_ns:
                if best is None or abs(keys[j] - t) < abs(keys[best] - t):
                    best = j
        if best is not None:
            out[t] = by_t[keys[best]]
    return out


def parse_extrinsic_yaml(path):
    """XRSLAM 配置 yaml(lib/vio/ffi/xrslam_config.dart 生成)里 cam0.extrinsic 的 q_bc(x,y,z,w)/ p_bc。"""
    txt = open(path).read()
    q = re.search(r'q_bc:\s*\[([^\]]+)\]', txt)
    p = re.search(r'p_bc:\s*\[([^\]]+)\]', txt)
    if not (q and p):
        raise SystemExit(f'🔴 {path} 里找不到 q_bc / p_bc')
    qv = [float(x) for x in q.group(1).split(',')]
    pv = np.array([float(x) for x in p.group(1).split(',')])
    return quat_to_rmat(*qv), pv


def xrslam_body_poses(path, frame_ts, R_bc, p_bc, ledger=None, shift_s=None, tol_ns=500_000):
    """XRSLAM BODY 位姿 → 录制帧时间 → 相机位姿(OpenCV 轴,scale_eval.body_to_cam 同式)。

    ledger:手机回放的 intrinsics_ledger.csv(列 t_ns = 录制帧时间,t_effective = 喂进引擎的时间,
            即 BODY 位姿的时间戳)⇒ 精确反查。
    shift_s:{frame_t_ns: td + exposure/2}(Mac 宿主回放)⇒ scale_eval.remap_to_frames 的做法。
    """
    rows = _tum_rows(path)
    stats = {'rows': len(rows), 'mapping': 'ledger' if ledger else 'shift'}
    eff_to_frame = {}
    if ledger:
        import csv
        with open(ledger) as f:
            for r in csv.DictReader(f):
                if r.get('t_effective') and r.get('t_ns') and int(r['t_ns']) >= 0:
                    eff_to_frame[int(round(float(r['t_effective']) * 1e9))] = int(r['t_ns'])
    else:
        for t_frame, sh in shift_s.items():
            eff_to_frame[t_frame + int(round(sh * 1e9))] = t_frame
    keys = sorted(eff_to_frame)
    by_t = {}
    unmapped = 0
    for t_ns, p_wb, q in rows:
        i = bisect.bisect_left(keys, t_ns)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(keys) and abs(keys[j] - t_ns) <= tol_ns:
                if best is None or abs(keys[j] - t_ns) < abs(keys[best] - t_ns):
                    best = j
        if best is None:
            unmapped += 1
            continue
        R_wb = quat_to_rmat(*q)
        by_t[eff_to_frame[keys[best]]] = (R_wb @ R_bc, p_wb + R_wb @ p_bc)
    stats['unmapped_rows'] = unmapped
    return _snap_to_frames(by_t, frame_ts, 1), stats


def xrslam_camera_by_frame(path, frame_ts, ledger=None):
    """[rec30] 手机回放的 poses_camera_by_recording_frame.csv → {录制帧 t_ns: (R_wc, C)}。

    键 = 整数纳秒 t_ns,与子集 camera_index.csv 的 t_ns **整数相等**才算配上(零容差、不插值)。
    位姿本来就是引擎交回的 CAMERA 位姿(world_from_camera、OpenCV 相机轴;与 BODY·T_bc 逐帧相等,
    run-fb5d3a8f 回放实测中心差 ≤ 1.5e-7 m、旋转 ≤ 1.5e-5°)⇒ 不经外参换算。
    ledger(可选,intrinsics_ledger.csv):引擎**收下**的录制帧 t_ns 集合,用来把缺位姿的子集帧分成
    「XRSLAM 没收」与「收了但不是 TRACKING_SUCCESS」。
    """
    import csv
    by_t, dup, offs = {}, 0, []
    with open(path) as f:
        for r in csv.DictReader(f):
            t = int(r['t_ns'])
            if t in by_t:
                dup += 1
            q = [float(r[k]) for k in ('qx', 'qy', 'qz', 'qw')]
            by_t[t] = (quat_to_rmat(*q), np.array([float(r['tx']), float(r['ty']), float(r['tz'])]))
            if r.get('engine_t'):
                offs.append(float(r['engine_t']) - t * 1e-9)
    matched = {t: by_t[t] for t in frame_ts if t in by_t}
    missing = [t for t in frame_ts if t not in by_t]
    stats = {'rows': len(by_t), 'mapping': 'exact_recording_t_ns (integer equality, no interpolation)',
             'duplicate_t_ns': dup, 'recording_frames': len(frame_ts),
             'recording_frames_with_pose': len(matched), 'recording_frames_without_pose': len(missing),
             'engine_t_minus_t_ns_s': [min(offs), max(offs)] if offs else None}
    if ledger:
        with open(ledger) as f:
            admitted = {int(r['t_ns']) for r in csv.DictReader(f) if r.get('t_ns') and int(r['t_ns']) >= 0}
        stats['missing_not_admitted_by_xrslam'] = sum(1 for t in missing if t not in admitted)
        stats['missing_admitted_but_not_tracking'] = sum(1 for t in missing if t in admitted)
        stats['ledger'] = os.path.abspath(ledger)
    return matched, stats


# ═════════════════════════════════════════════════════════════════════════════════════════
# 帧对 + 匹配(只算一次)
# ═════════════════════════════════════════════════════════════════════════════════════════

def DR_nearest(keys, key, tol):
    """depth_ruler.run() 里的 nearest(),原样(它是 run 的内部函数,没法 import)。"""
    i = bisect.bisect_left(keys, key)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(keys) and abs(keys[j] - key) <= tol:
            if best is None or abs(keys[j] - key) < abs(keys[best] - key):
                best = j
    return best


class Scene:
    """录制 + 深度 + 帧对 + 匹配。所有轨迹共用同一组帧对。"""
