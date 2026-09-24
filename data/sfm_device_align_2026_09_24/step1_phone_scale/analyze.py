#!/usr/bin/python3
"""Step 1: does on-device SfM finalize change delivered scale vs the device (ARKit) trajectory?

Read-only. Reads capture files in place; never opens iCloud 'dataless' placeholders.
Writes only results.json / results.tsv into this script's directory.
"""
import collections
import hashlib
import json
import os
import re
import sqlite3
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STAT = os.path.join(HERE, 'all_files_stat.txt')

META = 'official_sfm_sparse_meta.json'
FED = 'official_sfm_fed_frames.jsonl'
SIDE = 'official_sfm_live.db.arkit_pose_v1'
DIAG = 'sfm_match_fail.jsonl'
DB = 'official_sfm_live.db'


def R_wxyz(w, x, y, z):
    n = np.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def umeyama(src, dst):
    """dst ~= s * R @ src + t. Returns s, R, t, rms (in dst units)."""
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)
    n = len(src)
    ms, md = src.mean(0), dst.mean(0)
    xs, xd = src - ms, dst - md
    cov = xd.T @ xs / n
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    var_s = (xs ** 2).sum() / n
    s = np.trace(np.diag(D) @ S) / var_s
    t = md - s * R @ ms
    res = dst - (s * (R @ src.T).T + t)
    rms = np.sqrt((res ** 2).sum(1).mean())
    return s, R, t, rms, res


def rot_deg(R):
    c = (np.trace(R) - 1) / 2
    return float(np.degrees(np.arccos(np.clip(c, -1, 1))))


def available(fs, name):
    return name in fs and 'dataless' not in fs[name][0] and fs[name][1] > 0


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()[:10]


def load_inventory():
    dirs = collections.defaultdict(dict)
    for line in open(STAT):
        fl, sz, p = line.rstrip('\n').split('|', 2)
        d, f = os.path.split(p)
        dirs[d][f] = (fl, int(sz))
    caps = collections.defaultdict(list)
    for d, fs in dirs.items():
        b = os.path.basename(d)
        if re.fullmatch(r'cap_\d{16}', b):
            caps[b].append(d)
    return dirs, caps


def read_sidecar(p):
    b = open(p, 'rb').read()
    magic, ver, count, body = struct.unpack('<8sIII', b[:20])
    assert magic == b'ARKPOS1\x00', magic
    assert body == count * 104 and len(b) == 32 + body, (len(b), count)
    out = {}
    gnorms = []
    for i in range(count):
        r = b[32 + i * 104:32 + (i + 1) * 104]
        fid, iid = struct.unpack('<ii', r[:8])
        active = r[8]
        qx, qy, qz, qw = struct.unpack('<4d', r[24:56])
        t = np.array(struct.unpack('<3d', r[56:80]))
        g = np.array(struct.unpack('<3d', r[80:104]))
        R = R_wxyz(qw, qx, qy, qz)
        out[fid] = dict(image_id=iid, active=active, R=R, t=t, C=-R.T @ t)
        gnorms.append(np.linalg.norm(g))
    return out, gnorms


def read_db_image_ids(p):
    con = sqlite3.connect('file:%s?immutable=1' % p, uri=True)
    m = {}
    for iid, name in con.execute('select image_id, name from images'):
        mm = re.match(r'frame_(\d+)\.jpg', name)
        if mm:
            m[int(mm.group(1))] = iid
    con.close()
    return m


def read_diag(p):
    live = []
    build = None
    other_stages = collections.Counter()
    for line in open(p, errors='replace'):
        if '"live_cloud_arkit_ba_sim3_v2"' in line:
            try:
                d = json.loads(line)
            except Exception:
                continue
            live.append(d)
            other_stages[d.get('stage')] += 1
        elif build is None and '"build_stamp"' in line:
            try:
                build = json.loads(line).get('built')
            except Exception:
                pass
    return live, build, other_stages


