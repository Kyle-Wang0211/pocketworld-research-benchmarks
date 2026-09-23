#!/bin/bash
R=$HOME/Developer/viobench-recordings; P=$R/_paper_cmp; GT=$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum
run(){ # name slam dev seq
  [ -f "$P/$1.tum" ] || /tmp/pw_euroc_new "$2" "$3" "euroc://$4" "$P/$1.tum" >/dev/null 2>&1
  /usr/bin/python3 $R/ate.py "$P/$1.tum" $GT --ref-y-up 2>/dev/null | /usr/bin/python3 -c "
import sys,re; s=sys.stdin.read(); g=re.search(r'配对\s+(\d+).*?Sim3 ATE\s+([\d.]+)\s*cm.*?尺度偏差\s+([\d.]+)%.*?SE3 ATE\s+([\d.]+)\s*cm',s,re.S)
print('%-28s 配对 %4s  尺度 %6s%%  Sim3 %6scm  SE3 %6scm'%('$1',g.group(1),g.group(3),g.group(2),g.group(4)) if g else '$1 评分失败')"
}
echo "── 1920×1440 臂(td=+8)  $(date +%H:%M:%S)"
cp $R/_sweep_phone/p_td+8_ba0.tum $P/A_bench1920.tum 2>/dev/null
run A_bench1920           $R/_sweep/slam_bench.yaml        $P/dev_1920_td8.yaml         $R/_euroc_6e2d4b99
run B_parallax30          $P/slam_parallax30.yaml          $P/dev_1920_td8.yaml         $R/_euroc_6e2d4b99
run C_noise9              $R/_sweep/slam_bench.yaml        $P/dev_1920_td8_noise9.yaml  $R/_euroc_6e2d4b99
run D_parallax30_noise9   $P/slam_parallax30.yaml          $P/dev_1920_td8_noise9.yaml  $R/_euroc_6e2d4b99
echo "── 640×480 论文档臂(上游 slam+device 逐字,td=+8)"
for i in $(seq 1 120); do grep -q "✅" /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad/conv640.log 2>/dev/null && break; sleep 5; done
run E_paper640            $P/slam_paper.yaml               $P/dev_paper640_td8.yaml     $R/_euroc_6e2d4b99_640
echo "── 完成 $(date +%H:%M:%S)"
