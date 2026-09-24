"""GSO -> MVSNet/blend 训练格式, v2 (2026-09-14): 相机/灯光/归一化/渲染设置整本复刻
Zero-1-to-3 官方渲染脚本 objaverse-rendering/scripts/blender_script.py (cvlab-columbia/zero123, 本机存档 /root/zero123_blender_script.py):
  normalize_scene()      :251-262  scale = 1/max(bbox 边长), 再平移到 bbox 中心=原点
  set_camera_location()  :136-145  位置 = sample_spherical(radius_min=1.5, radius_max=2.2, maxz=2.2, minz=-2.2)
                                   (随机方向 × 随机半径, 相机 to_track_quat('-Z','Y') 看向原点)
  sample_spherical()     :119-128  vec~U(-1,1)^3 归一化 × radius~U(rmin,rmax), 限 minz<z<maxz
  灯光                    :69-75    一盏 AREA, energy 3000, location z=0.5, scale (100,100,100)
  相机                    :61-62    lens 35 mm, sensor_width 32 mm
  渲染                    :77-92    CYCLES, samples 128, use_denoising True, film_transparent True
  视角数 = 49: DTU 数据集 (Aanæs et al. IJCV 2016 §3.2 "59 scenes contained 49 camera positions")
  分辨率 768x576 (非 512x512): CasDiffMVS 官方 BlendedMVS 低清口径, blend.py 不 resize, 同 batch 必须同尺寸
我们自己的适配代码(有自证, 与 v1 同): 贴图修复 + 材质断言 + Z 通道取深度 + 跨视图重投影自证 (相邻 = 相机位置最近的视角)。
用法: python gso_stage1_v2.py <model_dir> <out_root> <scan_name> <n_views> [samples]
"""
import sys, os, json, math, shutil, random, glob
import numpy as np

MODEL, OUT_ROOT, SCAN = sys.argv[1], sys.argv[2], sys.argv[3]
NV = int(sys.argv[4]); SAMPLES = int(sys.argv[5]) if len(sys.argv) > 5 else 128
W, H = 768, 576

tex = glob.glob(f"{MODEL}/materials/textures/*.png")
assert tex, f"没找到贴图: {MODEL}"
link = f"{MODEL}/meshes/{os.path.basename(tex[0])}"
if not os.path.exists(link):
    os.symlink(os.path.abspath(tex[0]), link)

import bpy, mathutils
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=f"{MODEL}/meshes/model.obj")
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert objs, "导入后无网格"
n_img = 0
for o in objs:
    for ms in o.material_slots:
        if ms.material and ms.material.use_nodes:
            for nd in ms.material.node_tree.nodes:
                if nd.type == "TEX_IMAGE" and nd.image is not None and tuple(nd.image.size)[0] > 0:
                    n_img += 1
assert n_img > 0, f"🔴 材质没有加载任何图像纹理 ({MODEL})"
print(f"[TEX-SELFCHECK] 已加载图像纹理节点 {n_img} 个  OK", flush=True)

# ---- normalize_scene (zero123 blender_script.py:189-262 逐字语义) ----
def scene_meshes():
    for obj in bpy.context.scene.objects.values():
        if isinstance(obj.data, bpy.types.Mesh):
            yield obj
def scene_root_objects():
    for obj in bpy.context.scene.objects.values():
        if not obj.parent:
            yield obj
def scene_bbox():
    bbox_min = (math.inf,) * 3; bbox_max = (-math.inf,) * 3
    for obj in scene_meshes():
        for coord in obj.bound_box:
            coord = obj.matrix_world @ Vector(coord)
            bbox_min = tuple(min(x, y) for x, y in zip(bbox_min, coord))
            bbox_max = tuple(max(x, y) for x, y in zip(bbox_max, coord))
    return Vector(bbox_min), Vector(bbox_max)
bbox_min, bbox_max = scene_bbox()
scale = 1 / max(bbox_max - bbox_min)
for obj in scene_root_objects():
    obj.scale = obj.scale * scale
bpy.context.view_layer.update()
bbox_min, bbox_max = scene_bbox()
offset = -(bbox_min + bbox_max) / 2
for obj in scene_root_objects():
    obj.matrix_world.translation += offset
bpy.context.view_layer.update()
print(f"[NORMALIZE] scale={scale:.4f} bbox={tuple(round(v,3) for v in scene_bbox()[0])}..{tuple(round(v,3) for v in scene_bbox()[1])}", flush=True)

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.render.film_transparent = True
sc.render.resolution_x = W; sc.render.resolution_y = H; sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "OPEN_EXR_MULTILAYER"
sc.view_layers[0].use_pass_z = True
prefs = bpy.context.preferences.addons["cycles"].preferences
for dt in prefs.get_device_types(bpy.context): prefs.get_devices_for_type(dt[0])
if any(d.type == "OPTIX" for d in prefs.devices):
    prefs.compute_device_type = "OPTIX"; sc.cycles.device = "GPU"
    for d in prefs.devices: d.use = (d.type == "OPTIX")
print(f"[DEV] cycles.device={sc.cycles.device}", flush=True)

# ---- 灯光 (zero123 :69-75) ----
Ld = bpy.data.lights.new("Area", type="AREA"); Ld.energy = 3000
L = bpy.data.objects.new("Area", Ld); sc.collection.objects.link(L)
L.location[2] = 0.5; L.scale = (100.0, 100.0, 100.0)
# ---- 相机 (zero123 :61-62) ----
cam_d = bpy.data.cameras.new("Camera"); cam_d.lens = 35; cam_d.sensor_width = 32
cam = bpy.data.objects.new("Camera", cam_d); sc.collection.objects.link(cam); sc.camera = cam

