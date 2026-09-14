import ast, os
fixed = []

# ① ply2bins.py:翻转前后必须自证落在已知展示帧(拿官方768当参照)
p = "/root/ply2bins.py"; s = open(p).read()
if "FRAME-SELFCHECK" not in s:
    old = 'P[:,1]*=-1; P[:,2]*=-1'
    new = '''# 🔴 这一步假设输入在 COLMAP 帧。翻完必须自证落在展示帧,否则静默出错(历史上栽过:
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
    print("[FRAME-SELFCHECK] 🔴 参照文件不存在,本次未自证")'''
    assert old in s, "ply2bins 锚点未命中"
    s = s.replace(old, new, 1)
    ast.parse(s); open(p,"w").write(s); fixed.append("ply2bins.py 加帧自证")

# ② mono_dypcd.py:目录名与常数键的隐含契约,提前断言
p = "/root/mono_dypcd.py"; s = open(p).read()
if "SCAN-CONTRACT" not in s:
    old = 'dyp.filter_depth(PAIR, PAIR, SRC, out_ply)'
    new = '''# 🔴 隐含契约:filter_depth 拿 PAIR 的 basename 当 scan 键去查 s_all/conf_all/...
# 参数化路径时极易破坏(2026-09-11 就因 PAIRDIR 不以 scene0 结尾而 KeyError)。提前断言。
_key = os.path.basename(PAIR.rstrip("/"))
print(f"[SCAN-CONTRACT] PAIR basename = {_key!r};常数表已注入的键 = {sorted(dyp.s_all)}")
assert _key in dyp.s_all, (f"🔴 basename {_key!r} 不在常数表里 ⇒ filter_depth 会 KeyError。"
                           f"PAIRDIR 必须以 /{SCAN} 结尾。")
dyp.filter_depth(PAIR, PAIR, SRC, out_ply)'''
    assert old in s, "mono_dypcd 锚点未命中"
    s = s.replace(old, new, 1)
    ast.parse(s); open(p,"w").write(s); fixed.append("mono_dypcd.py 加 scan 键契约断言")

print("已加固:", *fixed, sep="\n  ")
