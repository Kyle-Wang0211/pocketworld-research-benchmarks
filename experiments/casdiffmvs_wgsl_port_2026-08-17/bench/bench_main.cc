// CasDiffMVS 端上 bench —— iOS / Android 共用一份,只差取峰值内存那一个函数。
//
// 量三件事,每件都有明确判据:
//   ① 峰值内存 —— 后台线程 20ms 采样取峰。**采样太疏会漏掉帧内峰值**(APDe 那次的教训)。
//   ② 稳态延迟 —— 丢弃首帧(含 shader 编译与预热),取中位数。
//   ③ 数值正确性 —— 与打包进来的 host 参考深度逐像素比。
//      🔴 必须验:08-18 已吃过一次亏 —— WebGPU 不报错、速度正常、结果全 NaN。
//
// 🔴 图优化必须设成 ORT_ENABLE_BASIC:
//    ORT_ENABLE_EXTENDED 及以上会让 WebGPU EP 产生非有限值(已上报 #32147 的姊妹问题
//    https://github.com/microsoft/onnxruntime/issues/32145),而且**是静默的**。
//
// ⚠️ 本文件未经真机运行验证(2026-08-18 写就时手头无 Android 设备,
//    iOS 侧 ORT 构建亦未完成)。任何"跑通"的结论都必须以真机输出为准。

#include <onnxruntime_cxx_api.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

// ── 峰值内存:两端口径不同,必须分别取 ──────────────────────────────
#if defined(__APPLE__)
#include <mach/mach.h>
// 🔑 用 phys_footprint,**不是 resident_size** —— jetsam 判定用的就是它。
static size_t peak_mem_now() {
  task_vm_info_data_t info;
  mach_msg_type_number_t cnt = TASK_VM_INFO_COUNT;
  if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &cnt) != KERN_SUCCESS)
    return 0;
  return (size_t)info.phys_footprint;
}
static const char* kMemMetric = "phys_footprint (jetsam 口径)";
#else
// Android/Linux:VmHWM = 进程历史峰值 RSS,由内核维护,不依赖我们的采样频率。
// ⚠️ Android 的 LMKD 判定与 iOS jetsam 不同口径,这里取 VmHWM 只作可比的上界。
static size_t read_status_kb(const char* key) {
  FILE* f = fopen("/proc/self/status", "r");
  if (!f) return 0;
  char line[256];
  size_t kb = 0, klen = strlen(key);
  while (fgets(line, sizeof(line), f)) {
    if (strncmp(line, key, klen) == 0) { sscanf(line + klen, " %zu", &kb); break; }
  }
  fclose(f);
  return kb;
}
static size_t peak_mem_now() { return read_status_kb("VmRSS:") * 1024; }
static size_t peak_mem_hwm() { return read_status_kb("VmHWM:") * 1024; }
static const char* kMemMetric = "VmHWM (peak RSS)";
#endif

struct Header {
  uint32_t n_frames, n_view, H, W, n_depth, n_img;
};

static std::vector<char> read_all(const std::string& p) {
  FILE* f = fopen(p.c_str(), "rb");
  if (!f) { fprintf(stderr, "🔴 打不开 %s\n", p.c_str()); exit(1); }
  fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
  std::vector<char> b(n);
  if (fread(b.data(), 1, n, f) != (size_t)n) { fprintf(stderr, "🔴 读短了\n"); exit(1); }
  fclose(f);
  return b;
}

