// APDe-MVS WGSL 移植:单帧闭环流水驱动
//
// 目的:把 2741 行"编译通过但从未执行"的 WGSL 真跑一遍,出一张深度图。
//       编译通过 ≠ 数值正确 —— 半像素偏移、R 写成 R^T、plane.w 语义切换点
//       搞错,任何一个都会让深度图变成噪声。单帧闭环是最便宜的排雷。
//
// Pass 顺序照抄 APD.cu:2685-2729:
//   [InitRandomStates]            ← 我们改成确定性播种,不需要这个 pass
//   (use_APD) FindNearestStrongPoint → GenAnchors → NeigbourUpdate
//   RandomInitialization
//   for i in 0..max_iterations:
//       BlackPixelUpdateStrong → RedPixelUpdateStrong
//       (use_APD) RANSACToGetFitPlane → BlackPixelUpdateWeak → RedPixelUpdateWeak
//   GetDepthandNormal
//   BlackPixelFilterStrong → RedPixelFilterStrong
//   DepthToWeak
//   (geom||APD) ConfidenceCompute
//   LocalRefine
//
// ⚠️ 第一轮故意 use_APD=0 / geom_consistency=0 —— 最短路径,先验证核心几何。
//    APD 支和几何一致性支各自再单独开一轮,便于定位问题。

#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <map>
#include <string>

struct Params {
  uint32_t width, height, ref_index, num_images;
  uint32_t num_anchors, iter;
  int32_t  strong_radius, strong_increment;
  uint32_t rand_seed;
  float    depth_min, depth_max, geom_factor;
  uint32_t geom_consistency, use_impetus, state;
  uint32_t rotate_time;
  float    ransac_threshold;
  uint32_t top_k, use_apd, weak_peak_radius;
  int32_t  weak_radius, weak_increment;
  uint32_t _pad0, _pad1;
};
static_assert(sizeof(Params) == 96, "Params 必须 96 B,与 apde_common.wgsl 一致");

struct Camera {
  float K0[4], K1[4], K2[4];
  float R0[4], R1[4], R2[4];
  float t[4], c[4];
  float depth_min, depth_max;
  int32_t width, height;
};
static_assert(sizeof(Camera) == 144, "Camera 必须 144 B,与 apde_common.wgsl 一致");

static std::vector<uint8_t> readFile(const char* p) {
  FILE* f = fopen(p, "rb");
  if (!f) { fprintf(stderr, "open failed: %s\n", p); exit(1); }
  fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
  std::vector<uint8_t> b(n);
  if (fread(b.data(), 1, n, f) != (size_t)n) { fprintf(stderr, "read short: %s\n", p); exit(1); }
  fclose(f); return b;
}

