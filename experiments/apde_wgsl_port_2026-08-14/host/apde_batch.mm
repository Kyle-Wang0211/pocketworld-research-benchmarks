// APDe-MVS WGSL:414 帧批量跑,产出融合器能吃的 pass1 缓存。
//
// 输入(prep_batch.py 产出):images.f16 / cams.f32 / neighbors.i32 / frames.json
// 输出:depth.f32 (N,H,W) + conf.f32 (N,H,W) 两个裸二进制,
//       由 pack_p1cache.py 打成 p1cache_apde.npz 喂给
//       pw_diffmvs_geomcons.py —— **与 CasDiffMVS 用同一个融合器**,
//       所以对比只测深度图质量,不掺融合器差异。
//
// ⚠️ conf 的口径(改过一次,记账):
//    初版我编了 conf = 1 - cost/2。实测发现它**滤掉平滑表面、保留高梯度边缘**,
//    方向反了 —— 因为 NCC 代价在纹理边缘天然更低,而平滑面上代价略高但深度更可信。
//    现在用 APDe 自己的 ConfidenceCompute:跨视图一致性计数
//    (基数1 + 每源{有深度+1, 重投影≤2px+2, 相对深度差≤2%+2}),4 源上限 21。
//    它需要 geom_consistency=1 且 depth_tex 装**各源视图自己的**深度 ⇒ 必须两遍跑。
//
// 两遍结构:
//   Pass A  round0(FIRST_INIT / 无 geom)      → 每帧深度
//   Pass B  REFINE_ITER + geom_consistency=1,depth_tex 装 Pass A 的邻居深度,
//           末尾 ConfidenceCompute            → 最终深度 + 真置信度

#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <vector>
#include <map>
#include <string>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <algorithm>

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
static_assert(sizeof(Params) == 96, "Params 96B,与 apde_common.wgsl 一致");

struct Camera {
  float K0[4], K1[4], K2[4], R0[4], R1[4], R2[4], t[4], c[4];
  float depth_min, depth_max; int32_t width, height;
};
static_assert(sizeof(Camera) == 144, "Camera 144B,与 apde_common.wgsl 一致");

static std::vector<uint8_t> rd(const std::string& p) {
  FILE* f = fopen(p.c_str(), "rb");
  if (!f) { fprintf(stderr, "open %s\n", p.c_str()); exit(1); }
  fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
  std::vector<uint8_t> b(n);
  if (fread(b.data(), 1, n, f) != (size_t)n) { fprintf(stderr, "short read\n"); exit(1); }
  fclose(f); return b;
}

