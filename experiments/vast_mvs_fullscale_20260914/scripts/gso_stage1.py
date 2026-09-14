"""GSO -> MVSNet/blend 训练格式(bpy 直驱 Cycles/OptiX)。

🔴 本文件是**我们自己的适配代码**(BlenderProc 官方工具在本机只走 CPU,~85s/视角不可用;
   bpy 直驱实测走 OptiX ~7s/视角)。因此配了两道无自由参数的自证:
   ① 材质断言:每个材质必须有已加载的图像纹理(否则渲出灰模,MVS 零光度信号)
   ② 跨视图重投影自证:用视角 i 的深度反投影再投到视角 j,与 j 自己的深度比。
      约定正确 ⇒ 误差≈0;任一约定翻转(Y/Z、cam2world/world2cam、射线深度/Z深度) ⇒ 误差爆炸。
共视分数不自写:import tartanground2mvsnet 里已验证的官方复刻实现。
用法: python gso_render.py <model_dir> <out_root> <scan_name> <n_views> [samples]
"""
import sys, os, json, math, shutil
import numpy as np

MODEL, OUT_ROOT, SCAN = sys.argv[1], sys.argv[2], sys.argv[3]
NV = int(sys.argv[4]); SAMPLES = int(sys.argv[5]) if len(sys.argv) > 5 else 128
WR, HR = 1024, 768          # 渲染分辨率(4:3,留余地,存档用)
W,  H  = 768, 576           # 训练分辨率(官方 BlendedMVS 口径),两轴同为 0.75 缩放

# ---- 贴图修复(GSO 的 mtl 写 texture.png,文件却在 materials/textures/) ----
import glob
tex = glob.glob(f"{MODEL}/materials/textures/*.png")
assert tex, f"没找到贴图: {MODEL}"
link = f"{MODEL}/meshes/{os.path.basename(tex[0])}"
if not os.path.exists(link):
    os.symlink(os.path.abspath(tex[0]), link)
assert os.path.exists(link), "贴图软链断开"

import bpy, mathutils
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=f"{MODEL}/meshes/model.obj")
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert objs, "导入后无网格"

# ---- 自证①:材质必须真的加载了图像 ----
n_img = 0
for o in objs:
    for ms in o.material_slots:
        if ms.material and ms.material.use_nodes:
            for nd in ms.material.node_tree.nodes:
                # 判据用 image.size:非零说明 Blender 真打开了文件并读到图像头。
                # has_data 是懒加载标志,像素未被访问前恒 False,不能当判据(09-11 误报一次)
                if nd.type == "TEX_IMAGE" and nd.image is not None and tuple(nd.image.size)[0] > 0:
                    n_img += 1
assert n_img > 0, f"🔴 材质没有加载任何图像纹理 ⇒ 会渲出灰模 ({MODEL})"
print(f"[TEX-SELFCHECK] 已加载图像纹理节点 {n_img} 个  OK", flush=True)

pts = np.array([list(o.matrix_world @ mathutils.Vector(v)) for o in objs for v in o.bound_box])
ctr = pts.mean(0); rad = float(np.linalg.norm(pts - ctr, axis=1).max()); # 相机距离有出处:Objaverse-XL/Wonder3D 把物体归一化到单位立方体后 radius=2.0,
# 单位立方体外接球半径=sqrt(3)/2=0.866 ⇒ 等价于 2.0/0.866 = 2.309 倍包围球半径。
# (Zero-1-to-3 的 radius_min=1.5/max=2.2 对应 1.73~2.54,2.309 落在区间内)
dist = rad * 2.309

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = SAMPLES
sc.render.resolution_x = WR; sc.render.resolution_y = HR
sc.render.image_settings.file_format = "OPEN_EXR_MULTILAYER"  # 单层 EXR 不含 Z 通道
sc.view_layers[0].use_pass_z = True
prefs = bpy.context.preferences.addons["cycles"].preferences
for dt in prefs.get_device_types(bpy.context): prefs.get_devices_for_type(dt[0])
if any(d.type == "OPTIX" for d in prefs.devices):
    prefs.compute_device_type = "OPTIX"; sc.cycles.device = "GPU"
    for d in prefs.devices: d.use = (d.type == "OPTIX")
print(f"[DEV] cycles.device={sc.cycles.device}", flush=True)

for i in range(3):
    L = bpy.data.objects.new(f"L{i}", bpy.data.lights.new(f"L{i}", type="SUN"))
    L.data.energy = 3.0
    a = 2 * math.pi * i / 3
    L.rotation_euler = (math.radians(50), 0, a)
    sc.collection.objects.link(L)
cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam); sc.camera = cam
sc.render.film_transparent = False
# 世界:Poly Haven 室内 HDRI(CC0,商用无需署名)。提供真实光照与背景色。
# 🔴 HDRI 是无限远环境贴图,不提供深度真值 —— 深度监督来自下面的地面平面。
import glob as _g, random as _rnd
_hdris = sorted(_g.glob("/root/ph_assets/hdri/*.hdr"))
assert _hdris, "🔴 没有 HDRI 素材,背景会退回虚空"
_rng = _rnd.Random(abs(hash(SCAN)) % (2**31))
_hdr = _rng.choice(_hdris)
sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
_wt = sc.world.node_tree
for n in list(_wt.nodes):
    if n.type != "OUTPUT_WORLD": _wt.nodes.remove(n)
