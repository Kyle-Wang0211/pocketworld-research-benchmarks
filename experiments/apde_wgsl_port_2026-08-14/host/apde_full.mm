// APDe-MVS WGSL:**完整**多轮 + 多尺度 + APD + 几何一致性 批量跑
//
// 照抄 main.cpp:306-360 的轮次结构(round_num=2, geom_iteration=1):
//   Round 0  scale=2(448×256)  state=FIRST_INIT   use_APD=0  geom=0
//   Round 0g scale=2           state=REFINE_ITER  use_APD=0  geom=1
//   Round 1  scale=1(896×512)  state=REFINE_INIT  use_APD=1  geom=0
//            ransac_threshold = 0.01 - 1*0.00125,rotate_time = min(2^1,4)=2
//   Round 1g scale=1           state=REFINE_ITER  use_APD=1  geom=1  ← 出最终深度+置信度
//
// 多尺度(APD.cpp:564-585):图像缩 1/scale,K 的 fx/cx/fy/cy 同步乘 scale_x/scale_y。
// 轮间衔接:上一段的深度上采样成下一段的初值(state != FIRST_INIT 时
//           random_init_kernel 会 TransformNormal2RefCam 把 .w 换算回 d)。
//
// ⚠️ 每一段都需要**各源视图自己的**深度才能开 geom ⇒ 段内先全帧跑一遍存深度,
//    下一段再用。这就是为什么是"段"而不是"帧"级流水。

#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <vector>
#include <map>
#include <string>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cmath>
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
static_assert(sizeof(Params) == 96, "Params 96B");
struct Camera {
  float K0[4], K1[4], K2[4], R0[4], R1[4], R2[4], t[4], c[4];
  float depth_min, depth_max; int32_t width, height;
};
static_assert(sizeof(Camera) == 144, "Camera 144B");

static std::vector<uint8_t> rd(const std::string& p) {
  FILE* f=fopen(p.c_str(),"rb"); if(!f){fprintf(stderr,"open %s\n",p.c_str());exit(1);}
  fseek(f,0,SEEK_END); long n=ftell(f); fseek(f,0,SEEK_SET);
  std::vector<uint8_t> b(n);
  if(fread(b.data(),1,n,f)!=(size_t)n){fprintf(stderr,"short\n");exit(1);}
  fclose(f); return b;
}
static inline float h2f(uint16_t h){
  uint32_t s=(h>>15)&1,e=(h>>10)&0x1F,m=h&0x3FF;
  if(e==0) return (s?-1.f:1.f)*ldexpf((float)m,-24);
  uint32_t x=(s<<31)|((e-15+127)<<23)|(m<<13); float o; memcpy(&o,&x,4); return o;
}
static inline uint16_t f2h(float v){
  uint32_t x; memcpy(&x,&v,4);
  uint32_t s=(x>>16)&0x8000,e=(x>>23)&0xFF,m=x&0x7FFFFF;
  int ne=(int)e-127+15;
  if(ne<=0) return (uint16_t)s;
  if(ne>=31) return (uint16_t)(s|0x7C00);
  return (uint16_t)(s|(ne<<10)|(m>>13));
}

