// [BATCH-REF 前置检查] PatchPC 里哪些字段是逐 reference 的?
// 一次 dispatch 只有一份 push constant,所以要么这些值全场景相同、
// 要么必须挪进按 RefIndex() 索引的 buffer。用真实场景数据判定,不靠猜。
#include "vulkan_apple/frozen_scene_loader.h"
#include <cstdio>
#include <set>
#include <string>
using namespace pocketworld::official_dense::vulkan;
int main(int argc, char** argv){
  FrozenScene scene; std::string detail;
  if(!LoadFrozenScene(argv[1], &scene, &detail)){
    std::printf("加载失败: %s\n", detail.c_str()); return 1; }
  std::printf("图像数 %zu\n\n", scene.images.size());
  std::set<std::string> ks, dims;
  float dmin_lo=1e30f, dmin_hi=-1e30f, dmax_lo=1e30f, dmax_hi=-1e30f;
  std::set<std::string> dranges;
  for (const auto& im : scene.images) {
    char k[256];
    std::snprintf(k,sizeof k,"fx=%.6f fy=%.6f cx=%.6f cy=%.6f",
                  im.K[0],im.K[4],im.K[2],im.K[5]);
    ks.insert(k);
    std::snprintf(k,sizeof k,"%ux%u",im.width,im.height); dims.insert(k);
    std::snprintf(k,sizeof k,"%.4f..%.4f",im.depth_min,im.depth_max);
    dranges.insert(k);
    dmin_lo=std::min(dmin_lo,im.depth_min); dmin_hi=std::max(dmin_hi,im.depth_min);
    dmax_lo=std::min(dmax_lo,im.depth_max); dmax_hi=std::max(dmax_hi,im.depth_max);
  }
  std::printf("不同的内参组合 : %zu %s\n", ks.size(), ks.size()==1?"✅ 全场景相同":"❌ 逐图不同");
  for (const auto& s : ks) { std::printf("    %s\n", s.c_str()); if(ks.size()>3) break; }
  std::printf("不同的分辨率   : %zu\n", dims.size());
  std::printf("不同的深度范围 : %zu %s\n", dranges.size(),
              dranges.size()==1?"✅ 全场景相同":"❌ 逐图不同");
  std::printf("    depth_min ∈ [%.4f, %.4f]\n", dmin_lo, dmin_hi);
  std::printf("    depth_max ∈ [%.4f, %.4f]\n", dmax_lo, dmax_hi);
  return 0;
}
