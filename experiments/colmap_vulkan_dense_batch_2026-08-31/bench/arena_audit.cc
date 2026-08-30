#include "vulkan_resource_arena/resource_arena_plan.h"
#include <cstdio>
#include <map>
using namespace pocketworld::official_dense::vulkan::resource_arena;
using pocketworld::official_dense::vulkan::PlanPhase;

int main(){
  ResourceArenaInput in{};
  in.width=2000; in.height=1500; in.source_width=2000; in.source_height=1500;
  in.num_sources=10; in.workspace_max_dim=2000;
  in.phase=PlanPhase::kPhotometricOnly;
  ResourceArenaPlan plan;
  if(!BuildResourceArenaPlan(in,&plan)){ std::printf("失败\n"); return 1; }

  std::printf("photometric 阶段的逐笔分配 (2000x1500, 10 src)\n\n");
  // 只看 photometric mode(索引 0)
  for (std::size_t m=0; m<kModeCount; ++m) {
    const ModePlan& mp = plan.modes[m];
    std::uint64_t modeTotal=0;
    std::printf("--- mode %zu ---\n", m);
    for (std::size_t r=0; r<kRotationCount; ++r) {
      const RotationPlan& rp = mp.rotations[r];
      std::uint64_t rotTotal=0; int cnt=0;
      for (std::size_t b=0; b<pocketworld::official_dense::vulkan::kBindingCount; ++b) {
        const BindingPlan& bp = rp.bindings[b];
        for (const AllocationPlan* a : {&bp.buffer, &bp.sampled_image}) {
          if (a->present()) { rotTotal += a->exact_bytes; ++cnt; }
        }
      }
      if (rotTotal) {
        std::printf("  rotation[%zu]  %8.3f GB  (%d 笔)  %llux%llu\n",
          r, rotTotal/1e9, cnt,
          (unsigned long long)rp.width, (unsigned long long)rp.height);
      }
      modeTotal += rotTotal;
    }
    if (modeTotal) std::printf("  mode 小计 %.3f GB\n\n", modeTotal/1e9);
  }
  return 0;
}