int main(int argc, const char** argv) {
  @autoreleasepool {
    std::string dir = argc>1?argv[1]:"/tmp/apde_batch";
    std::string lib = argc>2?argv[2]:"/tmp/vfin/apde.metallib";
    int limit = argc>3?atoi(argv[3]):0;
    const int W0=896, H0=512, NIMG=5, ITERS=3;

    auto imgsRaw = rd(dir+"/images.f16");
    auto camsRaw = rd(dir+"/cams.f32");
    auto nbRaw   = rd(dir+"/neighbors.i32");
    int NF = (int)(camsRaw.size()/(36*4));
    if (limit>0 && limit<NF) NF=limit;
    const uint16_t* IM=(const uint16_t*)imgsRaw.data();
    const float* CM=(const float*)camsRaw.data();
    const int32_t* NB=(const int32_t*)nbRaw.data();
    fprintf(stderr,"帧数 %d\n",NF);

    id<MTLDevice> dev=MTLCreateSystemDefaultDevice();
    fprintf(stderr,"GPU: %s\n",[[dev name]UTF8String]);
    NSError* e=nil;
    id<MTLLibrary> L=[dev newLibraryWithURL:[NSURL fileURLWithPath:
        [NSString stringWithUTF8String:lib.c_str()]] error:&e];
    if(!L){fprintf(stderr,"lib: %s\n",[[e description]UTF8String]);return 1;}

    std::map<std::string,std::vector<std::string>> kBuf,kTex,kSmp;
    { std::string bp=lib.substr(0,lib.rfind('/'))+"/bindings.txt";
      FILE* f=fopen(bp.c_str(),"r"); if(!f){fprintf(stderr,"缺 %s\n",bp.c_str());return 1;}
      char ln[4096];
      auto sp=[](const std::string& s){ std::vector<std::string> o; size_t p=0;
        while(p<=s.size()){ size_t c=s.find(',',p);
          if(c==std::string::npos){ if(p<s.size()) o.push_back(s.substr(p)); break; }
          o.push_back(s.substr(p,c-p)); p=c+1; } return o; };
      while(fgets(ln,sizeof(ln),f)){ std::string S(ln);
        while(!S.empty()&&(S.back()=='\n'||S.back()=='\r')) S.pop_back();
        size_t a=S.find('|'),b=S.find('|',a+1),c=S.find('|',b+1);
        if(a==std::string::npos||b==std::string::npos||c==std::string::npos) continue;
        std::string k=S.substr(0,a);
        kBuf[k]=sp(S.substr(a+1,b-a-1)); kTex[k]=sp(S.substr(b+1,c-b-1)); kSmp[k]=sp(S.substr(c+1)); }
      fclose(f); }
    std::map<std::string,id<MTLComputePipelineState>> psos;
    auto pso=[&](const std::string& n){ auto it=psos.find(n); if(it!=psos.end()) return it->second;
      id<MTLFunction> f=[L newFunctionWithName:[NSString stringWithUTF8String:n.c_str()]];
      NSError* er=nil; id<MTLComputePipelineState> p=[dev newComputePipelineStateWithFunction:f error:&er];
      if(!p){fprintf(stderr,"pso %s: %s\n",n.c_str(),[[er description]UTF8String]);exit(1);}
      psos[n]=p; return p; };

    // ── 段定义(照抄 main.cpp 的轮次配置)──────────────────────
    struct Seg { int scale; uint32_t state, use_apd, geom; float ransac; uint32_t rot, wpr; const char* tag; };
    std::vector<Seg> segs = {
      {2, 0u, 0u, 0u, 0.005f, 4u, 6u, "R0  scale2 FIRST_INIT"},
      {2, 2u, 0u, 1u, 0.005f, 4u, 4u, "R0g scale2 REFINE_ITER geom"},
      {1, 1u, 1u, 0u, 0.00875f, 2u, 6u, "R1  scale1 REFINE_INIT APD"},
      {1, 2u, 1u, 1u, 0.00875f, 2u, 4u, "R1g scale1 REFINE_ITER APD geom"},
    };

    id<MTLCommandQueue> Q=[dev newCommandQueue];
    // 上一段的深度(按上一段的分辨率),用于 geom 与轮间初值
    std::vector<float> prevDepth; int prevW=0, prevH=0;
    // 🔴 weak_info 必须跨段传递:原版 round≥1 的 weak_info 来自**上一轮
    //    DepthToWeak 的结果**(APD.cpp:627 从 weak_info_host 建 anchors_map)。
    //    我最初每帧把它重置成 STRONG,导致 weak_count=0、APD 前置整段被
    //    静默跳过(表现:耗时只有单帧实测的 1/5)。
    std::vector<uint8_t> prevWeak;
    std::vector<float> prevPlane;   // 整个平面(法向+深度)
    std::vector<float> outDepth((size_t)NF*W0*H0), outConf((size_t)NF*W0*H0);
    double t0=CFAbsoluteTimeGetCurrent();

    for (size_t si=0; si<segs.size(); ++si) {
      const Seg& S=segs[si];
      const int W=W0/S.scale, H=H0/S.scale;
      const size_t N=(size_t)W*H;
      fprintf(stderr,"── 段 %zu/%zu  %s  (%d×%d) ──\n",si+1,segs.size(),S.tag,W,H);

      // 资源按本段分辨率重建
      Params P{}; P.width=W; P.height=H; P.num_images=NIMG;
      P.strong_radius=5; P.strong_increment=2; P.rand_seed=1u;
      P.geom_factor=0.2f; P.top_k=4u; P.weak_radius=5; P.weak_increment=2;
      P.state=S.state; P.use_apd=S.use_apd; P.geom_consistency=S.geom;
      P.use_impetus=S.geom; P.ransac_threshold=S.ransac;
      P.rotate_time=S.rot; P.weak_peak_radius=S.wpr;

      id<MTLBuffer> bP=[dev newBufferWithLength:sizeof(P) options:MTLResourceStorageModeShared];
      id<MTLBuffer> bCams=[dev newBufferWithLength:32*sizeof(Camera) options:MTLResourceStorageModeShared];
      auto mk=[&](size_t n){ id<MTLBuffer> b=[dev newBufferWithLength:n options:MTLResourceStorageModeShared];
                             memset(b.contents,0,n); return b; };
      id<MTLBuffer> bMaps=mk(N*4),bPl=mk(N*16),bCost=mk(N*4),bSel=mk(N*4),bRand=mk(N*4),
                    bAnch=mk(N*4),bAncMap=mk(N*4),bVW=mk(N*32),bNear=mk(N*4),
                    bAncOut=mk(N*36),bFit=mk(N*16);

      MTLTextureDescriptor* td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
          MTLPixelFormatRGBA16Float width:W height:H mipmapped:NO];
      td.usage=MTLTextureUsageShaderRead; td.storageMode=MTLStorageModeShared;
      id<MTLTexture> refTex=[dev newTextureWithDescriptor:td];
      MTLTextureDescriptor* sdd=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
          MTLPixelFormatRGBA16Float width:W height:H mipmapped:NO];
      sdd.textureType=MTLTextureType2DArray; sdd.arrayLength=NIMG;
      sdd.usage=MTLTextureUsageShaderRead; sdd.storageMode=MTLStorageModeShared;
      id<MTLTexture> srcArr=[dev newTextureWithDescriptor:sdd];
      MTLTextureDescriptor* ddd=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
          MTLPixelFormatR32Float width:W height:H mipmapped:NO];
      ddd.textureType=MTLTextureType2DArray; ddd.arrayLength=NIMG;
      ddd.usage=MTLTextureUsageShaderRead; ddd.storageMode=MTLStorageModeShared;
      id<MTLTexture> depArr=[dev newTextureWithDescriptor:ddd];

      MTLSamplerDescriptor* q1=[MTLSamplerDescriptor new];
      q1.minFilter=MTLSamplerMinMagFilterLinear; q1.magFilter=MTLSamplerMinMagFilterLinear;
      q1.sAddressMode=MTLSamplerAddressModeClampToEdge; q1.tAddressMode=MTLSamplerAddressModeClampToEdge;
      id<MTLSamplerState> sampL=[dev newSamplerStateWithDescriptor:q1];
      MTLSamplerDescriptor* q2=[MTLSamplerDescriptor new];
      q2.minFilter=MTLSamplerMinMagFilterNearest; q2.magFilter=MTLSamplerMinMagFilterNearest;
      q2.sAddressMode=MTLSamplerAddressModeClampToEdge; q2.tAddressMode=MTLSamplerAddressModeClampToEdge;
      id<MTLSamplerState> sampN=[dev newSamplerStateWithDescriptor:q2];

      std::map<std::string,id<MTLBuffer>> byName={
        {"P",bP},{"cams",bCams},{"packed_maps",bMaps},{"plane_hypotheses",bPl},
        {"costs",bCost},{"selected_views",bSel},{"rand_states",bRand},
        {"anchors",bAnch},{"anchors_map",bAncMap},{"view_weights_buf",bVW},
        {"weak_nearest_buf",bNear},{"anchors_out",bAncOut},{"fit_plane_hypos",bFit}};
      std::map<std::string,id<MTLTexture>> texByName={
        {"ref_tex",refTex},{"src_tex",srcArr},{"depth_tex",depArr}};
      std::map<std::string,id<MTLSamplerState>> smpByName={{"samp",sampL},{"samp_nearest",sampN}};

      auto run=[&](const std::string& k, bool half, uint32_t it){
        P.iter=it; memcpy(bP.contents,&P,sizeof(P));
        id<MTLCommandBuffer> cb=[Q commandBuffer];
        id<MTLComputeCommandEncoder> en=[cb computeCommandEncoder];
        [en setComputePipelineState:pso(k)];
        const auto& bl=kBuf[k]; const auto& tl=kTex[k]; const auto& sl=kSmp[k];
        for(size_t i=0;i<bl.size();++i){ id<MTLBuffer> b=byName[bl[i]];
          if(!b){fprintf(stderr,"未知 buffer %s@%s\n",bl[i].c_str(),k.c_str());exit(1);}
          [en setBuffer:b offset:0 atIndex:i]; }
        for(size_t i=0;i<tl.size();++i) [en setTexture:texByName[tl[i]] atIndex:i];
        for(size_t i=0;i<sl.size();++i) [en setSamplerState:smpByName[sl[i]] atIndex:i];
        [en dispatchThreads:MTLSizeMake(W,half?H/2:H,1) threadsPerThreadgroup:MTLSizeMake(16,16,1)];
        [en endEncoding]; [cb commit]; [cb waitUntilCompleted];
      };

      std::vector<float> segDepth((size_t)NF*N);      // 只存深度,给 depth_tex 用
      std::vector<float> segPlane((size_t)NF*N*4);    // 存整个平面(法向+深度),给下一段当初值
      std::vector<uint8_t> segWeak((size_t)NF*N);
      std::vector<uint16_t> rgba(N*4);
      std::vector<float> gray(N), dtmp(N), zero(N,0.f);
      const uint16_t ONE=0x3C00;

      for (int f=0; f<NF; ++f) {
        int view[NIMG]; view[0]=f;
        for(int i=0;i<NIMG-1;++i) view[i+1]=NB[(size_t)f*4+i];

        // 相机(K 按 scale 缩放,照抄 APD.cpp:580-585)
        Camera* cs=(Camera*)bCams.contents; memset(cs,0,32*sizeof(Camera));
        const float sx=(float)W/(float)W0, sy=(float)H/(float)H0;
        for(int i=0;i<NIMG;++i){ const float* c=CM+(size_t)view[i]*36; Camera& C=cs[i];
          C.K0[0]=c[0]*sx; C.K0[1]=c[1]*sx; C.K0[2]=c[2]*sx;
          C.K1[0]=c[3]*sy; C.K1[1]=c[4]*sy; C.K1[2]=c[5]*sy;
          C.K2[0]=c[6];    C.K2[1]=c[7];    C.K2[2]=c[8];
          for(int r=0;r<3;++r){ C.R0[r]=c[9+r]; C.R1[r]=c[12+r]; C.R2[r]=c[15+r];
                                C.t[r]=c[18+r]; C.c[r]=c[21+r]; }
          C.depth_min=c[24]; C.depth_max=c[25]; C.width=W; C.height=H; }
        P.depth_min=CM[(size_t)f*36+24]; P.depth_max=CM[(size_t)f*36+25];

        // 图像(按 scale 双线性降采样)
        for(int i=0;i<NIMG;++i){
          const uint16_t* g0=IM+(size_t)view[i]*W0*H0;
          if (S.scale==1) { for(size_t p=0;p<N;++p) gray[p]=h2f(g0[p]); }
          else {
            for(int y=0;y<H;++y) for(int x=0;x<W;++x){
              float acc=0; int n=0;
              for(int dy=0;dy<S.scale;++dy) for(int dx=0;dx<S.scale;++dx){
                int yy=y*S.scale+dy, xx=x*S.scale+dx;
                if(yy<H0&&xx<W0){ acc+=h2f(g0[(size_t)yy*W0+xx]); n++; } }
              gray[(size_t)y*W+x]=n?acc/n:0.f; }
          }
          for(size_t p=0;p<N;++p){ uint16_t h=f2h(gray[p]);
            rgba[p*4]=h; rgba[p*4+1]=h; rgba[p*4+2]=h; rgba[p*4+3]=ONE; }
          if(i==0) [refTex replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0
                              withBytes:rgba.data() bytesPerRow:W*8];
          [srcArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
                      withBytes:rgba.data() bytesPerRow:W*8 bytesPerImage:0];
        }

        // depth_tex:上一段各源视图的深度,重采样到本段分辨率
        if (S.geom && !prevDepth.empty()) {
          for(int i=0;i<NIMG;++i){
            const float* pd = (view[i]<NF) ? prevDepth.data()+(size_t)view[i]*prevW*prevH : nullptr;
            if(!pd){ [depArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
                                 withBytes:zero.data() bytesPerRow:W*4 bytesPerImage:0]; continue; }
            for(int y=0;y<H;++y) for(int x=0;x<W;++x){
              int py=y*prevH/H, px=x*prevW/W;
              dtmp[(size_t)y*W+x]=pd[(size_t)py*prevW+px]; }
            [depArr replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
                        withBytes:dtmp.data() bytesPerRow:W*4 bytesPerImage:0];
          }
        }

        // 状态复位;非 FIRST_INIT 时用上一段深度当初值(最近邻上采样)
        { uint32_t* m=(uint32_t*)bMaps.contents;
          if (prevWeak.empty()) {
            // 首段:weak_info=STRONG, confidence=1(APD.cpp:656 的 else 分支)
            const uint32_t init=1u|(1u<<8);
            for(size_t i=0;i<N;++i) m[i]=init;
          } else {
            // 后续段:继承上一段 DepthToWeak 判出的 weak_info(最近邻重采样)
            const uint8_t* pw=prevWeak.data()+(size_t)f*prevW*prevH;
            for(int y=0;y<H;++y) for(int x=0;x<W;++x){
              int py=y*prevH/H, px=x*prevW/W;
              m[(size_t)y*W+x]=(uint32_t)pw[(size_t)py*prevW+px] | (1u<<8);
            }
          }
        }
        memset(bCost.contents,0,N*4); memset(bSel.contents,0,N*4); memset(bVW.contents,0,N*32);
        if (S.state==0u) memset(bPl.contents,0,N*16);
        else {
          // 🔴 必须搬**整个平面**(法向 xyz + 深度 w),不能只搬深度。
          //    原版非首轮是从文件读 depth **和 normal** 两张图(APD.cpp:667-668)。
          //    我最初只搬深度、memset 掉法向 ⇒ 法向为零 ⇒
          //    TransformNormal2RefCam/GetDistance2Origin 全退化,
          //    表现是后续段 DepthToWeak 判出 0% WEAK、APD 支再次空转。
          float* pl=(float*)bPl.contents;
          const float* pp=prevPlane.data()+(size_t)f*prevW*prevH*4;
          for(int y=0;y<H;++y) for(int x=0;x<W;++x){
            int py=y*prevH/H, px=x*prevW/W;
            const float* src=pp+((size_t)py*prevW+px)*4;
            float* dst=pl+((size_t)y*W+x)*4;
            dst[0]=src[0]; dst[1]=src[1]; dst[2]=src[2]; dst[3]=src[3]; }
        }

        // APD 前置(需要 anchors_map)
        if (S.use_apd) {
          int wc=0; int32_t* am=(int32_t*)bAncMap.contents;
          const uint32_t* m=(const uint32_t*)bMaps.contents;
          for(size_t i=0;i<N;++i){ if((m[i]&0xFFu)==0u) am[i]=wc++; else am[i]=-1; }
          if (wc>0) {
            run("nearest_strong_kernel",false,0);
            run("gen_anchors_kernel",false,0);
            run("neighbour_update_kernel",false,0);
          }
        }
        run("random_init_kernel",false,0);
        for(int it=0; it<ITERS; ++it){
          run("black_pixel_update_strong",true,(uint32_t)it);
          run("red_pixel_update_strong",true,(uint32_t)it);
          if (S.use_apd) {
            run("ransac_fit_plane_kernel",false,(uint32_t)it);
            run("black_pixel_update_weak",true,(uint32_t)it);
            run("red_pixel_update_weak",true,(uint32_t)it);
          }
        }
        run("depth_and_normal_kernel",false,0);
        run("black_pixel_filter_strong",true,0);
        run("red_pixel_filter_strong",true,0);
        run("depth_to_weak_kernel",false,0);
        if (S.geom || S.use_apd) run("confidence_kernel",false,0);
        run("local_refine_kernel",false,0);

        const float* pl=(const float*)bPl.contents;
        float* sd2=segDepth.data()+(size_t)f*N;
        for(size_t i=0;i<N;++i) sd2[i]=pl[i*4+3];
        memcpy(segPlane.data()+(size_t)f*N*4, pl, N*16);
        { const uint32_t* mp=(const uint32_t*)bMaps.contents;
          uint8_t* sw=segWeak.data()+(size_t)f*N;
          for(size_t i=0;i<N;++i) sw[i]=(uint8_t)(mp[i]&0xFFu); }

        if (si==segs.size()-1) {  // 最后一段:出最终深度 + 置信度
          const uint32_t* mp=(const uint32_t*)bMaps.contents;
          float* dO=outDepth.data()+(size_t)f*N; float* cO=outConf.data()+(size_t)f*N;
          const float CONF_MAX=21.0f;   // 4 源上限 = 1 + 4*5
          for(size_t i=0;i<N;++i){ dO[i]=pl[i*4+3];
            cO[i]=std::max(0.f,std::min(1.f,(float)((mp[i]>>8)&0xFFu)/CONF_MAX)); }
        }
        if(f%100==0||f==NF-1)
          fprintf(stderr,"    帧 %d/%d  已用 %.0fs\n",f+1,NF,CFAbsoluteTimeGetCurrent()-t0);
      }
      { size_t c0=0,c1=0,c2=0; for(size_t i=0;i<segWeak.size();++i){
          if(segWeak[i]==0) c0++; else if(segWeak[i]==1) c1++; else c2++; }
        size_t tot=segWeak.size();
        fprintf(stderr,"    → 本段 WEAK %.1f%%  STRONG %.1f%%  UNKNOWN %.1f%%\n",
                100.0*c0/tot,100.0*c1/tot,100.0*c2/tot); }
      prevDepth.swap(segDepth); prevPlane.swap(segPlane); prevWeak.swap(segWeak); prevW=W; prevH=H;
    }

    double el=CFAbsoluteTimeGetCurrent()-t0;
    printf("完整流水 %d 帧,%.1f s(%.0f ms/帧)\n",NF,el,el/NF*1000);
    FILE* fd=fopen((dir+"/depth_full.f32").c_str(),"wb");
    fwrite(outDepth.data(),4,outDepth.size(),fd); fclose(fd);
    FILE* fc=fopen((dir+"/conf_full.f32").c_str(),"wb");
    fwrite(outConf.data(),4,outConf.size(),fc); fclose(fc);
    printf("→ %s/depth_full.f32  %s/conf_full.f32\n",dir.c_str(),dir.c_str());
    return 0;
  }
}
