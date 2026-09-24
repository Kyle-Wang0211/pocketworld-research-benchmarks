#!/usr/bin/env python3
"""binary_little_endian PLY(x,y,z,r,g,b) -> 查看页 .pos/.col,并翻到展示帧。"""
import sys, os, numpy as np
SRC, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
with open(SRC,"rb") as f:
    hdr=b""
    while b"end_header" not in hdr: hdr += f.read(1)
    f.read(1)
    off=f.tell()
h=hdr.decode("latin1")
n=int([l for l in h.split("\n") if l.startswith("element vertex")][0].split()[-1])
dt=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
a=np.memmap(SRC, dtype=dt, mode="r", offset=off, shape=(n,))
P=np.stack([a["x"],a["y"],a["z"]],1).astype(np.float32)
C=np.stack([a["r"],a["g"],a["b"]],1).astype(np.uint8)
print(f"{n:,} 点  COLMAP帧中位 {np.round(np.median(P,0),3).tolist()}")
# 🔴 这一步假设输入在 COLMAP 帧。翻完必须自证落在展示帧,否则静默出错(历史上栽过:
# quad_20260909/off768.pos 就是 COLMAP 帧,被当成展示帧用,整窗错位)。
REF = "/root/bins_fc/fusecut.pos"          # 官方768 展示帧,已知基准
P[:,1]*=-1; P[:,2]*=-1
_med = np.median(P, 0)
if os.path.exists(REF):
    _r = np.fromfile(REF, dtype=np.float32).reshape(-1,3)
    _rm = np.median(_r, 0)
    _d = float(np.linalg.norm(_med - _rm))
    _flip = float(np.linalg.norm(_med*np.array([1,-1,-1],np.float32) - _rm))
    print(f"[FRAME-SELFCHECK] 本云中位 {np.round(_med,3).tolist()}  参照 {np.round(_rm,3).tolist()}")
    print(f"[FRAME-SELFCHECK] 距参照 {_d:.2f} m;若再翻一次则 {_flip:.2f} m")
    if _flip < _d:
        raise SystemExit(f"🔴 FRAME-MISMATCH: 再翻一次更近({_flip:.2f} < {_d:.2f} m)"
                         f" ⇒ 输入很可能已经是展示帧,不该再翻。停下,别产出错帧的 bins。")
    if _d > 8.0:
        print(f"🔴 警告:距参照 {_d:.2f} m,超出同场景应有范围,请人工确认")
else:
    print("[FRAME-SELFCHECK] 🔴 参照文件不存在,本次未自证")
P.tofile(f"{OUT}/{TAG}.pos"); C.tofile(f"{OUT}/{TAG}.col")
print(f"展示帧中位 {np.round(np.median(P,0),3).tolist()}   写出 {OUT}/{TAG}")
