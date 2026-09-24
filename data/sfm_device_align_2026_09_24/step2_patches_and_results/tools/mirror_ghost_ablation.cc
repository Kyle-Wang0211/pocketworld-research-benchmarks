// Ablation: why does the delivered point set change after DEVICE-ALIGN-V1?
// Reads the post-alignment model dumped by the run, undoes / re-applies parts of the
// applied Sim3 and re-runs the core's own delivery filter chain pieces
// (tri-angle predicate copied verbatim from official_aether_sfm_c.cc:11717-11741,
//  aether_mirror_ghost::Detect from official_mirror_ghost.h unchanged).
#include "official_mirror_ghost.h"
#include "colmap/scene/reconstruction.h"
#include "colmap/geometry/sim3.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
static bool PassTri(const colmap::Reconstruction& recon, const colmap::Point3D& point, double min_cos) {
  constexpr int kMaxObs = 32; Eigen::Vector3d dirs[kMaxObs]; int k = 0;
  for (const auto& el : point.track.Elements()) {
    if (k >= kMaxObs) break;
    if (!recon.ExistsImage(el.image_id)) continue;
    const auto& image = recon.Image(el.image_id);
    if (!image.HasPose()) continue;
    const Eigen::Vector3d v = image.ProjectionCenter() - point.xyz;
    const double norm = v.norm(); if (!(norm > 0.0)) continue;
    dirs[k++] = v / norm;
  }
  if (k < 2) return false;
  for (int i = 0; i < k; ++i) for (int j = i + 1; j < k; ++j) if (dirs[i].dot(dirs[j]) <= min_cos) return true;
  return false;
}
static void Run(const char* tag, const colmap::Reconstruction& r) {
  const double min_cos = std::cos(3.0 * M_PI / 180.0);
  std::vector<aether_mirror_ghost::P3> mp;
  for (const auto& [pid, p] : r.Points3D()) if (PassTri(r, p, min_cos))
    mp.push_back({(float)p.xyz.x(), (float)p.xyz.y(), (float)p.xyz.z()});
  const auto res = aether_mirror_ghost::Detect(mp);
  std::printf("%-26s survivors=%zu floor_y=%.4f candidates=%d killed=%zu eps=%.5f\n", tag, mp.size(), res.floor_y, res.candidates, res.kill.size(), res.eps);
}
int main(int argc, char** argv) {
  // args: model_dir scale qw qx qy qz tx ty tz  (applied device_from_recon)
  colmap::Reconstruction post; post.Read(argv[1]);
  const colmap::Sim3d T(std::atof(argv[2]), Eigen::Quaterniond(std::atof(argv[3]), std::atof(argv[4]), std::atof(argv[5]), std::atof(argv[6])).normalized(),
                        Eigen::Vector3d(std::atof(argv[7]), std::atof(argv[8]), std::atof(argv[9])));
  Run("post (as delivered)", post);
  colmap::Reconstruction pre = post; pre.Transform(colmap::Inverse(T)); Run("pre = post*T^-1", pre);
  { colmap::Reconstruction x = pre; x.Transform(colmap::Sim3d(T.scale(), Eigen::Quaterniond::Identity(), Eigen::Vector3d::Zero())); Run("pre*scale_only", x); }
  { colmap::Reconstruction x = pre; x.Transform(colmap::Sim3d(1.0, T.rotation(), Eigen::Vector3d::Zero())); Run("pre*rotation_only", x); }
  { colmap::Reconstruction x = pre; x.Transform(colmap::Sim3d(1.0, Eigen::Quaterniond::Identity(), T.translation())); Run("pre*translation_only", x); }
  return 0;
}
