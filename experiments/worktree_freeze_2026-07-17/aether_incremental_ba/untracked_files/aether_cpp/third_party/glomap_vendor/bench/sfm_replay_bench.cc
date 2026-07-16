// sfm_replay_bench.cc — [INCREMENTAL-GLOBAL-BA A/B 2026-07-13] HOST-ONLY driver
// that replays a pulled device sfm_live.db through the streaming SfM ABI so the
// capture-time rolling global BA (AETHER_INCREMENTAL_GLOBAL_BA) can be A/B'd
// against the finalize output WITHOUT a device.
//
// It is the FIRST caller of aether_sfm_add_frame_features (the feature-injection
// sibling of add_frame, built exactly for this — see aether_sfm_c.h:110). Per
// frame it reads the db's keypoints + RootSIFT descriptors + shared camera
// intrinsics and the ARKit CamFromWorld pose prior from the sidecar. The host
// replay build also reuses the pulled device db's exact matches and verified
// two-view geometries through AETHER_REPLAY_MATCH_DB, then:
//     aether_sfm_create
//   → aether_sfm_add_frame_features × N        (stored device pairs; no rematch)
//   → aether_sfm_finalize_async → poll REFINED  (this is the SHIPPING finalize:
//        the sync aether_sfm_finalize rebuilds from the db and never touches the
//        in-memory live_recon that the rolling global BA refines, so only the
//        async live_reuse path exercises the incremental-BA finalize collapse.)
//
// The rolling global BA runs during add_frame_features (MaybeIncrementalGlobalRefine,
// gated on AETHER_INCREMENTAL_GLOBAL_BA=1); the finalize collapse runs in the
// RefineGlobalBA worker. Run twice — env unset (OFF) vs =1 (ON) — and diff the
// finalize sparse cloud (dumped as cloud.ply + COLMAP bin model) + reproj/point
// counts + streaming/finalize wall time.
//
// usage: sfm_replay_bench_exe <src_sfm_live.db> <poses.jsonl> <out_dir>
//        [--k=12] [--max-frames=0] [--pair-db=<path>]
//        [--intrinsics-tsv=<path>]
//
// Both arms MUST use identical args; the only intended variable is the
// AETHER_INCREMENTAL_GLOBAL_BA env (and its cadence/window/rounds knobs).

#include "aether_sfm_c.h"

#include "colmap/feature/types.h"
#include "colmap/scene/camera.h"
#include "colmap/scene/database.h"
#include "colmap/scene/image.h"

#include <glog/logging.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <cstdint>
#include <unordered_map>
#include <vector>

// ─── host GPU-symbol stubs ──────────────────────────────────────────
// aether_sfm_c.cc references the platform Metal TUs (pwsfm_gpu_match.mm /
// dsp_sift_gpu_c) as __attribute__((weak)) so device links them real and host
// resolves them to null. But this exe is the FIRST host caller to pull
// aether_sfm_c.cc.o out of libglomap_full.a, and macOS ld64 rejects a plain
// weak *reference* with no definition ("Undefined symbols"). Provide no-op
// host definitions (production source untouched). use_gpu_match=0 gates every
// call site off, so these never actually run — they exist only to link.
extern "C" int aether_dsp_sift_extract_gpu(const uint8_t*, int, int, int, int,
                                           float*, uint8_t*, int, int*) {
  return -1;  // "GPU extractor unavailable" → add_frame falls back to CPU
}
extern "C" int aether_gpu_match_gemm_pairs(const uint8_t*, int, const uint8_t*,
                                           int, double, uint32_t*, int, int*) {
  return 2;  // "Metal unavailable" (rc bucket 2) → pair skipped if ever called
}
extern "C" int aether_gpu_match_gemm_pairs_guided(
    const uint8_t*, int, const float*, const uint8_t*, int, const float*,
    double, const float*, const float*, int, float, uint32_t*, int, int*) {
  return 2;
}
extern "C" int aether_gpu_match_last_error(char*, int) { return 0; }