def analyze_copy(d, fs, perturb=None):
    meta = json.load(open(os.path.join(d, META)))
    fed = {}
    if available(fs, FED):
        for line in open(os.path.join(d, FED)):
            try:
                j = json.loads(line)
            except Exception:
                continue
            if 'arkitCameraCenterWorld' in j:
                fed[j['frameId']] = j
    side, gnorms = ({}, [])
    if available(fs, SIDE):
        side, gnorms = read_sidecar(os.path.join(d, SIDE))

    dev = {}  # frame_id -> dict(C, R (COLMAP or ARKit axes; only |components| used), ts)
    xcheck = []
    for fid, j in fed.items():
        q = j['arkitCamFromWorldQwxyz']
        dev[fid] = dict(C=np.array(j['arkitCameraCenterWorld'], float), R=R_wxyz(*q),
                        ts=j.get('captureTimestamp'))
    for fid, s in side.items():
        if fid in dev:
            xcheck.append(float(np.abs(dev[fid]['C'] - s['C']).max()))
        else:
            dev[fid] = dict(C=s['C'], R=s['R'], ts=None)

    img_id = {fid: s['image_id'] for fid, s in side.items()}
    if not img_id and available(fs, DB):
        try:
            img_id = read_db_image_ids(os.path.join(d, DB))
        except Exception as e:  # noqa
            img_id = {}
    img_src = 'sidecar' if side else ('db' if img_id else 'assumed fid+1')
    if not img_id:
        img_id = {fid: fid + 1 for fid in dev}

    reg = [p for p in meta.get('poses', []) if p.get('registered', True)]
    delivered = {}
    for p in reg:
        R = R_wxyz(*p['quat_wxyz'])
        t = np.array(p['t'], float)
        delivered[p['frame_id']] = dict(R=R, t=t, C=-R.T @ t)

    common = sorted(set(delivered) & set(dev))
    if perturb == 'shuffle':
        rng = np.random.default_rng(0)
        perm = list(rng.permutation(common))
        dev_ids = dict(zip(common, perm))
    else:
        dev_ids = {f: f for f in common}
    if len(common) < 4:
        return dict(dir=d, error='too few matched frames (%d)' % len(common))
    src = np.array([dev[dev_ids[f]]['C'] for f in common])
    dst = np.array([delivered[f]['C'] for f in common])
    if perturb == 'scale110':
        dst = dst * 1.10
    s, R, t, rms, res = umeyama(src, dst)
    # robust refit: trim centers whose residual (device-equivalent) > max(3*median, 30 mm), up to 3 passes
    keep = np.ones(len(common), bool)
    for _ in range(3):
        rs, RR, tt, rr, _res = umeyama(src[keep], dst[keep])
        full = np.linalg.norm(dst - (rs * (RR @ src.T).T + tt), axis=1) / rs
        thr = max(3 * np.median(full[keep]), 0.030)
        new_keep = full <= thr
        if new_keep.sum() < 4 or (new_keep == keep).all():
            break
        keep = new_keep
    rs, RR, tt, rrms, _ = umeyama(src[keep], dst[keep])
    robust = dict(scale=float(rs), rms_mm_dev=float(rrms / rs * 1000), n_out=int((~keep).sum()),
                  outlier_fids=[int(common[i]) for i in np.where(~keep)[0]])
    # robust: median ratio of pairwise distances (delivered/device) over pairs > 5 cm apart
    ratios = []
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            dd = np.linalg.norm(src[i] - src[j])
            if dd > 0.05:
                ratios.append(np.linalg.norm(dst[i] - dst[j]) / dd)
    med_ratio = float(np.median(ratios)) if ratios else float('nan')
    # extent of device trajectory
    extent = float(np.max(np.linalg.norm(src - src.mean(0), axis=1)))

    # absolute (no alignment) center differences: does recon world == device world?
    abs_diff = np.linalg.norm(dst - src, axis=1)

    # photo interval from device timestamps of fed frames
    ts = sorted(v['ts'] for v in dev.values() if v.get('ts') is not None)
    interval = float(np.median(np.diff(ts))) if len(ts) > 1 else float('nan')
    span = float(ts[-1] - ts[0]) if len(ts) > 1 else float('nan')

    # gauge pair: lowest two registered image ids (std::set<image_t> order)
    reg_iids = sorted((img_id.get(f, f + 1), f) for f in delivered)
    (i1, f1), (i2, f2) = reg_iids[0], reg_iids[1]
    gauge = {}
    if f1 in dev and f2 in dev:
        C1, C2 = dev[f1]['C'], dev[f2]['C']
        b1 = dev[f1]['R'] @ (C2 - C1)  # baseline in image1 camera frame (axis flip only changes signs)
        k = int(np.argmax(np.abs(b1)))
        lever = abs((dev[f2]['R'] @ (C2 - C1))[k])
        gauge = dict(f1=f1, f2=f2, iid1=i1, iid2=i2, base_m=float(np.linalg.norm(C2 - C1)),
                     comp_axis=k, comp_m=float(abs(b1[k])), lever_m=float(lever),
                     dt_s=(dev[f2]['ts'] - dev[f1]['ts']) if dev[f1].get('ts') is not None and dev[f2].get('ts') is not None else None)
        # delivered-model baseline between the same pair, in device-scale-free ratio
        D1, D2 = delivered[f1]['C'], delivered[f2]['C']
        gauge['pair_ratio_deliv_over_dev'] = float(np.linalg.norm(D2 - D1) / max(np.linalg.norm(C2 - C1), 1e-12))
        gauge['absdiff_img1_mm'] = float(np.linalg.norm(D1 - C1) * 1000)
        gauge['absdiff_img2_mm'] = float(np.linalg.norm(D2 - C2) * 1000)

    live = None
    build = None
    live_stages = None
    if available(fs, DIAG):
        lv, build, live_stages = read_diag(os.path.join(d, DIAG))
        valid = [x for x in lv if x.get('valid')]
        if valid:
            last = valid[-1]
            live = dict(stage=last.get('stage'), seq=last.get('snapshot_seq'),
                        pairs=last.get('pair_count'), inliers=last.get('inlier_count'),
                        live_over_dev=last.get('arkit_to_ba_scale'),
                        rot_deg=last.get('arkit_to_ba_rotation_deg'),
                        res_p50_mm=1000 * last.get('residual_p50_m', float('nan')),
                        n_valid=len(valid),
                        scale_range=[min(x['arkit_to_ba_scale'] for x in valid),
                                     max(x['arkit_to_ba_scale'] for x in valid)])

    return dict(
        dir=d, meta_md5=md5(os.path.join(d, META)), written_at=meta.get('written_at'),
        refined=meta.get('refined'), phase1=meta.get('summary', {}).get('phase1'),
        gravity_align=meta.get('gravity_align_quat_wxyz'), scale_anchor=meta.get('scale_anchor_factor'),
        n_fed=len(fed) or len(side), n_reg=len(delivered), n_matched=len(common),
        interval_s=interval, span_s=span, extent_m=extent,
        final_over_dev=float(s), rot_deg=rot_deg(R), rms_mm_dev=float(rms / s * 1000), robust=robust,
        pairwise_median_ratio=med_ratio,
        abs_center_diff_mm_p50=float(np.median(abs_diff) * 1000),
        abs_center_diff_mm_max=float(np.max(abs_diff) * 1000),
        gauge=gauge, live=live, build=build, img_src=img_src,
        sidecar_gravity_norm=[float(min(gnorms)), float(max(gnorms))] if gnorms else None,
        sidecar_vs_fed_center_maxdiff=max(xcheck) if xcheck else None,
    )


