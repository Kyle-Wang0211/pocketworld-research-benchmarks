#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <vulkan/vulkan.h>
int main(){
  void* h=dlopen("libvulkan.so",RTLD_NOW); if(!h){printf("dlopen libvulkan.so failed\n");return 1;}
  PFN_vkGetInstanceProcAddr gipa=(PFN_vkGetInstanceProcAddr)dlsym(h,"vkGetInstanceProcAddr");
  PFN_vkCreateInstance ci=(PFN_vkCreateInstance)gipa(NULL,"vkCreateInstance");
  PFN_vkEnumerateInstanceVersion eiv=(PFN_vkEnumerateInstanceVersion)gipa(NULL,"vkEnumerateInstanceVersion");
  uint32_t iv=VK_API_VERSION_1_0; if(eiv) eiv(&iv);
  printf("instance apiVersion=%u.%u.%u\n",VK_VERSION_MAJOR(iv),VK_VERSION_MINOR(iv),VK_VERSION_PATCH(iv));
  VkApplicationInfo ai={VK_STRUCTURE_TYPE_APPLICATION_INFO}; ai.apiVersion=VK_API_VERSION_1_1;
  VkInstanceCreateInfo ici={VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO}; ici.pApplicationInfo=&ai;
  VkInstance inst; VkResult r=ci(&ici,NULL,&inst); printf("vkCreateInstance(1.1)=%d\n",r); if(r) return 2;
  PFN_vkEnumeratePhysicalDevices epd=(PFN_vkEnumeratePhysicalDevices)gipa(inst,"vkEnumeratePhysicalDevices");
  PFN_vkGetPhysicalDeviceProperties gpp=(PFN_vkGetPhysicalDeviceProperties)gipa(inst,"vkGetPhysicalDeviceProperties");
  PFN_vkEnumerateDeviceExtensionProperties edep=(PFN_vkEnumerateDeviceExtensionProperties)gipa(inst,"vkEnumerateDeviceExtensionProperties");
  PFN_vkGetPhysicalDeviceFeatures gpf=(PFN_vkGetPhysicalDeviceFeatures)gipa(inst,"vkGetPhysicalDeviceFeatures");
  uint32_t n=0; epd(inst,&n,NULL); VkPhysicalDevice pd[4]; if(n>4)n=4; epd(inst,&n,pd); printf("physical devices=%u\n",n);
  for(uint32_t i=0;i<n;i++){ VkPhysicalDeviceProperties p; gpp(pd[i],&p);
    printf("[%u] %s  api=%u.%u.%u driver=0x%x vendor=0x%x maxComputeWorkGroupInvocations=%u maxComputeSharedMemorySize=%u\n",i,p.deviceName,VK_VERSION_MAJOR(p.apiVersion),VK_VERSION_MINOR(p.apiVersion),VK_VERSION_PATCH(p.apiVersion),p.driverVersion,p.vendorID,p.limits.maxComputeWorkGroupInvocations,p.limits.maxComputeSharedMemorySize);
    VkPhysicalDeviceFeatures f; gpf(pd[i],&f); printf("    shaderInt16=%d shaderFloat64=%d shaderInt64=%d\n",f.shaderInt16,f.shaderFloat64,f.shaderInt64);
    uint32_t ne=0; edep(pd[i],NULL,&ne,NULL); VkExtensionProperties ex[256]; if(ne>256)ne=256; edep(pd[i],NULL,&ne,ex);
    printf("    device extensions (%u):",ne); for(uint32_t k=0;k<ne;k++) printf(" %s",ex[k].extensionName); printf("\n"); }
  return 0; }
