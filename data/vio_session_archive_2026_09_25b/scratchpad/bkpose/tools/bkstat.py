#!/usr/bin/env python3
# bkstat.py <tag> <recording dir>:后端位姿 CSV 覆盖统计(只读)。
import csv, sys, collections
tag, rec = sys.argv[1], sys.argv[2]
W = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/bkpose/runs/'
rows = list(csv.DictReader(open(W + tag + '.backend.csv')))
keyed = list(csv.DictReader(open(W + tag + '.keyed.csv')))
fed = [l.split() for l in open(W + tag + '.map')]
kinds = collections.Counter(r['kind'] for r in rows)
first = {}; final = {}; window = {}
for r in rows:
    k = int(r['t_ns'])
    d = {'1': first, '2': final, '3': window}[r['kind']]
    if r['kind'] == '1' and k in first:
        continue
    d.setdefault(k, r)
unmapped = sum(1 for r in rows if r['t_ns'] == '-1')
fin_or_win = set(final) | set(window)
both = set(first) & fin_or_win
kf_first = sum(1 for r in first.values() if r['is_keyframe'] == '1')
fr = sorted(int(r['recording_frame']) for r in first.values())
mod3 = collections.Counter(f % 3 for f in fr)
sub = [int(l.split(',')[0]) for l in open(rec + '/ruler_subset/camera_index.csv').read().split('\n')[1:] if l]
print(f'{tag}: 喂入帧 {len(fed)},前端键控行 {len(keyed)}')
print(f'  事件条数 {dict(kinds)},未映射到录制帧 {unmapped}')
print(f'  有首次估计的帧 {len(first)}(其中当时是关键帧 {kf_first}),有定稿值(Final)的帧 {len(final)},'
      f'收尾仍在窗口 {len(window)},首次+定稿/窗口都有 {len(both)}')
print(f'  首次估计帧占喂入帧 {100*len(first)/len(fed):.1f}%;录制帧号 mod 3 分布 {dict(mod3)}')
print(f'  首个后端帧 录制帧 {fr[0] if fr else None},最后 {fr[-1] if fr else None}')
print(f'  米尺子集 {len(sub)} 帧,与有首次估计的帧重合 {len(set(sub) & set(first))},与定稿/窗口重合 {len(set(sub) & fin_or_win)}')