def main():
    dirs, caps = load_inventory()
    if len(sys.argv) > 1 and sys.argv[1] == 'controls':
        out = {}
        R = json.load(open(os.path.join(HERE, 'results.json')))['results']
        for cid, vs in R.items():
            d = vs[0]['dir']
            base = vs[0]
            sc = analyze_copy(d, dirs[d], perturb='scale110')
            sh = analyze_copy(d, dirs[d], perturb='shuffle')
            out[cid] = dict(base=base['robust']['scale'], base_rms=base['robust']['rms_mm_dev'],
                            scaled=sc['robust']['scale'], scaled_rms=sc['robust']['rms_mm_dev'],
                            shuffled=sh['final_over_dev'], shuffled_rms=sh['rms_mm_dev'],
                            shuffled_robust=sh['robust']['scale'], shuffled_robust_rms=sh['robust']['rms_mm_dev'],
                            shuffled_n_out=sh['robust']['n_out'], n=base['n_matched'], extent_m=base['extent_m'])
        json.dump(out, open(os.path.join(HERE, 'controls.json'), 'w'), indent=1)
        print('controls', len(out))
        return
    results = {}
    unusable = {}
    for cid in sorted(caps):
        copies = []
        for d in caps[cid]:
            fs = dirs[d]
            if available(fs, META) and (available(fs, FED) or available(fs, SIDE)):
                copies.append(d)
        if not copies:
            kinds = collections.Counter()
            for d in caps[cid]:
                fs = dirs[d]
                kinds['+'.join(sorted(k + ('~' if 'dataless' in v[0] else '') for k, v in fs.items()))] += 1
            unusable[cid] = dict(n_copies=len(caps[cid]), kinds=dict(kinds))
            continue
        by_hash = collections.defaultdict(list)
        for d in copies:
            by_hash[md5(os.path.join(d, META))].append(d)
        versions = []
        for h, ds in by_hash.items():
            # prefer a copy that also has the diag + sidecar
            ds_sorted = sorted(ds, key=lambda d: (not available(dirs[d], DIAG), not available(dirs[d], SIDE), d))
            r = analyze_copy(ds_sorted[0], dirs[ds_sorted[0]])
            r['n_copies_same_meta'] = len(ds)
            versions.append(r)
        results[cid] = versions
    json.dump(dict(results=results, unusable=unusable), open(os.path.join(HERE, 'results.json'), 'w'), indent=1, default=float)
    print('analyzed', len(results), 'unusable', len(unusable))


if __name__ == '__main__':
    main()
