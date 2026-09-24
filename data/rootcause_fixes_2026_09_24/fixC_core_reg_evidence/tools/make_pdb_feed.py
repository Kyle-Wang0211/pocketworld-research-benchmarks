#!/usr/bin/python3
"""make_pdb_feed.py <cap_id> — PHONEDB-mode feed: order/ids/poses = official_sfm_fed_frames.jsonl, K = capture db cameras row,
size = fed gray size; features are read by the driver from the db itself. Read-only, dataless-checked."""
import json, os, sqlite3, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cap = sys.argv[1]
d = {r['cap']: r for r in json.load(open(W + '/results/phone_gate/phone_gate.json'))['rows']}[cap]['dir']
def ok(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    if r.returncode != 0 or 'dataless' in r.stdout: raise SystemExit('dataless or missing: ' + p)
    return p
fed = [json.loads(l) for l in open(ok(d + '/official_sfm_fed_frames.jsonl'))]
con = sqlite3.connect(f'file:{ok(d + "/official_sfm_live.db")}?immutable=1', uri=True)
K = {int(''.join(c for c in n if c.isdigit())): cid for n, cid in con.execute('select name,camera_id from images')}
P = {cid: np.frombuffer(p, np.float64).tolist() for cid, p in con.execute('select camera_id,params from cameras')}
with open(W + f'/inputs/feed_pdb_{cap}.jsonl', 'w') as ff:
    for j in fed:
        ff.write(json.dumps({'frameIndex': j['frameId'], 'byteOffset': 0, 'w': j['grayW'], 'h': j['grayH'],
                             'fxfycxcy': P[K[j['frameId']]][:4], 'arkitCamFromWorldQwxyz': j['arkitCamFromWorldQwxyz'],
                             'arkitCamFromWorldTxyz': j['arkitCamFromWorldTxyz']}) + '\n')
print(cap, len(fed), 'frames; db', d + '/official_sfm_live.db')
