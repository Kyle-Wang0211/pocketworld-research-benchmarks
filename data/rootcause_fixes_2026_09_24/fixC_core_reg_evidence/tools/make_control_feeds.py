#!/usr/bin/python3
"""Positive (x1.10 device scale) and negative (shuffled frame<->pose) control feeds.
Input feeds = B's harness feeds (copied, unchanged); only pose fields are touched.
  x110 : device camera centres C' = 1.10*C  <=>  CamFromWorld t' = -R(1.10 C) = 1.10 t, R unchanged.
  shuf : (q, t) pairs permuted across frames with a fixed-seed derangement; image bytes, K,
         frameIndex/byteOffset untouched, so every image is fed with another frame's pose."""
import json, os, sys, random
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = W + '/base_sfmB/inputs'; OUT = W + '/inputs'
def load(n): return [json.loads(l) for l in open(f'{SRC}/feed_{n}.jsonl')]
def dump(n, rows):
    with open(f'{OUT}/feed_{n}.jsonl', 'w') as f:
        for r in rows: f.write(json.dumps(r) + '\n')
    print(n, len(rows))
for base in ('S_prod74_A', 'S_prod74_Xhost', 'S_deb74_A'):
    rows = load(base)
    for r in rows: r['arkitCamFromWorldTxyz'] = [1.10 * x for x in r['arkitCamFromWorldTxyz']]
    dump(base + '_x110', rows)
for base in ('S_prod74_A', 'S_prod74_Xhost'):
    rows = load(base); n = len(rows); rng = random.Random(20260924)
    while True:
        perm = list(range(n)); rng.shuffle(perm)
        if all(perm[i] != i for i in range(n)): break
    poses = [(r['arkitCamFromWorldQwxyz'], r['arkitCamFromWorldTxyz']) for r in rows]
    for i, r in enumerate(rows):
        r['arkitCamFromWorldQwxyz'], r['arkitCamFromWorldTxyz'] = poses[perm[i]]
    dump(base + '_shuf', rows); print('  perm', perm)
