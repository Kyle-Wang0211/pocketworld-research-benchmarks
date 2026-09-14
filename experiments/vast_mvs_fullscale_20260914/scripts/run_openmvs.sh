#!/usr/bin/env bash
# The community-standard small-team pipeline, copied whole with DEFAULT parameters, nothing tuned:
#   COLMAP sparse -> InterfaceCOLMAP -> DensifyPointCloud -> ReconstructMesh -> RefineMesh -> TextureMesh
# (OpenMVS is AGPL: research baseline only, cannot ship.)
set -uo pipefail
W=/root/mvs_scene; cd $W
B=/usr/local/bin/OpenMVS
echo "[$(date +%H:%M:%S)] InterfaceCOLMAP"
$B/InterfaceCOLMAP -i $W -o $W/scene.mvs --image-folder $W/images > $W/1_interface.log 2>&1; echo "  rc=$?"
ls -la $W/scene.mvs 2>/dev/null | awk {printf   scene.mvs %.1f MB\n, /1048576}
echo "[$(date +%H:%M:%S)] DensifyPointCloud (defaults)"
$B/DensifyPointCloud $W/scene.mvs -w $W > $W/2_densify.log 2>&1; echo "  rc=$?"
grep -iE "point-cloud|points" $W/2_densify.log | tail -2 | cut -c1-120
echo "[$(date +%H:%M:%S)] ReconstructMesh (defaults)"
$B/ReconstructMesh $W/scene_dense.mvs -w $W > $W/3_mesh.log 2>&1; echo "  rc=$?"
echo "[$(date +%H:%M:%S)] RefineMesh (defaults)"
$B/RefineMesh $W/scene_dense_mesh.mvs -w $W > $W/4_refine.log 2>&1; echo "  rc=$?"
echo "[$(date +%H:%M:%S)] TextureMesh (defaults)"
$B/TextureMesh $W/scene_dense_mesh_refine.mvs -w $W > $W/5_texture.log 2>&1; echo "  rc=$?"
ls -la $W/*.ply $W/*.png 2>/dev/null | awk {printf   %.1f MB %s\n, /1048576, } | tail -6
echo "[$(date +%H:%M:%S)] OPENMVS_DONE"
