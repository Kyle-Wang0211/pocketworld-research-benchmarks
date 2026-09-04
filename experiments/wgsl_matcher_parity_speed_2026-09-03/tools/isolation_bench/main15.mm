#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <cstdio>
#include <vector>
#include <algorithm>
struct P { uint32_t numA, numB; float ratio, dist; uint32_t numWg, rowBase, p1, p2; };
int main() {
  @autoreleasepool {
    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    id<MTLCommandQueue> q = [dev newCommandQueue];
    NSError* err = nil;
    const uint32_t N = 8192, D = 128, WGR = 128, TG = N / WGR;
    NSArray* names = @[@"now", @"bfly", @"now_mma"];
    NSMutableArray* pipes = [NSMutableArray new];
    for (NSString* n in names) {
      NSString* f = [NSString stringWithFormat:@"/private/tmp/mmaform/%@.metal", n];
      NSString* s = [NSString stringWithContentsOfFile:f encoding:NSUTF8StringEncoding error:&err];
      id<MTLLibrary> L = [dev newLibraryWithSource:s options:[MTLCompileOptions new] error:&err];
      if (!L) { printf("compile %s: %s\n", n.UTF8String, err.localizedDescription.UTF8String); return 1; }
      [pipes addObject:[dev newComputePipelineStateWithFunction:[L newFunctionWithName:n] error:&err]];
    }
    NSString* hs = [NSString stringWithContentsOfFile:@"/private/tmp/mmaform/k.metal" encoding:NSUTF8StringEncoding error:&err];
    id<MTLLibrary> Lh = [dev newLibraryWithSource:hs options:[MTLCompileOptions new] error:&err];
    id<MTLComputePipelineState> pH = [dev newComputePipelineStateWithFunction:[Lh newFunctionWithName:@"formA"] error:&err];
    id<MTLBuffer> A=[dev newBufferWithLength:(size_t)N*D options:MTLResourceStorageModeShared];
    id<MTLBuffer> B=[dev newBufferWithLength:(size_t)N*D options:MTLResourceStorageModeShared];
    id<MTLBuffer> O=[dev newBufferWithLength:(size_t)N*4 options:MTLResourceStorageModeShared];
    id<MTLBuffer> C=[dev newBufferWithLength:(size_t)N*TG*12 options:MTLResourceStorageModePrivate];
    id<MTLBuffer> o2=[dev newBufferWithLength:TG*4 options:MTLResourceStorageModeShared];
    // 真实夹具:u8 描述子 → _Float16(u8) 不缩放(与生产 TU 的 UploadDesc 逐字一致)
    { auto load=[&](const char* p, id<MTLBuffer> buf){
        FILE* f=fopen(p,"rb"); if(!f){printf("no %s\n",p);exit(1);}
        std::vector<unsigned char> u((size_t)N*D); size_t got=fread(u.data(),1,u.size(),f); fclose(f);
        printf("%s read %zu\n", p, got);
        memcpy(buf.contents, u.data(), u.size()); };
      load("/private/tmp/tg/fx/a.u8", A); load("/private/tmp/tg/fx/b.u8", B); }
    uint32_t NB = (uint32_t)atoi(getenv("NB")?getenv("NB"):"8192");
    P prm{N,NB,0.8f,1.0f,TG,0,0,0};
    auto runT=[&](id<MTLComputePipelineState> p){
      id<MTLCommandBuffer> cb=[q commandBuffer]; id<MTLComputeCommandEncoder> e=[cb computeCommandEncoder];
      [e setComputePipelineState:p];
      [e setBuffer:A offset:0 atIndex:0];[e setBuffer:B offset:0 atIndex:1];
      [e setBuffer:O offset:0 atIndex:2];[e setBytes:&prm length:sizeof(prm) atIndex:3];
      [e setBuffer:C offset:0 atIndex:4];[e setThreadgroupMemoryLength:30720 atIndex:0];
      [e dispatchThreadgroups:MTLSizeMake(TG,1,1) threadsPerThreadgroup:MTLSizeMake(512,1,1)];
      [e endEncoding];[cb commit];[cb waitUntilCompleted];
      return (cb.GPUEndTime-cb.GPUStartTime)*1000.0; };
    auto runH=[&]{
      id<MTLCommandBuffer> cb=[q commandBuffer]; id<MTLComputeCommandEncoder> e=[cb computeCommandEncoder];
      [e setComputePipelineState:pH];
      [e setBuffer:A offset:0 atIndex:0];[e setBuffer:o2 offset:0 atIndex:1];
      uint32_t t=256;[e setBytes:&t length:4 atIndex:2];
      [e setThreadgroupMemoryLength:8192 atIndex:0];[e setThreadgroupMemoryLength:16384 atIndex:1];
      [e dispatchThreadgroups:MTLSizeMake(TG,1,1) threadsPerThreadgroup:MTLSizeMake(512,1,1)];
      [e endEncoding];[cb commit];[cb waitUntilCompleted];
      return (cb.GPUEndTime-cb.GPUStartTime)*1000.0; };
    for (id p in pipes) { double acc=0; while(acc<300.0) acc+=runT(p); }
    { double acc=0; while(acc<300.0) acc+=runH(); }
    std::vector<std::vector<double>> v(pipes.count+1);
    for (int r=0;r<25;r++){ for (NSUInteger i=0;i<pipes.count;i++) v[i].push_back(runT(pipes[i])); v[pipes.count].push_back(runH()); }
    for (NSUInteger i=0;i<=pipes.count;i++){ std::sort(v[i].begin(),v[i].end());
      const char* n = i<pipes.count ? [names[i] UTF8String] : "手写(仅MMA)";
      printf("numB=%u %-10s p50=%.3f min=%.3f\n", NB, n, v[i][12], v[i][0]); }
  }
  return 0;
}
