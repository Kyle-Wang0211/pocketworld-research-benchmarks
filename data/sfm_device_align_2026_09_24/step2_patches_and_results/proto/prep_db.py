#!/usr/bin/python3
"""Copy a phone capture's COLMAP database (sqlite online backup from an immutable=1 read-only handle, so the source
dir is never written) into step2/proto/<cap>/db.db and add the fed ARKit camera centres as upstream PosePrior rows
(schema = vendored COLMAP 3.14 scene/database_sqlite.cc:1226-1260 WritePosePrior / :401-418 ReadPosePriorRow:
corr_data_id=image_id, corr_sensor_id=camera_id, corr_sensor_type=CAMERA(0, util/types.h:137), position=3 doubles,
position_covariance=9 doubles (overwritten by the CLI's --overwrite_priors_covariance), coordinate_system=CARTESIAN(1),
gravity=NaN). Only the copy is modified."""
import json, os, sqlite3, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG = {r['cap']: r for r in json.load(open(W + '/results/phone_gate/phone_gate.json'))['rows']}
cap = sys.argv[1]; d = PG[cap]['dir']; out = W + f'/proto/{cap}'; os.makedirs(out, exist_ok=True)
def ok(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    if r.returncode != 0 or 'dataless' in r.stdout: raise SystemExit('dataless/missing ' + p)
    return p
src = sqlite3.connect(f'file:{ok(d + "/official_sfm_live.db")}?immutable=1', uri=True)
dst_p = out + '/db.db'
if os.path.exists(dst_p): os.remove(dst_p)
dst = sqlite3.connect(dst_p); src.backup(dst); src.close()
fed = {j['frameId']: j for j in (json.loads(l) for l in open(ok(d + '/official_sfm_fed_frames.jsonl')))}
n = 0
dst.execute('delete from pose_priors')
for iid, name, cid in dst.execute('select image_id,name,camera_id from images').fetchall():
    f = int(''.join(c for c in name if c.isdigit()))
    if f not in fed: continue
    C = np.array(fed[f]['arkitCameraCenterWorld'], np.float64)
    dst.execute('insert into pose_priors(pose_prior_id,corr_data_id,corr_sensor_id,corr_sensor_type,position,position_covariance,gravity,coordinate_system) values (?,?,?,?,?,?,?,?)',
                (iid, iid, cid, 0, C.tobytes(), (np.eye(3) * 0.04 ** 2).T.tobytes(), np.full(3, np.nan).tobytes(), 1))
    n += 1
dst.commit(); dst.close()
os.makedirs(out + '/noimages', exist_ok=True)
print(cap, 'db copy', os.path.getsize(dst_p) >> 20, 'MiB; pose priors', n)
