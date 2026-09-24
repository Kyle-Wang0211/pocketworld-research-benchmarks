// device_align_offline.cc — host checker that drives the EXACT core header
// (official_pipeline/src/device_pose_alignment_v1.h) from text pairs, so the
// offline gate numbers (90 phone captures, held-out even/odd, controls) come
// from the same code the core runs at the end of finalize.
//
// usage: device_align_offline <pairs.txt> [prior_position_std_m=kDevicePriorPositionStdM] [fit=all|even|odd]
// The std is turned into each pair's position_covariance with the same
// upstream expression the core uses (DevicePriorPositionCovariance =
// exe/sfm.cc:508-513); a value <= 0 sets a zero covariance, which upstream's
// trace <= 0 test skips, i.e. the "no valid covariance" fallback (1.0 m).
// pairs.txt lines:
//   frame_id  rqw rqx rqy rqz rtx rty rtz  dqw dqx dqy dqz dtx dty dtz
// r* = delivered CamFromWorld, d* = device CamFromWorld in COLMAP camera axes
// (FrameRecord::cam_from_world convention). even/odd = pair index parity.
// Output: one JSON object on stdout.
#include "device_pose_alignment_v1.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>

int main(int argc, char** argv) {
  if (argc < 2) {
    std::fprintf(stderr, "usage: %s pairs.txt [prior_position_std_m] [all|even|odd]\n",
                 argv[0]);
    return 1;
  }
  const double sigma =
      argc > 2 ? std::atof(argv[2]) : aether::sfm::kDevicePriorPositionStdM;
  const std::string fit = argc > 3 ? argv[3] : "all";
  std::vector<aether::sfm::DeviceCentrePairV1> pairs;
  std::ifstream in(argv[1]);
  std::string line;
  while (std::getline(in, line)) {
    if (line.empty() || line[0] == '#') continue;
    std::istringstream ss(line);
    aether::sfm::DeviceCentrePairV1 p;
    double r[7], d[7];
    ss >> p.frame_id;
    for (double& v : r) ss >> v;
    for (double& v : d) ss >> v;
    if (!ss) {
      std::fprintf(stderr, "bad line: %s\n", line.c_str());
      return 2;
    }
    p.recon_cam_from_world = colmap::Rigid3d(
        Eigen::Quaterniond(r[0], r[1], r[2], r[3]).normalized(),
        Eigen::Vector3d(r[4], r[5], r[6]));
    p.device_cam_from_world = colmap::Rigid3d(
        Eigen::Quaterniond(d[0], d[1], d[2], d[3]).normalized(),
        Eigen::Vector3d(d[4], d[5], d[6]));
    p.position_covariance =
        sigma > 0 ? aether::sfm::DevicePriorPositionCovariance(sigma, sigma, sigma)
                  : Eigen::Matrix3d::Zero().eval();
    pairs.push_back(p);
  }
  std::vector<char> mask(pairs.size(), 1);
  if (fit != "all") {
    const size_t want = fit == "even" ? 0 : 1;
    for (size_t i = 0; i < pairs.size(); ++i) mask[i] = (i % 2 == want);
  }
  const auto res = aether::sfm::EstimateDeviceAlignmentV1(
      pairs, fit == "all" ? nullptr : &mask);
  const colmap::Sim3d& T = res.device_from_recon;
  std::printf(
      "{\"status\":\"%s\",\"applied\":%s,\"n_pairs\":%d,\"n_fit\":%d,"
      "\"ransac_inliers\":%d,\"inliers_all\":%d,\"trials\":%zu,"
      "\"sigma_m\":%.6g,\"max_error_m\":%.9g,\"scale\":%.12g,"
      "\"q\":[%.12g,%.12g,%.12g,%.12g],\"t\":[%.12g,%.12g,%.12g],"
      "\"centre_err_m\":{\"median\":%.9g,\"p90\":%.9g,\"max\":%.9g},"
      "\"rot_err_deg\":{\"median\":%.9g,\"max\":%.9g},\"fit_mask\":[",
      aether::sfm::DeviceAlignStatusNameV1(res.status),
      res.Applied() ? "true" : "false", res.n_pairs, res.n_fit,
      res.n_ransac_inliers, res.n_inliers_all, res.ransac_trials, res.sigma_m,
      res.max_error_m, T.scale(), T.rotation().w(), T.rotation().x(),
      T.rotation().y(), T.rotation().z(), T.translation().x(),
      T.translation().y(), T.translation().z(),
      res.errors.proj_center_errors.median, res.errors.proj_center_errors.p90,
      res.errors.proj_center_errors.max, res.errors.rotation_errors_deg.median,
      res.errors.rotation_errors_deg.max);
  for (size_t i = 0; i < mask.size(); ++i)
    std::printf("%s%d", i ? "," : "", mask[i] ? 1 : 0);
  std::printf("],\"frame_ids\":[");
  for (size_t i = 0; i < pairs.size(); ++i)
    std::printf("%s%d", i ? "," : "", pairs[i].frame_id);
  std::printf("],\"centre_err_all_m\":[");
  for (size_t i = 0; i < res.centre_error_m.size(); ++i)
    std::printf("%s%.9g", i ? "," : "", res.centre_error_m[i]);
  std::printf("],\"inlier_all\":[");
  for (size_t i = 0; i < res.inlier_all.size(); ++i)
    std::printf("%s%d", i ? "," : "", res.inlier_all[i] ? 1 : 0);
  std::printf("]}\n");
  return 0;
}
