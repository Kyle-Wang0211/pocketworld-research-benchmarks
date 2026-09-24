#!/usr/bin/python3
"""Image-side quality per frame (read-only; dataless-checked): production blur metric re-implemented with OpenCV's own
Laplacian (cv2.Laplacian ksize=1 == the 4-neighbour kernel of pw-dense-stage lib/quality/quality_compute.dart:104-116) on a
128x128 INTER_AREA thumbnail of the 12 MP still (APPROXIMATION: production thumbnails come from the preview buffer via
AetherARKitPlugin extractGray128), threshold FrameQualityConstants.blurThresholdLaplacian = 200; mean brightness
(dark < 60, bright > 200); plus full-image (1008x756) Laplacian variance; db keypoints, #partners with >=15 verified
inliers, total verified inliers. Optional contact sheet of listed frames."""
import json, os, sqlite3, subprocess, sys
import numpy as np, cv2
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG = {r['cap']: r for r in json.load(open(W + '/results/phone_gate/phone_gate.json'))['rows']}
MAXID = 2147483647
def ok(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    return p if (r.returncode == 0 and 'dataless' not in r.stdout) else None
cap = sys.argv[1]; sheet = [int(v) for v in sys.argv[2].split(',')] if len(sys.argv) > 2 else []
r = PG[cap]; d = r['dir']; a = r['r040']
err = dict(zip(a['frame_ids'], a['centre_err_all_m'])); inl = dict(zip(a['frame_ids'], a['inlier_all']))
fed = [json.loads(l) for l in open(ok(d + '/official_sfm_fed_frames.jsonl'))]
con = sqlite3.connect(f'file:{ok(d + "/official_sfm_live.db")}?immutable=1', uri=True)
img = {int(''.join(c for c in n if c.isdigit())): iid for iid, n in con.execute('select image_id,name from images')}
nkp = dict(con.execute('select image_id,rows from keypoints'))
part = {}; tot = {}
for pid, rows in con.execute('select pair_id,rows from two_view_geometries'):
    i, j = divmod(pid, MAXID)
    for x in (i, j):
        tot[x] = tot.get(x, 0) + rows
        if rows >= 15: part[x] = part.get(x, 0) + 1
thumbs = []
for j in sorted(fed, key=lambda j: j['captureTimestamp']):
    f = j['frameId']; jp = ok(d + '/photos_highres/' + os.path.basename(j['jpegPath']))
    if not jp: print('  %3d  (photo not in backup)' % f); continue
    g = cv2.imread(jp, cv2.IMREAD_GRAYSCALE)
    t128 = cv2.resize(g, (128, 128), interpolation=cv2.INTER_AREA)
    s128 = float(cv2.Laplacian(t128, cv2.CV_64F, ksize=1)[1:-1, 1:-1].var())
    s1k = float(cv2.Laplacian(cv2.resize(g, (1008, 756), interpolation=cv2.INTER_AREA), cv2.CV_64F, ksize=1)[1:-1, 1:-1].var())
    iid = img[f]
    print('  %3d %-22s blur128=%7.1f%s full1k=%7.1f mean=%5.1f | kp=%5d partners(>=15 inl)=%3d verified_inl_total=%6d | err=%7.1fmm %s' % (
        f, os.path.basename(jp), s128, ' <200 BLURRY' if s128 < 200 else '', s1k, g.mean(), nkp.get(iid, 0), part.get(iid, 0), tot.get(iid, 0),
        1e3 * err.get(f, float('nan')), '' if inl.get(f, 1) else 'OUTLIER'))
    if f in sheet:
        th = cv2.resize(g, (403, 302), interpolation=cv2.INTER_AREA)
        cv2.putText(th, 'f%d %s' % (f, 'OUT' if not inl.get(f, 1) else ''), (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 255, 2)
        thumbs.append(th)
if thumbs:
    while len(thumbs) % 4: thumbs.append(np.zeros_like(thumbs[0]))
    rows = [np.hstack(thumbs[k:k + 4]) for k in range(0, len(thumbs), 4)]
    cv2.imwrite(W + f'/taskB/sheet_{cap}.png', np.vstack(rows))
