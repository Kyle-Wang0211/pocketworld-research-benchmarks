// pose_store_mark_untrusted <in.arkit_pose_v1> <out.arkit_pose_v1> fid[,fid...]
// Reads a pose store with the core's ReadArkitPoseStoreV1, sets
// device_pose_untrusted on the listed frame ids, writes with
// WriteArkitPoseStoreV1 (the production writer). Host-only harness tool.
#include "arkit_pose_store_v1.h"
#include <cstdio>
#include <cstdlib>
#include <set>
#include <sstream>
#include <string>
int main(int argc, char** argv) {
  if (argc < 4) { std::fprintf(stderr, "usage\n"); return 1; }
  std::vector<aether::sfm::ArkitPoseRecordV1> recs;
  if (aether::sfm::ReadArkitPoseStoreV1(argv[1], &recs) != aether::sfm::ArkitPoseStoreStatusV1::kOk) {
    std::fprintf(stderr, "read failed\n"); return 2;
  }
  std::set<int> ids; std::stringstream ss(argv[3]); std::string tok;
  while (std::getline(ss, tok, ',')) {  // "a-b" ranges and single ids
    const size_t dash = tok.find('-');
    if (dash != std::string::npos && dash > 0) {
      for (int v = std::atoi(tok.substr(0, dash).c_str());
           v <= std::atoi(tok.substr(dash + 1).c_str()); ++v) ids.insert(v);
    } else if (!tok.empty()) {
      ids.insert(std::atoi(tok.c_str()));
    }
  }
  int n = 0;
  for (auto& r : recs) if (ids.count(r.frame_id)) { r.device_pose_untrusted = true; ++n; }
  if (aether::sfm::WriteArkitPoseStoreV1(argv[2], recs) != aether::sfm::ArkitPoseStoreStatusV1::kOk) {
    std::fprintf(stderr, "write failed\n"); return 3;
  }
  std::vector<aether::sfm::ArkitPoseRecordV1> back;
  if (aether::sfm::ReadArkitPoseStoreV1(argv[2], &back) != aether::sfm::ArkitPoseStoreStatusV1::kOk || back.size() != recs.size()) {
    std::fprintf(stderr, "re-read failed\n"); return 4;
  }
  int m = 0; for (auto& r : back) m += r.device_pose_untrusted ? 1 : 0;
  std::printf("marked %d/%zu untrusted (re-read %d)\n", n, recs.size(), m);
  return 0;
}
