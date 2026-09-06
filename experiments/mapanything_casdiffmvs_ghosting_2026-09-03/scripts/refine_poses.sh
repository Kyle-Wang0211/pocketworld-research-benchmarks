#!/usr/bin/env bash
# Pose + intrinsics refinement with official COLMAP 4.1.1, global settings only.
#   1. fresh database: DSP-SIFT at the project's standard 16384 budget on the 4032x3024 originals
#   2. exhaustive matching (132 images -> 8,646 pairs): the production model's tracks are 3 views long
#      at the median; exhaustive matching is what lengthens them
#   3. re-triangulate on the PRODUCTION poses (frame unchanged), then bundle-adjust poses + PINHOLE
#      intrinsics jointly
#   4. report reprojection error, track length, observations per image before/after
set -euo pipefail
COLMAP=/root/colmap-4.1.1-src/build/src/colmap/exe/colmap
W=/root/pose_refine_20260907; IMG=/root/mapanything_apache_production_sparse_colmap_20260903/input/images
PROD=/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse
mkdir -p $W/tri $W/ba; cd $W
$COLMAP -h 2>&1 | head -1
# production median intrinsics as the single shared camera's initialisation
INIT=$(/venv/main/bin/python - <<PY
import sys; sys.path.insert(0,"/root")
from mapanything.utils.colmap import read_model; import numpy as np
cams,_,_=read_model("$PROD",ext=".bin"); P=np.array([c.params for c in cams.values()])
print(",".join(f"{v:.4f}" for v in np.median(P,0)))
PY
)
echo "init camera params (fx,fy,cx,cy): $INIT"
/usr/bin/time -f "feature_extractor %E" $COLMAP feature_extractor --database_path $W/database.db --image_path $IMG \
  --ImageReader.camera_model PINHOLE --ImageReader.single_camera 1 --ImageReader.camera_params "$INIT" \
  --SiftExtraction.max_num_features 16384 --SiftExtraction.domain_size_pooling 1 --FeatureExtraction.use_gpu 1
/usr/bin/time -f "exhaustive_matcher %E" $COLMAP exhaustive_matcher --database_path $W/database.db --FeatureMatching.use_gpu 1 --FeatureMatching.guided_matching 1
# the input model must reference the database's image ids/names and the shared camera: rebuild it
/venv/main/bin/python - <<PY
import sys, sqlite3, numpy as np; sys.path.insert(0,"/root")
from mapanything.utils.colmap import read_model
import pycolmap
prod = pycolmap.Reconstruction("$PROD")
db = sqlite3.connect("$W/database.db"); rows = db.execute("SELECT image_id, name, camera_id FROM images").fetchall()
name2id = {n: (i, c) for i, n, c in rows}
cam_id = rows[0][2]
rec = pycolmap.Reconstruction()
cam = pycolmap.Camera(model="PINHOLE", width=4032, height=3024, params=[float(x) for x in "$INIT".split(",")], camera_id=cam_id)
rec.add_camera(cam)
for im in prod.images.values():
    iid, cid = name2id[im.name]
    new = pycolmap.Image(name=im.name, camera_id=cam_id, image_id=iid)
    new.cam_from_world = im.cam_from_world
    rec.add_image(new); rec.register_image(iid)
import os; os.makedirs("$W/init", exist_ok=True); rec.write("$W/init")
print("init model: images", rec.num_images(), "camera", cam_id)
PY
/usr/bin/time -f "point_triangulator %E" $COLMAP point_triangulator --database_path $W/database.db --image_path $IMG --input_path $W/init --output_path $W/tri
/usr/bin/time -f "bundle_adjuster %E" $COLMAP bundle_adjuster --input_path $W/tri --output_path $W/ba \
  --BundleAdjustment.refine_focal_length 1 --BundleAdjustment.refine_principal_point 1 --BundleAdjustment.refine_rig_from_world 1 --BundleAdjustment.refine_sensor_from_rig 1 --BundleAdjustmentCeres.max_num_iterations 100
/venv/main/bin/python - <<PY
import sys; sys.path.insert(0,"/root")
from mapanything.utils.colmap import read_model; import numpy as np, json
out={}
for tag,D in [("production","$PROD"),("triangulated","$W/tri"),("refined_BA","$W/ba")]:
    cams,imgs,p3d=read_model(D,ext=".bin")
    err=np.array([p.error for p in p3d.values()]); trk=np.array([len(p.image_ids) for p in p3d.values()])
    nobs=[int((im.point3D_ids>=0).sum()) for im in imgs.values()]; cam=list(cams.values())[0]
    out[tag]={"points":len(p3d),"reproj_p50":float(np.median(err)),"reproj_p90":float(np.percentile(err,90)),"track_p50":float(np.median(trk)),"track_mean":float(trk.mean()),"obs_per_image_p50":float(np.median(nobs)),"fx":float(cam.params[0]),"fy":float(cam.params[1]),"cx":float(cam.params[2]),"cy":float(cam.params[3]),"n_cams":len(cams)}
    o=out[tag]; print(f"{tag:13s} pts {o['points']:>9,}  reproj p50 {o['reproj_p50']:.3f} p90 {o['reproj_p90']:.3f}  track p50 {o['track_p50']:.0f} mean {o['track_mean']:.1f}  obs/img {o['obs_per_image_p50']:.0f}  fx {o['fx']:.1f} cx {o['cx']:.1f} cy {o['cy']:.1f}")
json.dump(out,open("$W/stats.json","w"),indent=2)
PY
echo REFINE_DONE
