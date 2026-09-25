#!/usr/bin/env python3
# bk_keyed.py <tag>:把 Mac 回放器的 <tag>.backend.csv 转成台架 PwBenchReplay 同列的
# poses_backend_{first,final}_by_recording_frame.csv(first = 首次后端估计;final = 离窗定稿,
# 收尾仍在窗口的帧取收尾整窗快照)。规则与 PwBenchReplay.swift writeOutputs 同一套。
import csv, sys
W = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/bkpose/runs/'
tag = sys.argv[1]
first, final, window = {}, {}, {}
for r in csv.DictReader(open(W + tag + '.backend.csv')):
    k = r['engine_t_hex']
    if r['kind'] == '1': first.setdefault(k, r)
    elif r['kind'] == '2': final[k] = r
    elif r['kind'] == '3': window[k] = r
for k, r in window.items(): final.setdefault(k, r)
H = 'recording_frame,t_ns,tx,ty,tz,qx,qy,qz,qw,engine_t\n'
def row(r): return '%s,%s,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f\n' % (r['recording_frame'], r['t_ns'], *[float(r[c]) for c in ('tx','ty','tz','qx','qy','qz','qw','engine_t')])
fs = sorted(first.values(), key=lambda r: float(r['engine_t']))
open(W + tag + '.bk_first.csv', 'w').write(H + ''.join(row(r) for r in fs if r['recording_frame'] != '-1'))
open(W + tag + '.bk_final.csv', 'w').write(H + ''.join(row(final[k]) for k in (r['engine_t_hex'] for r in fs) if k in final and final[k]['recording_frame'] != '-1'))
print(tag, 'first', len(fs), 'final', sum(1 for r in fs if r['engine_t_hex'] in final))
