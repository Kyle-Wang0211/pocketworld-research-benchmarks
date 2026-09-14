"""GSO 渲染成本探测(仅测量,非生产管线)。
测:加载 OBJ + 环绕 N 个视角 + RGB&深度(Z pass) 的耗时,以及采样数的线性关系。
输出多层 EXR(含 Z),相机内外参直接从 bpy 取。
"""
import bpy, os, sys, time, math, json
import mathutils

OBJ = sys.argv[sys.argv.index("--obj") + 1]
OUT = sys.argv[sys.argv.index("--out") + 1]
NV = int(sys.argv[sys.argv.index("--views") + 1])
SAMPLES = int(sys.argv[sys.argv.index("--samples") + 1])
RES = int(sys.argv[sys.argv.index("--res") + 1]) if "--res" in sys.argv else 768

t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=OBJ)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert objs, "no mesh"
t_load = time.time() - t0

# 包围盒 → 相机距离
import numpy as np
pts = []
for o in objs:
    for v in o.bound_box: pts.append(o.matrix_world @ mathutils.Vector(v))
P = np.array([[p.x, p.y, p.z] for p in pts])
ctr = P.mean(0); rad = float(np.linalg.norm(P - ctr, axis=1).max())
dist = rad * 2.8

sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = SAMPLES
sc.render.resolution_x = RES; sc.render.resolution_y = RES * 3 // 4
sc.render.image_settings.file_format = "OPEN_EXR_MULTILAYER"
sc.view_layers[0].use_pass_z = True
prefs = bpy.context.preferences.addons["cycles"].preferences
for dt in prefs.get_device_types(bpy.context): prefs.get_devices_for_type(dt[0])
types = [d.type for d in prefs.devices]
if "OPTIX" in types:
    prefs.compute_device_type = "OPTIX"; sc.cycles.device = "GPU"
    for d in prefs.devices: d.use = (d.type == "OPTIX")
print("[DEV] types=", types, "cycles.device=", sc.cycles.device, flush=True)

light = bpy.data.objects.new("L", bpy.data.lights.new("L", type="SUN"))
light.data.energy = 5.0; sc.collection.objects.link(light)
cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam); sc.camera = cam

os.makedirs(OUT, exist_ok=True)
meta = {}
t1 = time.time()
for i in range(NV):
    th = 2 * math.pi * i / NV; ph = math.radians(20 + 40 * (i % 3) / 2)
    loc = mathutils.Vector((ctr[0] + dist*math.cos(th)*math.cos(ph),
                            ctr[1] + dist*math.sin(th)*math.cos(ph),
                            ctr[2] + dist*math.sin(ph)))
    cam.location = loc
    cam.rotation_euler = (loc - mathutils.Vector(ctr)).to_track_quat("Z", "Y").to_euler()
    bpy.context.view_layer.update()
    sc.render.filepath = os.path.join(OUT, "view_%03d" % i)
    bpy.ops.render.render(write_still=True)
    meta["view_%03d" % i] = {"loc": list(loc), "rot": list(cam.rotation_euler)}
t_render = time.time() - t1
json.dump(meta, open(os.path.join(OUT, "cams.json"), "w"))
print("[TIME] 加载 %.2fs | 渲染 %d 视角 %.2fs | 每视角 %.3fs | samples=%d res=%dx%d"
      % (t_load, NV, t_render, t_render / NV, SAMPLES, sc.render.resolution_x, sc.render.resolution_y), flush=True)
