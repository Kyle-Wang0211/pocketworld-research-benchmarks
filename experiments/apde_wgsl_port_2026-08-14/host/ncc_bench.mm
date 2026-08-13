// APDe-MVS WGSL spike:host 载具(Metal)
//
// 目的:量出 ComputeBilateralNCCOld 在 Apple GPU 上的真实吞吐,
//       用来外推 APDe-MVS 整体能否进 30s 预算。
//
// 外推依据(全部从 APDe-MVS 源码取,非估计):
//   max_iterations   = 3      (main.h:81 / main.cpp:322)
//   num_images       = 5      ⇒ 每次算 4 个源视图 (ComputeMultiViewCostVectorOld)
//   strong_radius=5, increment=2 ⇒ 窗口 6×6 = 36 次取样/NCC
//   CheckerboardPropagationStrong 调 ComputeMultiViewCostVector 9 次
//   ⇒ 每参考图 NCC 次数 ≈ 像素 × 3 × 9 × 4 = 像素 × 108
//
// 本载具一次 dispatch = 每像素 1 次 NCC(1 假设 × 1 视图),
// 所以"每参考图耗时 ≈ 单次 dispatch × 108"。
//
// ⚠️ 这是 spike。GPL 血统取证未完成前不得进产品树。

#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <vector>
#include <cstdio>
#include <cmath>
#include <algorithm>

// 与 WGSL 的 Params 逐字段对齐(std140/std430 打包)
// ⚠️ 必须与 wgsl/apde_common.wgsl 的 Params 逐字段一致。
//    错位不会报错,会静默读到垃圾数据 —— 改一边必须改另一边。
struct Params {
  uint32_t width, height, ref_index, num_images;
  uint32_t num_anchors, iter;
  int32_t  strong_radius, strong_increment;
  uint32_t rand_seed, _pad_p0;
};

// ⚠️ 必须与 wgsl/apde_common.wgsl 的 Camera 逐字段一致:
//    8 个 vec4 + 2 f32 + 2 i32 = 144 字节
struct Camera {
  float K0[4], K1[4], K2[4];
  float R0[4], R1[4], R2[4];
  float t[4];
  float c[4];               // 相机中心,Get3DPointonWorld_cu 用
  float depth_min, depth_max;
  int32_t width, height;
};

static void fill_identity_camera(Camera& c, int w, int h, float tx) {
  float fx = 900.0f, fy = 900.0f, cx = w * 0.5f, cy = h * 0.5f;
  c.K0[0]=fx; c.K0[1]=0;  c.K0[2]=cx; c.K0[3]=0;
  c.K1[0]=0;  c.K1[1]=fy; c.K1[2]=cy; c.K1[3]=0;
  c.K2[0]=0;  c.K2[1]=0;  c.K2[2]=1;  c.K2[3]=0;
  c.R0[0]=1; c.R0[1]=0; c.R0[2]=0; c.R0[3]=0;
  c.R1[0]=0; c.R1[1]=1; c.R1[2]=0; c.R1[3]=0;
  c.R2[0]=0; c.R2[1]=0; c.R2[2]=1; c.R2[3]=0;
  c.t[0]=tx; c.t[1]=0; c.t[2]=0; c.t[3]=0;   // 只有基线平移
  // c = -R^T·t;R=I 时即 -t
  c.c[0]=-tx; c.c[1]=0; c.c[2]=0; c.c[3]=0;
  c.depth_min=0.5f; c.depth_max=10.0f;
  c.width=w; c.height=h;
}

