#include "vulkan_host/dispatch_plan.h"
#include <cstdio>
#include <map>
using namespace pocketworld::official_dense::vulkan;
static const char* Name(Operation o){
  switch(o){
#define C(x) case Operation::x: return #x;
  C(kUploadReferenceImage) C(kReferenceFilter) C(kUploadSourceImages)
  C(kUploadSourceDepthMaps) C(kUploadTransformsAndCalibrations)
  C(kInitializeRng) C(kInitializeRandomDepth) C(kInitializeRandomNormal)
  C(kCopyPhotometricDepth) C(kCopyPhotometricNormal)
  C(kInitializeSelectionAndWorkspace) C(kBarrier) C(kInitialCost)
  C(kAllocateConsistencyMask) C(kClearConsistencyMask) C(kSweep)
  C(kRotateResource) C(kSelectCalibrationAndPose) C(kRotateFinalMask)
  C(kReadbackDepth) C(kReadbackNormal) C(kReadbackMask) C(kWaitPhotometricAll)
#undef C
  } return "?";
}
int main(){
  PlanOptions opt{}; opt.iterations=5; opt.phase=PlanPhase::kPhotometricOnly;
  opt.geom_consistency=false; opt.filter=false;
  const DispatchPlan plan=CreateDispatchPlan(1U,opt);
  std::map<int,int> c;
  for(const PlanStep&s:plan.steps) c[static_cast<int>(s.operation)]++;
  std::printf("photometric plan 共 %zu 步\n",plan.steps.size());
  std::multimap<int,int,std::greater<>> by;
  for(auto&[k,v]:c) by.emplace(v,k);
  for(auto&[v,k]:by) std::printf("  %4d ×  %s\n",v,Name(static_cast<Operation>(k)));
  return 0;
}
