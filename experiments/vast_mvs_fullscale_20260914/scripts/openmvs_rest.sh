#!/usr/bin/env bash
# OpenMVS half of the community pipeline, default parameters, nothing tuned.
set -uo pipefail
W=/root/community; B=/usr/local/bin/OpenMVS
cd $W
echo "[$(date +%H:%M:%S)] DensifyPointCloud"
$B/DensifyPointCloud $W/scene.mvs -w $W > $W/6_densify.log 2>&1; echo "  rc=$?"
tr '\r' '\n' < $W/6_densify.log | grep -iE "point-cloud composed|points$" | tail -2 | cut -c1-120
[ -f $W/scene_dense.mvs ] || { echo DENSIFY_FAILED; tr '\r' '\n' < $W/6_densify.log | tail -3 | cut -c1-160; exit 1; }
echo "[$(date +%H:%M:%S)] ReconstructMesh"
$B/ReconstructMesh $W/scene_dense.mvs -w $W > $W/7_mesh.log 2>&1; echo "  rc=$?"
[ -f $W/scene_dense_mesh.mvs ] || { echo MESH_FAILED; tail -3 $W/7_mesh.log | cut -c1-160; exit 1; }
echo "[$(date +%H:%M:%S)] RefineMesh"
$B/RefineMesh $W/scene_dense_mesh.mvs -w $W > $W/8_refine.log 2>&1; echo "  rc=$?"
IN=$W/scene_dense_mesh_refine.mvs; [ -f $IN ] || IN=$W/scene_dense_mesh.mvs
echo "[$(date +%H:%M:%S)] TextureMesh on $(basename $IN)"
$B/TextureMesh $IN -w $W > $W/9_tex.log 2>&1; echo "  rc=$?"
ls -la $W/*.ply $W/*.png 2>/dev/null | awk '{printf "  %.1f MB %s\n", $5/1048576, $9}'
echo "[$(date +%H:%M:%S)] OPENMVS_DONE"