int main(int argc, const char** argv) {
  @autoreleasepool {
    int W = (argc > 1) ? atoi(argv[1]) : 896;
    int H = (argc > 2) ? atoi(argv[2]) : 512;
    // sa_mask 非零比例:决定走分支 A(规则窗)还是分支 B(自适应形变)
    float weak_ratio = (argc > 3) ? atof(argv[3]) : 0.0f;

    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    if (!dev) { fprintf(stderr, "no Metal device\n"); return 1; }
    fprintf(stderr, "GPU: %s\n", [[dev name] UTF8String]);

    NSError* err = nil;
    NSString* libPath = [NSString stringWithUTF8String:
      (argc > 4) ? argv[4] : "/tmp/ncc_sc.metallib"];
    id<MTLLibrary> lib = [dev newLibraryWithURL:[NSURL fileURLWithPath:libPath] error:&err];
    if (!lib) { fprintf(stderr, "load metallib failed: %s\n", [[err description] UTF8String]); return 1; }

    id<MTLFunction> fn = [lib newFunctionWithName:@"ncc_bench"];
    if (!fn) { fprintf(stderr, "no ncc_bench entry\n"); return 1; }
    id<MTLComputePipelineState> pso = [dev newComputePipelineStateWithFunction:fn error:&err];
    if (!pso) { fprintf(stderr, "pipeline failed: %s\n", [[err description] UTF8String]); return 1; }

    fprintf(stderr, "maxTotalThreadsPerThreadgroup = %lu, threadExecutionWidth = %lu\n",
            (unsigned long)pso.maxTotalThreadsPerThreadgroup,
            (unsigned long)pso.threadExecutionWidth);

    const size_t N = (size_t)W * H;

    // buffer(0) Params
    Params P{};
    P.width = W; P.height = H; P.ref_index = 0; P.num_images = 5;
    P.num_anchors = 0;
    P.iter = (argc > 5) ? (uint32_t)atoi(argv[5]) : 1u;   // 每像素重复几次 NCC
    P.strong_radius = 5; P.strong_increment = 2;   // 源码默认
    P.rand_seed = 1u; P._pad_p0 = 0u;              // 确定性种子(默认固定)
    id<MTLBuffer> bufP = [dev newBufferWithBytes:&P length:sizeof(P)
                                         options:MTLResourceStorageModeShared];

    // buffer(1) cams[32]
    std::vector<Camera> cams(32);
    for (int i = 0; i < 32; ++i) fill_identity_camera(cams[i], W, H, i * 0.08f);
    id<MTLBuffer> bufCams = [dev newBufferWithBytes:cams.data()
                                             length:cams.size()*sizeof(Camera)
                                            options:MTLResourceStorageModeShared];

    // buffer(2) packed_maps —— sa_mask 在第 16..23 位
    std::vector<uint32_t> maps(N, 0u);
    if (weak_ratio > 0.0f) {
      uint32_t seed = 12345u;
      for (size_t i = 0; i < N; ++i) {
        seed = seed * 1664525u + 1013904223u;
        if ((seed >> 8) % 1000u < (uint32_t)(weak_ratio * 1000.0f)) {
          maps[i] = (1u + ((seed >> 20) % 3u)) << 16;   // 非零 sa_id
        }
      }
    }
    id<MTLBuffer> bufMaps = [dev newBufferWithBytes:maps.data()
                                             length:maps.size()*sizeof(uint32_t)
                                            options:MTLResourceStorageModeShared];

    // buffer(3) costs
    id<MTLBuffer> bufCosts = [dev newBufferWithLength:N*sizeof(float)
                                              options:MTLResourceStorageModeShared];

    // texture(0/1) —— C4:用可过滤的 rgba16float
    MTLTextureDescriptor* td = [MTLTextureDescriptor
        texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA16Float
                                     width:W height:H mipmapped:NO];
    td.usage = MTLTextureUsageShaderRead;
    td.storageMode = MTLStorageModeShared;
    id<MTLTexture> texRef = [dev newTextureWithDescriptor:td];
    id<MTLTexture> texSrc = [dev newTextureWithDescriptor:td];

    // 填真实感纹理:带结构的伪随机(不是常数,否则方差为 0 会全部走 early-out,
    // 测出来的数字会假性偏快)
    {
      std::vector<uint16_t> px(N * 4);
      auto h2 = [](float v)->uint16_t {           // f32 → f16
        uint32_t x; memcpy(&x, &v, 4);
        uint32_t s=(x>>16)&0x8000, e=((x>>23)&0xFF), m=x&0x7FFFFF;
        int ne = (int)e - 127 + 15;
        if (ne <= 0) return (uint16_t)s;
        if (ne >= 31) return (uint16_t)(s|0x7C00);
        return (uint16_t)(s | (ne<<10) | (m>>13));
      };
      for (size_t i = 0; i < N; ++i) {
        int x = (int)(i % W), y = (int)(i / W);
        float v = 0.5f + 0.35f*sinf(x*0.11f)*cosf(y*0.13f) + 0.1f*sinf((x+y)*0.37f);
        uint16_t hv = h2(v);
        px[i*4+0]=hv; px[i*4+1]=hv; px[i*4+2]=hv; px[i*4+3]=h2(1.0f);
      }
      MTLRegion rg = MTLRegionMake2D(0,0,W,H);
      [texRef replaceRegion:rg mipmapLevel:0 withBytes:px.data() bytesPerRow:W*8];
      // src 图给一点位移,模拟视差
      for (size_t i = 0; i < N; ++i) {
        int x = (int)(i % W), y = (int)(i / W);
        float v = 0.5f + 0.35f*sinf((x+3)*0.11f)*cosf(y*0.13f) + 0.1f*sinf((x+3+y)*0.37f);
        uint16_t hv = h2(v);
        px[i*4+0]=hv; px[i*4+1]=hv; px[i*4+2]=hv; px[i*4+3]=h2(1.0f);
      }
      [texSrc replaceRegion:rg mipmapLevel:0 withBytes:px.data() bytesPerRow:W*8];
    }

    MTLSamplerDescriptor* sd = [MTLSamplerDescriptor new];
    sd.minFilter = MTLSamplerMinMagFilterLinear;   // C4:硬件双线性
    sd.magFilter = MTLSamplerMinMagFilterLinear;
    sd.sAddressMode = MTLSamplerAddressModeClampToEdge;
    sd.tAddressMode = MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> samp = [dev newSamplerStateWithDescriptor:sd];

    id<MTLCommandQueue> q = [dev newCommandQueue];

    // C3:workgroup 尺寸必须与 WGSL 里的 @workgroup_size 一致 —— 这就是
    //     "单一数据源"要解决的问题。这里手写 16×16 是 spike 的临时做法,
    //     产品化时必须由构建期从 WGSL 生成。
    MTLSize tg = MTLSizeMake(16, 16, 1);
    MTLSize grid = MTLSizeMake(W, H, 1);

    auto run_once = [&]() -> double {
      id<MTLCommandBuffer> cb = [q commandBuffer];
      id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
      [enc setComputePipelineState:pso];
      [enc setBuffer:bufP     offset:0 atIndex:0];
      [enc setBuffer:bufCams  offset:0 atIndex:1];
      [enc setBuffer:bufMaps  offset:0 atIndex:2];
      [enc setBuffer:bufCosts offset:0 atIndex:3];
      [enc setTexture:texRef atIndex:0];
      [enc setTexture:texSrc atIndex:1];
      [enc setSamplerState:samp atIndex:0];
      [enc dispatchThreads:grid threadsPerThreadgroup:tg];
      [enc endEncoding];
      [cb commit];
      [cb waitUntilCompleted];
      return (cb.GPUEndTime - cb.GPUStartTime) * 1000.0;   // ms
    };

    for (int i = 0; i < 5; ++i) run_once();              // 预热
    std::vector<double> ts;
    for (int i = 0; i < 30; ++i) ts.push_back(run_once());
    std::sort(ts.begin(), ts.end());
    double med = ts[ts.size()/2], best = ts.front(), worst = ts.back();

    // 有效性自检:代价必须有分布,不能全是 COST_MAX(=2.0),否则说明
    // 内循环被 early-out 跳过了,数字是假的。
    const float* c = (const float*)bufCosts.contents;
    size_t maxed = 0; double sum = 0;
    for (size_t i = 0; i < N; ++i) { if (c[i] >= 1.999f) maxed++; sum += c[i]; }
    double maxed_pct = 100.0 * maxed / N;

    const double NCC_PER_REF = 3.0 * 9.0 * 4.0;   // 迭代 × 假设 × 源视图 = 108

    printf("\n");
    printf("═══ APDe-MVS NCC kernel — Metal 实测 ═══\n");
    printf("  分辨率        %d × %d  (%.3f MP)   repeat=%u\n", W, H, N/1e6, P.iter);
    printf("  弱纹理比例    %.0f%%  (%s)\n", weak_ratio*100,
           weak_ratio > 0 ? "混合分支 A/B" : "全走分支 A 规则窗");
    printf("  单次 dispatch 中位 %.3f ms   最好 %.3f   最差 %.3f\n", med, best, worst);
    printf("  ── 有效性自检 ──\n");
    printf("  代价=COST_MAX 占比 %.1f%%  (过高说明内循环被跳过,数字不可信)\n", maxed_pct);
    printf("  代价均值 %.4f\n", sum / N);
    printf("  ── 外推 (×108 = 3 迭代 × 9 假设 × 4 源视图) ──\n");
    printf("  每参考图      %.2f ms\n", med * NCC_PER_REF);
    printf("  ⚠️ 这只是 NCC 一项,不含传播/精修/融合的其余开销\n");
    return 0;
  }
}