int main(int argc, const char** argv) {
  @autoreleasepool {
    const char* fx  = (argc > 1) ? argv[1] : "/tmp/fx";
    const char* lib = (argc > 2) ? argv[2] : "/tmp/chk/apde.metallib";
    const char* out = (argc > 3) ? argv[3] : "/tmp/fx/depth.f32";
    int W = 896, H = 512, NIMG = 5, ITERS = 3;
    float dmin = 2.607f, dmax = 8.982f;
    if (argc > 4) dmin = atof(argv[4]);
    if (argc > 5) dmax = atof(argv[5]);

    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    fprintf(stderr, "GPU: %s\n", [[dev name] UTF8String]);
    NSError* err = nil;
    id<MTLLibrary> L = [dev newLibraryWithURL:[NSURL fileURLWithPath:
        [NSString stringWithUTF8String:lib]] error:&err];
    if (!L) { fprintf(stderr, "lib: %s\n", [[err description] UTF8String]); return 1; }

    // 🔴 per-kernel binding remap 表(单帧闭环踩出来的必需品)
    //    naga/spirv-cross 会剥掉 kernel 未使用的 binding 并紧凑重编号 ⇒
    //    host 不能用固定 index 表,必须按名字绑。详见 tools/gen_binding_map.py。
    std::map<std::string, std::vector<std::string>> kBuf, kTex, kSmp;
    {
      char bp[512]; snprintf(bp, 512, "%s", lib);
      char* slash = strrchr(bp, '/');
      if (slash) strcpy(slash, "/bindings.txt"); else snprintf(bp, 512, "bindings.txt");
      FILE* f = fopen(bp, "r");
      if (!f) { fprintf(stderr, "缺 bindings.txt(%s)—— 先跑 gen_binding_map.py\n", bp); return 1; }
      char line[4096];
      auto split = [](const std::string& s) {
        std::vector<std::string> o; size_t p0 = 0;
        while (p0 <= s.size()) { size_t c = s.find(',', p0);
          if (c == std::string::npos) { if (p0 < s.size()) o.push_back(s.substr(p0)); break; }
          o.push_back(s.substr(p0, c - p0)); p0 = c + 1; }
        return o; };
      while (fgets(line, sizeof(line), f)) {
        std::string L(line); while (!L.empty() && (L.back()=='\n'||L.back()=='\r')) L.pop_back();
        size_t a = L.find('|'), b = L.find('|', a+1), c = L.find('|', b+1);
        if (a==std::string::npos||b==std::string::npos||c==std::string::npos) continue;
        std::string k = L.substr(0,a);
        kBuf[k] = split(L.substr(a+1, b-a-1));
        kTex[k] = split(L.substr(b+1, c-b-1));
        kSmp[k] = split(L.substr(c+1));
      }
      fclose(f);
      fprintf(stderr, "binding 表: %zu 个 kernel\n", kBuf.size());
    }

    auto mkpso = [&](const char* n) -> id<MTLComputePipelineState> {
      id<MTLFunction> f = [L newFunctionWithName:[NSString stringWithUTF8String:n]];
      if (!f) { fprintf(stderr, "missing kernel: %s\n", n); exit(1); }
      NSError* e = nil;
      id<MTLComputePipelineState> p = [dev newComputePipelineStateWithFunction:f error:&e];
      if (!p) { fprintf(stderr, "pso %s: %s\n", n, [[e description] UTF8String]); exit(1); }
      return p;
    };

    const size_t N = (size_t)W * H;

    // ── Params(第一轮:关 APD、关几何一致性)────────────────────
    Params P{};
    P.width = W; P.height = H; P.ref_index = 0; P.num_images = NIMG;
    P.num_anchors = 0; P.iter = 0;
    P.strong_radius = 5; P.strong_increment = 2;     // main.h:88-89
    P.rand_seed = 1u;
    P.depth_min = dmin; P.depth_max = dmax;
    P.geom_factor = 0.2f;
    P.geom_consistency = 0u; P.use_impetus = 0u;
    P.state = 0u;                                     // FIRST_INIT
    P.rotate_time = 4u; P.ransac_threshold = 0.005f;
    P.top_k = 4u; P.use_apd = 0u; P.weak_peak_radius = 4u;
    P.weak_radius = 5; P.weak_increment = 2;
    id<MTLBuffer> bP = [dev newBufferWithBytes:&P length:sizeof(P)
                                       options:MTLResourceStorageModeShared];

    auto camsRaw = readFile([[NSString stringWithFormat:@"%s/cams.bin", fx] UTF8String]);
    id<MTLBuffer> bCams = [dev newBufferWithBytes:camsRaw.data() length:camsRaw.size()
                                          options:MTLResourceStorageModeShared];

    auto mkbuf = [&](size_t bytes) {
      id<MTLBuffer> b = [dev newBufferWithLength:bytes options:MTLResourceStorageModeShared];
      memset(b.contents, 0, bytes); return b;
    };
    id<MTLBuffer> bMaps    = mkbuf(N * 4);            // packed_maps
    // 🔴 不能全清零!APD.cpp:656 的 else 分支(不用 APD 时):
    //      weak_info_host = Mat(h, w, CV_8UC1, Scalar(STRONG));
    //      confidence_host = Mat::ones(h, w, CV_8UC1);
    //    而 WEAK=0 / STRONG=1 / UNKNOWN=2(main.h:74)。
    //    全零 = 全 WEAK ⇒ CheckerboardFilterStrong 的 `!= WEAK` 恒假,
    //    三个中值滤波 pass 全部空转 —— 单帧闭环第一次跑就是这么发现的
    //    (三个 pass 前后数字一模一样)。
    {
      uint32_t* m = (uint32_t*)bMaps.contents;
      const uint32_t init = 1u /*weak_info=STRONG*/ | (1u << 8) /*confidence=1*/;
      for (size_t i = 0; i < N; ++i) m[i] = init;
    }
    id<MTLBuffer> bPlanes  = mkbuf(N * 16);           // plane_hypotheses vec4
    id<MTLBuffer> bCosts   = mkbuf(N * 4);
    id<MTLBuffer> bSelView = mkbuf(N * 4);
    id<MTLBuffer> bRand    = mkbuf(N * 4);            // 未用(确定性播种)
    id<MTLBuffer> bAnchors = mkbuf(N * 4);
    id<MTLBuffer> bAncMap  = mkbuf(N * 4);
    id<MTLBuffer> bVW      = mkbuf(N * 32);           // view_weights 8 u32/px
    id<MTLBuffer> bNearest = mkbuf(N * 4);
    id<MTLBuffer> bAncOut  = mkbuf(N * 4 * 9);
    id<MTLBuffer> bFitPl   = mkbuf(N * 16);

    // ── 纹理 ───────────────────────────────────────────────────
    MTLTextureDescriptor* td = [MTLTextureDescriptor
        texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA16Float
                                     width:W height:H mipmapped:NO];
    td.usage = MTLTextureUsageShaderRead; td.storageMode = MTLStorageModeShared;
    // ref_tex 是单张(参考图);src_tex 必须是数组,层号 = src_idx
    id<MTLTexture> refTex = [dev newTextureWithDescriptor:td];
    {
      auto px = readFile([[NSString stringWithFormat:@"%s/img_0.f16", fx] UTF8String]);
      [refTex replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0
                  withBytes:px.data() bytesPerRow:W*8];
    }
    MTLTextureDescriptor* sd2 = [MTLTextureDescriptor
        texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA16Float
                                     width:W height:H mipmapped:NO];
    sd2.textureType = MTLTextureType2DArray; sd2.arrayLength = 32;
    sd2.usage = MTLTextureUsageShaderRead; sd2.storageMode = MTLStorageModeShared;
    id<MTLTexture> srcArr = [dev newTextureWithDescriptor:sd2];
    // ⚠️ 层号约定:层 i 放 img_i,即层 1..4 是 4 个源视图,与 cams[1..4] 对齐。
    //    层 0 放参考图(不会被 NCC 用到,src_idx 从 1 起)。
    for (int i = 0; i < NIMG; ++i) {
      auto px = readFile([[NSString stringWithFormat:@"%s/img_%d.f16", fx, i] UTF8String]);
      [srcArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
                  withBytes:px.data() bytesPerRow:W*8 bytesPerImage:0];
    }
    // 深度纹理数组(第一轮 geom_consistency=0,内容不影响结果,但必须绑)
    MTLTextureDescriptor* dd = [MTLTextureDescriptor
        texture2DDescriptorWithPixelFormat:MTLPixelFormatR32Float
                                     width:W height:H mipmapped:NO];
    dd.textureType = MTLTextureType2DArray; dd.arrayLength = 32;
    dd.usage = MTLTextureUsageShaderRead; dd.storageMode = MTLStorageModeShared;
    id<MTLTexture> depthArr = [dev newTextureWithDescriptor:dd];

    MTLSamplerDescriptor* sl = [MTLSamplerDescriptor new];
    sl.minFilter = MTLSamplerMinMagFilterLinear; sl.magFilter = MTLSamplerMinMagFilterLinear;
    sl.sAddressMode = MTLSamplerAddressModeClampToEdge;
    sl.tAddressMode = MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> sampLin = [dev newSamplerStateWithDescriptor:sl];
    MTLSamplerDescriptor* sn = [MTLSamplerDescriptor new];
    sn.minFilter = MTLSamplerMinMagFilterNearest; sn.magFilter = MTLSamplerMinMagFilterNearest;
    sn.sAddressMode = MTLSamplerAddressModeClampToEdge;
    sn.tAddressMode = MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> sampNear = [dev newSamplerStateWithDescriptor:sn];

    id<MTLCommandQueue> Q = [dev newCommandQueue];

    // ⚠️ C3:workgroup 尺寸必须与 WGSL 的 @workgroup_size 一致(16×16)
    MTLSize tg = MTLSizeMake(16, 16, 1);

    // ⚠️ 红黑 pass 只覆盖一半行 ⇒ grid 高度减半(照抄原版 grid_size_half)
    // 名字 → 资源。名字必须与 apde_bindings.wgsl 里的变量名逐字一致。
    std::map<std::string, id<MTLBuffer>> byName = {
      {"P",bP},{"cams",bCams},{"packed_maps",bMaps},{"plane_hypotheses",bPlanes},
      {"costs",bCosts},{"selected_views",bSelView},{"rand_states",bRand},
      {"anchors",bAnchors},{"anchors_map",bAncMap},{"view_weights_buf",bVW},
      {"weak_nearest_buf",bNearest},{"anchors_out",bAncOut},{"fit_plane_hypos",bFitPl}};
    std::map<std::string, id<MTLTexture>> texByName;
    std::map<std::string, id<MTLSamplerState>> smpByName;
    std::string curKernel;

    auto dispatch = [&](id<MTLComputePipelineState> pso, bool half, uint32_t iter) {
      P.iter = iter; memcpy(bP.contents, &P, sizeof(P));
      id<MTLCommandBuffer> cb = [Q commandBuffer];
      id<MTLComputeCommandEncoder> e = [cb computeCommandEncoder];
      [e setComputePipelineState:pso];
      // 按名字绑,索引 = 该 kernel 实际使用列表里的位置
      const auto& bl = kBuf[curKernel]; const auto& tl = kTex[curKernel];
      const auto& sml = kSmp[curKernel];
      for (size_t i = 0; i < bl.size(); ++i) {
        id<MTLBuffer> b = byName[bl[i]];
        if (!b) { fprintf(stderr, "未知 buffer 名 %s(kernel %s)\n",
                          bl[i].c_str(), curKernel.c_str()); exit(1); }
        [e setBuffer:b offset:0 atIndex:i];
      }
      for (size_t i = 0; i < tl.size(); ++i) [e setTexture:texByName[tl[i]] atIndex:i];
      for (size_t i = 0; i < sml.size(); ++i) [e setSamplerState:smpByName[sml[i]] atIndex:i];
      [e dispatchThreads:MTLSizeMake(W, half ? H/2 : H, 1) threadsPerThreadgroup:tg];
      [e endEncoding]; [cb commit]; [cb waitUntilCompleted];
      return (cb.GPUEndTime - cb.GPUStartTime) * 1000.0;
    };

    // 分段自检:每个 pass 后统计 plane.w 的分布。
    // ⚠️ .w 的语义在 GetDepthandNormal 处切换:之前是「平面到原点距离 d」,
    //    之后才是「深度」。所以前后两段的数字不能用同一把尺子看。
    auto probe = [&](const char* tag, bool w_is_depth) {
      const float* pl = (const float*)bPlanes.contents;
      std::vector<float> v; v.reserve(N);
      for (size_t i = 0; i < N; ++i) { float d = pl[i*4+3];
        if (d == d && d > 0.0f && d < 1e6f) v.push_back(d); }
      if (v.empty()) { printf("      [%s] 无有效值\n", tag); return; }
      std::sort(v.begin(), v.end());
      auto q=[&](double f){ return v[(size_t)(f*(v.size()-1))]; };
      size_t inr = 0;
      if (w_is_depth) for (float x : v) if (x >= dmin && x <= dmax) inr++;
      printf("      [%s] 有效%.0f%%  p25 %.3f  p50 %.3f  p75 %.3f  p99 %.3f%s\n",
             tag, 100.0*v.size()/N, q(.25), q(.50), q(.75), q(.99),
             w_is_depth ? [&]{ static char b[64];
               snprintf(b,64,"  在范围内 %.0f%%", 100.0*inr/v.size()); return b; }() : "");
    };

    texByName = {{"ref_tex",refTex},{"src_tex",srcArr},{"depth_tex",depthArr}};
    smpByName = {{"samp",sampLin},{"samp_nearest",sampNear}};

    struct Stage { const char* name; bool half; };
    std::vector<Stage> pre  = {{"random_init_kernel", false}};
    std::vector<Stage> loop = {{"black_pixel_update_strong", true},
                               {"red_pixel_update_strong",   true}};
    std::vector<Stage> post = {{"depth_and_normal_kernel", false},
                               {"black_pixel_filter_strong", true},
                               {"red_pixel_filter_strong",   true},
                               {"depth_to_weak_kernel",   false},
                               {"local_refine_kernel",    false}};

    // 轮次开关:0=只跑 round0(FIRST_INIT/无APD),1=再跑 round1(REFINE_INIT/开APD)
    int rounds = (argc > 6) ? atoi(argv[6]) : 1;
    // 对照实验开关:round1 里关掉 APD 专属 kernel,只留 REFINE_INIT 的二次精修。
    // 用来把「APD 的贡献」与「多跑一轮精修的贡献」分开。
    int apdOn = (argc > 7) ? atoi(argv[7]) : 1;
    printf("═══ 单帧闭环(rounds=%d)═══\n", rounds);
    double total = 0;
    // 逐 pass dump 平面,供 numpy 算与真值的相关系数
    int dumpIdx = 0;
    auto dumpPlanes = [&](const char* tag) {
      char path[512]; snprintf(path, 512, "%s/planes_%02d_%s.f32", fx, dumpIdx++, tag);
      FILE* f = fopen(path, "wb"); fwrite(bPlanes.contents, 16, N, f); fclose(f);
    };
    bool wIsDepth = false;
    for (auto& s : pre)  { curKernel = s.name; double t = dispatch(mkpso(s.name), s.half, 0);
                           total += t; printf("  %-28s %8.2f ms\n", s.name, t);
                           probe(s.name, wIsDepth); dumpPlanes(s.name); }
    for (int i = 0; i < ITERS; ++i)
      for (auto& s : loop) { curKernel = s.name; double t = dispatch(mkpso(s.name), s.half, (uint32_t)i);
                             total += t; printf("  %-24s[%d] %8.2f ms\n", s.name, i, t);
                             probe(s.name, wIsDepth); dumpPlanes(s.name); }
    for (auto& s : post) { curKernel = s.name; double t = dispatch(mkpso(s.name), s.half, 0);
                           total += t; printf("  %-28s %8.2f ms\n", s.name, t);
                           if (!strcmp(s.name, "depth_and_normal_kernel")) wIsDepth = true;
                           probe(s.name, wIsDepth); dumpPlanes(s.name); }
    printf("  %-28s %8.2f ms\n", "── 合计 ──", total);

    // ══ Round 1:REFINE_INIT + use_APD ═════════════════════════
    // 照抄 main.cpp:313-320 的轮次配置:
    //   i==0 → state=FIRST_INIT, use_APD=false
    //   i>=1 → state=REFINE_INIT, use_APD=true,
    //          ransac_threshold = 0.01 - i*0.00125, rotate_time = min(2^i, 4)
    if (rounds >= 2) {
      printf("\n═══ Round 1(REFINE_INIT + use_APD)═══\n");

      // 🔴 anchors_map 必须 host 算(APD.cpp:627-639):
      //    对 WEAK 像素给递增序号,非 WEAK 给 -1;anchors 缓冲按 weak_count 分配。
      //    weak_info 来自上一轮 DepthToWeak 的结果(packed_maps 低 8 位)。
      int weak_count = 0;
      {
        const uint32_t* m = (const uint32_t*)bMaps.contents;
        int32_t* am = (int32_t*)bAncMap.contents;
        for (size_t i = 0; i < N; ++i) {
          if ((m[i] & 0xFFu) == 0u /*WEAK*/) am[i] = weak_count++;
          else am[i] = -1;
        }
        printf("  Weak count: %d / %zu = %.2f%%\n", weak_count, N, 100.0*weak_count/N);
      }
      if (weak_count == 0) {
        printf("  ⚠️ 没有 WEAK 像素,APD 支无事可做(上一轮 DepthToWeak 把全图判成 STRONG)\n");
      } else {
        // anchors_out 按 weak_count*ANCHOR_NUM 重新分配(原版 cudaMalloc 同)
        bAncOut = [dev newBufferWithLength:(size_t)weak_count*9*4
                                   options:MTLResourceStorageModeShared];
        memset(bAncOut.contents, 0xFF, (size_t)weak_count*9*4);
        byName["anchors_out"] = bAncOut;

        P.state = 1u;            // REFINE_INIT
        P.use_apd = 1u;
        P.ransac_threshold = 0.01f - 1*0.00125f;
        P.rotate_time = 2u;      // min(2^1, 4)
        P.weak_peak_radius = 6u;

        P.use_apd = apdOn ? 1u : 0u;
        std::vector<Stage> apd_pre;
        if (apdOn) apd_pre = {{"nearest_strong_kernel", false},
                              {"gen_anchors_kernel",    false},
                              {"neighbour_update_kernel", false},
                              {"random_init_kernel",    false}};
        else       apd_pre = {{"random_init_kernel",    false}};
        // 锚点自检:GenAnchors 之后统计 weak_reliable 与真实锚点数
        auto anchorProbe = [&]() {
          const uint32_t* m = (const uint32_t*)bMaps.contents;
          size_t rel = 0, wk = 0;
          for (size_t i = 0; i < N; ++i) {
            if ((m[i] & 0xFFu) == 0u) { wk++; if (((m[i]>>24)&0xFFu) == 1u) rel++; }
          }
          const uint32_t* a = (const uint32_t*)bAncOut.contents;
          size_t filled = 0, tot = (size_t)weak_count*9;
          for (size_t i = 0; i < tot; ++i) if (a[i] != 0xFFFFFFFFu) filled++;
          printf("      [锚点自检] WEAK %zu, weak_reliable=1 的 %zu (%.1f%%), "
                 "锚点槽非空 %zu/%zu (%.1f%%)\n",
                 wk, rel, wk?100.0*rel/wk:0.0, filled, tot, tot?100.0*filled/tot:0.0);
        };

        std::vector<Stage> apd_loop;
        if (apdOn) apd_loop = {{"black_pixel_update_strong", true},
                               {"red_pixel_update_strong",   true},
                               {"ransac_fit_plane_kernel",   false},
                               {"black_pixel_update_weak",   true},
                               {"red_pixel_update_weak",     true}};
        else       apd_loop = {{"black_pixel_update_strong", true},
                               {"red_pixel_update_strong",   true}};
        wIsDepth = false;
        for (auto& s : apd_pre) { curKernel = s.name;
          double t = dispatch(mkpso(s.name), s.half, 0); total += t;
          printf("  %-28s %8.2f ms\n", s.name, t); probe(s.name, wIsDepth); dumpPlanes(s.name);
          if (!strcmp(s.name, "gen_anchors_kernel")) anchorProbe(); }
        for (int i = 0; i < ITERS; ++i)
          for (auto& s : apd_loop) { curKernel = s.name;
            double t = dispatch(mkpso(s.name), s.half, (uint32_t)i); total += t;
            printf("  %-24s[%d] %8.2f ms\n", s.name, i, t); probe(s.name, wIsDepth); dumpPlanes(s.name); }
        for (auto& s : post) { curKernel = s.name;
          double t = dispatch(mkpso(s.name), s.half, 0); total += t;
          printf("  %-28s %8.2f ms\n", s.name, t);
          if (!strcmp(s.name, "depth_and_normal_kernel")) wIsDepth = true;
          probe(s.name, wIsDepth); dumpPlanes(s.name); }
        printf("  %-28s %8.2f ms\n", "── 两轮合计 ──", total);
      }
    }

    // ══ geom_consistency 轮(main.cpp:333-348 的内层 j 循环)═══════
    //   state=REFINE_ITER, geom_consistency=true, weak_peak_radius=max(4-2j,2)
    // 🔴 前置:depth_tex 必须装上**各源视图自己的深度图**。
    //    单帧闭环里我们只算了参考帧的深度,所以这里退而求其次:
    //    把参考帧深度投影不到别的视图 —— 真正做法是每帧都跑一遍再互填。
    //    ⇒ 单帧闭环只能验证 kernel 跑得通、数值不炸,**不能验证几何收益**。
    //      真正的几何一致性收益要等 414 帧批量那一步。
    int geomIter = (argc > 8) ? atoi(argv[8]) : 0;
    if (geomIter > 0) {
      printf("\n═══ geom_consistency 轮(REFINE_ITER)═══\n");
      // 把当前参考帧深度写进 depth_tex 的第 0 层(自一致性,弱验证)
      {
        const float* pl = (const float*)bPlanes.contents;
        std::vector<float> dep(N);
        for (size_t i = 0; i < N; ++i) dep[i] = pl[i*4+3];
        for (int L = 0; L < NIMG; ++L)
          [depthArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:L
                        withBytes:dep.data() bytesPerRow:W*4 bytesPerImage:0];
        printf("  ⚠️ depth_tex 各层暂填同一张参考帧深度(单帧闭环的局限)\n");
      }
      P.state = 2u;                 // REFINE_ITER
      P.geom_consistency = 1u;
      P.use_impetus = 1u;
      for (int j = 0; j < geomIter; ++j) {
        P.weak_peak_radius = (uint32_t)std::max(4 - 2*j, 2);
        std::vector<Stage> gl = {{"random_init_kernel", false},
                                 {"black_pixel_update_strong", true},
                                 {"red_pixel_update_strong",   true}};
        for (auto& s : gl) { curKernel = s.name;
          double t = dispatch(mkpso(s.name), s.half, (uint32_t)j); total += t;
          printf("  %-24s[%d] %8.2f ms\n", s.name, j, t); }
        for (auto& s : post) { curKernel = s.name;
          double t = dispatch(mkpso(s.name), s.half, 0); total += t; }
        probe("geom_iter_done", true);
      }
    }

    // ── 导出深度图(plane.w 在 GetDepthandNormal 之后就是深度)──
    const float* pl = (const float*)bPlanes.contents;
    std::vector<float> depth(N);
    size_t valid = 0; double sum = 0; float lo = 1e30f, hi = -1e30f;
    for (size_t i = 0; i < N; ++i) {
      float d = pl[i*4+3];
      depth[i] = d;
      if (d > 0.0f && d < 1e6f && d == d) { valid++; sum += d; lo = std::min(lo,d); hi = std::max(hi,d); }
    }
    FILE* f = fopen(out, "wb"); fwrite(depth.data(), 4, N, f); fclose(f);

    { // costs 分布:CheckerboardFilterStrong 有 `costs[center] < 0.001 return` 的早退
      const float* c = (const float*)bCosts.contents;
      std::vector<float> v(c, c + N); std::sort(v.begin(), v.end());
      size_t tiny = 0; for (float x : v) if (x < 0.001f) tiny++;
      printf("\n  costs 分布: p25 %.4f  p50 %.4f  p75 %.4f   <0.001 占 %.1f%%\n",
             v[N/4], v[N/2], v[3*N/4], 100.0*tiny/N);
    }
    printf("\n═══ 深度图自检 ═══\n");
    printf("  有效像素 %.1f%% (%zu / %zu)\n", 100.0*valid/N, valid, N);
    if (valid) printf("  深度 min %.3f  max %.3f  mean %.3f   (fixture 范围 %.3f–%.3f)\n",
                      lo, hi, sum/valid, dmin, dmax);
    printf("  → %s\n", out);
    // 🔴 判据:有效率过低或深度跑到范围外,说明几何有错,别急着看图
    if (valid < N/2)          printf("  🔴 有效率 < 50%%,几何几乎肯定有错\n");
    else if (lo < dmin*0.5f || hi > dmax*2.0f)
                              printf("  🔴 深度越界,几何有错\n");
    else                      printf("  ✅ 通过粗筛(不代表数值对,还要看图)\n");
    return 0;
  }
}