int main(int argc, const char** argv) {
  @autoreleasepool {
    std::string dir = argc > 1 ? argv[1] : "/tmp/apde_batch";
    std::string lib = argc > 2 ? argv[2] : "/tmp/vfin/apde.metallib";
    int limit = argc > 3 ? atoi(argv[3]) : 0;
    const int W = 896, H = 512, NIMG = 5, ITERS = 3;
    const size_t N = (size_t)W * H;

    auto imgs  = rd(dir + "/images.f16");
    auto camsR = rd(dir + "/cams.f32");
    auto nbR   = rd(dir + "/neighbors.i32");
    int NF = (int)(camsR.size() / (36 * 4));
    if (limit > 0 && limit < NF) NF = limit;
    const uint16_t* IM = (const uint16_t*)imgs.data();
    const float* CM = (const float*)camsR.data();
    const int32_t* NB = (const int32_t*)nbR.data();
    fprintf(stderr, "帧数 %d\n", NF);

    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    fprintf(stderr, "GPU: %s\n", [[dev name] UTF8String]);
    NSError* e = nil;
    id<MTLLibrary> L = [dev newLibraryWithURL:[NSURL fileURLWithPath:
        [NSString stringWithUTF8String:lib.c_str()]] error:&e];
    if (!L) { fprintf(stderr, "lib: %s\n", [[e description] UTF8String]); return 1; }

    // per-kernel binding remap 表(必需,见 gen_binding_map.py)
    std::map<std::string, std::vector<std::string>> kBuf, kTex, kSmp;
    {
      std::string bp = lib.substr(0, lib.rfind('/')) + "/bindings.txt";
      FILE* f = fopen(bp.c_str(), "r");
      if (!f) { fprintf(stderr, "缺 %s\n", bp.c_str()); return 1; }
      char line[4096];
      auto split = [](const std::string& s) {
        std::vector<std::string> o; size_t p = 0;
        while (p <= s.size()) { size_t c = s.find(',', p);
          if (c == std::string::npos) { if (p < s.size()) o.push_back(s.substr(p)); break; }
          o.push_back(s.substr(p, c - p)); p = c + 1; } return o; };
      while (fgets(line, sizeof(line), f)) {
        std::string S(line); while (!S.empty() && (S.back()=='\n'||S.back()=='\r')) S.pop_back();
        size_t a = S.find('|'), b = S.find('|', a+1), c = S.find('|', b+1);
        if (a==std::string::npos||b==std::string::npos||c==std::string::npos) continue;
        std::string k = S.substr(0,a);
        kBuf[k]=split(S.substr(a+1,b-a-1)); kTex[k]=split(S.substr(b+1,c-b-1));
        kSmp[k]=split(S.substr(c+1));
      }
      fclose(f);
    }
    std::map<std::string, id<MTLComputePipelineState>> psos;
    auto pso = [&](const std::string& n) {
      auto it = psos.find(n); if (it != psos.end()) return it->second;
      id<MTLFunction> f = [L newFunctionWithName:[NSString stringWithUTF8String:n.c_str()]];
      NSError* er = nil;
      id<MTLComputePipelineState> p = [dev newComputePipelineStateWithFunction:f error:&er];
      if (!p) { fprintf(stderr, "pso %s: %s\n", n.c_str(), [[er description] UTF8String]); exit(1); }
      psos[n] = p; return p;
    };

    Params P{};
    P.width=W; P.height=H; P.num_images=NIMG;
    P.strong_radius=5; P.strong_increment=2; P.rand_seed=1u;
    P.geom_factor=0.2f; P.geom_consistency=0u; P.use_impetus=0u;
    P.state=0u; P.rotate_time=4u; P.ransac_threshold=0.005f;
    P.top_k=4u; P.use_apd=0u; P.weak_peak_radius=6u;
    P.weak_radius=5; P.weak_increment=2;
    id<MTLBuffer> bP = [dev newBufferWithLength:sizeof(P) options:MTLResourceStorageModeShared];
    id<MTLBuffer> bCams = [dev newBufferWithLength:32*sizeof(Camera) options:MTLResourceStorageModeShared];
    auto mk=[&](size_t n){ id<MTLBuffer> b=[dev newBufferWithLength:n options:MTLResourceStorageModeShared];
                           memset(b.contents,0,n); return b; };
    id<MTLBuffer> bMaps=mk(N*4), bPlanes=mk(N*16), bCosts=mk(N*4), bSel=mk(N*4),
                  bRand=mk(N*4), bAnch=mk(N*4), bAncMap=mk(N*4), bVW=mk(N*32),
                  bNear=mk(N*4), bAncOut=mk(N*36), bFit=mk(N*16);

    MTLTextureDescriptor* td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatRGBA16Float width:W height:H mipmapped:NO];
    td.usage=MTLTextureUsageShaderRead; td.storageMode=MTLStorageModeShared;
    id<MTLTexture> refTex=[dev newTextureWithDescriptor:td];
    MTLTextureDescriptor* sd=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatRGBA16Float width:W height:H mipmapped:NO];
    sd.textureType=MTLTextureType2DArray; sd.arrayLength=NIMG;
    sd.usage=MTLTextureUsageShaderRead; sd.storageMode=MTLStorageModeShared;
    id<MTLTexture> srcArr=[dev newTextureWithDescriptor:sd];
    MTLTextureDescriptor* dd=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatR32Float width:W height:H mipmapped:NO];
    dd.textureType=MTLTextureType2DArray; dd.arrayLength=NIMG;
    dd.usage=MTLTextureUsageShaderRead; dd.storageMode=MTLStorageModeShared;
    id<MTLTexture> depArr=[dev newTextureWithDescriptor:dd];

    MTLSamplerDescriptor* s1=[MTLSamplerDescriptor new];
    s1.minFilter=MTLSamplerMinMagFilterLinear; s1.magFilter=MTLSamplerMinMagFilterLinear;
    s1.sAddressMode=MTLSamplerAddressModeClampToEdge; s1.tAddressMode=MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> sampL=[dev newSamplerStateWithDescriptor:s1];
    MTLSamplerDescriptor* s2=[MTLSamplerDescriptor new];
    s2.minFilter=MTLSamplerMinMagFilterNearest; s2.magFilter=MTLSamplerMinMagFilterNearest;
    s2.sAddressMode=MTLSamplerAddressModeClampToEdge; s2.tAddressMode=MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> sampN=[dev newSamplerStateWithDescriptor:s2];

    std::map<std::string,id<MTLBuffer>> byName={
      {"P",bP},{"cams",bCams},{"packed_maps",bMaps},{"plane_hypotheses",bPlanes},
      {"costs",bCosts},{"selected_views",bSel},{"rand_states",bRand},
      {"anchors",bAnch},{"anchors_map",bAncMap},{"view_weights_buf",bVW},
      {"weak_nearest_buf",bNear},{"anchors_out",bAncOut},{"fit_plane_hypos",bFit}};
    std::map<std::string,id<MTLTexture>> texByName={
      {"ref_tex",refTex},{"src_tex",srcArr},{"depth_tex",depArr}};
    std::map<std::string,id<MTLSamplerState>> smpByName={{"samp",sampL},{"samp_nearest",sampN}};

    id<MTLCommandQueue> Q=[dev newCommandQueue];
    std::vector<uint16_t> rgba(N*4);
    std::vector<float> outDepth((size_t)NF*N), outConf((size_t)NF*N);
    const uint16_t ONE_F16 = 0x3C00;   // 1.0 in f16

    auto run=[&](const std::string& k, bool half, uint32_t it){
      P.iter=it; memcpy(bP.contents,&P,sizeof(P));
      id<MTLCommandBuffer> cb=[Q commandBuffer];
      id<MTLComputeCommandEncoder> en=[cb computeCommandEncoder];
      [en setComputePipelineState:pso(k)];
      const auto& bl=kBuf[k]; const auto& tl=kTex[k]; const auto& sl2=kSmp[k];
      for(size_t i=0;i<bl.size();++i){ id<MTLBuffer> b=byName[bl[i]];
        if(!b){fprintf(stderr,"未知 buffer %s@%s\n",bl[i].c_str(),k.c_str());exit(1);}
        [en setBuffer:b offset:0 atIndex:i]; }
      for(size_t i=0;i<tl.size();++i) [en setTexture:texByName[tl[i]] atIndex:i];
      for(size_t i=0;i<sl2.size();++i) [en setSamplerState:smpByName[sl2[i]] atIndex:i];
      [en dispatchThreads:MTLSizeMake(W, half?H/2:H, 1)
            threadsPerThreadgroup:MTLSizeMake(16,16,1)];
      [en endEncoding]; [cb commit]; [cb waitUntilCompleted];
    };

    // ══ 两遍结构 ═══════════════════════════════════════════════
    //  Pass A: round0(FIRST_INIT / 无 geom),出每帧深度
    //  Pass B: REFINE_ITER + geom_consistency=1,depth_tex 装**各源视图自己的**
    //          深度(来自 Pass A),末尾跑 ConfidenceCompute 取真置信度。
    //
    // 🔴 为什么必须这样:上一版 conf = 1 - cost/2 是我自己编的映射,实测它
    //    **滤掉平滑表面、保留高梯度边缘**,方向反了。APDe 自己的置信度是
    //    ConfidenceCompute 的跨视图一致性计数(基数1 + 每源有深度+1 +
    //    重投影像素≤2px+2 + 相对深度差≤2%+2),4 源视图上限 21。
    //    那才是该喂给融合器 photo_mask 的东西。
    std::vector<float> passA((size_t)NF*N);
    int PASSES = (argc > 4) ? atoi(argv[4]) : 2;

    double t0=CFAbsoluteTimeGetCurrent();
    for (int pass=0; pass<PASSES; ++pass) {
    fprintf(stderr, "── Pass %c ──\n", 'A'+pass);
    for (int f=0; f<NF; ++f) {
      int view[NIMG]; view[0]=f;
      for (int i=0;i<NIMG-1;++i) view[i+1]=NB[(size_t)f*4+i];

      // 相机表
      Camera* cs=(Camera*)bCams.contents; memset(cs,0,32*sizeof(Camera));
      for (int i=0;i<NIMG;++i){ const float* c=CM+(size_t)view[i]*36; Camera& C=cs[i];
        for(int r=0;r<3;++r){ C.K0[r]=c[r]; C.K1[r]=c[3+r]; C.K2[r]=c[6+r];
                              C.R0[r]=c[9+r]; C.R1[r]=c[12+r]; C.R2[r]=c[15+r];
                              C.t[r]=c[18+r]; C.c[r]=c[21+r]; }
        C.depth_min=c[24]; C.depth_max=c[25]; C.width=W; C.height=H; }
      P.depth_min=CM[(size_t)f*36+24]; P.depth_max=CM[(size_t)f*36+25];

      // 纹理:灰度 f16 → RGBA16F
      for (int i=0;i<NIMG;++i){
        const uint16_t* g=IM+(size_t)view[i]*N;
        for(size_t p=0;p<N;++p){ rgba[p*4]=g[p]; rgba[p*4+1]=g[p]; rgba[p*4+2]=g[p];
                                 rgba[p*4+3]=ONE_F16; }
        if(i==0) [refTex replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0
                            withBytes:rgba.data() bytesPerRow:W*8];
        [srcArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
                    withBytes:rgba.data() bytesPerRow:W*8 bytesPerImage:0];
      }

      // Pass B:装各源视图自己的深度进 depth_tex(几何一致性的前提)
      if (pass==1) {
        std::vector<float> zeroDep(N, 0.0f);
        for (int i=0;i<NIMG;++i) {
          // ⚠️ limit 调试模式下邻居索引可能 >= NF(邻居表按完整 413 帧算),
          //    直接取 passA 会越界读(我加 limit 时就这么段错误过一次)。
          //    越界的源视图喂 0 深度 ⇒ ComputeGeomConsistencyCost 的
          //    `src_depth == 0` 分支返回 max_cost,语义上等于"该视图无信息"。
          const float* srcDep = (view[i] < NF) ? passA.data()+(size_t)view[i]*N
                                               : zeroDep.data();
          [depArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
                      withBytes:srcDep bytesPerRow:W*4 bytesPerImage:0];
        }
      }

      // 状态复位:packed_maps 必须初始化成 STRONG|conf=1(APD.cpp:656)
      { uint32_t* m=(uint32_t*)bMaps.contents; const uint32_t init=1u|(1u<<8);
        for(size_t i=0;i<N;++i) m[i]=init; }
      memset(bCosts.contents,0,N*4);
      memset(bSel.contents,0,N*4); memset(bVW.contents,0,N*32);
      if (pass==0) { memset(bPlanes.contents,0,N*16); P.state=0u; /*FIRST_INIT*/
                     P.geom_consistency=0u; P.use_impetus=0u; }
      else {
        // 用 Pass A 的深度当初值(.w=深度,法向已在世界系)⇒ state=REFINE_ITER,
        // random_init_kernel 会 TransformNormal2RefCam 再换算成 d。
        float* pl=(float*)bPlanes.contents;
        const float* pa=passA.data()+(size_t)f*N;
        for(size_t i=0;i<N;++i) pl[i*4+3]=pa[i];
        P.state=2u; /*REFINE_ITER*/ P.geom_consistency=1u; P.use_impetus=1u;
        P.weak_peak_radius=4u;
      }

      run("random_init_kernel",false,0);
      for(int it=0; it<ITERS; ++it){
        run("black_pixel_update_strong",true,(uint32_t)it);
        run("red_pixel_update_strong",true,(uint32_t)it);
      }
      run("depth_and_normal_kernel",false,0);
      run("black_pixel_filter_strong",true,0);
      run("red_pixel_filter_strong",true,0);
      run("depth_to_weak_kernel",false,0);
      if (pass==1) run("confidence_kernel",false,0);   // 真置信度
      run("local_refine_kernel",false,0);

      const float* pl=(const float*)bPlanes.contents;
      if (pass==0) {
        float* pa=passA.data()+(size_t)f*N;
        for(size_t i=0;i<N;++i) pa[i]=pl[i*4+3];
      } else {
        const uint32_t* mp=(const uint32_t*)bMaps.contents;
        float* dOut=outDepth.data()+(size_t)f*N;
        float* cOut=outConf.data()+(size_t)f*N;
        // ConfidenceCompute 的计数:基数1 + 每源(有深度+1, 像素≤2px+2, 深度≤2%+2)
        // 4 源上限 = 1 + 4*5 = 21。归一化到 [0,1]。
        const float CONF_MAX = 21.0f;
        for(size_t i=0;i<N;++i){
          dOut[i]=pl[i*4+3];
          float cc=(float)((mp[i]>>8)&0xFFu);
          cOut[i]=std::max(0.0f, std::min(1.0f, cc/CONF_MAX));
        }
      }
      if (f%50==0 || f==NF-1) {
        double el=CFAbsoluteTimeGetCurrent()-t0;
        fprintf(stderr,"  [%c] 帧 %d/%d  已用 %.1fs\n",'A'+pass,f+1,NF,el);
      }
    }
    }  // pass
    double el=CFAbsoluteTimeGetCurrent()-t0;
    printf("全部 %d 帧完成,%.1f s(%.0f ms/帧)\n", NF, el, el/NF*1000);

    FILE* fd=fopen((dir+"/depth.f32").c_str(),"wb");
    fwrite(outDepth.data(),4,outDepth.size(),fd); fclose(fd);
    FILE* fc=fopen((dir+"/conf.f32").c_str(),"wb");
    fwrite(outConf.data(),4,outConf.size(),fc); fclose(fc);
    printf("→ %s/depth.f32  %s/conf.f32\n", dir.c_str(), dir.c_str());
    return 0;
  }
}
