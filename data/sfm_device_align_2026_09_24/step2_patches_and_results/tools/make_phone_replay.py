#!/usr/bin/python3
"""Build a harness feed + raw-luma frames.bin for one phone capture (read-only on the capture dir).
Frame order/ids = official_sfm_fed_frames.jsonl (what Dart fed); pose = its arkitCamFromWorld (ARKit axes,
the same ABI convention the harness driver passes to pwofficial_add_frame); K = the photo's own sidecar
intrinsics_fxfycxcy (4032x3024). Gray = PIL 'L' of the 12 MP JPEG (deviation: production decodes the JPEG
inside the core; PIL luma is the Rec.601 luma of the decoded RGB). Every file is checked for 'dataless'."""
import json, os, subprocess, sys
from PIL import Image
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cap_dir, name = sys.argv[1], sys.argv[2]
def ok(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    if r.returncode != 0 or 'dataless' in r.stdout: raise SystemExit('dataless or missing: ' + p)
    return p
fed = [json.loads(l) for l in open(ok(cap_dir + '/official_sfm_fed_frames.jsonl'))]
os.makedirs(W + '/phone', exist_ok=True)
fb = W + f'/phone/{name}.frames.bin'
off = 0
with open(fb, 'wb') as fo, open(W + f'/inputs/feed_{name}.jsonl', 'w') as ff:
    for j in fed:
        base = os.path.basename(j['jpegPath'])
        jp = ok(cap_dir + '/photos_highres/' + base); sc = ok(jp[:-4] + '.json')
        K = json.load(open(sc))['intrinsics_fxfycxcy']
        im = Image.open(jp).convert('L'); w, h = im.size
        assert (w, h) == (j['grayW'], j['grayH']), (w, h)
        fo.write(im.tobytes())
        ff.write(json.dumps({'frameIndex': j['frameId'], 'byteOffset': off, 'w': w, 'h': h, 'fxfycxcy': K,
                             'arkitCamFromWorldQwxyz': j['arkitCamFromWorldQwxyz'],
                             'arkitCamFromWorldTxyz': j['arkitCamFromWorldTxyz']}) + '\n')
        off += w * h
print(name, len(fed), 'frames ->', fb, off)
