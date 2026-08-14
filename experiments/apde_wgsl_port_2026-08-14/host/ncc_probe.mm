// WGSL NCC 单点对拍:host 预置平面 → 跑 ncc_probe → 导出 costs
// 与 numpy 金标准逐点比,用来隔离"公式对但 WGSL 实现错"。
#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <vector>
#include <cstdio>
#include <cstring>

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

static std::vector<uint8_t> rd(const char* p) {
  FILE* f = fopen(p, "rb"); if (!f) { fprintf(stderr,"open %s\n",p); exit(1); }
  fseek(f,0,SEEK_END); long n=ftell(f); fseek(f,0,SEEK_SET);
  std::vector<uint8_t> b(n); fread(b.data(),1,n,f); fclose(f); return b;
}

int main(int argc, const char** argv) {
  @autoreleasepool {
    const char* fx = argv[1]; const char* lib = argv[2];
    const char* planes_in = argv[3]; const char* costs_out = argv[4];
    int W=896,H=512; size_t N=(size_t)W*H;

    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    NSError* e=nil;
    id<MTLLibrary> L=[dev newLibraryWithURL:[NSURL fileURLWithPath:
        [NSString stringWithUTF8String:lib]] error:&e];
    id<MTLFunction> fn=[L newFunctionWithName:[NSString stringWithUTF8String:(argc>5?argv[5]:"ncc_probe")]];
    id<MTLComputePipelineState> pso=[dev newComputePipelineStateWithFunction:fn error:&e];
    if(!pso){fprintf(stderr,"pso: %s\n",[[e description]UTF8String]);return 1;}

    Params P{}; P.width=W;P.height=H;P.num_images=5;
    P.strong_radius=5;P.strong_increment=2;P.rand_seed=1;
    P.depth_min=0.1f;P.depth_max=100.f;P.top_k=4;
    id<MTLBuffer> bP=[dev newBufferWithBytes:&P length:sizeof(P) options:MTLResourceStorageModeShared];
    auto cams=rd([[NSString stringWithFormat:@"%s/cams.bin",fx]UTF8String]);
    id<MTLBuffer> bC=[dev newBufferWithBytes:cams.data() length:cams.size() options:MTLResourceStorageModeShared];
    auto pl=rd(planes_in);
    id<MTLBuffer> bPl=[dev newBufferWithBytes:pl.data() length:pl.size() options:MTLResourceStorageModeShared];
    auto mk=[&](size_t n){ id<MTLBuffer> b=[dev newBufferWithLength:n options:MTLResourceStorageModeShared];
                           memset(b.contents,0,n); return b; };
    id<MTLBuffer> bMaps=mk(N*4);
    { uint32_t* m=(uint32_t*)bMaps.contents; for(size_t i=0;i<N;++i) m[i]=1u|(1u<<8); }
    id<MTLBuffer> bCost=mk(N*4);
    std::vector<id<MTLBuffer>> rest;
    for (int i=0;i<7;++i) rest.push_back(mk(N*32));

    MTLTextureDescriptor* td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatRGBA16Float width:W height:H mipmapped:NO];
    td.usage=MTLTextureUsageShaderRead; td.storageMode=MTLStorageModeShared;
    id<MTLTexture> ref=[dev newTextureWithDescriptor:td];
    { auto px=rd([[NSString stringWithFormat:@"%s/img_0.f16",fx]UTF8String]);
      [ref replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 withBytes:px.data() bytesPerRow:W*8]; }
    MTLTextureDescriptor* sd=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatRGBA16Float width:W height:H mipmapped:NO];
    sd.textureType=MTLTextureType2DArray; sd.arrayLength=32;
    sd.usage=MTLTextureUsageShaderRead; sd.storageMode=MTLStorageModeShared;
    id<MTLTexture> src=[dev newTextureWithDescriptor:sd];
    for(int i=0;i<5;++i){ auto px=rd([[NSString stringWithFormat:@"%s/img_%d.f16",fx,i]UTF8String]);
      [src replaceRegion:MTLRegionMake2D(0,0,W,H) mipmapLevel:0 slice:i
               withBytes:px.data() bytesPerRow:W*8 bytesPerImage:0]; }
    MTLTextureDescriptor* dd=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatR32Float width:W height:H mipmapped:NO];
    dd.textureType=MTLTextureType2DArray; dd.arrayLength=32;
    dd.usage=MTLTextureUsageShaderRead; dd.storageMode=MTLStorageModeShared;
    id<MTLTexture> dep=[dev newTextureWithDescriptor:dd];

    MTLSamplerDescriptor* s1=[MTLSamplerDescriptor new];
    s1.minFilter=MTLSamplerMinMagFilterLinear; s1.magFilter=MTLSamplerMinMagFilterLinear;
    s1.sAddressMode=MTLSamplerAddressModeClampToEdge; s1.tAddressMode=MTLSamplerAddressModeClampToEdge;
    id<MTLSamplerState> sl=[dev newSamplerStateWithDescriptor:s1];
    MTLSamplerDescriptor* s2=[MTLSamplerDescriptor new];
    s2.minFilter=MTLSamplerMinMagFilterNearest; s2.magFilter=MTLSamplerMinMagFilterNearest;
    id<MTLSamplerState> sn=[dev newSamplerStateWithDescriptor:s2];

    id<MTLCommandQueue> q=[dev newCommandQueue];
    id<MTLCommandBuffer> cb=[q commandBuffer];
    id<MTLComputeCommandEncoder> en=[cb computeCommandEncoder];
    [en setComputePipelineState:pso];
    [en setBuffer:bP offset:0 atIndex:0];   [en setBuffer:bC offset:0 atIndex:1];
    [en setBuffer:bMaps offset:0 atIndex:2];[en setBuffer:bPl offset:0 atIndex:3];
    [en setBuffer:bCost offset:0 atIndex:4];
    for (int i=0;i<7;++i) [en setBuffer:rest[i] offset:0 atIndex:5+i];
    [en setTexture:ref atIndex:0]; [en setTexture:src atIndex:1]; [en setTexture:dep atIndex:2];
    [en setSamplerState:sl atIndex:0]; [en setSamplerState:sn atIndex:1];
    [en dispatchThreads:MTLSizeMake(W,H,1) threadsPerThreadgroup:MTLSizeMake(16,16,1)];
    [en endEncoding]; [cb commit]; [cb waitUntilCompleted];

    FILE* f=fopen(costs_out,"wb"); fwrite(bCost.contents,4,N,f); fclose(f);
    printf("→ %s\n", costs_out);
    return 0;
  }
}