int main(int argc, char** argv) {
  const char* model = argc > 1 ? argv[1] : "model.onnx";
  const char* inputs = argc > 2 ? argv[2] : "inputs.bin";
  const int   ep     = argc > 3 ? atoi(argv[3]) : 1;   // 1=WebGPU  0=CPU

  auto blob = read_all(inputs);
  if (memcmp(blob.data(), "PWMVSB02", 8) != 0) {
    fprintf(stderr, "🔴 输入文件 magic 不对(期望 PWMVSB02)\n"); return 1;
  }
  Header h; memcpy(&h, blob.data() + 8, sizeof(h));
  const size_t HW = (size_t)h.H * h.W;
  const uint16_t* bank = (const uint16_t*)(blob.data() + 8 + sizeof(h));
  const char* cur = (const char*)(bank + (size_t)h.n_img * HW);
  printf("输入:%u 帧 · %u 视图 · %ux%u · 图像库 %u 张\n",
         h.n_frames, h.n_view, h.W, h.H, h.n_img);

  // ── 峰值采样线程(20ms)──
  std::atomic<size_t> peak{0};
  std::atomic<bool> stop{false};
  std::thread sampler([&] {
    while (!stop.load()) {
      size_t m = peak_mem_now();
      size_t p = peak.load();
      while (m > p && !peak.compare_exchange_weak(p, m)) {}
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
  });

  Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "pwbench");
  Ort::SessionOptions so;
  // 🔴 见文件头:EXTENDED 及以上会让 WebGPU 静默产生非有限值。
  so.SetGraphOptimizationLevel(ORT_ENABLE_BASIC);
  if (ep == 1) {
    std::unordered_map<std::string, std::string> opts;
    so.AppendExecutionProvider("WebGPU", opts);
  }
  auto t_sess = std::chrono::steady_clock::now();
  Ort::Session sess(env, model, so);
  double sess_ms = std::chrono::duration<double, std::milli>(
      std::chrono::steady_clock::now() - t_sess).count();

  Ort::AllocatorWithDefaultOptions alloc;
  std::vector<std::string> in_names_s;
  for (size_t i = 0; i < sess.GetInputCount(); ++i)
    in_names_s.push_back(sess.GetInputNameAllocated(i, alloc).get());
  std::vector<const char*> in_names;
  for (auto& s : in_names_s) in_names.push_back(s.c_str());
  const char* out_names[] = {"depth", "conf0", "conf1", "conf2"};

  auto meminfo = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
  std::vector<double> ms;
  double worst_rel = 0.0; size_t bad1 = 0, tot = 0, nonfinite = 0;

  const size_t n2 = (size_t)(h.H / 4) * (h.W / 4);
  const size_t n3 = (size_t)(h.H / 2) * (h.W / 2);

  for (uint32_t f = 0; f < h.n_frames; ++f) {
    const int32_t* vidx = (const int32_t*)cur;                 cur += 4 * h.n_view;
    const float*   pm[3];
    for (int s = 0; s < 3; ++s) { pm[s] = (const float*)cur;   cur += 4 * h.n_view * 32; }
    const float* dv  = (const float*)cur;                      cur += 4 * h.n_depth;
    const float* nz2 = (const float*)cur;                      cur += 4 * n2;
    const float* nz3 = (const float*)cur;                      cur += 4 * n3;
    const float* ref = (const float*)cur;                      cur += 4 * HW;

    // 灰度 fp16 → 3 通道 fp32(模型输入是 3 通道)
    std::vector<float> imgs((size_t)h.n_view * 3 * HW);
    for (uint32_t v = 0; v < h.n_view; ++v) {
      const uint16_t* g = bank + (size_t)vidx[v] * HW;
      for (size_t i = 0; i < HW; ++i) {
        // fp16 → fp32(手写,避免依赖 _Float16 在两端的可用性差异)
        uint16_t x = g[i];
        uint32_t sign = (uint32_t)(x >> 15) << 31;
        uint32_t exp  = (x >> 10) & 0x1F, man = x & 0x3FF, bits;
        if (exp == 0)        bits = man ? (sign | ((127 - 15 + 1) << 23) | (man << 13)) : sign;
        else if (exp == 31)  bits = sign | 0x7F800000u | (man << 13);
        else                 bits = sign | ((exp - 15 + 127) << 23) | (man << 13);
        float fv; memcpy(&fv, &bits, 4);
        for (int c = 0; c < 3; ++c)
          imgs[((size_t)v * 3 + c) * HW + i] = fv;
      }
    }

    std::vector<int64_t> sh_img{1, h.n_view, 3, h.H, h.W};
    std::vector<int64_t> sh_pm {1, h.n_view, 2, 4, 4};
    std::vector<int64_t> sh_dv {1, h.n_depth};
    std::vector<int64_t> sh_n2 {1, 1, h.H / 4, h.W / 4};
    std::vector<int64_t> sh_n3 {1, 1, h.H / 2, h.W / 2};

    std::vector<Ort::Value> vals;
    auto push = [&](const float* p, std::vector<int64_t>& s, size_t n) {
      vals.push_back(Ort::Value::CreateTensor<float>(
          meminfo, const_cast<float*>(p), n, s.data(), s.size()));
    };
    // ⚠️ 必须按 sess 报告的输入名顺序喂,而不是按我以为的顺序 ——
    //    stage_iters=[1,3,3] 让 pm_stage4 从不被读,导出时被裁掉(踩过 InvalidArgument)。
    for (auto& nm : in_names_s) {
      if      (nm == "imgs")         push(imgs.data(), sh_img, imgs.size());
      else if (nm == "pm_stage1")    push(pm[0], sh_pm, (size_t)h.n_view * 32);
      else if (nm == "pm_stage2")    push(pm[1], sh_pm, (size_t)h.n_view * 32);
      else if (nm == "pm_stage3")    push(pm[2], sh_pm, (size_t)h.n_view * 32);
      else if (nm == "depth_values") push(dv,  sh_dv, h.n_depth);
      else if (nm == "noise_stage2") push(nz2, sh_n2, n2);
      else if (nm == "noise_stage3") push(nz3, sh_n3, n3);
      else { fprintf(stderr, "🔴 未知输入 %s\n", nm.c_str()); return 1; }
    }

    auto t0 = std::chrono::steady_clock::now();
    auto out = sess.Run(Ort::RunOptions{nullptr}, in_names.data(), vals.data(),
                        vals.size(), out_names, 4);
    double dt = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - t0).count();
    if (f > 0) ms.push_back(dt);                    // 丢弃首帧(编译+预热)

    const float* d = out[0].GetTensorData<float>();
    for (size_t i = 0; i < HW; ++i) {
      if (!std::isfinite(d[i])) { ++nonfinite; continue; }
      double r = std::fabs(d[i] - ref[i]) / std::max(ref[i], 1e-6f);
      if (r > 0.01) ++bad1;
      worst_rel = std::max(worst_rel, r);
      ++tot;
    }
    printf("  帧%2u  %7.1f ms\n", f, dt);
  }

  stop.store(true); sampler.join();
  std::sort(ms.begin(), ms.end());
  double med = ms.empty() ? 0 : ms[ms.size() / 2];
