#!/usr/bin/python3
"""Offline replay of the EXISTING production Dart SCALE-ANCHOR estimator
(pw-dense-stage@1a43510 lib/official_capture/gravity_align.dart:231-330, verbatim math)
on the 90 step-1 phone captures. Read-only; reuses step-1's dataless-aware inventory."""
import json, os, sys
import numpy as np
S1 = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/step1'
sys.path.insert(0, S1)
import analyze as A

def dart_scale(ba_c, ark_c):
    # gravity_align.dart:231-330: <3 pairs -> null; ratio da/db over db>1e-6; median = ratios[n//2]; |s-1|>0.15 -> null
    if len(ba_c) < 3: return None, 'not_enough_pairs'
    cb, ca = ba_c.mean(0), ark_c.mean(0)
    db = np.linalg.norm(ba_c - cb, axis=1); da = np.linalg.norm(ark_c - ca, axis=1)
    ok = (db > 1e-6) & np.isfinite(da) & (da > 0)
    r = np.sort(da[ok] / db[ok])
    if len(r) < 3: return None, 'not_enough_ratios'
    s = float(r[len(r) // 2])
    if not np.isfinite(s) or s <= 0: return s, 'non_finite_scale'
    if abs(s - 1) > 0.15: return s, 'scale_out_of_band'
    return s, None

dirs, caps = A.load_inventory()
R = json.load(open(os.path.join(S1, 'results.json')))['results']
out = []
for cid, vs in sorted(R.items()):
    d = vs[0]['dir']; fs = dirs[d]
    assert A.available(fs, A.META) and A.available(fs, A.FED), d
    meta = json.load(open(os.path.join(d, A.META)))
    fed = {}
    for line in open(os.path.join(d, A.FED)):
        try: j = json.loads(line)
        except Exception: continue
        if 'arkitCameraCenterWorld' in j: fed[j['frameId']] = np.array(j['arkitCameraCenterWorld'], float)
    ba, ark = [], []
    for p in meta.get('poses', []):
        if not p.get('registered', True) or p['frame_id'] not in fed: continue
        q = p['quat_wxyz']
        if sum(x * x for x in q) < 1e-12: continue
        Rm = A.R_wxyz(*q); t = np.array(p['t'], float)
        ba.append(-Rm.T @ t); ark.append(fed[p['frame_id']])
    ba, ark = np.array(ba), np.array(ark)
    s_dart, why = dart_scale(ba, ark)
    # Dart s is ark/ba; step-1 'delivered/device' is ba/ark (umeyama device->delivered)
    out.append(dict(cap=cid, n=len(ba), s_dart_ark_over_ba=s_dart, refuse_reason=why,
                    step1_delivered_over_device=vs[0]['robust']['scale'],
                    step1_rms_mm=vs[0]['robust']['rms_mm_dev']))
json.dump(out, open(os.path.join(os.path.dirname(__file__), 'dart_anchor_offline.json'), 'w'), indent=1)
n = len(out); refused = [o for o in out if o['refuse_reason']]
print('captures', n, 'refused', len(refused), [ (o['cap'], o['refuse_reason'], round(o['s_dart_ark_over_ba'] or -1, 3)) for o in refused])
# what delivered/device would be after applying the Dart anchor (scale-only): step1_scale * s_dart
post = np.array([o['step1_delivered_over_device'] * o['s_dart_ark_over_ba'] for o in out if not o['refuse_reason']])
pre = np.array([o['step1_delivered_over_device'] for o in out])
f = lambda a: 'median|dev| %.2f%% p90 %.2f%% max %.2f%%' % tuple(100 * x for x in (np.median(abs(a - 1)), np.percentile(abs(a - 1), 90), np.max(abs(a - 1))))
print('pre (as delivered, anchor dead):', f(pre))
print('post (if anchor had been live, Umeyama delivered/device after s):', f(post))
for c in ('cap_1789119308200005', 'cap_1787733401226757'):
    o = [x for x in out if x['cap'] == c][0]; print(c, o)
