#include "vulkan_apple/frozen_scene_loader.h"
#include <cstdio>
using namespace pocketworld::official_dense::vulkan;
int main(int argc, char** argv){
  FrozenScene scene; std::string detail;
  if(!LoadFrozenScene(argv[1], &scene, &detail)) return 1;
  const int slot = argc > 2 ? std::atoi(argv[2]) : 0;
  std::printf("%d", slot);
  for (const std::int32_t s : scene.images[slot].source_indices)
    std::printf(" %d", s);
  std::printf("\n");
  return 0;
}
