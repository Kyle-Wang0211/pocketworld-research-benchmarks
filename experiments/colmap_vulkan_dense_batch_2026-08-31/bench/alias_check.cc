// 验证 alias 去重后的真实内存:按 (image, alias_group) 去重再加总,
// 这与 resource_arena.cc 的 AddPlan 行为一致。
#include "vulkan_resource_arena/resource_arena_plan.h"
#include <cstdio>
#include <map>
#include <set>
using namespace pocketworld::official_dense::vulkan::resource_arena;
using pocketworld::official_dense::vulkan::PlanPhase;
using pocketworld::official_dense::vulkan::kBindingCount;

int main(){
  ResourceArenaInput in{};
  in.width=2000; in.height=1500; in.source_width=2000; in.source_height=1500;
  in.num_sources=10; in.workspace_max_dim=2000;
  in.phase=PlanPhase::kPhotometricOnly;
  ResourceArenaPlan plan;
  if(!BuildResourceArenaPlan(in,&plan)){ std::printf("失败\n"); return 1; }

  std::map<std::uint64_t,std::uint64_t> uniq;   // alias_group -> bytes
  std::uint64_t naive=0;
  auto add=[&](const AllocationPlan& a){
    if(!a.present()) return;
    naive += a.exact_bytes;
    uniq[a.alias_group] = a.exact_bytes;
  };
  for (const ModePlan& mp : plan.modes) {
    for (const RotationPlan& rp : mp.rotations)
      for (std::size_t b=0;b<kBindingCount;++b){
        add(rp.bindings[b].buffer); add(rp.bindings[b].sampled_image);
      }
    add(mp.reference_upload_staging); add(mp.reference_depth_upload_staging);
    add(mp.reference_normal_upload_staging); add(mp.source_depth_upload_staging);
    add(mp.source_gray_buffer_upload_staging); add(mp.source_gray_image_upload_staging);
    add(mp.depth_readback); add(mp.normal_readback); add(mp.mask_readback);
  }
  std::uint64_t dedup=0; for(auto&[g,b]:uniq) dedup+=b;
  std::printf("朴素加总(不去重) : %.3f GB\n", naive/1e9);
  std::printf("按 alias 去重后   : %.3f GB   (%zu 个唯一 group)\n", dedup/1e9, uniq.size());
  ResourceArenaMemorySummary s;
  SummarizeResourceArenaMemory(plan,&s);
  std::printf("Summarize 报告    : %.3f GB\n", s.total_bytes/1e9);
  return 0;
}
