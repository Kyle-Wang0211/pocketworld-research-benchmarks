// PWMatchProbe(Android arm64)—— 命令行原生二进制,adb push 到 /data/local/tmp 就能跑。
//
// 目的不是测速,是回答三个问题(2026-09-05,用户手上只有一台老华为):
//   ① 这台机器的 Vulkan 驱动上报什么?(kernel=mma 还是 tiled、subgroup 宽度、
//      cooperative matrix 配置在不在)
//   ② 同一份 WGSL 在 Vulkan 后端能不能跑起来
//   ③ 🔴 输出 sha 是否与 Mac / A16 完全一致 —— 夹具 fx13 的答案是 a59db73512ce。
//      对得上,"一套源码三端逐字节一致"就从口号变成实证,哪怕它慢十倍。
//
// 不用 fair_match_common.h:那个头依赖 CommonCrypto(Apple 专有),
// 这里自带一份可移植 SHA-256,免得为了安卓去改 Apple 侧四道门在用的公共头。
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <chrono>
#include <string>
#include <vector>
#include <algorithm>

extern "C" int pwdawn_gpu_match_gemm_pairs(const uint8_t*, int, const uint8_t*, int,
                                           double, uint32_t*, int, int*);
extern "C" int pwdawn_gpu_match_backend_info(char*, int);
extern "C" int pwdawn_gpu_match_last_error(char*, int);

