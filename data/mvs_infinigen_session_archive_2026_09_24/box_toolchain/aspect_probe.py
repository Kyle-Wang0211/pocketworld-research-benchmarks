# -*- coding: utf-8 -*-
"""4:3 坑的最小复现 + 官方修法 + 裁剪等价性。不开 scene.blend, 不渲染, 纯相机数学。"""
import numpy as np, bpy
from infinigen.core.placement import camera as cam_mod
from infinigen.core.util import camera as cam_util

def K_of(cam, W, H):
    bpy.context.scene.render.resolution_x = W
    bpy.context.scene.render.resolution_y = H
    bpy.context.view_layer.update()
    return np.array(cam_util.get_calibration_matrix_K_from_blender(cam.data), dtype=float)

print("blender", bpy.app.version_string)
# --- 复现 coarse: 先设 16:9 分辨率再 spawn_camera (execute_tasks.py:235 -> camera.py:117)
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 720
cam = cam_mod.spawn_camera()
print("spawn @1280x720 -> sensor = %s x %s, lens = %.6f mm"
      % (cam.data.sensor_width, cam.data.sensor_height, cam.data.lens))
cam.data.lens = 15.0   # 固定焦距, 让三档可比 (camview 实测 fx=600 @1280x720 <=> 15mm)

K_169 = K_of(cam, 1280, 720); print("K(1280x720) =\n", K_169)

# --- (a) 只改分辨率不改 sensor = ig_res.sh 走的 render_resolution_override 那条路
try:
    K_bad = K_of(cam, 768, 576)
    print("🔴 预期报错却没报:", K_bad)
except ValueError as e:
    print("(a) 复现成功, 报错原文:", str(e)[:150])

# --- (b) 官方修法: 改分辨率后调用 adjust_camera_sensor (infinigen2/exporters/render_cycles.py:338-346 的官方顺序)
bpy.context.scene.render.resolution_x = 768
bpy.context.scene.render.resolution_y = 576
cam_mod.adjust_camera_sensor(cam)
print("(b) adjust 后 sensor = %s x %s" % (cam.data.sensor_width, cam.data.sensor_height))
K_768 = K_of(cam, 768, 576); print("K(768x576) =\n", K_768)

# --- (c) 裁剪等价: 1280x720 横向中心裁到 960x720 (4:3) 对不对得上原生 960x720
bpy.context.scene.render.resolution_x = 960
bpy.context.scene.render.resolution_y = 720
cam_mod.adjust_camera_sensor(cam)
K_960 = K_of(cam, 960, 720); print("K(960x720 原生 4:3) =\n", K_960)

x0 = (1280 - 960) // 2
K_crop = K_169.copy(); K_crop[0, 2] -= x0
print("K(1280x720 裁 x0=%d) =\n" % x0, K_crop)
print("(c) 裁剪 vs 原生 最大绝对差 =", np.abs(K_crop - K_960).max())

s = 768 / 960.0
K_cs = K_crop.copy(); K_cs[:2, :] *= s
print("(c2) 裁剪后再各向同性缩放 %.4f =\n" % s, K_cs)
print("(c2) vs 原生 K(768x576) 最大绝对差 =", np.abs(K_cs - K_768).max())

# --- adjust_camera_sensor 自己对 4:3 到底会不会 assert
for (W, H) in [(1280,720),(768,576),(1024,768),(1920,1080),(1000,750),(1366,768)]:
    sw = 18*(W/H)
    print("  adjust_camera_sensor(%d x %d): 18*W/H = %r  is_integer=%s" % (W,H,sw,sw.is_integer()))
