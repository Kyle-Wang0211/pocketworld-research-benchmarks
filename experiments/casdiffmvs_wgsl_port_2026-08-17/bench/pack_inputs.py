#!/usr/bin/env python3
"""把 N 帧的全部推理输入打成一个二进制,供端上 bench 读取。

  python3.11 pack_inputs.py --fixture .../fx_official --ref .../bench_baseline/EXTNF \
      --out inputs.bin --frames 8

为什么要打包:端上 bench **不应依赖设备上的任何采集数据**,也不该去碰产品 app 的沙盒。
把输入连同参考深度一起塞进 bench 自己的 bundle,自给自足。

格式(全部小端):
  magic "PWMVSB02" (8B)
  n_frames u32 · n_view u32 · H u32 · W u32 · n_depth u32 · n_img u32
  图像库:f16[n_img * H * W]                ← 灰度,唯一图只存一次
  每帧:
    view_idx  i32[n_view]                  ← 指向图像库;端上灰度→3通道就地展开
    pm1/2/3   f32[n_view*2*4*4] ×3        (stage1/2/3;stage4 从不被读)
    dv        f32[n_depth]
    noise2    f32[(H/4)*(W/4)]
    noise3    f32[(H/2)*(W/2)]
    ref_depth f32[H*W]                     ← 端上直接对拍,不用回传大数组

🔴 v01 曾把每帧 10 个视图各存一份 f32 三通道 ⇒ 8 帧 443 MB,推不进设备。
   病根两个:灰度被复制成 3 通道存了;相邻帧共用大量视图却各存一份。
   v02 改成"唯一图 fp16 灰度存一次 + 每帧只存索引",体积降一个量级。

🔑 噪声取自参考跑的 `--ext-noise` 落盘结果 —— 实测它与模型内部 randn_like
   97 帧逐比特相同,所以端上吃同一份噪声就能与 host 参考逐像素比。
   不这么做的话,对拍的是扩散噪声(同输入两跑 21.5% 像素差 >1%)。
"""
import argparse, json, os, struct
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--ref", required=True, help="含 depth/ 与 noise/ 的参考跑目录")
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=8)
    args = ap.parse_args()

    meta = json.load(open(f"{args.fixture}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    NIMG = meta["num_src"] + 1
    ND = 384
    IM = np.fromfile(f"{args.fixture}/images.f16", np.float16).reshape(NF, H, W)
    CM = np.fromfile(f"{args.fixture}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{args.fixture}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
    n = min(args.frames, NF)

    with open(args.out, "wb") as fo:
        # 先算出这 n 帧真正用到的唯一图像,建立紧凑索引
        views = [[f] + list(NB[f][:NIMG - 1]) for f in range(n)]
        uniq = sorted({int(v) for vv in views for v in vv})
        remap = {g: i for i, g in enumerate(uniq)}
        fo.write(b"PWMVSB02")
        fo.write(struct.pack("<6I", n, NIMG, H, W, ND, len(uniq)))
        fo.write(IM[uniq].astype(np.float16).tobytes())      # 图像库
        for f in range(n):
            view = views[f]
            fo.write(np.array([remap[int(v)] for v in view], np.int32).tobytes())
            Ks = np.stack([CM[v, 0:9].reshape(3, 3) for v in view])
            wc = np.stack([np.vstack([np.hstack([CM[v, 9:18].reshape(3, 3),
                                                 CM[v, 18:21][:, None]]),
                                      [0, 0, 0, 1]]).astype(np.float32) for v in view])
            base = np.zeros((NIMG, 2, 4, 4), np.float32)
            base[:, 0] = wc
            base[:, 1, :3, :3] = Ks
            for dv_ in (8.0, 4.0, 2.0):
                mm = base.copy()
                mm[:, 1, :2, :] = base[:, 1, :2, :] / dv_
                fo.write(mm.astype(np.float32).tobytes())
            dv = np.linspace(1 / float(CM[f, 25]), 1 / float(CM[f, 24]),
                             ND, dtype=np.float32)
            fo.write(dv.tobytes())
            nz = np.load(f"{args.ref}/noise/{f:04d}.npz")
            fo.write(nz["n2"].astype(np.float32).tobytes())
            fo.write(nz["n3"].astype(np.float32).tobytes())
            fo.write(np.load(f"{args.ref}/depth/{f:04d}.npy")
                     .astype(np.float32).tobytes())
    sz = os.path.getsize(args.out)
    print(f"✅ {args.out}  {sz/1e6:.1f} MB  ({n} 帧 · {NIMG} 视图 · {W}×{H})")
    print(f"   唯一图 {len(uniq)} 张(fp16 灰度,{len(uniq)*H*W*2/1e6:.0f} MB)"
          f" + 每帧 {(sz - 32 - len(uniq)*H*W*2)/n/1e6:.2f} MB 小张量与参考深度")
    print(f"   ⚠️ 端上需把灰度就地展开成 3 通道(模型输入是 3 通道)")


if __name__ == "__main__":
    main()
