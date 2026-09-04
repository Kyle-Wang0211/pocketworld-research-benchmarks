#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <cstdio>
#include <vector>
#include <algorithm>
// 阳性对照专用:同一个 command buffer / 同一个 encoder 里连排 K 次 dispatch，
// 中间用 memoryBarrierWithScope 串行化 —— 彻底消掉 CPU 侧空隙。
// 若 CPU 饥饿假设成立，这样测出的每次耗时应回到健康值 3.87。
int main(int argc, char** argv) { @autoreleasepool {
  id<MTLDevice> dev = MTLCreateSystemDefaultDevice(); NSError* err=nil;
  id<MTLCommandQueue> q = [dev newCommandQueue];
  NSString* src = [NSString stringWithContentsOfFile:@"/private/tmp/mmaform/k.metal"
                                            encoding:NSUTF8StringEncoding error:&err];
  id<MTLLibrary> L = [dev newLibraryWithSource:src options:[MTLCompileOptions new] error:&err];
  if (!L) { printf("compile: %s\n", err.localizedDescription.UTF8String); return 1; }
  id<MTLComputePipelineState> p = [dev newComputePipelineStateWithFunction:[L newFunctionWithName:@"formA"] error:&err];
  const uint32_t TG=64;
  id<MTLBuffer> A=[dev newBufferWithLength:8192*128*2 options:MTLResourceStorageModeShared];
  id<MTLBuffer> O=[dev newBufferWithLength:TG*4 options:MTLResourceStorageModeShared];
  auto run=[&](int K){
    id<MTLCommandBuffer> cb=[q commandBuffer]; id<MTLComputeCommandEncoder> e=[cb computeCommandEncoder];
    [e setComputePipelineState:p];
    [e setBuffer:A offset:0 atIndex:0];[e setBuffer:O offset:0 atIndex:1];
    uint32_t t=256;[e setBytes:&t length:4 atIndex:2];
    [e setThreadgroupMemoryLength:8192 atIndex:0];[e setThreadgroupMemoryLength:16384 atIndex:1];
    for (int i=0;i<K;i++){
      [e dispatchThreadgroups:MTLSizeMake(TG,1,1) threadsPerThreadgroup:MTLSizeMake(512,1,1)];
      if (i+1<K) [e memoryBarrierWithScope:MTLBarrierScopeBuffers];
    }
    [e endEncoding];[cb commit];[cb waitUntilCompleted];
    return (cb.GPUEndTime-cb.GPUStartTime)*1000.0/K; };
  for (int K : {1, 4, 16, 64}) {
    for (int w=0;w<3;w++) run(K);
    std::vector<double> v; for (int i=0;i<9;i++) v.push_back(run(K));
    std::sort(v.begin(),v.end());
    printf("每个 cmdbuf 内 %2d 次 dispatch → 单次 p50=%.3f  min=%.3f  （健康值 3.87）\n", K, v[4], v[0]);
  }
} return 0; }
