import ast
p = "/root/diffmvs/filter.py"
s = open(p).read()
assert "TEX_GATE" not in s, "已打过补丁"

hdr = '''import os as _os
import cv2 as _cv2
# 纹理门(可选, env TEX_GATE 控制, 默认 0 = 完全不改变官方行为)。
# 用户重定义的目标:白墙粘连 = 瞎造的几何 => 不知道就别输出, 没有墙也行。
# 只在官方 final_mask 上再 AND 一个"该像素邻域有没有纹理"的判据, 不碰官方任何阈值。
# 判据:参考图 11x11 灰度局部标准差(灰度归一到[0,1])。低于阈值 => 匹配代价曲线是平的 => 丢弃。
_TEX_GATE = float(_os.environ.get("TEX_GATE", "0"))
def _tex_std(img_bgr, win=11):
    g = _cv2.cvtColor(img_bgr, _cv2.COLOR_BGR2GRAY).astype("float32") / 255.0
    m = _cv2.blur(g, (win, win)); m2 = _cv2.blur(g * g, (win, win))
    import numpy as _np
    return _np.sqrt(_np.clip(m2 - m * m, 0, None))
'''
s = hdr + s

old = "        final_mask = np.logical_and(photo_mask, geo_mask)"
new = """        final_mask = np.logical_and(photo_mask, geo_mask)
        if _TEX_GATE > 0:
            _img = _cv2.imread(os.path.join(out_folder, "images/{:0>8}.jpg".format(ref_view)))
            if _img is not None:
                if _img.shape[:2] != final_mask.shape[:2]:
                    _img = _cv2.resize(_img, (final_mask.shape[1], final_mask.shape[0]),
                                       interpolation=_cv2.INTER_AREA)
                final_mask = np.logical_and(final_mask, _tex_std(_img) >= _TEX_GATE)"""
assert old in s, "anchor missing"
s = s.replace(old, new, 1)
ast.parse(s)
open(p, "w").write(s)
print("patched: TEX_GATE 已加入 filter.py, 默认 0 不改变官方行为")
