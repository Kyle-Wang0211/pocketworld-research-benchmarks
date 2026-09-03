// sgmatrix_probe.cc — dump EVERY subgroup-matrix config the local Dawn adapter
// exposes (component type, result component type, M/N/K) + related features.
// Decisive evidence for "can WGSL do mixed precision / integer MMA on M3?"
#include <webgpu/webgpu_cpp.h>
#include <cstdio>
#include <cstring>
#include <vector>
static const char* CT(wgpu::SubgroupMatrixComponentType t) {
  switch (t) {
    case wgpu::SubgroupMatrixComponentType::F32: return "f32";
    case wgpu::SubgroupMatrixComponentType::F16: return "f16";
    case wgpu::SubgroupMatrixComponentType::U32: return "u32";
    case wgpu::SubgroupMatrixComponentType::I32: return "i32";
    case wgpu::SubgroupMatrixComponentType::U8:  return "u8";
    case wgpu::SubgroupMatrixComponentType::I8:  return "i8";
    default: return "?";
  }
}
int main() {
  wgpu::InstanceDescriptor idesc{};
  std::vector<wgpu::InstanceFeatureName> ifeats = {
      wgpu::InstanceFeatureName::TimedWaitAny};
  idesc.requiredFeatureCount = ifeats.size();
  idesc.requiredFeatures = ifeats.data();
  // chromium_experimental_subgroup_matrix is gated behind allow_unsafe_apis
  // (same as the production TU does, pwofficial_gpu_match_dawn.cc:855-861).
  const char* allow = "allow_unsafe_apis";
  wgpu::DawnTogglesDescriptor toggles{};
  toggles.enabledToggleCount = 1;
  toggles.enabledToggles = &allow;
  idesc.nextInChain = &toggles;
  wgpu::Instance inst = wgpu::CreateInstance(&idesc);
  if (!inst) { std::printf("FAIL no instance\n"); return 1; }
  wgpu::Adapter adapter;
  wgpu::RequestAdapterOptions opts{};
  opts.powerPreference = wgpu::PowerPreference::HighPerformance;
  inst.WaitAny(inst.RequestAdapter(&opts, wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::RequestAdapterStatus s, wgpu::Adapter a, wgpu::StringView m) {
        if (s == wgpu::RequestAdapterStatus::Success) adapter = std::move(a);
        else std::printf("FAIL adapter: %.*s\n", (int)m.length, m.data);
      }), UINT64_MAX);
  if (!adapter) return 1;

  wgpu::AdapterInfo info{};
  wgpu::AdapterPropertiesSubgroupMatrixConfigs cfgs{};
  const bool has_sgm = adapter.HasFeature(wgpu::FeatureName::ChromiumExperimentalSubgroupMatrix);
  if (has_sgm) info.nextInChain = &cfgs;
  adapter.GetInfo(&info);
  std::printf("adapter=\"%.*s\" backend=%d\n", (int)info.device.length, info.device.data, (int)info.backendType);
  std::printf("subgroup range=[%u,%u]\n", info.subgroupMinSize, info.subgroupMaxSize);
  const wgpu::FeatureName probe[] = {
      wgpu::FeatureName::Subgroups,
      wgpu::FeatureName::ChromiumExperimentalSubgroupMatrix,
      wgpu::FeatureName::ShaderF16,
      wgpu::FeatureName::TimestampQuery,
      wgpu::FeatureName::Float32Filterable,
  };
  const char* pn[] = {"subgroups","subgroup-matrix","shader-f16","timestamp-query","f32-filterable"};
  for (size_t i = 0; i < sizeof(probe)/sizeof(probe[0]); ++i)
    std::printf("feature %-16s = %d\n", pn[i], (int)adapter.HasFeature(probe[i]));
  // packed integer dot product is a WGSL language feature, query via instance
  wgpu::SupportedWGSLLanguageFeatures wf{};
  inst.GetWGSLLanguageFeatures(&wf);
  std::printf("wgsl language features: %zu\n", (size_t)wf.featureCount);
  if (!has_sgm) { std::printf("NO subgroup-matrix feature\n"); return 0; }
  std::printf("subgroup matrix configs: %zu\n", (size_t)cfgs.configCount);
  for (size_t i = 0; i < cfgs.configCount; ++i) {
    const wgpu::SubgroupMatrixConfig& k = cfgs.configs[i];
    std::printf("  cfg[%zu] in=%-3s out=%-3s M=%u N=%u K=%u\n", i,
                CT(k.componentType), CT(k.resultComponentType), k.M, k.N, k.K);
  }
  return 0;
}