namespace {
struct Sha256 {
  uint32_t h[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                   0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
  uint64_t len = 0;
  uint8_t buf[64];
  size_t n = 0;
  static uint32_t ror(uint32_t x, int r) { return (x >> r) | (x << (32 - r)); }
  void block(const uint8_t* p) {
    static const uint32_t K[64] = {
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = (uint32_t)p[i*4] << 24 | (uint32_t)p[i*4+1] << 16 | (uint32_t)p[i*4+2] << 8 | p[i*4+3];
    for (int i = 16; i < 64; ++i) {
      const uint32_t s0 = ror(w[i-15],7) ^ ror(w[i-15],18) ^ (w[i-15] >> 3);
      const uint32_t s1 = ror(w[i-2],17) ^ ror(w[i-2],19) ^ (w[i-2] >> 10);
      w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],x=h[7];
    for (int i = 0; i < 64; ++i) {
      const uint32_t S1 = ror(e,6) ^ ror(e,11) ^ ror(e,25);
      const uint32_t ch = (e & f) ^ (~e & g);
      const uint32_t t1 = x + S1 + ch + K[i] + w[i];
      const uint32_t S0 = ror(a,2) ^ ror(a,13) ^ ror(a,22);
      const uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
      const uint32_t t2 = S0 + mj;
      x=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=x;
  }
  void update(const void* data, size_t sz) {
    const uint8_t* p = (const uint8_t*)data;
    len += sz;
    while (sz) {
      const size_t take = std::min(sz, 64 - n);
      memcpy(buf + n, p, take);
      n += take; p += take; sz -= take;
      if (n == 64) { block(buf); n = 0; }
    }
  }
  std::string hex() {
    uint64_t bits = len * 8;
    uint8_t pad = 0x80;
    update(&pad, 1);
    uint8_t z = 0;
    while (n != 56) update(&z, 1);
    uint8_t be[8];
    for (int i = 0; i < 8; ++i) be[i] = (uint8_t)(bits >> (56 - 8*i));
    update(be, 8);
    char out[65];
    for (int i = 0; i < 8; ++i) snprintf(out + i*8, 9, "%08x", h[i]);
    return std::string(out, 64);
  }
};
std::vector<uint8_t> ReadN(const std::string& p, size_t cap) {
  std::vector<uint8_t> v;
  FILE* f = fopen(p.c_str(), "rb");
  if (!f) return v;
  v.resize(cap);
  v.resize(fread(v.data(), 1, cap, f));
  fclose(f);
  return v;
}
double NowMs() {
  using namespace std::chrono;
  return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}
}  // namespace

static int run_probe(const std::string& fx, int rows, int reps, FILE* out) {
#define printf(...) fprintf(out, __VA_ARGS__)

  char info[512] = {0};
  const int ilen = pwdawn_gpu_match_backend_info(info, sizeof(info));
#ifndef PW_PROBE_BUILD_ID
#define PW_PROBE_BUILD_ID "unknown"
#endif
  // [BUILD-ID 2026-09-05] 装机≠生效:第三批曾在旧 .so 上跑(新 APK 只编未装)。把编进 .so 的 TU sha 打出来,
  // 脚本对照期望值,不一致直接判 FAIL。
  printf("BUILD_ID %s\n", PW_PROBE_BUILD_ID);
  printf("BACKEND_INFO %s\n", ilen > 0 ? info : "(无 GPU / Dawn 初始化失败)");
  if (ilen <= 0) {
    char err[512] = {0};
    pwdawn_gpu_match_last_error(err, sizeof(err));
    printf("LAST_ERROR %s\n", err);
    return 3;
  }

  const size_t need = (size_t)rows * 128u;
  std::vector<uint8_t> A = ReadN(fx + "/a.u8", need), B = ReadN(fx + "/b.u8", need);
  if (A.size() < need || B.size() < need) {
    printf("FIXTURE_SHORT a=%zu b=%zu need=%zu\n", A.size(), B.size(), need);
    return 4;
  }
  const int cap = rows * 2;
  std::vector<uint32_t> pairs(2 * (size_t)cap);
  int n = 0, rc = 0;
  std::vector<double> t;
  for (int i = 0; i < reps; ++i) {
    const double t0 = NowMs();
    rc = pwdawn_gpu_match_gemm_pairs(A.data(), rows, B.data(), rows, 0.8,
                                     pairs.data(), cap, &n);
    t.push_back(NowMs() - t0);
    if (rc != 0) break;
  }
  Sha256 s;
  if (rc == 0) s.update(pairs.data(), sizeof(uint32_t) * 2 * (size_t)n);
  std::sort(t.begin(), t.end());
  printf("RESULT rows=%d rc=%d count=%d sha256=%s p50_ms=%.3f min_ms=%.3f\n",
         rows, rc, n, rc == 0 ? s.hex().c_str() : "-",
         t.empty() ? 0.0 : t[t.size()/2], t.empty() ? 0.0 : t[0]);
  if (rc != 0) {
    char err[512] = {0};
    pwdawn_gpu_match_last_error(err, sizeof(err));
    printf("LAST_ERROR %s\n", err);
  }
  return rc;
#undef printf
}

#include <jni.h>
#include <unistd.h>
#include <cstdlib>
extern "C" JNIEXPORT jstring JNICALL
Java_com_kyle_pwprobe_Main_run(JNIEnv* env, jclass, jstring jfix, jint rows, jint reps,
                               jstring jkernel, jstring jextra, jstring jout) {
  const char* fix = env->GetStringUTFChars(jfix, nullptr);
  const char* kernel = env->GetStringUTFChars(jkernel, nullptr);
  const char* extra = env->GetStringUTFChars(jextra, nullptr);
  const char* outp = env->GetStringUTFChars(jout, nullptr);
  if (kernel && *kernel) setenv("OFFICIAL_AETHER_MATCH_DAWN_KERNEL", kernel, 1);
  // extra: "K=V;K2=V2"
  std::string ex = extra ? extra : "";
  size_t s0 = 0;
  while (s0 < ex.size()) {
    size_t e = ex.find(';', s0); if (e == std::string::npos) e = ex.size();
    std::string kv = ex.substr(s0, e - s0); size_t q = kv.find('=');
    if (q != std::string::npos) setenv(kv.substr(0, q).c_str(), kv.substr(q + 1).c_str(), 1);
    s0 = e + 1;
  }
  // 指纹文件:app 里 HOME 通常未设,给它一个可读的位置
  setenv("HOME", outp, 0);
  FILE* out = fopen(outp, "w");
  if (!out) return env->NewStringUTF("open out failed");
  // [STDERR→文件] 设备上 stderr 不可见:把 TU 的锚点告警 / direct-chain 日志并进输出文件。
  fflush(stderr); dup2(fileno(out), 2);
  if (getenv("PW_PROBE_ALU") != nullptr) {
    // [ALU-PEAK] 纯算术峰值探针:此刻这台 GPU 的 FMA 天花板(GFMA/s),与匹配核无关。
    extern int pwdawn_probe_alu_shape(const char*, uint32_t, uint32_t, double*, double*);
    const char* shapes[] = {"chain16", "gemm44", "gemm44ld", "gemm84"};
    for (const char* sh : shapes) {
      double ms = 0, gf = 0;
      const int arc = pwdawn_probe_alu_shape(sh, 1024u, 4096u, &ms, &gf);
      fprintf(out, "ALU_LADDER shape=%s rc=%d ms=%.3f gfma_s=%.2f\n", sh, arc, ms, gf);
    }
  }
  const int rc = run_probe(fix, rows, reps, out);
  fprintf(out, "PROBE_DONE rc=%d\n", rc);
  fclose(out);
  std::string res = "rc=" + std::to_string(rc) + " -> " + outp;
  env->ReleaseStringUTFChars(jfix, fix); env->ReleaseStringUTFChars(jkernel, kernel);
  env->ReleaseStringUTFChars(jextra, extra); env->ReleaseStringUTFChars(jout, outp);
  return env->NewStringUTF(res.c_str());
}