namespace {

double NowMs() {
  using namespace std::chrono;
  return duration<double, std::milli>(steady_clock::now().time_since_epoch())
      .count();
}

std::string ArgS(int argc, char** argv, const char* key, const char* def) {
  const size_t kl = std::strlen(key);
  for (int i = 1; i < argc; ++i)
    if (std::strncmp(argv[i], key, kl) == 0) {
      const char* eq = std::strchr(argv[i], '=');
      if (eq) return std::string(eq + 1);
    }
  return std::string(def);
}

// ─── minimal jsonl pose parser ──────────────────────────────────────
// Each line: {"frameId":N, ... "arkitCamFromWorldQwxyz":[qw,qx,qy,qz],
//             "arkitCamFromWorldTxyz":[tx,ty,tz], ...}
struct Pose {
  bool ok = false;
  std::array<double, 4> q{1, 0, 0, 0};  // CamFromWorld qw,qx,qy,qz
  std::array<double, 3> t{0, 0, 0};     // CamFromWorld tx,ty,tz
};

struct Intrinsics {
  float fx = 0.0f;
  float fy = 0.0f;
  float cx = 0.0f;
  float cy = 0.0f;
};

// Parse the N doubles inside the "[...]" that follows `key` in `line`.
static bool ParseArray(const std::string& line, const char* key, double* out,
                       int n) {
  const size_t k = line.find(key);
  if (k == std::string::npos) return false;
  const size_t lb = line.find('[', k);
  if (lb == std::string::npos) return false;
  const char* p = line.c_str() + lb + 1;
  char* end = nullptr;
  for (int i = 0; i < n; ++i) {
    out[i] = std::strtod(p, &end);
    if (end == p) return false;
    p = end;
    while (*p == ',' || *p == ' ') ++p;
  }
  return true;
}

std::unordered_map<int, Pose> LoadPoses(const std::string& path) {
  std::unordered_map<int, Pose> poses;
  std::ifstream in(path);
  std::string line;
  while (std::getline(in, line)) {
    const size_t fk = line.find("\"frameId\":");
    if (fk == std::string::npos) continue;
    const int fid = std::atoi(line.c_str() + fk + 10);
    Pose p;
    const bool okq =
        ParseArray(line, "\"arkitCamFromWorldQwxyz\":", p.q.data(), 4);
    const bool okt =
        ParseArray(line, "\"arkitCamFromWorldTxyz\":", p.t.data(), 3);
    p.ok = okq && okt;
    poses[fid] = p;
  }
  return poses;
}

std::unordered_map<int, Intrinsics> LoadIntrinsics(const std::string& path) {
  std::unordered_map<int, Intrinsics> intrinsics;
  if (path.empty()) return intrinsics;
  std::ifstream in(path);
  int frame_id = -1;
  Intrinsics k;
  while (in >> frame_id >> k.fx >> k.fy >> k.cx >> k.cy) {
    intrinsics[frame_id] = k;
  }
  return intrinsics;
}

void WritePly(const std::string& path, const aether_sfm_point_t* pts, int n) {
  std::ofstream out(path, std::ios::binary);
  out << "ply\nformat binary_little_endian 1.0\n";
  out << "element vertex " << n << "\n";
  out << "property float x\nproperty float y\nproperty float z\n";
  out << "property uchar red\nproperty uchar green\nproperty uchar blue\n";
  out << "end_header\n";
  for (int i = 0; i < n; ++i) {
    out.write(reinterpret_cast<const char*>(&pts[i].x), sizeof(float) * 3);
    out.write(reinterpret_cast<const char*>(&pts[i].r), 1);
    out.write(reinterpret_cast<const char*>(&pts[i].g), 1);
    out.write(reinterpret_cast<const char*>(&pts[i].b), 1);
  }
}

}  // namespace

