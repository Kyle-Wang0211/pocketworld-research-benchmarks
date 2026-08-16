// APDe-MVS WGSL → iPhone 真机打点
//
// 目的:拿到两个决定生死的数,与 CasDiffMVS 的 A16 认证数字(710ms / 485MB)对齐口径。
//   1. ms/帧 @ 896×512(出货档 = 两遍简版;138 帧实测它与完整流水精度相同)
//   2. 内存峰值 —— 用 **phys_footprint**,因为 jetsam 判定用的就是它,
//      不是 resident_size。iPhone 11 的预算是 1700MB 减去 App 自身约 1020MB。
//
// 与 host 版(apde_batch.mm)的差异,都是为了让数字可信:
//   a. 逐帧耗时全部打印 ⇒ 热降频会表现为后段单帧变慢,单一均值会把它藏起来
//   b. 后台线程每 20ms 采样 phys_footprint 取峰值 ⇒ 峰值在帧内,采样太疏会漏
//   c. GPU 分配量单独精确累加 ⇒ 与 host 侧 fixture 加载开销分开记账,
//      否则测的是我的测试脚手架不是算法
//   d. 不写 depth/conf 落盘(只测速度内存,省 IO 干扰)
//
// ⚠️ 本 app 用独立 bundle id,与产品 com.kyle.PocketWorld 完全无关,不碰其数据。

#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#include <mach/mach.h>
#include <pthread.h>
#include <vector>
#include <map>
#include <string>
#include <atomic>
#include <algorithm>

// ── 与 WGSL 侧的 ABI 契约(错位不报错只静默读垃圾,故两边都上 static_assert)──
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
static_assert(sizeof(Params) == 96, "Params 96B");
struct Camera {
  float K0[4], K1[4], K2[4], R0[4], R1[4], R2[4], t[4], c[4];
  float depth_min, depth_max; int32_t width, height;
};
static_assert(sizeof(Camera) == 144, "Camera 144B");

// ── phys_footprint 采样(jetsam 口径)──────────────────────────
static size_t phys_footprint_now() {
  task_vm_info_data_t info; mach_msg_type_number_t cnt = TASK_VM_INFO_COUNT;
  if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &cnt) != KERN_SUCCESS)
    return 0;
  return (size_t)info.phys_footprint;
}
static std::atomic<size_t> g_peak{0};
static std::atomic<bool>   g_sampling{false};
static void* sampler(void*) {
  while (g_sampling.load()) {
    size_t v = phys_footprint_now();
    size_t p = g_peak.load();
    while (v > p && !g_peak.compare_exchange_weak(p, v)) {}
    usleep(20000);   // 20ms
  }
  return nullptr;
}

static NSString* res(NSString* n) {
  return [[NSBundle mainBundle] pathForResource:n ofType:nil];
}
static std::vector<uint8_t> rd(NSString* path) {
  NSData* d = [NSData dataWithContentsOfFile:path];
  if (!d) { NSLog(@"[APDE] 读不到 %@", path); return {}; }
  std::vector<uint8_t> b(d.length);
  memcpy(b.data(), d.bytes, d.length);
  return b;
}