#if defined(__APPLE__)
  size_t pk = peak.load();
#else
  size_t pk = std::max(peak.load(), peak_mem_hwm());
#endif

  printf("\n══ 结果(EP=%s)══\n", ep == 1 ? "WebGPU" : "CPU");
  printf("  会话建立      %.0f ms\n", sess_ms);
  printf("  稳态延迟      中位 %.1f ms  (min %.1f  max %.1f,已丢首帧)\n",
         med, ms.empty() ? 0 : ms.front(), ms.empty() ? 0 : ms.back());
  printf("  峰值内存      %.0f MB   [%s]\n", pk / 1e6, kMemMetric);
  printf("  预算 1500 MB  %s\n", pk / 1e6 <= 1500 ? "✅ 在预算内" : "🔴 超预算");
  printf("\n  与 host 参考对拍:非有限 %zu  >1%% 的像素 %.4f%%  最大相对差 %.3f%%\n",
         nonfinite, 100.0 * bad1 / std::max<size_t>(tot, 1), 100.0 * worst_rel);
  printf("  ⇒ %s\n", (nonfinite == 0 && 100.0 * bad1 / std::max<size_t>(tot, 1) < 0.1)
                     ? "✅ 数值与 host 一致" : "🔴 数值不一致 —— 先查这个,别信上面的速度");
  return 0;
}
