#!/bin/bash
cd /root/tsdf_improve/diag
P=/root/venv_o3d_fix/bin/python
echo "[start] $(date)"
for B in floorbox suitcase; do
  for V in 0.012 0.006 0.003 0.0015; do
    a=$(free -g | awk '/Mem:/{print $7}'); while [ "$a" -lt 25 ]; do echo "wait mem $a"; sleep 30; a=$(free -g | awk '/Mem:/{print $7}'); done
    OMP_NUM_THREADS=12 /usr/bin/time -f "$B $V oddshift peak %M KB %e s" $P detail_tsdf.py $B $V 0.04 oddshift
  done
  for SG in 1 0; do
  SINGLE=$SG TAGM=shift_single$SG OMP_NUM_THREADS=12 /usr/bin/time -f "metric $B single=$SG peak %M KB %e s" $P detail_metric.py $B det_${B}_v0.003_t0.04_all_raw.ply \
     "v0.012=det_${B}_v0.012_t0.04_even_raw.ply,det_${B}_v0.012_t0.04_oddshift_raw.ply" \
     "v0.012_noshift=det_${B}_v0.012_t0.04_even_raw.ply,det_${B}_v0.012_t0.04_odd_raw.ply" \
     "v0.006=det_${B}_v0.006_t0.04_even_raw.ply,det_${B}_v0.006_t0.04_oddshift_raw.ply" \
     "v0.003=det_${B}_v0.003_t0.04_even_raw.ply,det_${B}_v0.003_t0.04_oddshift_raw.ply" \
     "v0.0015=det_${B}_v0.0015_t0.04_even_raw.ply,det_${B}_v0.0015_t0.04_oddshift_raw.ply" \
     "v0.003_taubin10=det_${B}_v0.003_t0.04_even_post.ply,det_${B}_v0.003_t0.04_oddshift_post.ply"
  done
done
echo "[done] $(date)"
