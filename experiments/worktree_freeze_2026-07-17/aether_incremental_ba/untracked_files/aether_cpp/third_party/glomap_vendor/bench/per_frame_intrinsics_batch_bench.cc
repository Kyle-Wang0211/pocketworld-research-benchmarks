// Host-only A/B: optionally re-estimate every stored two-view geometry with
// the camera bound to each image, then run the shipping incremental pipeline.

#include "aether_sfm_c.h"

#include "colmap/estimators/two_view_geometry.h"
#include "colmap/feature/types.h"
#include "colmap/feature/utils.h"
#include "colmap/scene/database.h"
#include "colmap/util/types.h"

#include <glog/logging.h>

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <unordered_map>
#include <vector>

extern "C" int aether_dsp_sift_extract_gpu(const uint8_t*, int, int, int, int,
                                           float*, uint8_t*, int, int*) {
  return -1;
}
extern "C" int aether_gpu_match_gemm_pairs(const uint8_t*, int, const uint8_t*,
                                           int, double, uint32_t*, int, int*) {
  return 2;
}
extern "C" int aether_gpu_match_gemm_pairs_guided(
    const uint8_t*, int, const float*, const uint8_t*, int, const float*,
    double, const float*, const float*, int, float, uint32_t*, int, int*) {
  return 2;
}
extern "C" int aether_gpu_match_last_error(char*, int) { return 0; }

namespace {

void WritePly(const std::string& path, const aether_sfm_point_t* points, int n) {
  std::ofstream out(path, std::ios::binary);
  out << "ply\nformat binary_little_endian 1.0\n";
  out << "element vertex " << n << "\n";
  out << "property float x\nproperty float y\nproperty float z\n";
  out << "property uchar red\nproperty uchar green\nproperty uchar blue\n";
  out << "end_header\n";
  for (int i = 0; i < n; ++i) {
    out.write(reinterpret_cast<const char*>(&points[i].x), sizeof(float) * 3);
    out.write(reinterpret_cast<const char*>(&points[i].r), 1);
    out.write(reinterpret_cast<const char*>(&points[i].g), 1);
    out.write(reinterpret_cast<const char*>(&points[i].b), 1);
  }
}

int ReestimateTwoViewGeometries(const std::string& db_path) {
  auto db = colmap::Database::Open(db_path);
  const auto images = db->ReadAllImages();
  const auto cameras = db->ReadAllCameras();
  std::unordered_map<colmap::image_t, colmap::Image> image_by_id;
  std::unordered_map<colmap::camera_t, colmap::Camera> camera_by_id;
  for (const auto& image : images) image_by_id.emplace(image.ImageId(), image);
  for (const auto& camera : cameras) camera_by_id.emplace(camera.camera_id, camera);

  colmap::TwoViewGeometryOptions options;
  int updated = 0;
  int empty = 0;
  for (const auto& [pair_id, matches] : db->ReadAllMatches()) {
    const auto [image_id1, image_id2] = colmap::PairIdToImagePair(pair_id);
    const auto& image1 = image_by_id.at(image_id1);
    const auto& image2 = image_by_id.at(image_id2);
    const auto points1 = colmap::FeatureKeypointsToPointsVector(
        db->ReadKeypoints(image_id1));
    const auto points2 = colmap::FeatureKeypointsToPointsVector(
        db->ReadKeypoints(image_id2));
    auto geometry = colmap::EstimateTwoViewGeometry(
        camera_by_id.at(image1.CameraId()), points1,
        camera_by_id.at(image2.CameraId()), points2, matches, options);
    db->UpdateTwoViewGeometry(image_id1, image_id2, geometry);
    ++updated;
    if (geometry.inlier_matches.empty()) ++empty;
  }
  std::printf("TVG updated=%d empty=%d cameras=%zu images=%zu\n", updated, empty,
              cameras.size(), images.size());
  return updated;
}

}  // namespace

int main(int argc, char** argv) {
  google::InitGoogleLogging(argv[0]);
  FLAGS_logtostderr = 1;
  if (argc < 3) {
    std::fprintf(stderr, "usage: %s <db> <out_dir> [--reestimate-tvg]\n", argv[0]);
    return 1;
  }
  const std::string db_path = argv[1];
  const std::string out_dir = argv[2];
  const bool reestimate = argc >= 4 && std::string(argv[3]) == "--reestimate-tvg";
  std::filesystem::create_directories(out_dir);
  if (reestimate) ReestimateTwoViewGeometries(db_path);

  aether_sfm_options_t options;
  aether_sfm_options_default(&options);
  aether_sfm_session_t* session = nullptr;
  char summary[1024] = {0};
  const auto rc = aether_sfm_run(db_path.c_str(), "", &options, &session,
                                 summary, sizeof(summary));
  std::printf("RESULT rc=%d summary=%s\n", static_cast<int>(rc), summary);
  if (rc != AETHER_SFM_OK || session == nullptr) return 2;

  aether_sfm_point_t* points = nullptr;
  int n_points = 0;
  int32_t* observation_offsets = nullptr;
  aether_sfm_track_obs_t* observations = nullptr;
  int64_t n_observations = 0;
  const auto getter_start = std::chrono::steady_clock::now();
  if (aether_sfm_get_points_tracked(
          session, &points, &n_points, &observation_offsets, &observations,
          &n_observations) != AETHER_SFM_OK) {
    aether_sfm_free(session);
    return 3;
  }
  const double getter_ms = std::chrono::duration<double, std::milli>(
                               std::chrono::steady_clock::now() - getter_start)
                               .count();
  std::printf("GETTER points=%d observations=%lld ms=%.3f\n", n_points,
              static_cast<long long>(n_observations), getter_ms);
  WritePly(out_dir + "/cloud.ply", points, n_points);
  std::ofstream track_out(out_dir + "/track_lengths.csv");
  track_out << "point_index,track_length\n";
  for (int i = 0; i < n_points; ++i) {
    track_out << i << ',' << (observation_offsets[i + 1] - observation_offsets[i])
              << '\n';
  }
  aether_sfm_points_free(points);
  aether_sfm_track_obs_free(observation_offsets, observations);
  int n_poses = 0;
  if (aether_sfm_get_poses(session, nullptr, 0, &n_poses) != AETHER_SFM_OK) {
    aether_sfm_free(session);
    return 4;
  }
  std::vector<aether_sfm_pose_t> poses(static_cast<size_t>(n_poses));
  if (aether_sfm_get_poses(session, poses.data(), n_poses, &n_poses) !=
      AETHER_SFM_OK) {
    aether_sfm_free(session);
    return 4;
  }
  std::ofstream pose_out(out_dir + "/poses.csv");
  pose_out << "frame_id,registered,qw,qx,qy,qz,tx,ty,tz\n";
  for (const auto& pose : poses) {
    pose_out << pose.frame_id << ',' << pose.registered;
    for (double value : pose.qwxyz) pose_out << ',' << value;
    for (double value : pose.t) pose_out << ',' << value;
    pose_out << '\n';
  }
  const auto dump_rc = aether_sfm_debug_dump_model(session, out_dir.c_str());
  aether_sfm_free(session);
  std::printf("ARTIFACT points=%d dump_rc=%d out=%s\n", n_points,
              static_cast<int>(dump_rc), out_dir.c_str());
  return dump_rc == AETHER_SFM_OK ? 0 : 5;
}
