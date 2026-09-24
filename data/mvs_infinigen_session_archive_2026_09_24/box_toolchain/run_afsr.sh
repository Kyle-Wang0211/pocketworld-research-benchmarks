#!/bin/bash
# 三档只差 visibility_filtering 的设置,其余参数一字不动(全默认)
WS=$1; TAG=$2
CB=/root/colmap-4.1.0-fa8e3b3/build/src/colmap/exe/colmap
mkdir -p /root/afsr/out
run () {
  NAME=$1; shift
  echo "=== $TAG/$NAME : $@ ==="
  /usr/bin/time -v $CB advancing_front_mesher \
    --input_path $WS --output_path /root/afsr/out/${TAG}_${NAME}.ply \
    --AdvancingFrontMeshing.num_threads 32 "$@" \
    > /root/afsr/out/${TAG}_${NAME}.log 2>&1
  echo "exit=$?"
  grep -E "Maximum resident|Elapsed \(wall" /root/afsr/out/${TAG}_${NAME}.log
  grep -E "Built |Removed |Mesh has |Visibility counter|Elapsed time" /root/afsr/out/${TAG}_${NAME}.log | tail -8
}
run off  --AdvancingFrontMeshing.visibility_filtering 0
run post --AdvancingFrontMeshing.visibility_filtering 1 --AdvancingFrontMeshing.visibility_post_filtering 1
run pre  --AdvancingFrontMeshing.visibility_filtering 1 --AdvancingFrontMeshing.visibility_post_filtering 0
echo ALL_DONE
