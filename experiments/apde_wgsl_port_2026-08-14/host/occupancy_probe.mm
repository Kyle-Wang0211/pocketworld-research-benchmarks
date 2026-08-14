// 占用率探针:maxTotalThreadsPerThreadgroup 会因寄存器/私有内存压力下降。
// 1024 = 无压力。这是判断 lane 私有数组代价的直接指标。
#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <cstdio>
int main(int argc,const char**argv){@autoreleasepool{
  if(argc<2){printf("usage: occupancy_probe <metallib>\n");return 1;}
  id<MTLDevice> d=MTLCreateSystemDefaultDevice();
  printf("GPU: %s\n",[[d name]UTF8String]);
  NSError*e=nil;
  id<MTLLibrary> l=[d newLibraryWithURL:[NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]] error:&e];
  if(!l){printf("lib fail: %s\n",[[e description]UTF8String]);return 1;}
  for(NSString*n in [l functionNames]){
    id<MTLFunction> f=[l newFunctionWithName:n];
    id<MTLComputePipelineState> p=[d newComputePipelineStateWithFunction:f error:&e];
    if(!p){printf("  %-30s FAIL\n",[n UTF8String]);continue;}
    printf("  %-30s maxThreads/TG=%4lu  execWidth=%2lu  staticTGMem=%lu B\n",
      [n UTF8String],(unsigned long)p.maxTotalThreadsPerThreadgroup,
      (unsigned long)p.threadExecutionWidth,(unsigned long)p.staticThreadgroupMemoryLength);
  }
}return 0;}