rng = random.Random(abs(hash(SCAN)) % (2**31)); nprng = np.random.default_rng(abs(hash(SCAN)) % (2**31))
def sample_spherical(radius_min=1.5, radius_max=2.2, maxz=2.2, minz=-2.2):   # zero123 :119-128
    while True:
        vec = nprng.uniform(-1, 1, 3)
        radius = nprng.uniform(radius_min, radius_max, 1)
        vec = vec / np.linalg.norm(vec, axis=0) * radius[0]
        if maxz > vec[2] > minz:
            return vec
def set_camera_location():                                                    # zero123 :136-145
    x, y, z = sample_spherical(radius_min=1.5, radius_max=2.2, maxz=2.2, minz=-2.2)
    cam.location = (float(x), float(y), float(z))
    direction = -cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

import OpenEXR, Imath, cv2
from PIL import Image as PILImage
for sub in ("blended_images", "cams", "rendered_depth_maps"):
    os.makedirs(f"{OUT_ROOT}/{SCAN}/{sub}", exist_ok=True)
TMP = f"/dev/shm/gso_{SCAN}"; os.makedirs(TMP, exist_ok=True)
fx = W * cam_d.lens / cam_d.sensor_width        # sensor_fit AUTO, 宽边 = sensor_width
K = np.array([[fx, 0, W / 2.0], [0, fx, H / 2.0], [0, 0, 1]], dtype=np.float64)
BL2CV = np.diag([1.0, -1.0, -1.0])
Ks, Es, Ds, Cs = [], [], [], []
for i in range(NV):
    set_camera_location(); bpy.context.view_layer.update()
    sc.render.filepath = f"{TMP}/v{i:03d}"
    bpy.ops.render.render(write_still=True)
    f = OpenEXR.InputFile(f"{TMP}/v{i:03d}.exr"); ch = list(f.header()["channels"].keys())
    zname = [c for c in ch if c.endswith("Z")][0]
    z = np.frombuffer(f.channel(zname, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(H, W).copy()
    rgbn = [[c for c in ch if c.endswith("Combined." + k)][0] for k in ("R", "G", "B")]
    rgb = np.stack([np.frombuffer(f.channel(c, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(H, W) for c in rgbn], -1)
    img = (np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    PILImage.fromarray(img).save(f"{OUT_ROOT}/{SCAN}/blended_images/{i:08d}.jpg", quality=95)   # 95 = OpenCV grfmt_jpeg.cpp 默认
    Rw = np.array(cam.matrix_world.to_3x3()); Rcv = Rw @ BL2CV; t = np.array(cam.matrix_world.translation)
    E = np.eye(4); E[:3, :3] = Rcv.T; E[:3, 3] = -Rcv.T @ t
    Ks.append(K.copy()); Es.append(E); Ds.append(z); Cs.append(t.copy())
print(f"[RENDER] {NV} 视角完成", flush=True)
shutil.rmtree(TMP, ignore_errors=True)

def reproj_err(i, j):
    Ki, Ei, Di = Ks[i], Es[i], Ds[i]; Kj, Ej, Dj = Ks[j], Es[j], Ds[j]
    m = np.isfinite(Di) & (Di > 0) & (Di < 1e4)
    if m.sum() < 500: return None
    ys, xs = np.nonzero(m)
    sel = np.random.default_rng(0).choice(len(xs), size=min(4000, len(xs)), replace=False)
    xs, ys = xs[sel], ys[sel]; d = Di[ys, xs]
    pc = np.linalg.inv(Ki) @ (np.stack([xs, ys, np.ones_like(xs)]) * d)
    pw = np.linalg.inv(Ei) @ np.vstack([pc, np.ones(pc.shape[1])])
    pj = (Ej @ pw)[:3]; zz = pj[2]; good = zz > 1e-6
    uv = Kj @ (pj / np.where(good, zz, 1))
    u = np.round(uv[0]).astype(int); v = np.round(uv[1]).astype(int)
    inb = good & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    if inb.sum() < 100: return None
    dj = Dj[v[inb], u[inb]]; ok = np.isfinite(dj) & (dj > 0) & (dj < 1e4)
    if ok.sum() < 100: return None
    return float(np.median(np.abs(zz[inb][ok] - dj[ok]) / dj[ok])), int(ok.sum())
# 随机视角没有"相邻"序号: 对前 6 个视角各取相机位置最近的另一个视角 (遮挡最少) 做重投影
C = np.stack(Cs); errs = []
for i in range(min(6, NV)):
    dmat = np.linalg.norm(C - C[i], axis=1); dmat[i] = np.inf; j = int(np.argmin(dmat))
    e = reproj_err(i, j)
    if e: errs.append(e)
assert errs, "🔴 重投影自证:没有可比较的像素"
med = float(np.median([e[0] for e in errs]))
print("[REPROJ-SELFCHECK] 最近视角对 重投影相对深度误差 中位 = %.6f (样本 %s)" % (med, [e[1] for e in errs]), flush=True)
assert med < 0.01, "🔴 重投影误差 %.4f ⇒ 内外参或深度约定有翻转" % med
np.save(f"{OUT_ROOT}/{SCAN}/_depths.npy", np.stack(Ds).astype(np.float32))
json.dump({"K": [k.tolist() for k in Ks], "E": [e.tolist() for e in Es], "W": W, "H": H, "NV": NV},
          open(f"{OUT_ROOT}/{SCAN}/_meta.json", "w"))
print("[STAGE1-DONE]", SCAN, "reproj=%.6f" % med, flush=True)
