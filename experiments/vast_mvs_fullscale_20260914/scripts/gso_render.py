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
W, H = 768, 576

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
ctr = pts.mean(0); rad = float(np.linalg.norm(pts - ctr, axis=1).max()); dist = rad * 2.6

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = SAMPLES
sc.render.resolution_x = W; sc.render.resolution_y = H
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
sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.35, 0.38, 1)
print("[SETUP] done", flush=True)

# ---------------- 渲染 + 取内外参 ----------------
import OpenEXR, Imath
os.makedirs(f"{OUT_ROOT}/{SCAN}/blended_images", exist_ok=True)
os.makedirs(f"{OUT_ROOT}/{SCAN}/cams", exist_ok=True)
os.makedirs(f"{OUT_ROOT}/{SCAN}/rendered_depth_maps", exist_ok=True)
TMP = f"/dev/shm/gso_{SCAN}"; os.makedirs(TMP, exist_ok=True)

def K_from_cam():
    # Blender 透视相机 -> OpenCV K。判据:水平视场角
    f_mm = cam_d.lens; sw = cam_d.sensor_width
    fx = W * f_mm / sw; fy = fx            # 方形像素
    return np.array([[fx, 0, W / 2.0], [0, fy, H / 2.0], [0, 0, 1]], dtype=np.float64)

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
    z = np.frombuffer(f.channel(zname, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(H, W).copy()
    cnames = list(ch)
    rgbn = [[c for c in cnames if c.endswith("Combined." + k)][0] for k in ("R", "G", "B")]
    rgb = np.stack([np.frombuffer(f.channel(c, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(H, W)
                    for c in rgbn], -1)
    img = (np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    from PIL import Image as PILImage
    PILImage.fromarray(img).save(f"{OUT_ROOT}/{SCAN}/blended_images/{i:08d}.jpg", quality=95)

    Rw = np.array(cam.matrix_world.to_3x3())          # cam->world (Blender)
    Rcv = Rw @ BL2CV                                   # cam->world (OpenCV)
    t = np.array(cam.matrix_world.translation)
    E = np.eye(4); E[:3, :3] = Rcv.T; E[:3, 3] = -Rcv.T @ t   # world->cam
    K = K_from_cam()
    Ks.append(K); Es.append(E); Ds.append(z)

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

# ---------------- 写 MVSNet 格式 ----------------
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import save_pfm
for i in range(NV):
    z = Ds[i].copy()
    z[~np.isfinite(z)] = 0.0
    z[z > 1e4] = 0.0                       # Blender 背景是极大值
    save_pfm(f"{OUT_ROOT}/{SCAN}/rendered_depth_maps/{i:08d}.pfm", z.astype(np.float32))
    v = z[z > 0]
    dmin, dmax = float(v.min()), float(v.max())
    with open(f"{OUT_ROOT}/{SCAN}/cams/{i:08d}_cam.txt", "w") as f:
        f.write("extrinsic\n")
        for r in Es[i]: f.write(" ".join("%.9f" % x for x in r) + "\n")
        f.write("\nintrinsic\n")
        for r in Ks[i]: f.write(" ".join("%.9f" % x for x in r) + "\n")
        f.write("\n%f %f\n" % (dmin, dmax))
print("[WRITE] cams/depth 完成", flush=True)

# ---------------- pair.txt:复用已验证的官方共视分数实现 ----------------
import importlib.util
spec = importlib.util.spec_from_file_location("tg", "/root/tartanground2mvsnet.py")
tg = importlib.util.module_from_spec(spec)
os.environ["DIFFMVS_DIR"] = "/root/diffmvs"
import types
_argv = sys.argv; sys.argv = ["tg"]
try: spec.loader.exec_module(tg)
except SystemExit: pass
sys.argv = _argv
print("[SCORE] 复用 tartanground2mvsnet 的官方共视分数实现:",
      [n for n in ("calc_score_from_points", "check_geometric_consistency", "cam_center_from_E") if hasattr(tg, n)], flush=True)

centers = [tg.cam_center_from_E(E) for E in Es]
scores = np.zeros((NV, NV))
for i in range(NV):
    zi = Ds[i]; m = np.isfinite(zi) & (zi > 0) & (zi < 1e4)
    ys, xs = np.nonzero(m)
    if len(xs) < 200: continue
    sel = np.random.default_rng(i).choice(len(xs), size=min(4000, len(xs)), replace=False)
    xs, ys = xs[sel], ys[sel]; d = zi[ys, xs]
    pc = np.linalg.inv(Ks[i]) @ (np.stack([xs, ys, np.ones_like(xs)]) * d)
    pw = (np.linalg.inv(Es[i]) @ np.vstack([pc, np.ones(pc.shape[1])]))[:3].T
    for j in range(NV):
        if i == j: continue
        scores[i, j] = tg.calc_score_from_points(centers[i], centers[j], pw)
with open(f"{OUT_ROOT}/{SCAN}/cams/pair.txt", "w") as f:
    f.write("%d\n" % NV)
    for i in range(NV):
        order = np.argsort(-scores[i]); order = [j for j in order if j != i][:10]
        f.write("%d\n%d " % (i, len(order)))
        f.write(" ".join("%d %.6f" % (j, scores[i, j]) for j in order) + "\n")
nz = int((scores > 0).sum())
print("[PAIR] 写出 pair.txt;共视矩阵非零 %d/%d" % (nz, NV * NV - NV), flush=True)
print("[DONE]", SCAN, flush=True)