static void run_bench() {
  @autoreleasepool {
    const int W = 896, H = 512, NIMG = 5, ITERS = 3;
    const size_t N = (size_t)W * H;

    NSLog(@"[APDE] ══ APDe-MVS WGSL 真机打点 ══");
    NSLog(@"[APDE] 设备 %@  iOS %@", [[UIDevice currentDevice] model],
          [[UIDevice currentDevice] systemVersion]);

    auto imgs  = rd(res(@"images.f16"));
    auto camsR = rd(res(@"cams.f32"));
    auto nbR   = rd(res(@"neighbors.i32"));
    if (imgs.empty() || camsR.empty() || nbR.empty()) { NSLog(@"[APDE] fixture 缺失,退出"); return; }
    int NF = (int)(camsR.size() / (36 * 4));
    const uint16_t* IM = (const uint16_t*)imgs.data();
    const float* CM = (const float*)camsR.data();
    const int32_t* NB = (const int32_t*)nbR.data();
    NSLog(@"[APDE] fixture %d 帧 @ %d×%d", NF, W, H);

    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    NSLog(@"[APDE] GPU %@", [dev name]);
    NSError* e = nil;
    id<MTLLibrary> L = [dev newLibraryWithURL:[NSURL fileURLWithPath:res(@"apde_ios.metallib")]
                                        error:&e];
    if (!L) { NSLog(@"[APDE] metallib 失败 %@", e); return; }

    // per-kernel binding remap(naga/spirv-cross 会剥掉未用 binding 并重编号)
    std::map<std::string, std::vector<std::string>> kBuf, kTex, kSmp;
    {
      NSString* txt = [NSString stringWithContentsOfFile:res(@"bindings.txt")
                                                encoding:NSUTF8StringEncoding error:nil];
      auto split = [](const std::string& s) {
        std::vector<std::string> o; size_t p = 0;
        while (p <= s.size()) { size_t c = s.find(',', p);
          if (c == std::string::npos) { if (p < s.size()) o.push_back(s.substr(p)); break; }
          o.push_back(s.substr(p, c - p)); p = c + 1; } return o; };
      for (NSString* line in [txt componentsSeparatedByString:@"\n"]) {
        std::string S = [line UTF8String] ?: "";
        size_t a = S.find('|'); if (a == std::string::npos) continue;
        size_t b = S.find('|', a+1), c = S.find('|', b+1);
        if (b == std::string::npos || c == std::string::npos) continue;
        std::string k = S.substr(0, a);
        kBuf[k] = split(S.substr(a+1, b-a-1));
        kTex[k] = split(S.substr(b+1, c-b-1));
        kSmp[k] = split(S.substr(c+1));
      }
    }
    std::map<std::string, id<MTLComputePipelineState>> psos;
    auto pso = [&](const std::string& n) {
      auto it = psos.find(n); if (it != psos.end()) return it->second;
      id<MTLFunction> f = [L newFunctionWithName:[NSString stringWithUTF8String:n.c_str()]];
      NSError* er = nil;
      id<MTLComputePipelineState> p = [dev newComputePipelineStateWithFunction:f error:&er];
      if (!p) { NSLog(@"[APDE] pso %s 失败 %@", n.c_str(), er); exit(1); }
      psos[n] = p; return p;
    };

    // ── GPU 资源(逐字节记账,与 host fixture 开销分开)──
    size_t gpu_bytes = 0;
    Params P{};
    P.width=W; P.height=H; P.num_images=NIMG;
    P.strong_radius=5; P.strong_increment=2; P.rand_seed=1u;
    P.geom_factor=0.2f; P.geom_consistency=0u; P.use_impetus=0u;
    P.state=0u; P.rotate_time=4u; P.ransac_threshold=0.005f;
    P.top_k=4u; P.use_apd=0u; P.weak_peak_radius=6u;
    P.weak_radius=5; P.weak_increment=2;
    id<MTLBuffer> bP = [dev newBufferWithLength:sizeof(P) options:MTLResourceStorageModeShared];
    id<MTLBuffer> bCams = [dev newBufferWithLength:32*sizeof(Camera) options:MTLResourceStorageModeShared];
    gpu_bytes += sizeof(P) + 32*sizeof(Camera);
    auto mk = [&](size_t n){ gpu_bytes += n;
      id<MTLBuffer> b = [dev newBufferWithLength:n options:MTLResourceStorageModeShared];
      memset(b.contents, 0, n); return b; };
    id<MTLBuffer> bMaps=mk(N*4), bPlanes=mk(N*16), bCosts=mk(N*4), bSel=mk(N*4),
                  bRand=mk(N*4), bAnch=mk(N*4), bAncMap=mk(N*4), bVW=mk(N*32),
                  bNear=mk(N*4), bAncOut=mk(N*36), bFit=mk(N*16);

    MTLTextureDescriptor* td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatRGBA16Float width:W height:H mipmapped:NO];
    td.usage = MTLTextureUsageShaderRead; td.storageMode = MTLStorageModeShared;
    id<MTLTexture> refTex = [dev newTextureWithDescriptor:td];
    gpu_bytes += N*8;
    MTLTextureDescriptor* sd = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatRGBA16Float width:W height:H mipmapped:NO];
    sd.textureType = MTLTextureType2DArray; sd.arrayLength = NIMG;
    sd.usage = MTLTextureUsageShaderRead; sd.storageMode = MTLStorageModeShared;
    id<MTLTexture> srcArr = [dev newTextureWithDescriptor:sd];
    gpu_bytes += N*8*NIMG;
    MTLTextureDescriptor* dd = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatR32Float width:W height:H mipmapped:NO];
    dd.textureType = MTLTextureType2DArray; dd.arrayLength = NIMG;
    dd.usage = MTLTextureUsageShaderRead; dd.storageMode = MTLStorageModeShared;
    id<MTLTexture> depArr = [dev newTextureWithDescriptor:dd];
    gpu_bytes += N*4*NIMG;

    MTLSamplerDescriptor* s1 = [MTLSamplerDescriptor new];
    s1.minFilter=MTLSamplerMinMagFilterLinear; s1.magFilter=MTLSamplerMinMagFilterLinear;
    s1.sAddressMode=MTLSamplerAddressModeClampToEdge; s1.tAddressMode=MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> sampL = [dev newSamplerStateWithDescriptor:s1];
    MTLSamplerDescriptor* s2 = [MTLSamplerDescriptor new];
    s2.minFilter=MTLSamplerMinMagFilterNearest; s2.magFilter=MTLSamplerMinMagFilterNearest;
    s2.sAddressMode=MTLSamplerAddressModeClampToEdge; s2.tAddressMode=MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> sampN = [dev newSamplerStateWithDescriptor:s2];

    NSLog(@"[APDE] GPU 常驻分配 %.1f MB  (与 CasDiffMVS 485MB 同口径对比项)",
          gpu_bytes/1048576.0);

    std::map<std::string,id<MTLBuffer>> byName = {
      {"P",bP},{"cams",bCams},{"packed_maps",bMaps},{"plane_hypotheses",bPlanes},
      {"costs",bCosts},{"selected_views",bSel},{"rand_states",bRand},
      {"anchors",bAnch},{"anchors_map",bAncMap},{"view_weights_buf",bVW},
      {"weak_nearest_buf",bNear},{"anchors_out",bAncOut},{"fit_plane_hypos",bFit}};
    std::map<std::string,id<MTLTexture>> texByName = {
      {"ref_tex",refTex},{"src_tex",srcArr},{"depth_tex",depArr}};
    std::map<std::string,id<MTLSamplerState>> smpByName = {{"samp",sampL},{"samp_nearest",sampN}};

    id<MTLCommandQueue> Q = [dev newCommandQueue];
    std::vector<uint16_t> rgba(N*4);
    std::vector<float> passA((size_t)NF*N);
    const uint16_t ONE_F16 = 0x3C00;

    // 逐 kernel GPU 时间累计
    std::map<std::string,double> kms;
    auto run = [&](const std::string& k, bool half, uint32_t it) {
      P.iter = it; memcpy(bP.contents, &P, sizeof(P));
      id<MTLCommandBuffer> cb = [Q commandBuffer];
      id<MTLComputeCommandEncoder> en = [cb computeCommandEncoder];
      [en setComputePipelineState:pso(k)];
      const auto& bl=kBuf[k]; const auto& tl=kTex[k]; const auto& sl=kSmp[k];
      for (size_t i=0;i<bl.size();++i) {
        id<MTLBuffer> b = byName[bl[i]];
        if (!b) { NSLog(@"[APDE] 未知 buffer %s@%s", bl[i].c_str(), k.c_str()); exit(1); }
        [en setBuffer:b offset:0 atIndex:i];
      }
      for (size_t i=0;i<tl.size();++i) [en setTexture:texByName[tl[i]] atIndex:i];
      for (size_t i=0;i<sl.size();++i) [en setSamplerState:smpByName[sl[i]] atIndex:i];
      [en dispatchThreads:MTLSizeMake(W, half?H/2:H, 1)
            threadsPerThreadgroup:MTLSizeMake(16,16,1)];
      [en endEncoding]; [cb commit]; [cb waitUntilCompleted];
      kms[k] += ([cb GPUEndTime] - [cb GPUStartTime]) * 1000.0;
    };

    g_sampling = true; g_peak = phys_footprint_now();
    pthread_t th; pthread_create(&th, nullptr, sampler, nullptr);

    std::vector<double> frame_ms;
    double t0 = CFAbsoluteTimeGetCurrent();
    for (int pass=0; pass<2; ++pass) {
      NSLog(@"[APDE] ── Pass %c ──", 'A'+pass);
      for (int f=0; f<NF; ++f) {
        double tf = CFAbsoluteTimeGetCurrent();
        int view[NIMG]; view[0]=f;
        for (int i=0;i<NIMG-1;++i) view[i+1]=NB[(size_t)f*4+i];

        Camera* cs=(Camera*)bCams.contents; memset(cs,0,32*sizeof(Camera));
        for (int i=0;i<NIMG;++i) {
          const float* c = CM+(size_t)view[i]*36; Camera& C=cs[i];
          for (int r=0;r<3;++r) {
            C.K0[r]=c[r]; C.K1[r]=c[3+r]; C.K2[r]=c[6+r];
            C.R0[r]=c[9+r]; C.R1[r]=c[12+r]; C.R2[r]=c[15+r];
            C.t[r]=c[18+r]; C.c[r]=c[21+r];
          }
          C.depth_min=c[24]; C.depth_max=c[25]; C.width=W; C.height=H;
        }
        P.depth_min=CM[(size_t)f*36+24]; P.depth_max=CM[(size_t)f*36+25];

        for (int i=0;i<NIMG;++i) {
          const uint16_t* g = IM+(size_t)view[i]*N;
          for (size_t p=0;p<N;++p) { rgba[p*4]=g[p]; rgba[p*4+1]=g[p];
                                     rgba[p*4+2]=g[p]; rgba[p*4+3]=ONE_F16; }
          if (i==0) [refTex replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0
                               withBytes:rgba.data() bytesPerRow:W*8];
          [srcArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
                      withBytes:rgba.data() bytesPerRow:W*8 bytesPerImage:0];
        }

        if (pass==1) {
          std::vector<float> zeroDep(N, 0.0f);
          for (int i=0;i<NIMG;++i) {
            const float* srcDep = (view[i] < NF) ? passA.data()+(size_t)view[i]*N
                                                 : zeroDep.data();
            [depArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
                        withBytes:srcDep bytesPerRow:W*4 bytesPerImage:0];
          }
        }

        { uint32_t* m=(uint32_t*)bMaps.contents; const uint32_t init=1u|(1u<<8);
          for (size_t i=0;i<N;++i) m[i]=init; }
        memset(bCosts.contents,0,N*4);
        memset(bSel.contents,0,N*4); memset(bVW.contents,0,N*32);
        if (pass==0) { memset(bPlanes.contents,0,N*16); P.state=0u;
                       P.geom_consistency=0u; P.use_impetus=0u; }
        else {
          float* pl=(float*)bPlanes.contents;
          const float* pa=passA.data()+(size_t)f*N;
          for (size_t i=0;i<N;++i) pl[i*4+3]=pa[i];
          P.state=2u; P.geom_consistency=1u; P.use_impetus=1u; P.weak_peak_radius=4u;
        }

        run("random_init_kernel",false,0);
        for (int it=0; it<ITERS; ++it) {
          run("black_pixel_update_strong",true,(uint32_t)it);
          run("red_pixel_update_strong",true,(uint32_t)it);
        }
        run("depth_and_normal_kernel",false,0);
        run("black_pixel_filter_strong",true,0);
        run("red_pixel_filter_strong",true,0);
        run("depth_to_weak_kernel",false,0);
        if (pass==1) run("confidence_kernel",false,0);
        run("local_refine_kernel",false,0);

        if (pass==0) {
          const float* pl=(const float*)bPlanes.contents;
          float* pa=passA.data()+(size_t)f*N;
          for (size_t i=0;i<N;++i) pa[i]=pl[i*4+3];
        }

        double ms = (CFAbsoluteTimeGetCurrent()-tf)*1000.0;
        frame_ms.push_back(ms);
        // 🔴 逐帧全打:热降频只在后段显形,均值会把它藏起来
        NSLog(@"[APDE]   [%c] 帧 %2d/%d  %.0f ms   footprint %.0f MB",
              'A'+pass, f+1, NF, ms, phys_footprint_now()/1048576.0);
      }
    }
    double total = CFAbsoluteTimeGetCurrent()-t0;
    g_sampling = false; pthread_join(th, nullptr);

    // ── 报告 ──
    size_t half = frame_ms.size()/2;
    double sumA=0, sumB=0;
    for (size_t i=0;i<half;++i) sumA += frame_ms[i];
    for (size_t i=half;i<frame_ms.size();++i) sumB += frame_ms[i];
    std::vector<double> srt = frame_ms; std::sort(srt.begin(), srt.end());

    NSLog(@"[APDE] ═══════════ 结果 ═══════════");
    NSLog(@"[APDE] 总耗时 %.1f s / %d 帧 × 2 遍", total, NF);
    NSLog(@"[APDE] **出货口径 ms/帧(两遍合计)= %.0f ms**", total/NF*1000.0);
    NSLog(@"[APDE]   Pass A 平均 %.0f ms   Pass B 平均 %.0f ms", sumA/half, sumB/(frame_ms.size()-half));
    NSLog(@"[APDE]   单遍分位 p10 %.0f  p50 %.0f  p90 %.0f ms",
          srt[srt.size()/10], srt[srt.size()/2], srt[srt.size()*9/10]);
    NSLog(@"[APDE] **内存峰值 phys_footprint = %.0f MB**  (jetsam 口径)",
          g_peak.load()/1048576.0);
    NSLog(@"[APDE]   其中 GPU 常驻分配 %.1f MB;其余是 fixture + passA 等测试脚手架",
          gpu_bytes/1048576.0);
    NSLog(@"[APDE] ── 逐 kernel GPU 时间(全程累计)──");
    std::vector<std::pair<double,std::string>> ks;
    for (auto& kv : kms) ks.push_back({kv.second, kv.first});
    std::sort(ks.rbegin(), ks.rend());
    double ktot=0; for (auto& k : ks) ktot += k.first;
    for (auto& k : ks)
      NSLog(@"[APDE]   %-30s %8.1f ms  (%.1f%%)", k.second.c_str(), k.first, 100*k.first/ktot);
    NSLog(@"[APDE]   GPU 合计 %.1f ms,占墙钟 %.1f%%(其余是 host 侧纹理上传/复位)",
          ktot, 100*ktot/(total*1000));
    NSLog(@"[APDE] ═══════════ 完 ═══════════");
  }
}

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (nonatomic, strong) UIWindow* window;
@end
@implementation AppDelegate
- (BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)o {
  self.window = [[UIWindow alloc] initWithFrame:[[UIScreen mainScreen] bounds]];
  UIViewController* vc = [UIViewController new];
  vc.view.backgroundColor = [UIColor blackColor];
  UILabel* lb = [[UILabel alloc] initWithFrame:vc.view.bounds];
  lb.text = @"APDe bench 运行中…\n(结果在 console)";
  lb.numberOfLines = 0; lb.textColor = [UIColor whiteColor];
  lb.textAlignment = NSTextAlignmentCenter;
  [vc.view addSubview:lb];
  self.window.rootViewController = vc;
  [self.window makeKeyAndVisible];
  // 🔴 别在主线程跑:iOS 看门狗会因主线程长时间无响应直接杀掉进程
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    run_bench();
    dispatch_async(dispatch_get_main_queue(), ^{ lb.text = @"完成,见 console"; });
  });
  return YES;
}
@end

int main(int argc, char* argv[]) {
  @autoreleasepool {
    return UIApplicationMain(argc, argv, nil, NSStringFromClass([AppDelegate class]));
  }
}
