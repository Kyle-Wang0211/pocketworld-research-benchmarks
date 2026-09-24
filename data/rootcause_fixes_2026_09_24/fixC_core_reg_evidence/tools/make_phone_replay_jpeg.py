#!/usr/bin/python3
"""[TASKB-JPEG] Harness feed for one phone capture WITHOUT a frames.bin: each line names the capture's own 12 MP JPEG
(driver decodes it, see driver [TASKB-JPEG]). Frame order/ids/poses = official_sfm_fed_frames.jsonl (what Dart fed,
fed order); K = the capture db's `cameras` row for that image (exactly what the phone core received), read with sqlite
immutable=1. Read-only on the capture dir; every file is stat'ed for 'dataless' before it is opened or referenced."""
import json, os, sqlite3, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cap_dir, name = sys.argv[1], sys.argv[2]
def ok(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    if r.returncode != 0 or 'dataless' in r.stdout: raise SystemExit('dataless or missing: ' + p)
    return p
fed = [json.loads(l) for l in open(ok(cap_dir + '/official_sfm_fed_frames.jsonl'))]
con = sqlite3.connect(f'file:{ok(cap_dir + "/official_sfm_live.db")}?immutable=1', uri=True)
K = {}
for name_, cid in con.execute('select name,camera_id from images'):
    K[int(''.join(c for c in name_ if c.isdigit()))] = cid
P = {cid: np.frombuffer(p, np.float64).tolist() for cid, p in con.execute('select camera_id,params from cameras')}
with open(W + f'/inputs/feed_{name}.jsonl', 'w') as ff:
    for j in fed:
        jp = ok(cap_dir + '/photos_highres/' + os.path.basename(j['jpegPath']))
        ff.write(json.dumps({'frameIndex': j['frameId'], 'byteOffset': -1, 'jpeg': jp, 'w': j['grayW'], 'h': j['grayH'],
                             'fxfycxcy': P[K[j['frameId']]][:4],
                             'arkitCamFromWorldQwxyz': j['arkitCamFromWorldQwxyz'],
                             'arkitCamFromWorldTxyz': j['arkitCamFromWorldTxyz']}) + '\n')
print(name, len(fed), 'frames (JPEG mode)')
