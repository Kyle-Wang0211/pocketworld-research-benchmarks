import ast
p = "/root/diffmvs/filter.py"
s = open(p).read()
assert "VAR_GATE" not in s, "已打过"
hdr = '''import os as _os2
# 种子方差门(env VAR_GATE, 默认 0 = 不改变官方行为)。
# 依据:CasDiffMVS 是扩散模型(--ddim_eta 0 1 1 后两阶段随机采样)。白墙上代价曲线平 =>
# 不同种子挑到不同深度。实测白墙相对标准差 p50 0.228% vs 非白墙 0.044%(5.18x),
# 同种子两遍的地板只有 0.004%(信噪比 63.7x)。这是直接测"模型在不在瞎猜"。
_VAR_GATE = float(_os2.environ.get("VAR_GATE", "0"))
_VAR_DIR = _os2.environ.get("VAR_DIR", "/root/ms/varmap")
'''
s = hdr + s
old = "        final_mask = np.logical_and(photo_mask, geo_mask)"
new = """        final_mask = np.logical_and(photo_mask, geo_mask)
        if _VAR_GATE > 0:
            _vp = _os2.path.join(_VAR_DIR, "{:0>8}.npy".format(ref_view))
            if _os2.path.exists(_vp):
                _v = np.load(_vp)
                if _v.shape[:2] == final_mask.shape[:2]:
                    final_mask = np.logical_and(final_mask, _v < _VAR_GATE)"""
assert old in s
s = s.replace(old, new, 1)
ast.parse(s); open(p, "w").write(s)
print("patched: VAR_GATE 已加入, 默认 0 无害")
