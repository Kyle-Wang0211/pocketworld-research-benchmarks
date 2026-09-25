#!/usr/bin/env python3
"""真实聚簇点云台架判读。判读规矩与 analyze_points.py 同,先写死。

  主判据 = GPU 时间戳 p50;效应量 = 逐轮配对比值(轮 = 重复单位)。
  噪声底 = RM2/RM(同 pipeline 同 buffer,只换轮内位置)。
  阳性对照 = N/2 ÷ N ≈ 0.5,不过则整档作废。
  正确性 = 三种次序两两比:**并列的签名是三对同量级**;真错的签名是莫顿那两对
          远大于 native-random 那一对。另加「覆盖率必须完全相等」。
"""
import json, statistics, sys, glob

def paired(a,b): return [x/y for x,y in zip(a,b) if y>0]

for path in (sys.argv[1:] or sorted(glob.glob("cloud_run*.json"))):
    d=json.load(open(path))
    print("="*80)
    print(f"{path}   tag={d['tag']}")
    print(f"adapter : {d['adapter']}")
    cam=d['camera']; rad=d['point_radius_px']; bb=d['bbox']
    print(f"cloud   : N={d['n_points']:,}  bbox extent={bb['extent']} diag={bb['diag']}")
    print(f"camera  : {cam['name']}  dist={cam['dist']:.4f} (d_fit={cam['d_fit']:.4f})"
          f"  eye={cam['eye']}  znear={cam['znear']:.3f} zfar={cam['zfar']:.3f}")
    print(f"半径(生产口径 baseScale*camDist/depth, base={rad['base_scale']}px):"
          f" min {rad['min']:.2f}  p50 {rad['p50']:.2f}  p99 {rad['p99']:.2f}"
          f"  max {rad['max']:.2f}  被钳 {rad['n_clamped']}  相机后 {rad['n_behind_camera']}")
    if 'n_onscreen' in rad:
        print(f"画面内的点: {rad['n_onscreen']:,} / {d['n_points']:,} = "
              f"{100*rad['n_onscreen']/d['n_points']:.1f}%")
    print(f"schedule: K={d['K']} R={d['R']} warm={d['warmup']} arms={d['arm_mask']}")
    pc=d['permutation_check']
    print(f"置换校验(渲染之外): morton={pc['real_morton_is_permutation']} "
          f"random={pc['real_random_is_permutation']}")
    if d.get('wgpu_errors'): print("!! wgpu:",d['wgpu_errors'][:200])
    labs=d['labels']
    base=d['RN_gpu_ms']['p50'] if 'RN_gpu_ms' in d else d[labs[0]+'_gpu_ms']['p50']
    N=d['n_points']
    print()
    hdr=f"{'label':<5}{'gpu p50':>10}{'wall p50':>10}{'ms/1M':>9}{'fps(gpu)':>10}{'/RN':>8}"
    print(hdr); print("-"*len(hdr))
    names={'RN':'真云 PLY 原生序','RM':'真云 莫顿序','RM2':'  (RM 空臂=噪声底)',
           'RR':'真云 随机序','UM':'合成均匀 莫顿序','UR':'合成均匀 随机序'}
    for L in labs:
        g=d[L+'_gpu_ms']['p50']; w=d[L+'_wall_ms']['p50']
        print(f"{L:<5}{g:10.2f}{w:10.2f}{g/(N/1e6):9.2f}{1000/w:10.1f}{g/base:8.3f}"
              f"   {names.get(L,'')}")
    emp=d['empty_pass_gpu_ms']['p50']
    print(f"空 pass(1 点): {emp:.3f} ms = RN 的 {100*emp/base:.2f}%")
    h=d['positive_control_halfN_gpu_ms']['p50']
    r=h/base
    print(f"阳性对照 {d['positive_control_label']}(N/2)/(N) = {h:.2f}/{base:.2f} = {r:.4f}"
          f"  {'PASS' if 0.35<=r<=0.70 else '**FAIL -> 整档作废**'}")
    print()
    print(f"{'对比':<18}{'median':>9}{'min':>9}{'max':>9}{'wins':>8}")
    rRN=d.get('round_gpu_p50_RN',[])
    for L in labs:
        if L=='RN' or not rRN: continue
        rr=paired(d['round_gpu_p50_'+L],rRN)
        if not rr: continue
        print(f"{L+'/RN':<18}{statistics.median(rr):9.4f}{min(rr):9.4f}{max(rr):9.4f}"
              f"{sum(1 for x in rr if x<1):>5}/{len(rr):<2}")
    if 'round_gpu_p50_RM2' in d and 'round_gpu_p50_RM' in d:
        f=paired(d['round_gpu_p50_RM2'],d['round_gpu_p50_RM'])
        print(f"噪声底 |1-RM2/RM| = {100*abs(1-statistics.median(f)):.2f}%")
    # 局部性红利 / 聚簇 vs 均匀
    def ratio(a,b):
        if 'round_gpu_p50_'+a not in d or 'round_gpu_p50_'+b not in d: return None
        rr=paired(d['round_gpu_p50_'+a],d['round_gpu_p50_'+b])
        return (statistics.median(rr), min(rr), max(rr), sum(1 for x in rr if x<1), len(rr))
    print()
    for a,b,what in [('RM','RR','真云:莫顿序 ÷ 随机序  = 聚簇数据上的局部性红利'),
                     ('RN','RR','真云:原生序 ÷ 随机序  = MVS 输出自带多少局部性'),
                     ('RM','RN','真云:莫顿序 ÷ 原生序  = 再排一次还值不值'),
                     ('UM','UR','合成均匀:莫顿 ÷ 随机  = 均匀数据上的局部性红利'),
                     ('RM','UM','莫顿序下 聚簇 ÷ 均匀'),
                     ('RR','UR','随机序下 聚簇 ÷ 均匀')]:
        v=ratio(a,b)
        if v: print(f"  {a}/{b}  {v[0]:.4f}  [{v[1]:.4f},{v[2]:.4f}]  {v[3]}/{v[4]}轮  — {what}")
    dr=[]
    for L in labs:
        s=d.get('round_gpu_p50_'+L,[])
        if len(s)>=2 and s[0]>0: dr.append(f"{L} {100*(s[-1]/s[0]-1):+.1f}%")
    print("\n首轮→末轮漂移: "+"  ".join(dr))
    c=d['correctness_three_orders']
    print(f"\n正确性(同一批真点,三种 buffer 次序):")
    tot=1179*2556
    for k,lbl in [('d_native_random','原生 vs 随机'),('d_native_morton','原生 vs 莫顿'),
                  ('d_random_morton','随机 vs 莫顿')]:
        x=c[k]; print(f"  {lbl}: {x['pixels']:>7,} px ({100*x['pixels']/tot:.5f}%)"
                      f"  {x['bytes']:>8,} B  max_abs {x['max_abs']}")
    dab,dam,dbm=[c[k]['pixels'] for k in
                 ('d_native_random','d_native_morton','d_random_morton')]
    tot_px = 1179*2556
    # 判据(先写死):莫顿序有 bug 的签名 = **莫顿与另外两者都差得比它们彼此更远**。
    # 并列的签名 = 三对都在同一个极小的量级上,且谁大谁小只反映「两种次序在
    # 并列点上的相对访问顺序有多像」—— 原生序与莫顿序都是空间有序的,所以
    # 它们反而**最像**,d(原生,莫顿) 最小是合理的,不是异常。
    bug = (dam > 3*max(dab,1)) and (dbm > 3*max(dab,1))
    worst = max(dab,dam,dbm)/tot_px
    print(f"  判据:莫顿若有 bug,d(原生,莫顿) 与 d(随机,莫顿) **都**应远大于 "
          f"d(原生,随机) —— 实测 {dam} 和 {dbm} vs {dab}")
    print("  ⇒ " + ("🔴 **像真错,需要单独查**" if bug else
          f"**不是 bug**:最大的一对也只有 {100*worst:.5f}% 的像素,"
          f"且莫顿不是那个离群者 ⇒ f32 深度并列"))
    print(f"  覆盖率三者完全相等: {c['coverage_all_equal']}  "
          f"({c['native']['coverage']:.6f})  sd_rgb={c['native']['sd_rgb']}")
    n=d.get('negative_control_blended')
    if n:
        x=n['diff']
        print(f"阴性对照(混合+无深度,必须**大量不同**):{x['pixels']:,} px "
              f"({100*x['pixels']/tot:.3f}%)  = 正向那条的 {x['pixels']/max(dam,1):.0f} 倍")
