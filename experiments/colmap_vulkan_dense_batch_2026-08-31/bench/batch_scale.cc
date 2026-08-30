#include "vulkan_resource_arena/resource_arena_plan.h"
#include <cstdio>
using namespace pocketworld::official_dense::vulkan::resource_arena;
using pocketworld::official_dense::vulkan::PlanPhase;
int main(){
  std::printf("  N   device_local   总计      每 ref     层数上界\n");
  double base=0;
  for (std::uint64_t n : {1U,2U,4U,6U,8U}) {
    ResourceArenaInput in{};
    in.width=2000; in.height=1500; in.source_width=2000; in.source_height=1500;
    in.num_sources=10; in.workspace_max_dim=2000;
    in.phase=PlanPhase::kPhotometricOnly; in.batch_count=n;
    ResourceArenaPlan plan; ResourceArenaMemorySummary s;
    if(!BuildResourceArenaPlan(in,&plan)||!SummarizeResourceArenaMemory(plan,&s)){
      std::printf("  %2llu  构建失败\n",(unsigned long long)n); continue; }
    const double tot=s.total_bytes/1e9;
    if(n==1) base=tot;
    std::printf("  %2llu   %7.2f GB   %6.2f GB  %5.2f GB   %llu  %s\n",
      (unsigned long long)n, s.device_local_bytes/1e9, tot, tot/n,
      (unsigned long long)(in.num_sources*n),
      tot<=14.0?"✅ 装得下":"❌ 超 14GB 预算");
  }
  std::printf("\n  线性度检查(每 ref 应恒等于 N=1 的 %.3f GB)\n", base);
  return 0;
}
