#include "aether_ghost_mask.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<double> LoadBinaryPly(const char* path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open PLY");
  std::string line;
  std::size_t count = 0;
  bool binary_little_endian = false;
  while (std::getline(input, line)) {
    if (line == "format binary_little_endian 1.0") binary_little_endian = true;
    if (line.rfind("element vertex ", 0) == 0) {
      count = static_cast<std::size_t>(std::stoull(line.substr(15)));
    }
    if (line == "end_header") break;
  }
  if (!binary_little_endian || count == 0) {
    throw std::runtime_error("unsupported PLY header");
  }
  std::vector<double> xyz;
  xyz.reserve(count * 3);
  for (std::size_t index = 0; index < count; ++index) {
    float point[3];
    std::uint8_t color[3];
    input.read(reinterpret_cast<char*>(point), sizeof(point));
    input.read(reinterpret_cast<char*>(color), sizeof(color));
    if (!input) throw std::runtime_error("truncated PLY body");
    xyz.push_back(point[0]);
    xyz.push_back(point[1]);
    xyz.push_back(point[2]);
  }
  return xyz;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::fprintf(stderr, "usage: %s <binary_cloud.ply>\n", argv[0]);
    return 2;
  }
  try {
    const std::vector<double> xyz = LoadBinaryPly(argv[1]);
    std::vector<std::uint8_t> flags;
    aether_ghost::GhostMaskStats stats;
    aether_ghost::GhostMaskIntermediates intermediates;
    if (!aether_ghost::ComputeGhostMask(xyz.data(), xyz.size() / 3, &flags,
                                        &stats, &intermediates)) {
      std::fprintf(stderr, "degenerate cloud\n");
      return 1;
    }
    std::printf(
        "{\"points\":%lld,\"region\":%lld,\"band15\":%lld,"
        "\"cell_ghost\":%lld,\"bimodal_cells\":%lld,"
        "\"floor_cells\":%lld}\n",
        static_cast<long long>(stats.n_points),
        static_cast<long long>(stats.n_region),
        static_cast<long long>(stats.n_band15),
        static_cast<long long>(stats.n_cell_ghost),
        static_cast<long long>(stats.n_bim_cells),
        static_cast<long long>(stats.n_floor_cells));
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
}
