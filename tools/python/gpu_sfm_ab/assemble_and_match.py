"""Reproducible: frames list -> GPU batch extract -> db_gpu + db_cpu2 -> match
same 6159 pairs with the identical matcher. Run before fast_tri_9gate.py."""
import sqlite3, shutil, struct, subprocess, time
from pathlib import Path
import numpy as np
import pycolmap

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks")
WD = BR / "tools/python/gpu_sfm_ab"
IMG = BR / "data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict/photos_highres"
SRC_DB = BR / "tools/python/sfm_cmp/sfm_v7/db.db"
BATCH_EXE = BR.parent / "aether_cpp/third_party/glomap_vendor/build-verify/gpu_extract_batch_exe"
(WD / "feat").mkdir(parents=True, exist_ok=True)

# 1) frames.txt (name<TAB>abs_jpeg) from the db image set
c = sqlite3.connect(str(SRC_DB))
names = [r[0] for r in c.execute("select name from images order by image_id")]
(WD / "frames.txt").write_text("".join(f"{n}\t{IMG/n}\n" for n in names))
print(f"frames.txt: {len(names)} images")

# 2) GPU batch extract (persistent-harness exe) -> <name>.feat
print("GPU batch extract...", flush=True)
subprocess.run([str(BATCH_EXE), str(WD / "frames.txt"), str(WD / "feat"), "8192"], check=True)

# 3) db_gpu (GPU features, matches cleared) + db_cpu2 (CPU features, matches cleared)
gpudb, cpudb = WD / "db_gpu.db", WD / "db_cpu2.db"
shutil.copy(SRC_DB, gpudb); shutil.copy(SRC_DB, cpudb)
g = sqlite3.connect(str(gpudb))
for t in ("keypoints", "descriptors", "matches", "two_view_geometries"):
    g.execute(f"delete from {t}")
id2name = {i: n for i, n in g.execute("select image_id,name from images")}
for iid, nm in sorted(id2name.items()):
    with open(WD / "feat" / f"{nm}.feat", "rb") as f:
        n = struct.unpack("<i", f.read(4))[0]
        xy = np.frombuffer(f.read(8 * n), np.float32).reshape(n, 2)
        desc = np.frombuffer(f.read(128 * n), np.uint8).reshape(n, 128)
    kp = np.zeros((n, 6), np.float32); kp[:, 0] = xy[:, 0]; kp[:, 1] = xy[:, 1]; kp[:, 2] = 1; kp[:, 5] = 1
    g.execute("insert into keypoints(image_id,rows,cols,data) values(?,?,?,?)", (iid, n, 6, kp.tobytes()))
    g.execute("insert into descriptors(image_id,rows,cols,data) values(?,?,?,?)", (iid, n, 128, desc.tobytes()))
g.commit()
cc = sqlite3.connect(str(cpudb))
for t in ("matches", "two_view_geometries"):
    cc.execute(f"delete from {t}")
cc.commit()

# 4) pairs.txt = original 6159 pairs; match both dbs identically
id2name_s = {i: n for i, n in sqlite3.connect(str(SRC_DB)).execute("select image_id,name from images")}
pairs = []
for (pid,) in sqlite3.connect(str(SRC_DB)).execute("select pair_id from matches"):
    i2 = pid % 2147483647; i1 = (pid - i2) // 2147483647
    pairs.append((id2name_s[i1], id2name_s[i2]))
(WD / "pairs.txt").write_text("".join(f"{a} {b}\n" for a, b in pairs))


def match(db):
    mo = pycolmap.FeatureMatchingOptions(); mo.use_gpu = False
    mo.sift.cross_check = True; mo.sift.max_ratio = 0.8; mo.sift.max_distance = 0.7
    po = pycolmap.ImportedPairingOptions(); po.match_list_path = str(WD / "pairs.txt")
    t0 = time.time()
    pycolmap.match_image_pairs(str(db), matching_options=mo, pairing_options=po,
                               device=pycolmap.Device.cpu)
    cn = sqlite3.connect(str(db))
    inl = sum(r for (r,) in cn.execute("select rows from two_view_geometries"))
    print(f"  {db.name}: {inl} inliers in {time.time()-t0:.1f}s", flush=True)


for db in (gpudb, cpudb):
    match(db)
print("done — now run fast_tri_9gate.py")
