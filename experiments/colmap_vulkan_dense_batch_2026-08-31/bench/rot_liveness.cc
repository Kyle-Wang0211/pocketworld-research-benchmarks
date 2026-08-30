// [ROT-2 证据] 枚举官方 dispatch plan 的全部步骤,检验:
//   (a) 任何一步引用的 rotation 只可能是 {r} 或 {r, r+1 mod 4};
//   (b) 因此活跃集恒为相邻两个 ⇒ 按 parity(奇偶)复用物理缓冲不会自我覆盖。
// 这是「不靠推理靠枚举」的那一半证据;另一半是 bench.sh 的逐字节回归。
#include "vulkan_host/dispatch_plan.h"
#include <cstdio>
#include <set>
using namespace pocketworld::official_dense::vulkan;

int main(){
  for (PlanPhase phase : {PlanPhase::kPhotometricOnly, PlanPhase::kFull}) {
    PlanOptions opt{};
    opt.iterations = 5; opt.phase = phase;
    opt.geom_consistency = (phase == PlanPhase::kFull);
    opt.filter = (phase == PlanPhase::kFull);
    const DispatchPlan plan = CreateDispatchPlan(1U, opt);
    if (plan.status != PlanStatus::kReady) { std::printf("build 失败\n"); return 1; }
    std::set<std::pair<std::uint32_t,std::uint32_t>> pairs;
    std::size_t bad = 0;
    for (const PlanStep& s : plan.steps) {
      pairs.insert({s.rotation_before, s.rotation_after});
      const std::uint32_t d = (s.rotation_after + 4U - s.rotation_before) & 3U;
      if (d != 0U && d != 1U) {
        ++bad;
        std::printf("  ❌ 非相邻: before=%u after=%u op=%d\n",
                    s.rotation_before, s.rotation_after,
                    static_cast<int>(s.operation));
      }
    }
    std::printf("phase=%s  步骤 %zu  出现过的 (before,after) 组合:",
                phase==PlanPhase::kFull?"kFull":"kPhotometricOnly",
                plan.steps.size());
    for (auto&[a,b]:pairs) std::printf(" (%u→%u)",a,b);
    std::printf("\n  非相邻步骤数 = %zu  %s\n\n", bad, bad?"❌":"✅");
  }
  return 0;
}
