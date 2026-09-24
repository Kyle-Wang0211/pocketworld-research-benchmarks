#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SimpleProc (princeton-vl, BSD-3) -> CasDiffMVS blend.py 目录布局

出处逐项:
  分辨率/内参    实测原生 768x576, cx=384 cy=288 (无缩放)
  extrinsic      = lines[1:5] = cam_T_world   [mvsanywhere fork infinigen_cubism.py:393-396]
                                              [diffmvs blend.py:54-55  同]
  intrinsic      = lines[7:10]                [同上 :260 / blend.py:56-57]
  深度有效性     (d>0)&(d<1e3)                [infinigen_cubism.py:337,366]
                 —— 与我们 tartanground2mvsnet.py:337 已在用的过滤【逐字相同】
  depth_min/max  p1 / p99 of valid            [MVSNet colmap2mvsnet.py:356-357]
  depth_interval (max-min)/(num-1)            [colmap2mvsnet.py:373, interval_scale=1]
  depth_num      192                          [与 tartanground2mvsnet.py --depth_num_field 一致]
  JPEG quality   95                           [与 tartanground2mvsnet.py:328 一致]
  pair/元组      官方 train_pair_44000scenes.txt 逐行转录, 不自算共视分数
  视角数         8 = 1 ref + 7 src            [44k_scenes.yaml: num_images_in_tuple: 8]

自研标注: 无新自由参数。唯一移位前提 = colmap2mvsnet 的 zs 原本是稀疏 COLMAP 点深度,
         我们用稠密 GT 深度像素(与 TartanGround 域一致)。