_env = _wt.nodes.new("ShaderNodeTexEnvironment")
_env.image = bpy.data.images.load(_hdr)
_bg = _wt.nodes.new("ShaderNodeBackground")
_wt.links.new(_env.outputs["Color"], _bg.inputs["Color"])
_wt.links.new(_bg.outputs["Background"], _wt.nodes["World Output"].inputs["Surface"])
assert _env.image is not None and tuple(_env.image.size)[0] > 0, "🔴 HDRI 未加载"
print(f"[HDRI] {os.path.basename(_hdr)} {tuple(_env.image.size)}", flush=True)

# 地面平面:给背景真实几何与深度真值(产品场景=手办放在桌面上拍)
_texs = sorted(_g.glob("/root/ph_assets/tex/*.jpg"))
assert _texs, "🔴 没有地面材质"
_tex = _rng.choice(_texs)
bpy.ops.mesh.primitive_plane_add(size=rad * 40, location=(ctr[0], ctr[1], float(pts[:, 2].min())))
_plane = bpy.context.active_object
_m = bpy.data.materials.new("ground"); _m.use_nodes = True
_bsdf = _m.node_tree.nodes["Principled BSDF"]
_ti = _m.node_tree.nodes.new("ShaderNodeTexImage")
_ti.image = bpy.data.images.load(_tex)
_mp = _m.node_tree.nodes.new("ShaderNodeMapping")
_tc = _m.node_tree.nodes.new("ShaderNodeTexCoord")
_mp.inputs["Scale"].default_value = (8.0, 8.0, 8.0)
_m.node_tree.links.new(_tc.outputs["UV"], _mp.inputs["Vector"])
_m.node_tree.links.new(_mp.outputs["Vector"], _ti.inputs["Vector"])
_m.node_tree.links.new(_ti.outputs["Color"], _bsdf.inputs["Base Color"])
_plane.data.materials.append(_m)
assert tuple(_ti.image.size)[0] > 0, "🔴 地面材质未加载"
print(f"[GROUND] {os.path.basename(_tex)} 平面边长 {rad*40:.2f}", flush=True)
print("[SETUP] done", flush=True)

# ---------------- 渲染 + 取内外参 ----------------
import OpenEXR, Imath
os.makedirs(f"{OUT_ROOT}/{SCAN}/blended_images", exist_ok=True)
os.makedirs(f"{OUT_ROOT}/{SCAN}/cams", exist_ok=True)
os.makedirs(f"{OUT_ROOT}/{SCAN}/rendered_depth_maps", exist_ok=True)
TMP = f"/dev/shm/gso_{SCAN}"; os.makedirs(TMP, exist_ok=True)

def K_from_cam():
    # Blender 透视相机 -> OpenCV K(渲染分辨率下)。判据:水平视场角
    f_mm = cam_d.lens; sw = cam_d.sensor_width
    fx = WR * f_mm / sw; fy = fx           # 方形像素
    return np.array([[fx, 0, WR / 2.0], [0, fy, HR / 2.0], [0, 0, 1]], dtype=np.float64)

SCALE = W / float(WR)                      # 0.75
assert abs(SCALE - H / float(HR)) < 1e-9, "宽高缩放比必须一致,否则几何被拉变形"
def K_to_train(K):
    return np.diag([SCALE, SCALE, 1.0]) @ K

# Blender(相机看 -Z, +Y 上) -> OpenCV(看 +Z, +Y 下)
BL2CV = np.diag([1.0, -1.0, -1.0])

