#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <cstdio>
#include <vector>
#include <algorithm>
int main(){ @autoreleasepool {
  id<MTLDevice> dev=MTLCreateSystemDefaultDevice(); NSError* err=nil;
  id<MTLCommandQueue> q=[dev newCommandQueue];
  auto mk=[&](NSString* f){ NSString* s=[NSString stringWithContentsOfFile:f encoding:NSUTF8StringEncoding error:&err];
    id<MTLLibrary> L=[dev newLibraryWithSource:s options:[MTLCompileOptions new] error:&err];
    if(!L){printf("compile %s: %s\n",f.UTF8String,err.localizedDescription.UTF8String);exit(1);}
    return [dev newComputePipelineStateWithFunction:[L newFunctionWithName:@"formA"] error:&err]; };
  id<MTLComputePipelineState> pT=mk(@"/private/tmp/mmaform/k_ilp4.metal");
  id<MTLComputePipelineState> pN=mk(@"/private/tmp/mmaform/k_r2b.metal");
  printf("占用率探针 ILP4: maxTPT=%lu  R2: maxTPT=%lu\n",(unsigned long)pT.maxTotalThreadsPerThreadgroup,(unsigned long)pN.maxTotalThreadsPerThreadgroup);
  const uint32_t TG=64;
  id<MTLBuffer> A=[dev newBufferWithLength:8192*128*2 options:MTLResourceStorageModeShared];
  id<MTLBuffer> O=[dev newBufferWithLength:TG*4 options:MTLResourceStorageModeShared];
  auto run=[&](id<MTLComputePipelineState> p){
    id<MTLCommandBuffer> cb=[q commandBuffer]; id<MTLComputeCommandEncoder> e=[cb computeCommandEncoder];
    [e setComputePipelineState:p];[e setBuffer:A offset:0 atIndex:0];[e setBuffer:O offset:0 atIndex:1];
    uint32_t t=256;[e setBytes:&t length:4 atIndex:2];
    [e setThreadgroupMemoryLength:8192 atIndex:0];[e setThreadgroupMemoryLength:16384 atIndex:1];
    [e dispatchThreadgroups:MTLSizeMake(TG,1,1) threadsPerThreadgroup:MTLSizeMake(512,1,1)];
    [e endEncoding];[cb commit];[cb waitUntilCompleted];
    return (cb.GPUEndTime-cb.GPUStartTime)*1000.0; };
  { double a=0; while(a<300) a+=run(pT); } { double a=0; while(a<300) a+=run(pN); }
  std::vector<double> vt,vn; for(int i=0;i<15;i++){ vt.push_back(run(pT)); vn.push_back(run(pN)); }
  std::sort(vt.begin(),vt.end()); std::sort(vn.begin(),vn.end());
  printf("ILP4 常驻16/载入4      p50=%.3f min=%.3f\nR2b  常驻16/载入2      p50=%.3f min=%.3f\n⇒ %+.3f ms (%+.1f%%)\n",
         vt[7],vt[0],vn[7],vn[0], vn[7]-vt[7], 100.0*(vn[7]/vt[7]-1.0));
} return 0; }