"""
import os, sys, glob, tarfile, shutil, argparse, io
import numpy as np
from PIL import Image

DIFFMVS = os.environ.get("DIFFMVS_DIR", "/root/diffmvs")
sys.path.insert(0, DIFFMVS)
from datasets.data_io import save_pfm, read_pfm   # 官方 pfm 读写

JPEG_Q      = 95
DEPTH_NUM   = 192
SENTINEL_HI = 1e3

def valid_mask(d):
    """官方有效性定义 infinigen_cubism.py:337"""
    return np.isfinite(d) & (d > 0) & (d < SENTINEL_HI)

def depth_range(d):
    """colmap2mvsnet.py:356-357 —— p1/p99,索引方式逐字复刻 int(len(zs)*.01)"""
    zs = np.sort(d[valid_mask(d)].astype(np.float64))
    assert zs.size > 0, "全部深度无效"
    dmin = float(zs[int(len(zs) * .01)])
    dmax = float(zs[int(len(zs) * .99)])
    return dmin, dmax

def load_official_tuples(path):
    """train_pair_44000scenes.txt -> {scene: [(ref, [src...]), ...]} , 逐行转录"""
    d = {}
    with open(path) as f:
        for line in f:
            t = line.split()
            if not t: continue
            d.setdefault(t[0], []).append((int(t[1]), [int(x) for x in t[2:]]))
    return d

def scene_complete(out_root, scene):
    """目标已完整 -> 幂等跳过。🔴 防止 pipeline 重写正在被训练读取的文件(竞态)。"""
    sd = os.path.join(out_root, "sp_" + scene)
    if not os.path.isfile(os.path.join(sd, "cams", "pair.txt")): return False
    for f in range(8):
        if not (os.path.isfile(os.path.join(sd, "blended_images", "%08d.jpg" % f))
                and os.path.isfile(os.path.join(sd, "cams", "%08d_cam.txt" % f))
                and os.path.isfile(os.path.join(sd, "rendered_depth_maps", "%08d.pfm" % f))):
            return False
    return True


def write_scene(out_root, scene, frames, tuples):
    """frames: {fid: (png_bytes, npy_bytes, txt_text)}"""
    if scene_complete(out_root, scene):
        return os.path.join(out_root, "sp_" + scene), 8
    sd  = os.path.join(out_root, "sp_" + scene)
    dI  = os.path.join(sd, "blended_images")
    dC  = os.path.join(sd, "cams")
    dD  = os.path.join(sd, "rendered_depth_maps")
    for p in (dI, dC, dD): os.makedirs(p, exist_ok=True)

    fids = sorted(frames)
    for fid in fids:
        pngb, npyb, txt = frames[fid]

        # ---- 图像: RGBA -> RGB。alpha 必须恒 255,否则说明有透明背景(GSO 教训)
        im = Image.open(io.BytesIO(pngb))
        if im.mode == "RGBA":
            a = np.asarray(im)[:, :, 3]
            # 官方 mvsanywhere fork generic_mvs_dataset.py:465 `image = image[:3]` 直接丢 alpha, 不看值
            # (09-14 scene_28608 f0 83% 像素 alpha 251-254 撞上原断言) -> 只记录, 照官方丢掉
            if (a != 255).any():
                print("[alpha<255] %s f%d min=%d frac=%.3f" % (scene, fid, a.min(), (a != 255).mean()), flush=True)
            im = im.convert("RGB")
        elif im.mode != "RGB":
            im = im.convert("RGB")
        assert im.size == (768, 576), "%s f%d 分辨率 %s != (768,576)" % (scene, fid, im.size)
        im.save(os.path.join(dI, "%08d.jpg" % fid), quality=JPEG_Q)

        # ---- 深度: npy -> pfm (官方 save_pfm)
        d = np.load(io.BytesIO(npyb)).astype(np.float32)
        assert d.shape == (576, 768), "%s f%d 深度 shape %s" % (scene, fid, d.shape)
        save_pfm(os.path.join(dD, "%08d.pfm" % fid), d)   # 官方签名是 (filename, image)

        # ---- cam.txt: 原 extrinsic/intrinsic 原样保留 + 补第 12 行深度范围
        L = [l.rstrip() for l in txt.splitlines()]
        dmin, dmax = depth_range(d)
        iv = (dmax - dmin) / max(DEPTH_NUM - 1, 1)
        with open(os.path.join(dC, "%08d_cam.txt" % fid), "w") as fo:
            fo.write("extrinsic\n")
            for r in range(4): fo.write(L[1 + r] + " \n")
            fo.write("\nintrinsic\n")
            for r in range(3): fo.write(L[7 + r] + " \n")
            fo.write("\n%.6f %.6f %d %.6f \n" % (dmin, iv, DEPTH_NUM, dmax))

    # ---- pair.txt: 官方元组逐行转录 (分数恒 1.0 —— 官方元组本身不带分数)
    tp = tuples[scene]
    # 🔴 blend.py:34  pair_file = "{}/cams/pair.txt".format(scan)  —— 在 cams/ 下,不是 scan 根
    with open(os.path.join(dC, "pair.txt"), "w") as fo:
        fo.write("%d\n" % len(tp))
        for ref, srcs in tp:
            fo.write("%d\n" % ref)
            fo.write("%d " % len(srcs) + " ".join("%d 1.0" % s for s in srcs) + "\n")
    return sd, len(fids)

def scan_shard(tar_path):
    """读一个 shard -> {scene: {fid: [png,npy,txt]}} 与 tar 内出现的最后一个 scene 名"""
    frames = {}; last = None
    with tarfile.open(tar_path) as tf:
        for m in tf:
            if not m.isfile(): continue
            base, ext = os.path.splitext(m.name)
            parts = base.split("_")
            scene = "_".join(parts[:-1]); fid = int(parts[-1])
            frames.setdefault(scene, {}).setdefault(fid, [None, None, None])
            frames[scene][fid][{".png": 0, ".npy": 1, ".txt": 2}[ext]] = tf.extractfile(m).read()
            last = scene
    return frames, last


def process_shards(tars, out_root, tuples):
    """🔴 场景会跨 shard 切分 (实测 shard0 末=scene_10040_f5, shard1 首=scene_10040_f6),
       故必须顺序处理并把被切断的尾场景 carry 到下一个 shard。"""
    carry = {}; written = 0; dropped = []
    for ti, tp in enumerate(tars):
        frames, last = scan_shard(tp)
        for sc, fr in carry.items():                 # 合并上一个 shard 的残尾
            frames.setdefault(sc, {}).update(fr)
        carry = {}
        is_final = (ti == len(tars) - 1)
        for scene in sorted(frames, key=lambda x: int(x.split("_")[1])):
            fr = frames[scene]
            if scene == last and not is_final:       # 只有 tar 内最后一个场景可能被切断
                carry[scene] = fr; continue
            if len(fr) != 8 or not all(all(x is not None for x in v) for v in fr.values()):
                dropped.append((scene, len(fr))); continue
            if scene not in tuples:
                dropped.append((scene, -1)); continue
            fr2 = {k: (v[0], v[1], v[2].decode()) for k, v in fr.items()}
            write_scene(out_root, scene, fr2, tuples); written += 1
        print("[%d/%d] %s  累计写出 %d 场景  carry %s" % (
              ti + 1, len(tars), os.path.basename(tp), written, list(carry)), flush=True)
    return written, dropped


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tars", nargs="+", required=True)
    ap.add_argument("--out", default="/root/monotrain")
    ap.add_argument("--tuples", default="/root/mvsa_fork/data_splits/infinigen_cubism/train_pair_44000scenes.txt")
    a = ap.parse_args()
    tp = load_official_tuples(a.tuples)
    print("[info] 官方元组: %d 场景" % len(tp))
    w, dr = process_shards(sorted(a.tars), a.out, tp)
    print("[done] 写出 %d 场景, 丢弃 %d 个 (帧数!=8 或不在元组表)" % (w, len(dr)))
    for sc, n in dr[:20]: print("   drop %s (帧数 %d)" % (sc, n))
