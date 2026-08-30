#include "vulkan_resource_arena/resource_arena_plan.h"
#include <cstdio>
#include <map>
#include <string>
using namespace pocketworld::official_dense::vulkan::resource_arena;
using pocketworld::official_dense::vulkan::PlanPhase;
using pocketworld::official_dense::vulkan::kBindingCount;
int main(){
  ResourceArenaInput in{};
  in.width=2000; in.height=1500; in.source_width=2000; in.source_height=1500;
  in.num_sources=10; in.workspace_max_dim=2000;
  in.phase=PlanPhase::kPhotometricOnly;
  ResourceArenaPlan plan;
  if(!BuildResourceArenaPlan(in,&plan)) return 1;
  std::map<std::uint64_t,std::pair<std::uint64_t,std::string>> uniq;
  auto add=[&](const AllocationPlan&a,const std::string& tag){
    if(!a.present())return;
    auto it=uniq.find(a.alias_group);
    if(it==uniq.end()) uniq[a.alias_group]={a.exact_bytes,tag};
  };
  for(std::size_t m=0;m<plan.modes.size();++m){
    const ModePlan& mp=plan.modes[m];
    for(std::size_t r=0;r<mp.rotations.size();++r)
      for(std::size_t b=0;b<kBindingCount;++b){
        add(mp.rotations[r].bindings[b].buffer,"m"+std::to_string(m)+" rot"+std::to_string(r)+" buf["+std::to_string(b)+"]");
        add(mp.rotations[r].bindings[b].sampled_image,"m"+std::to_string(m)+" rot"+std::to_string(r)+" img["+std::to_string(b)+"]");
      }
    add(mp.reference_upload_staging,"m"+std::to_string(m)+" ref_stage");
    add(mp.reference_depth_upload_staging,"m"+std::to_string(m)+" refdepth_stage");
    add(mp.reference_normal_upload_staging,"m"+std::to_string(m)+" refnorm_stage");
    add(mp.source_depth_upload_staging,"m"+std::to_string(m)+" srcdepth_stage");
    add(mp.source_gray_buffer_upload_staging,"m"+std::to_string(m)+" srcgraybuf_stage");
    add(mp.source_gray_image_upload_staging,"m"+std::to_string(m)+" srcgrayimg_stage");
    add(mp.depth_readback,"m"+std::to_string(m)+" depth_rb");
    add(mp.normal_readback,"m"+std::to_string(m)+" normal_rb");
    add(mp.mask_readback,"m"+std::to_string(m)+" mask_rb");
  }
  std::multimap<std::uint64_t,std::string,std::greater<>> by;
  std::uint64_t tot=0;
  for(auto&[g,v]:uniq){ by.emplace(v.first,v.second); tot+=v.first; }
  std::printf("去重后 %.3f GB,前 14 大:\n",tot/1e9);
  int n=0; for(auto&[b,t]:by){ if(n++>=14)break; std::printf("  %7.1f MB  %s\n",b/1e6,t.c_str()); }
  return 0;
}
