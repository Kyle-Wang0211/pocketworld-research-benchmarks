#!/usr/bin/python3
"""lepton_feed.py <cap_id> — decode a capture's lepton-archived photos with the product's vendored Lepton 0.5.8
(lepton/lep_decode = pw-dense-stage vendor/lepton_jpeg/libs/ios-arm64 staticlib relinked for macOS, machine code untouched),
verify every decoded JPEG against the archive manifest's source_sha256 (byte-exact), and write the JPEG-mode feed
(inputs/feed_lp_<cap>.jsonl) exactly like make_phone_replay_jpeg.py: order/ids/poses = official_sfm_fed_frames.jsonl,
K = the capture db's cameras row. Capture dir read-only; every file stat'ed for 'dataless' first."""
import hashlib, json, os, sqlite3, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cap = sys.argv[1]
d = {r['cap']: r for r in json.load(open(W + '/results/phone_gate/phone_gate.json'))['rows']}[cap]['dir']
def ok(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    if r.returncode != 0 or 'dataless' in r.stdout: raise SystemExit('dataless or missing: ' + p)
    return p
man = json.load(open(ok(d + '/official_photo_archive.json')))['entries']
fed = [json.loads(l) for l in open(ok(d + '/official_sfm_fed_frames.jsonl'))]
con = sqlite3.connect(f'file:{ok(d + "/official_sfm_live.db")}?immutable=1', uri=True)
K = {int(''.join(c for c in n if c.isdigit())): cid for n, cid in con.execute('select name,camera_id from images')}
P = {cid: np.frombuffer(p, np.float64).tolist() for cid, p in con.execute('select camera_id,params from cameras')}
out = W + f'/lepton/jpg_{cap}'; os.makedirs(out, exist_ok=True)
args = []
for j in fed:
    b = os.path.basename(j['jpegPath']); e = man[b]
    src = ok(d + '/' + e['archive_relative_path']); dst = out + '/' + b
    if not os.path.exists(dst): args += [src, dst]
for k in range(0, len(args), 40):
    subprocess.run([W + '/lepton/lep_decode'] + args[k:k + 40], check=True, capture_output=True)
bad = 0
with open(W + f'/inputs/feed_lp_{cap}.jsonl', 'w') as ff:
    for j in fed:
        b = os.path.basename(j['jpegPath']); dst = out + '/' + b
        h = hashlib.sha256(open(dst, 'rb').read()).hexdigest()
        if h != man[b]['source_sha256'] or os.path.getsize(dst) != man[b]['source_bytes']: bad += 1
        ff.write(json.dumps({'frameIndex': j['frameId'], 'byteOffset': -1, 'jpeg': dst, 'w': j['grayW'], 'h': j['grayH'],
                             'fxfycxcy': P[K[j['frameId']]][:4], 'arkitCamFromWorldQwxyz': j['arkitCamFromWorldQwxyz'],
                             'arkitCamFromWorldTxyz': j['arkitCamFromWorldTxyz']}) + '\n')
print(cap, len(fed), 'frames decoded; sha256/size mismatches vs manifest:', bad)
