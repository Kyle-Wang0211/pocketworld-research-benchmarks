// PWMatchBench —— 设备侧匹配器台架。
//
// 起因(2026-09-04):整场 WGSL 匹配器战役都在 M3 Pro 上定价(收盘 0.986x 追平原生
// Metal),第一次上真机才发现 A16 上慢 8.5x —— 而且根因是设备**根本没跑 MMA 核**。
// 用户不该当测量仪器:"你能在电脑上一遍一遍测,为什么不装个 bench app 在手机上测"。
//
// 口径与 Mac 台架完全一致:两个后端**同一进程内交替**(不是两次启动、不靠 env),
// 直接调 pwmetal_* / pwdawn_*(它们不在 xcframework 的导出面上,所以这里直接编译
// 同一批 TU:gpu_match.mm[改名] / dispatch / dawn / thermal)。
#import <Foundation/Foundation.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include <chrono>
#include <CommonCrypto/CommonDigest.h>

extern "C" int pwmetal_gpu_match_gemm_pairs(const uint8_t*, int, const uint8_t*, int,
                                            double, uint32_t*, int, int*);
extern "C" int pwdawn_gpu_match_gemm_pairs(const uint8_t*, int, const uint8_t*, int,
                                           double, uint32_t*, int, int*);
extern "C" int pwdawn_gpu_match_backend_info(char*, int);
extern "C" double aether_match_gpu_ms;
extern "C" double aether_match_sleep_ms;
extern "C" int aether_match_chunks;

namespace {
double NowMs() {
  using namespace std::chrono;
  return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}
std::string Sha256Hex(const void* p, size_t n) {
  unsigned char d[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(p, (CC_LONG)n, d);
  char buf[2 * CC_SHA256_DIGEST_LENGTH + 1];
  for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; ++i) std::snprintf(buf + 2 * i, 3, "%02x", d[i]);
  return std::string(buf, 2 * CC_SHA256_DIGEST_LENGTH);
}
std::vector<uint8_t> ReadAll(const std::string& p, size_t cap) {
  std::vector<uint8_t> v;
  FILE* f = std::fopen(p.c_str(), "rb");
  if (!f) return v;
  v.resize(cap);
  const size_t got = std::fread(v.data(), 1, cap, f);
  v.resize(got);
  std::fclose(f);
  return v;
}
std::string g_out_path;
}  // namespace

extern "C" const char* pwbench_run(const char* fixture_dir, int rows, int reps,
                                   double ratio, const char* out_dir) {
  g_out_path.clear();
  const std::string fx = fixture_dir;
  // 夹具是 rows x 128 的原始 u8;取前 rows 行即可在同一份夹具上跑任意规模。
  const size_t need = (size_t)rows * 128u;
  std::vector<uint8_t> A = ReadAll(fx + "/a.u8", need);
  std::vector<uint8_t> B = ReadAll(fx + "/b.u8", need);
  if (A.size() < need || B.size() < need) return "";

  const int cap = rows * 2;
  std::vector<uint32_t> pm(2 * (size_t)cap), pd(2 * (size_t)cap);
  int nm = 0, nd = 0;

  char info[512] = {0};
  pwdawn_gpu_match_backend_info(info, sizeof(info));

  // 预热各一次(Dawn 首次含管线编译;Metal 首次含 PSO 建立)。
  pwmetal_gpu_match_gemm_pairs(A.data(), rows, B.data(), rows, ratio, pm.data(), cap, &nm);
  pwdawn_gpu_match_gemm_pairs(A.data(), rows, B.data(), rows, ratio, pd.data(), cap, &nd);

  std::vector<double> tm, td, gm, gd;
  std::vector<int> cm, cd;
  int rcm = 0, rcd = 0;
  std::string shm, shd;
  for (int i = 0; i < reps; ++i) {
    // 交替:同一轮里先 Metal 后 Dawn,热态与频率对两臂对称。
    aether_match_gpu_ms = 0; aether_match_chunks = 0;
    double t0 = NowMs();
    rcm = pwmetal_gpu_match_gemm_pairs(A.data(), rows, B.data(), rows, ratio, pm.data(), cap, &nm);
    tm.push_back(NowMs() - t0); gm.push_back(aether_match_gpu_ms); cm.push_back(aether_match_chunks);
    if (shm.empty() && rcm == 0) shm = Sha256Hex(pm.data(), sizeof(uint32_t) * 2 * (size_t)nm);

    aether_match_gpu_ms = 0; aether_match_chunks = 0;
    t0 = NowMs();
    rcd = pwdawn_gpu_match_gemm_pairs(A.data(), rows, B.data(), rows, ratio, pd.data(), cap, &nd);
    td.push_back(NowMs() - t0); gd.push_back(aether_match_gpu_ms); cd.push_back(aether_match_chunks);
    if (shd.empty() && rcd == 0) shd = Sha256Hex(pd.data(), sizeof(uint32_t) * 2 * (size_t)nd);
  }
  auto med = [](std::vector<double> v) {
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());
    return v[v.size() / 2];
  };
  auto medi = [](std::vector<int> v) {
    if (v.empty()) return 0;
    std::sort(v.begin(), v.end());
    return v[v.size() / 2];
  };
  auto join = [](const std::vector<double>& v) {
    std::string s;
    for (size_t i = 0; i < v.size(); ++i) {
      char b[32]; std::snprintf(b, sizeof(b), "%s%.3f", i ? "," : "", v[i]); s += b;
    }
    return s;
  };

  char path[1024];
  std::snprintf(path, sizeof(path), "%s/match_%d_%lld.json", out_dir, rows,
                (long long)(NowMs()));
  FILE* f = std::fopen(path, "w");
  if (!f) return "";
  std::fprintf(f,
      "{\"rows\":%d,\"reps\":%d,\"ratio\":%.3f,\"backend_info\":\"%s\","
      "\"metal\":{\"rc\":%d,\"n\":%d,\"sha12\":\"%s\",\"wall_p50\":%.3f,"
      "\"gpu_p50\":%.3f,\"chunks_p50\":%d,\"wall\":[%s]},"
      "\"dawn\":{\"rc\":%d,\"n\":%d,\"sha12\":\"%s\",\"wall_p50\":%.3f,"
      "\"gpu_p50\":%.3f,\"chunks_p50\":%d,\"wall\":[%s]},"
      "\"bytewise_identical\":%s,\"dawn_over_metal\":%.4f}\n",
      rows, reps, ratio, info,
      rcm, nm, shm.substr(0, 12).c_str(), med(tm), med(gm), medi(cm), join(tm).c_str(),
      rcd, nd, shd.substr(0, 12).c_str(), med(td), med(gd), medi(cd), join(td).c_str(),
      (!shm.empty() && shm == shd && nm == nd) ? "true" : "false",
      med(tm) > 0 ? med(td) / med(tm) : 0.0);
  std::fclose(f);
  g_out_path = path;
  return g_out_path.c_str();
}
