import blenderproc as bproc
"""GSO -> 多视图 RGB + 深度 + 位姿,用 BlenderProc 官方 API。
内外参一律从 bproc 取(get_intrinsics_as_K_matrix / get_camera_pose),不自己推导。
用法: blenderproc run gso_render_bp.py -- <obj> <out_dir> <views> <res_w> <res_h>
"""
import sys, os, json, math
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[-5:]
OBJ, OUT = argv[0], argv[1]
NV = int(argv[2]); W = int(argv[3]); H = int(argv[4])

bproc.init()
objs = bproc.loader.load_obj(OBJ)
assert objs, "load_obj 返回空"

# 包围球:用官方 get_bound_box
pts = np.concatenate([np.array(o.get_bound_box()) for o in objs], 0)
ctr = pts.mean(0)
rad = float(np.linalg.norm(pts - ctr, axis=1).max())
dist = rad * 2.6

light = bproc.types.Light()
light.set_type("SUN"); light.set_energy(4.0)
light.set_location([ctr[0] + dist, ctr[1] + dist, ctr[2] + dist * 1.5])

bproc.camera.set_resolution(W, H)
for i in range(NV):
    th = 2 * math.pi * i / NV
    ph = math.radians(15 + 45 * ((i * 7) % 5) / 4.0)      # 高低角交错,增大基线多样性
    loc = np.array([ctr[0] + dist * math.cos(th) * math.cos(ph),
                    ctr[1] + dist * math.sin(th) * math.cos(ph),
                    ctr[2] + dist * math.sin(ph)])
    rot = bproc.camera.rotation_from_forward_vec(ctr - loc)
    bproc.camera.add_camera_pose(bproc.math.build_transformation_mat(loc, rot))

bproc.renderer.set_render_devices(use_only_cpu=False, desired_gpu_device_type=["OPTIX", "CUDA"])
bproc.renderer.enable_depth_output(activate_antialiasing=False)
bproc.renderer.set_max_amount_of_samples(128)
data = bproc.renderer.render()

os.makedirs(f"{OUT}/images", exist_ok=True)
os.makedirs(f"{OUT}/depths", exist_ok=True)
from PIL import Image
K = bproc.camera.get_intrinsics_as_K_matrix()
meta = {"K": np.array(K).tolist(), "W": W, "H": H, "frames": []}
for i in range(NV):
    Image.fromarray(data["colors"][i][..., :3].astype(np.uint8)).save(f"{OUT}/images/{i:08d}.jpg", quality=95)
    d = np.asarray(data["depth"][i], dtype=np.float32)
    np.save(f"{OUT}/depths/{i:08d}.npy", d)
    c2w = np.array(bproc.camera.get_camera_pose(i))
    meta["frames"].append({"idx": i, "cam2world": c2w.tolist()})
json.dump(meta, open(f"{OUT}/meta.json", "w"))
fin = np.concatenate([np.asarray(x).ravel() for x in data["depth"]])
fin = fin[np.isfinite(fin)]
print("[GSO-RENDER] %d 视角 %dx%d | K fx=%.2f cx=%.2f | 深度 min/中位/max = %.4f/%.4f/%.4f | 非有限占比 %.4f"
      % (NV, W, H, K[0][0], K[0][2], fin.min(), np.median(fin), fin.max(),
         1.0 - fin.size / sum(np.asarray(x).size for x in data["depth"])), flush=True)
