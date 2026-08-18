#!/usr/bin/env python3
"""逐 ref 融合驱动 —— 官方 filter.py 的判定原样 import,循环体逐字照抄。

三个子命令:
  parity  先证两件事(mini pair,前 2 个 ref):
            ① 逐 ref 分解 == 官方整体 filter_depth(逐字节)
            ② 快速导出(结构化数组列填充) == 官方导出(逐 tuple)(逐字节)
  full    132 个 ref 全量,按 pair.txt 的最终 top-10 逐 ref 融合,快速导出,
          与官方全量 dense_P16k.ply 对 MD5
  stale   取一个重融名单里的 ref,用冻结时的旧 top-10 融一次,
          证明旧块 != 新块(重融不是空转)

⚠️ 深度图/置信度/相机/图片全部只读(shadow_out 里是指向别人产物的符号链接),
   本脚本只往自己的 shadow_out/mask 与本实验目录写。
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

REPO = os.path.expanduser(
    "~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0, REPO)
from filter import check_geometric_consistency, filter_depth   # noqa: E402 官方判定
from datasets.data_io import read_pfm, read_camera_parameters, save_mask, read_img  # noqa: E402
from plyfile import PlyData, PlyElement                        # noqa: E402

OUT = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/streaming_fuse_md5_20260818"
SHADOW = f"{OUT}/shadow_out"
EXP = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
OFFICIAL_PLY = f"{EXP}/dense_P16k.ply"

GEO_MASK_THRES = 3
GEO_PIXEL_THRES = 1.0
GEO_DEPTH_THRES = 0.01
PHOTO_THRES = [0.3, 0.5, 0.5]


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def fuse_ref(out_folder, ref_view, src_views, write_masks=True):
    """官方 filter_depth 的 per-ref 循环体,逐字照抄(仅把 src_views 变成参数)。

    返回 (xyz_world.T float64 (n,3), color u1 (n,3))——与官方 vertexs/vertex_colors
    的单个 append 元素完全相同。
    """
    ref_intrinsics, ref_extrinsics, depth_max, depth_min = read_camera_parameters(
        os.path.join(out_folder, 'cams/{:0>8}_cam.txt'.format(ref_view)))
    ref_img = read_img(os.path.join(out_folder, 'images/{:0>8}.jpg'.format(ref_view)))
    ref_depth_est = read_pfm(
        os.path.join(out_folder, 'depth_est/{:0>8}.pfm'.format(ref_view)))[0]

    confidence0 = read_pfm(
        os.path.join(out_folder, 'conf0/{:0>8}.pfm'.format(ref_view)))[0]
    confidence1 = read_pfm(
        os.path.join(out_folder, 'conf1/{:0>8}.pfm'.format(ref_view)))[0]
    confidence2 = read_pfm(
        os.path.join(out_folder, 'conf2/{:0>8}.pfm'.format(ref_view)))[0]

    photo_mask0 = confidence0 > PHOTO_THRES[0]
    photo_mask1 = confidence1 > PHOTO_THRES[1]
    photo_mask2 = confidence2 > PHOTO_THRES[2]
    photo_mask = photo_mask0 & photo_mask1 & photo_mask2

    all_srcview_depth_ests = []
    all_srcview_x = []
    all_srcview_y = []
    all_srcview_geomask = []
    geo_mask_sum = 0

    for i, src_view in enumerate(src_views):
        src_intrinsics, src_extrinsics, _, _ = read_camera_parameters(
            os.path.join(out_folder, 'cams/{:0>8}_cam.txt'.format(src_view)))
        src_depth_est = read_pfm(
            os.path.join(out_folder, 'depth_est/{:0>8}.pfm'.format(src_view)))[0]

        geo_mask, depth_reproj, x2d_src, y2d_src = check_geometric_consistency(
            ref_depth_est,
            ref_intrinsics,
            ref_extrinsics,
            src_depth_est,
            src_intrinsics,
            src_extrinsics,
            depth_max,
            depth_min,
            GEO_PIXEL_THRES,
            GEO_DEPTH_THRES
        )
        geo_mask_sum += geo_mask.astype(np.int32)
        all_srcview_depth_ests.append(depth_reproj)
        all_srcview_x.append(x2d_src)
        all_srcview_y.append(y2d_src)
        all_srcview_geomask.append(geo_mask)

    depth_est_averaged = (sum(all_srcview_depth_ests) + ref_depth_est) / (geo_mask_sum + 1)
    geo_mask = geo_mask_sum >= GEO_MASK_THRES

    final_mask = np.logical_and(photo_mask, geo_mask)
    if write_masks:
        os.makedirs(os.path.join(SHADOW, "mask"), exist_ok=True)
        save_mask(os.path.join(SHADOW, "mask/{:0>8}_photo.png".format(ref_view)), photo_mask)
        save_mask(os.path.join(SHADOW, "mask/{:0>8}_geo.png".format(ref_view)), geo_mask)
        save_mask(os.path.join(SHADOW, "mask/{:0>8}_final.png".format(ref_view)), final_mask)

    height, width = depth_est_averaged.shape[:2]
    x, y = np.meshgrid(np.arange(0, width), np.arange(0, height))
    valid_points = final_mask
    x, y, depth = x[valid_points], y[valid_points], depth_est_averaged[valid_points]
    color = ref_img[valid_points]
    xyz_ref = np.matmul(np.linalg.inv(ref_intrinsics),
                        np.vstack((x, y, np.ones_like(x))) * depth)
    xyz_world = np.matmul(np.linalg.inv(ref_extrinsics),
                          np.vstack((xyz_ref, np.ones_like(x))))[:3]
    return (xyz_world.transpose((1, 0)),
            (color * 255).astype(np.uint8),
            (photo_mask.mean(), geo_mask.mean(), final_mask.mean()))


def export_official(blocks_xyz64, blocks_col, plyfilename):
    """官方 filter_depth 尾部导出,逐字照抄(逐 tuple 转换)。"""
    vertexs = np.concatenate(blocks_xyz64, axis=0)
    vertex_colors = np.concatenate(blocks_col, axis=0)
    vertexs = np.array([tuple(v) for v in vertexs],
                       dtype=[('x', 'f4'), ('y', 'f4'), ('z', 'f4')])
    vertex_colors = np.array([tuple(v) for v in vertex_colors],
                             dtype=[('red', 'u1'), ('green', 'u1'), ('blue', 'u1')])
    vertex_all = np.empty(len(vertexs), vertexs.dtype.descr + vertex_colors.dtype.descr)
    for prop in vertexs.dtype.names:
        vertex_all[prop] = vertexs[prop]
    for prop in vertex_colors.dtype.names:
        vertex_all[prop] = vertex_colors[prop]
    el = PlyElement.describe(vertex_all, 'vertex')
    PlyData([el]).write(plyfilename)


def export_fast(blocks_xyz32, blocks_col, plyfilename):
    """快速导出:每块先 astype('f4')(与官方 float64→f4 同一 IEEE 转换,逐元素),
    结构化数组按列填充,不过 30M 个 python tuple。语义等价性由 parity 证。"""
    xyz = np.concatenate(blocks_xyz32, axis=0)
    col = np.concatenate(blocks_col, axis=0)
    vertex_all = np.empty(len(xyz), [('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
                                     ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')])
    vertex_all['x'] = xyz[:, 0]
    vertex_all['y'] = xyz[:, 1]
    vertex_all['z'] = xyz[:, 2]
    vertex_all['red'] = col[:, 0]
    vertex_all['green'] = col[:, 1]
    vertex_all['blue'] = col[:, 2]
    el = PlyElement.describe(vertex_all, 'vertex')
    PlyData([el]).write(plyfilename)


def read_pair(path):
    out = []
    with open(path) as f:
        n = int(f.readline())
        for _ in range(n):
            ref = int(f.readline())
            toks = f.readline().split()
            out.append((ref, [int(x) for x in toks[1::2]]))
    return out


def cmd_parity():
    pair = read_pair(f"{OUT}/pair_full/pair.txt")
    mini = pair[:2]
    # mini pair 文件给官方 filter_depth 用
    with open(f"{OUT}/pair_mini/pair.txt", "w") as f:
        f.write(f"{len(mini)}\n")
        for ref, srcs in mini:
            f.write(f"{ref}\n{len(srcs)} " +
                    " ".join(f"{s} 0.0" for s in srcs) + " \n")

    p_official = f"{OUT}/mini_official.ply"
    p_mine_off = f"{OUT}/mini_mine_officialexport.ply"
    p_mine_fast = f"{OUT}/mini_mine_fastexport.ply"

    filter_depth(f"{OUT}/pair_mini", SHADOW, p_official,
                 GEO_MASK_THRES, GEO_PIXEL_THRES, GEO_DEPTH_THRES,
                 PHOTO_THRES, "casdiffmvs", "general")

    bx64, bx32, bc = [], [], []
    for ref, srcs in mini:
        xyz64, col, _ = fuse_ref(SHADOW, ref, srcs)
        bx64.append(xyz64)
        bx32.append(xyz64.astype('f4'))
        bc.append(col)
    export_official(bx64, bc, p_mine_off)
    export_fast(bx32, bc, p_mine_fast)

    m = {p: md5(p) for p in (p_official, p_mine_off, p_mine_fast)}
    for p, h in m.items():
        print(f"{h}  {os.path.basename(p)}")
    assert len(set(m.values())) == 1, "🔴 parity 失败"
    print("✅ parity:逐 ref 分解 == 官方整体;快速导出 == 官方导出(逐字节)")


def cmd_full():
    pair = read_pair(f"{OUT}/pair_full/pair.txt")
    bx32, bc = [], []
    import time
    t0 = time.time()
    per_ref_ms = []
    for ref, srcs in pair:
        t1 = time.time()
        xyz64, col, stats = fuse_ref(SHADOW, ref, srcs)
        bx32.append(xyz64.astype('f4'))
        bc.append(col)
        per_ref_ms.append((time.time() - t1) * 1000)
        print(f"ref {ref:3d}  photo/geo/final {stats[0]:.4f}/{stats[1]:.4f}/{stats[2]:.4f}"
              f"  {per_ref_ms[-1]:.0f}ms", flush=True)
    p = f"{OUT}/stream_P16k.ply"
    export_fast(bx32, bc, p)
    h_mine, h_off = md5(p), md5(OFFICIAL_PLY)
    n_pts = sum(len(b) for b in bc)
    print(f"\n点数 {n_pts:,}   总耗时 {time.time()-t0:.0f}s"
          f"   逐ref融合中位 {np.median(per_ref_ms):.0f}ms")
    print(f"{h_mine}  stream_P16k.ply(流式调度装配)")
    print(f"{h_off}  dense_P16k.ply(官方全量,别人的产物,只读)")
    print("✅ MD5 一致" if h_mine == h_off else "🔴 MD5 不一致")
    json.dump({"md5_stream": h_mine, "md5_official": h_off,
               "points": int(n_pts),
               "per_ref_ms_median": float(np.median(per_ref_ms))},
              open(f"{OUT}/md5_verdict.json", "w"))


def cmd_stale():
    sched = json.load(open(f"{OUT}/schedule.json"))
    ref = sched["refuse"][0]
    stale = sched["frozen_list"][ref]
    final = sched["final_list"][ref]
    print(f"ref {ref}\n  冻结时 top-10 {stale}\n  最终   top-10 {final}")
    xyz_s, col_s, _ = fuse_ref(SHADOW, ref, stale, write_masks=False)
    xyz_f, col_f, _ = fuse_ref(SHADOW, ref, final, write_masks=False)
    same = (xyz_s.shape == xyz_f.shape and
            np.array_equal(xyz_s.astype('f4'), xyz_f.astype('f4')) and
            np.array_equal(col_s, col_f))
    print(f"  旧块点数 {len(col_s):,} / 新块点数 {len(col_f):,}  逐字节相同: {same}")
    print("✅ 旧块 != 新块 ⇒ 重融不是空转" if not same else
          "⚠️ 旧块 == 新块(该 ref 对 top-10 变化不敏感)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["parity", "full", "stale"])
    a = ap.parse_args()
    {"parity": cmd_parity, "full": cmd_full, "stale": cmd_stale}[a.cmd]()