int main(int argc, char** argv) {
  google::InitGoogleLogging(argv[0]);
  FLAGS_logtostderr = 1;
  if (argc < 4) {
    std::fprintf(stderr,
                 "usage: %s <src_sfm_live.db> <poses.jsonl> <out_dir> "
                 "[--k=12] [--max-frames=0] [--pair-db=<path>] "
                 "[--intrinsics-tsv=<path>]\n",
                 argv[0]);
    return 1;
  }
  const std::string src_db = argv[1];
  const std::string poses_path = argv[2];
  const std::string out_dir = argv[3];
  const int k = std::atoi(ArgS(argc, argv, "--k", "12").c_str());
  const int max_frames =
      std::atoi(ArgS(argc, argv, "--max-frames", "0").c_str());
  const std::string pair_db_path =
      ArgS(argc, argv, "--pair-db", src_db.c_str());
  const std::string intrinsics_path =
      ArgS(argc, argv, "--intrinsics-tsv", "");
  const bool keep_session_db =
      std::atoi(ArgS(argc, argv, "--keep-session-db", "1").c_str()) != 0;

  const char* incr = std::getenv("AETHER_INCREMENTAL_GLOBAL_BA");
  std::printf("REPLAY src_db=%s pair_db=%s poses=%s intrinsics=%s out=%s "
              "k=%d max_frames=%d "
              "AETHER_INCREMENTAL_GLOBAL_BA=%s\n",
              src_db.c_str(), pair_db_path.c_str(), poses_path.c_str(),
              intrinsics_path.empty() ? "(db-camera)" : intrinsics_path.c_str(),
              out_dir.c_str(), k, max_frames, incr ? incr : "(unset)");
  std::fflush(stdout);

  // ── source db (read-only): keypoints + descriptors + shared camera ──
  auto db = colmap::Database::Open(src_db);
  std::vector<colmap::Image> images = db->ReadAllImages();
  std::sort(images.begin(), images.end(),
            [](const colmap::Image& a, const colmap::Image& b) {
              return a.ImageId() < b.ImageId();
            });
  const auto poses = LoadPoses(poses_path);
  const auto intrinsics = LoadIntrinsics(intrinsics_path);
  std::printf("SOURCE n_images=%zu n_poses=%zu n_intrinsics=%zu\n",
              images.size(), poses.size(), intrinsics.size());
  std::fflush(stdout);

  auto pair_db = colmap::Database::Open(pair_db_path);
  const auto stored_matches = pair_db->ReadAllMatches();
  const auto stored_geometries = pair_db->ReadTwoViewGeometries();
  std::unordered_map<colmap::image_pair_t, int> pair_presence;
  int nonempty_matches = 0;
  int nonempty_geometries = 0;
  for (const auto& [pair_id, matches] : stored_matches) {
    pair_presence[pair_id] |= 1;
    if (!matches.empty()) ++nonempty_matches;
  }
  for (const auto& [pair_id, geometry] : stored_geometries) {
    pair_presence[pair_id] |= 2;
    if (!geometry.inlier_matches.empty()) ++nonempty_geometries;
  }
  const int geometry_only_pairs = static_cast<int>(std::count_if(
      pair_presence.begin(), pair_presence.end(),
      [](const auto& item) { return item.second == 2; }));
  const int geometry_missing_pairs = static_cast<int>(std::count_if(
      pair_presence.begin(), pair_presence.end(),
      [](const auto& item) { return item.second == 1; }));
  std::printf(
      "STORED_PAIRS matches=%zu nonempty_matches=%d two_view=%zu "
      "nonempty_two_view=%d geometry_missing=%d geometry_only=%d\n",
      stored_matches.size(), nonempty_matches, stored_geometries.size(),
      nonempty_geometries, geometry_missing_pairs, geometry_only_pairs);
  std::fflush(stdout);
  if (images.size() != poses.size() || stored_matches.empty() ||
      nonempty_matches != static_cast<int>(stored_matches.size()) ||
      geometry_only_pairs != 0) {
    std::fprintf(stderr, "stored replay input is incomplete\n");
    return 5;
  }
  if (!intrinsics_path.empty() && intrinsics.size() != images.size()) {
    std::fprintf(stderr,
                 "per-frame intrinsics are incomplete: got %zu for %zu images\n",
                 intrinsics.size(), images.size());
    return 7;
  }
  if (setenv("AETHER_REPLAY_MATCH_DB", pair_db_path.c_str(), 1) != 0) {
    std::perror("setenv AETHER_REPLAY_MATCH_DB");
    return 6;
  }

  // ── streaming session ──
  aether_sfm_options_t opt;
  aether_sfm_options_default(&opt);
  opt.use_gpu_match = 0;   // temporary replay core bypasses matching entirely
  opt.use_gpu_extract = 0;
  opt.k_neighbors = k;     // production capture uses 12 (spatial-first)
  const std::string sess_db = out_dir + "/session.db";
  std::remove(sess_db.c_str());
  aether_sfm_session_t* s = nullptr;
  aether_sfm_result_t rc = aether_sfm_create(sess_db.c_str(), &opt, &s);
  if (rc != AETHER_SFM_OK || !s) {
    std::fprintf(stderr, "aether_sfm_create failed: %s\n",
                 aether_sfm_result_str(rc));
    return 2;
  }

  int fed = 0, missing_pose = 0;
  const double t_stream0 = NowMs();
  for (const colmap::Image& img : images) {
    if (max_frames > 0 && fed >= max_frames) break;
    const colmap::image_t image_id = img.ImageId();
    const int frame_id = static_cast<int>(image_id) - 1;  // ABI: frame_id = id-1
    const colmap::FeatureKeypoints kps = db->ReadKeypoints(image_id);
    const colmap::FeatureDescriptors desc = db->ReadDescriptors(image_id);
    const int n = static_cast<int>(kps.size());
    if (n == 0 || desc.data.rows() != n || desc.data.cols() != 128) {
      std::fprintf(stderr, "frame %d: bad kp/desc (n=%d rows=%ld cols=%ld)\n",
                   frame_id, n, (long)desc.data.rows(), (long)desc.data.cols());
      continue;
    }
    const colmap::Camera cam = db->ReadCamera(img.CameraId());
    float fx = static_cast<float>(cam.FocalLengthX());
    float fy = static_cast<float>(cam.FocalLengthY());
    float cx = static_cast<float>(cam.PrincipalPointX());
    float cy = static_cast<float>(cam.PrincipalPointY());
    if (!intrinsics_path.empty()) {
      const auto intrinsics_it = intrinsics.find(frame_id);
      if (intrinsics_it == intrinsics.end()) {
        std::fprintf(stderr, "frame %d: missing per-frame intrinsics\n", frame_id);
        aether_sfm_free(s);
        return 7;
      }
      fx = intrinsics_it->second.fx;
      fy = intrinsics_it->second.fy;
      cx = intrinsics_it->second.cx;
      cy = intrinsics_it->second.cy;
    }
    const int w = static_cast<int>(cam.width);
    const int h = static_cast<int>(cam.height);

    std::vector<float> xy(static_cast<size_t>(n) * 2);
    for (int i = 0; i < n; ++i) {
      xy[2 * i] = kps[i].x;
      xy[2 * i + 1] = kps[i].y;
    }

    auto it = poses.find(frame_id);
    const double* q = nullptr;
    const double* t = nullptr;
    if (it != poses.end() && it->second.ok) {
      q = it->second.q.data();
      t = it->second.t.data();
    } else {
      ++missing_pose;  // add_frame_features accepts NULL pose (falls to no-prior)
    }

    int out_fid = -1;
    rc = aether_sfm_add_frame_features(s, xy.data(), desc.data.data(), n, w, h,
                                       fx, fy, cx, cy, q, t, &out_fid);
    if (rc != AETHER_SFM_OK) {
      std::fprintf(stderr, "add_frame_features frame %d failed: %s\n", frame_id,
                   aether_sfm_result_str(rc));
      continue;
    }
    ++fed;
    if (fed % 25 == 0) {
      std::printf("  fed %d/%zu frames (last n_kp=%d)\n", fed, images.size(), n);
      std::fflush(stdout);
    }
  }
  const double stream_ms = NowMs() - t_stream0;
  std::printf("STREAMED fed=%d missing_pose=%d stream_ms=%.1f\n", fed,
              missing_pose, stream_ms);
  std::fflush(stdout);

  // The device DB contains capture-time pairs plus finish-time repay/spatial
  // pairs. add_frame_features consumes only the live K-neighbour subset so the
  // in-memory live reconstruction follows production capture semantics. Before
  // the final global refinement, import the complete persisted pair graph into
  // the replay session verbatim. This is a database copy, never a matcher.
  {
    auto session_db = colmap::Database::Open(sess_db);
    int imported_matches = 0;
    int imported_geometries = 0;
    for (const auto& [pair_id, matches] : stored_matches) {
      const auto [image_id1, image_id2] = colmap::PairIdToImagePair(pair_id);
      if (session_db->ExistsMatches(image_id1, image_id2)) {
        session_db->DeleteMatches(image_id1, image_id2);
      }
      session_db->WriteMatches(image_id1, image_id2, matches);
      ++imported_matches;
      const colmap::TwoViewGeometry geometry =
          pair_db->ReadTwoViewGeometry(image_id1, image_id2);
      if (session_db->ExistsTwoViewGeometry(image_id1, image_id2)) {
        session_db->DeleteTwoViewGeometry(image_id1, image_id2);
      }
      session_db->WriteTwoViewGeometry(image_id1, image_id2, geometry);
      ++imported_geometries;
    }
    session_db->Close();
    std::printf("IMPORTED_STORED_GRAPH matches=%d two_view=%d matcher_calls=0\n",
                imported_matches, imported_geometries);
    std::fflush(stdout);
  }

  // ── finalize (async live_reuse path = shipping finalize) ──
  char fj[512] = {0};
  const double t_fin0 = NowMs();
  rc = aether_sfm_finalize_async(s, fj, sizeof(fj));
  if (rc != AETHER_SFM_OK) {
    std::fprintf(stderr, "finalize_async failed: %s\n",
                 aether_sfm_result_str(rc));
    aether_sfm_free(s);
    return 3;
  }
  std::printf("FINALIZE_ASYNC phase1=%s\n", fj);
  std::fflush(stdout);

  // Poll to REFINED (2) or ERROR (3).
  int status = aether_sfm_finalize_status(s);
  while (status != 2 && status != 3) {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    status = aether_sfm_finalize_status(s);
  }
  const double finalize_ms = NowMs() - t_fin0;
  if (status == 3) {
    std::fprintf(stderr, "finalize refine ERROR\n");
    aether_sfm_free(s);
    return 4;
  }
  std::printf("REFINED finalize_ms=%.1f\n", finalize_ms);
  std::fflush(stdout);

  // ── outputs: diag + poses + points ──
  double reproj = -1;
  int64_t npts = 0, ntrack3 = 0, nobs = 0;
  aether_sfm_final_diag(s, &reproj, &npts, &ntrack3, &nobs);

  std::vector<aether_sfm_pose_t> poses_out(images.size());
  int n_pose = 0;
  aether_sfm_get_poses(s, poses_out.data(), (int)poses_out.size(), &n_pose);
  int n_reg = 0;
  for (int i = 0; i < n_pose; ++i)
    if (poses_out[i].registered) ++n_reg;

  std::ofstream pose_out(out_dir + "/solved_poses.csv");
  pose_out << "frame_id,registered,qw,qx,qy,qz,tx,ty,tz\n";
  pose_out.precision(17);
  for (int i = 0; i < n_pose; ++i) {
    const auto& pose = poses_out[i];
    pose_out << pose.frame_id << ',' << pose.registered << ','
             << pose.qwxyz[0] << ',' << pose.qwxyz[1] << ','
             << pose.qwxyz[2] << ',' << pose.qwxyz[3] << ','
             << pose.t[0] << ',' << pose.t[1] << ',' << pose.t[2] << '\n';
  }
  pose_out.close();

  aether_sfm_point_t* pts = nullptr;
  int n_pts = 0;
  aether_sfm_get_points(s, &pts, &n_pts);
  WritePly(out_dir + "/cloud.ply", pts, n_pts);
  aether_sfm_points_free(pts);

  aether_sfm_debug_dump_model(s, out_dir.c_str());

  std::printf(
      "RESULT incr=%s n_reg=%d n_points=%lld track3plus=%lld n_obs=%lld "
      "mean_reproj_px=%.4f stream_ms=%.1f finalize_ms=%.1f total_ms=%.1f\n",
      incr ? incr : "off", n_reg, (long long)npts, (long long)ntrack3,
      (long long)nobs, reproj, stream_ms, finalize_ms, stream_ms + finalize_ms);
  std::fflush(stdout);

  aether_sfm_free(s);
  if (!keep_session_db) {
    // The replay session DB is a deterministic derivative of src_db + pair_db,
    // not a capture input. Large cap replays may opt out of retaining this
    // duplicate while keeping the model, PLY, command log, and immutable source
    // hashes. Never used by device/product builds.
    std::remove(sess_db.c_str());
    std::remove((sess_db + "-wal").c_str());
    std::remove((sess_db + "-shm").c_str());
  }
  return 0;
}