Ks, Es, Ds = [], [], []
for i in range(NV):
    th = 2 * math.pi * i / NV
    ph = math.radians(12 + 50 * ((i * 7) % 5) / 4.0)
    loc = mathutils.Vector((ctr[0] + dist * math.cos(th) * math.cos(ph),
                            ctr[1] + dist * math.sin(th) * math.cos(ph),
                            ctr[2] + dist * math.sin(ph)))
    cam.location = loc
    cam.rotation_euler = (loc - mathutils.Vector(ctr)).to_track_quat("Z", "Y").to_euler()
    bpy.context.view_layer.update()
    sc.render.filepath = f"{TMP}/v{i:03d}"
    bpy.ops.render.render(write_still=True)

    f = OpenEXR.InputFile(f"{TMP}/v{i:03d}.exr")
    ch = f.header()["channels"].keys()
    zname = [c for c in ch if c.endswith("Z")][0]
    z = np.frombuffer(f.channel(zname, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(HR, WR).copy()
    cnames = list(ch)
    rgbn = [[c for c in cnames if c.endswith("Combined." + k)][0] for k in ("R", "G", "B")]
    rgb = np.stack([np.frombuffer(f.channel(c, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(HR, WR)
                    for c in rgbn], -1)
    img = (np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    from PIL import Image as PILImage
    import cv2 as _cv2
    # 存档:渲染分辨率的 RGB + 深度(以后想提高训练分辨率不用重渲)
    os.makedirs(f"{OUT_ROOT}/{SCAN}/_archive", exist_ok=True)
    PILImage.fromarray(img).save(f"{OUT_ROOT}/{SCAN}/_archive/{i:08d}.jpg", quality=95)
    np.savez_compressed(f"{OUT_ROOT}/{SCAN}/_archive/{i:08d}_depth.npz", depth=z)
    # 降采样到训练分辨率:RGB 用面积平均,深度用最近邻(与 blend.py 的 stage 降采样同约定)
    img = np.array(PILImage.fromarray(img).resize((W, H), PILImage.LANCZOS))
    z = _cv2.resize(z, (W, H), interpolation=_cv2.INTER_NEAREST)
    PILImage.fromarray(img).save(f"{OUT_ROOT}/{SCAN}/blended_images/{i:08d}.jpg", quality=95)

    Rw = np.array(cam.matrix_world.to_3x3())          # cam->world (Blender)
    Rcv = Rw @ BL2CV                                   # cam->world (OpenCV)
    t = np.array(cam.matrix_world.translation)
    E = np.eye(4); E[:3, :3] = Rcv.T; E[:3, 3] = -Rcv.T @ t   # world->cam
    Ks.append(K_to_train(K_from_cam())); Es.append(E); Ds.append(z)   # K 与深度都落在训练分辨率

print(f"[RENDER] {NV} 视角完成", flush=True)
shutil.rmtree(TMP, ignore_errors=True)

# ---------------- 自证②:跨视图重投影(无自由参数) ----------------
# 用视角 i 的深度反投影成 3D,投到视角 j,与 j 自己的深度比。
# 约定全对 ⇒ 误差≈0;任一处翻转 ⇒ 误差爆炸。
def reproj_err(i, j):
    Ki, Ei, Di = Ks[i], Es[i], Ds[i]
    Kj, Ej, Dj = Ks[j], Es[j], Ds[j]
    m = np.isfinite(Di) & (Di > 0) & (Di < 1e4)
    if m.sum() < 500: return None
    ys, xs = np.nonzero(m)
    sel = np.random.default_rng(0).choice(len(xs), size=min(4000, len(xs)), replace=False)
    xs, ys = xs[sel], ys[sel]; d = Di[ys, xs]
    pc = np.linalg.inv(Ki) @ (np.stack([xs, ys, np.ones_like(xs)]) * d)      # 相机系
    pw = np.linalg.inv(Ei) @ np.vstack([pc, np.ones(pc.shape[1])])           # 世界系
    pj = (Ej @ pw)[:3]
    z = pj[2]; good = z > 1e-6
    uv = Kj @ (pj / np.where(good, z, 1))
    u = np.round(uv[0]).astype(int); v = np.round(uv[1]).astype(int)
    inb = good & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    if inb.sum() < 100: return None
    dj = Dj[v[inb], u[inb]]
    ok = np.isfinite(dj) & (dj > 0) & (dj < 1e4)
    if ok.sum() < 100: return None
    rel = np.abs(z[inb][ok] - dj[ok]) / dj[ok]
    return float(np.median(rel)), int(ok.sum())

# 🔴 只用**相邻**视角。实测:相邻 p50=0.00058、隔一个 0.157、对侧 0.344 ——
#    误差随视角间隔单调增大是**遮挡**(绕物体转 180° 正面点必然被挡),不是约定错误。
#    把对侧算进来等于拿遮挡当错误(09-11 我第一版就这么错的)。
#    闸取 1%:正确约定实测 0.058%(低 17 倍),任何真翻转 ≥10%(高 10 倍以上),阈值落在两侧大空档里。
errs = [reproj_err(i, i + 1) for i in range(min(4, NV - 1))]
errs = [e for e in errs if e]
assert errs, "🔴 重投影自证:没有可比较的像素"
med = float(np.median([e[0] for e in errs]))
print("[REPROJ-SELFCHECK] 相邻/对侧视角重投影相对深度误差 中位 = %.6f  (样本 %s)"
      % (med, [e[1] for e in errs]), flush=True)
assert med < 0.01, ("🔴 重投影误差 %.4f 远大于 0 ⇒ 内外参或深度约定有翻转,整批数据会废。"
                    "阳性含义:约定全对时该值应≈0(遮挡边缘贡献少量残差)" % med)

# ---------------- 阶段1产物:深度 npy + 内外参,交给阶段2 ----------------
np.save(f"{OUT_ROOT}/{SCAN}/_depths.npy", np.stack(Ds).astype(np.float32))
json.dump({"K": [k.tolist() for k in Ks], "E": [e.tolist() for e in Es], "W": W, "H": H, "NV": NV},
          open(f"{OUT_ROOT}/{SCAN}/_meta.json", "w"))
print("[STAGE1-DONE]", SCAN, "reproj=%.6f" % med, flush=True)
