// device_pose_alignment_v1.h — [DEVICE-ALIGN-V1 2026-09-24] end-of-finalize
// similarity alignment of the delivered reconstruction to the fed device
// trajectory (camera centres), plus the same fit's inliers/residuals as a
// garbage-pose gate. Header-only, no platform code, shared verbatim by the core
// (official_aether_sfm_c.cc RefineGlobalBA tail) and the host offline checker.
//
// WHY: finalize leaves the delivered model in whatever scale the live model and
// the global BA gauge (COLMAP TWO_CAMS_FROM_WORLD, incremental_mapper.cc:1273)
// ended up with; COLMAP's own gauge comment (bundle_adjustment_ceres.cc:626)
// says the gauge should be fixed differently "once we support IMUs or other
// sensors". COLMAP 3.14's upstream answer for sensor position priors is the
// pose-prior flow, whose first step is a robust Sim3 alignment of the
// reconstruction to the prior positions.
// This file copies exactly that first step; it does NOT copy the pose-prior
// bundle adjustment that follows it upstream (geometry stays untouched).
//
// COPIED PIECES (vendored COLMAP 3.14.0.dev0, glomap_vendor/colmap-src/colmap):
//   [C1] RANSAC max_error from prior covariances —
//        estimators/bundle_adjustment_ceres.cc:1402-1426
//        (PosePriorBundleAdjuster::AlignReconstruction).
//   [C2] per-prior position covariance — the upstream caller-supplied path of
//        the pose-prior mapper: RunPosePriorMapper (exe/sfm.cc:469) exposes
//        prior_position_std_{x,y,z} (sfm.cc:474-476, options sfm.cc:492-494)
//        and, with overwrite_priors_covariance (sfm.cc:473, 487-491), writes
//        covariance = Vector3d(std_x,std_y,std_z).cwiseAbs2().asDiagonal()
//        (sfm.cc:508-515) into EVERY pose prior
//        (UpdateDatabasePosePriorsCovariance, sfm.cc:66-80). Each pair below
//        carries that covariance in the upstream field
//        (PosePrior::position_covariance, geometry/pose_prior.h:64), and [C1]
//        consumes it unchanged. The 1.0 defaults at sfm.cc:474-476 and the
//        1.0 prior_position_fallback_stddev (bundle_adjustment.h:255) are only
//        what upstream uses when the caller supplies nothing; upstream expects
//        the caller to supply the sensor's accuracy.
//        SUPPLIED VALUE (input, not a deviation): σx=σy=σz =
//        kDevicePriorPositionStdM = 0.040 m, the product's device-pose
//        translation σ = pocketworld lib/vio/platform_pose/
//        platform_pose_source.dart:57 kPlatformTranslationSigmaFloorM
//        (pw-dense-stage @1a43510; line introduced 35c3046, 2026-08-26).
//        Its provenance note there (platform_pose_source.dart:10-14, 49-54):
//        first-hand published measurement, local median pose error 4.0 cm when
//        ARCore poses were fed to COLMAP as fixed values; claiming a smaller σ
//        requires an on-device calibration record first. x/y/z are equal
//        because that source states a single translation σ.
//   [C3] pairing + robust Sim3 — estimators/alignment.cc:246-279
//        (AlignReconstructionToPosePriors: src = registered image projection
//        centres, tgt = prior positions, EstimateSim3dRobust when
//        max_error > 0, "< 3" → fail).
//   [C4] apply — Reconstruction::Transform(tgt_from_src)
//        (bundle_adjustment_ceres.cc:1437, exe/model.cc:369; implementation
//        scene/reconstruction.cc:785-803). On failure nothing is applied
//        (bundle_adjustment_ceres.cc:1432-1436, exe/model.cc:364-367).
//   [C5] post-alignment per-image errors — estimators/alignment.cc:363-373
//        (ComputeImageAlignmentError: rotation_error_deg, proj_center_error)
//        and exe/model.cc:371-382 (error = |ProjectionCenter − ref location|
//        AFTER Transform), summarised with AlignmentErrorSummary::Compute
//        (alignment.cc:593-627).
//   [C6] inlier criterion — optim/loransac.h:359 / ransac.h:371
//        (residual² ≤ max_error²), residual = similarity_transform.h:161-164.
//
// DEVIATIONS (each with reason):
//   [D1] Fixed RANSAC seed. Upstream passes the mapper's random_seed
//        (incremental_mapper.cc:1284), which is -1 (= unseeded) in this core
//        (incremental_pipeline.h:95 default, copied unchanged at
//        official_incremental_pipeline.cc:150). A fixed seed makes the
//        delivered transform reproducible for identical input; precedent in
//        this core: upright_relative_pose_v1.h:22 (20260804).
//   [D2] The body of AlignReconstructionToPosePriors (alignment.cc:246-279)
//        is inlined over explicit (recon centre, device centre) pairs instead
//        of calling it with std::vector<PosePrior>: the upstream function
//        returns only bool and drops the RANSAC report, but the gate needs the
//        inlier mask; the same pairs also drive the host offline checker.
//        Pairing comes from the core's own FrameRecord (image_id ↔ device
//        CamFromWorld), exactly as the core's live Sim3 diagnostic does
//        (official_aether_sfm_c.cc:1928-1945, pre-patch line numbers), which
//        is the image-id join upstream does through PosePrior::corr_data_id.
//   [D3] No pose-prior bundle adjustment after the alignment (upstream
//        bundle_adjustment_ceres.cc:1289-1320 continues into a prior-weighted
//        BA). Approved scope is the alignment only; a similarity transform
//        leaves reprojection residuals and shape unchanged.
//   [D4] Gate flag (not upstream): upstream only distinguishes success /
//        failure. Here, a successful alignment in which at least one fed,
//        registered frame lies outside the χ²(3) 95% radius [C1] after the
//        transform is reported as kAlignedGateTripped (transform still applied,
//        as upstream does on success). What the product does on a trip is a UX
//        decision and is NOT made here.
//   [D5] Optional fit_mask (default: all pairs) so the host checker can fit on
//        a subset and evaluate held-out frames. The core always passes none.
//
// HISTORY: v1 first read σ from the upstream 1.0 m fallback (95% radius 2.8 m:
// shuffled-pose negative controls did not trip). Since 2026-09-24 (user
// decision "用官方参数填 VIO 精度") the covariance is supplied through the
// upstream per-prior mechanism [C2]; the threshold is still computed only by
// the copied upstream formula [C1] — no threshold is typed here.

#pragma once

#include "colmap/estimators/alignment.h"
#include "colmap/estimators/bundle_adjustment.h"
#include "colmap/estimators/solvers/similarity_transform.h"
#include "colmap/geometry/pose.h"
#include "colmap/geometry/rigid3.h"
#include "colmap/geometry/sim3.h"
#include "colmap/math/math.h"
#include "colmap/optim/ransac.h"

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <cmath>
#include <limits>
#include <string>
#include <vector>

namespace aether::sfm {

// [C2] caller-supplied device prior position std-dev, metres (one value per
// axis, as exe/sfm.cc:474-476 exposes them; all three equal because the source
// states a single translation σ). Source: pocketworld
// lib/vio/platform_pose/platform_pose_source.dart:57
// kPlatformTranslationSigmaFloorM = 0.040 (provenance in the file header).
inline constexpr double kDevicePriorPositionStdM = 0.040;

// [C2] exe/sfm.cc:508-513 verbatim: the covariance the overwrite path writes
// into every pose prior.
inline Eigen::Matrix3d DevicePriorPositionCovariance(
    double prior_position_std_x = kDevicePriorPositionStdM,
    double prior_position_std_y = kDevicePriorPositionStdM,
    double prior_position_std_z = kDevicePriorPositionStdM) {
  const Eigen::Matrix3d covariance =
      Eigen::Vector3d(
          prior_position_std_x, prior_position_std_y, prior_position_std_z)
          .cwiseAbs2()
          .asDiagonal();
  return covariance;
}

// [D1] fixed RANSAC seed (value = date of this change; any fixed value works).
inline constexpr int kDeviceAlignRansacSeedV1 = 20260924;

struct DeviceCentrePairV1 {
  int frame_id = -1;
  // Delivered model: CamFromWorld of the registered image (COLMAP axes).
  colmap::Rigid3d recon_cam_from_world;
  // Fed device pose: CamFromWorld already in COLMAP camera axes
  // (FrameRecord::cam_from_world, official_aether_sfm_c.cc:414-416 pre-patch).
  colmap::Rigid3d device_cam_from_world;
  // [C2] upstream PosePrior::position_covariance (geometry/pose_prior.h:64,
  // same NaN default = "no covariance"); the core fills it with
  // DevicePriorPositionCovariance() for every pair.
  Eigen::Matrix3d position_covariance =
      Eigen::Matrix3d::Constant(std::numeric_limits<double>::quiet_NaN());
};

enum class DeviceAlignStatusV1 : int {
  kNotRun = 0,
  kAligned = 1,                  // RANSAC ok, every pair within the radius
  kAlignedGateTripped = 2,       // RANSAC ok, ≥1 pair outside the radius [D4]
  kFailedInsufficientPairs = 3,  // < 3 pairs (alignment.cc:271-274)
  kFailedRansac = 4,             // report.success == false
  kDisabled = 5,                 // kill switch OFFICIAL_AETHER_DEVICE_ALIGN_V1=0
};

inline const char* DeviceAlignStatusNameV1(DeviceAlignStatusV1 s) {
  switch (s) {
    case DeviceAlignStatusV1::kNotRun: return "not_run";
    case DeviceAlignStatusV1::kAligned: return "aligned";
    case DeviceAlignStatusV1::kAlignedGateTripped: return "aligned_gate_tripped";
    case DeviceAlignStatusV1::kFailedInsufficientPairs:
      return "failed_insufficient_pairs";
    case DeviceAlignStatusV1::kFailedRansac: return "failed_ransac";
    case DeviceAlignStatusV1::kDisabled: return "disabled";
  }
  return "unknown";
}

struct DeviceAlignResultV1 {
  DeviceAlignStatusV1 status = DeviceAlignStatusV1::kNotRun;
  int n_pairs = 0;            // fed + registered frames
  int n_fit = 0;              // pairs handed to RANSAC (== n_pairs in the core)
  int n_ransac_inliers = 0;   // report.support.num_inliers (fit set)
  int n_inliers_all = 0;      // pairs within max_error after Transform [C6]
  size_t ransac_trials = 0;
  double max_error_m = 0.0;   // [C1]
  // [C2] sqrt(median(trace(Σ)/3)) that [C1] used, i.e. the effective prior σ
  // (reporting only; the threshold is max_error_m).
  double sigma_m = 0.0;
  // device_from_recon (upstream name: tgt_from_src / metric_from_orig).
  colmap::Sim3d device_from_recon;
  // [C5] over ALL pairs after the transform (device metres / degrees).
  colmap::AlignmentErrorSummary errors;
  std::vector<int> outlier_frame_ids;
  std::vector<double> centre_error_m;  // per pair, pair order
  std::vector<char> inlier_all;        // per pair, pair order

  bool Applied() const {
    return status == DeviceAlignStatusV1::kAligned ||
           status == DeviceAlignStatusV1::kAlignedGateTripped;
  }
};

// [C1] bundle_adjustment_ceres.cc:1404-1426 verbatim over the priors handed to
// the fit (upstream: pose_priors_ after the constructor's filter, i.e. priors
// with a position whose image is in the problem = our fit pairs). The
// covariances are whatever the caller put in [C2]; nothing is typed here.
// Returns max_error; *rms_sigma_m (nullable) = sqrt(median rms var).
inline double DeviceAlignMaxErrorV1(
    const std::vector<Eigen::Matrix3d>& position_covariances,
    double* rms_sigma_m = nullptr) {
  std::vector<double> rms_vars;
  rms_vars.reserve(position_covariances.size());
  for (const Eigen::Matrix3d& position_covariance : position_covariances) {
    const double trace = position_covariance.trace();
    if (trace <= 0.0) {
      continue;
    }
    rms_vars.push_back(trace / 3.0);
  }

  if (rms_vars.empty()) {
    // bundle_adjustment_ceres.cc:1415-1419 ("No pose priors with valid
    // covariance found."), fallback read from the upstream option default.
    const double fallback_stddev = colmap::PosePriorBundleAdjustmentOptions()
                                       .prior_position_fallback_stddev;
    rms_vars.push_back(fallback_stddev * fallback_stddev);
  }

  const double median_rms_var = colmap::Median(rms_vars);
  if (rms_sigma_m) *rms_sigma_m = std::sqrt(median_rms_var);
  // Set max error using the median RMS variance of valid pose priors.
  // Scaled by sqrt(chi-square 95% quantile, 3 DOF) to approximate a 95%
  // confidence radius.
  return std::sqrt(colmap::kChiSquare95ThreeDof * median_rms_var);
}

// [C3]+[C5]+[C6]; does NOT modify any reconstruction — the caller applies
// result.device_from_recon with Reconstruction::Transform [C4] iff Applied().
inline DeviceAlignResultV1 EstimateDeviceAlignmentV1(
    const std::vector<DeviceCentrePairV1>& pairs,
    const std::vector<char>* fit_mask = nullptr) {
  DeviceAlignResultV1 out;
  out.n_pairs = static_cast<int>(pairs.size());

  // alignment.cc:246-269 — src = image.ProjectionCenter(), tgt = prior pos.
  std::vector<Eigen::Vector3d> src;
  std::vector<Eigen::Vector3d> tgt;
  std::vector<Eigen::Matrix3d> fit_covariances;  // [C1] input
  src.reserve(pairs.size());
  tgt.reserve(pairs.size());
  fit_covariances.reserve(pairs.size());
  for (size_t i = 0; i < pairs.size(); ++i) {
    if (fit_mask && !(*fit_mask)[i]) continue;  // [D5]
    src.push_back(pairs[i].recon_cam_from_world.TgtOriginInSrc());
    tgt.push_back(pairs[i].device_cam_from_world.TgtOriginInSrc());
    fit_covariances.push_back(pairs[i].position_covariance);
  }
  out.n_fit = static_cast<int>(src.size());
  // alignment.cc:271-274
  if (src.size() < 3) {
    out.status = DeviceAlignStatusV1::kFailedInsufficientPairs;
    return out;
  }

  // bundle_adjustment_ceres.cc:1403 (alignment_ransac_options defaults) +
  // incremental_mapper.cc:1284 (random_seed) [D1]
  colmap::RANSACOptions ransac_options;
  ransac_options.random_seed = kDeviceAlignRansacSeedV1;
  ransac_options.max_error =
      DeviceAlignMaxErrorV1(fit_covariances, &out.sigma_m);
  out.max_error_m = ransac_options.max_error;

  // alignment.cc:276-277 (max_error > 0 ⇒ robust)
  colmap::Sim3d tgt_from_src;
  const auto report =
      colmap::EstimateSim3dRobust(src, tgt, ransac_options, tgt_from_src);
  out.ransac_trials = report.num_trials;
  if (!report.success) {
    out.status = DeviceAlignStatusV1::kFailedRansac;
    return out;
  }
  out.n_ransac_inliers = static_cast<int>(report.support.num_inliers);
  out.device_from_recon = tgt_from_src;

  // [C5] alignment.cc:363-373 per pair, over ALL pairs (fit + held-out).
  std::vector<colmap::ImageAlignmentError> errors;
  errors.reserve(pairs.size());
  out.centre_error_m.reserve(pairs.size());
  out.inlier_all.reserve(pairs.size());
  const double max_sq = out.max_error_m * out.max_error_m;  // [C6]
  for (const DeviceCentrePairV1& p : pairs) {
    const colmap::Rigid3d tgt_world_from_src_cam = colmap::Inverse(
        colmap::TransformCameraWorld(tgt_from_src, p.recon_cam_from_world));
    const colmap::Rigid3d tgt_world_from_tgt_cam =
        colmap::Inverse(p.device_cam_from_world);
    colmap::ImageAlignmentError error;
    error.image_name = std::to_string(p.frame_id);
    error.rotation_error_deg =
        colmap::RadToDeg(tgt_world_from_src_cam.rotation().angularDistance(
            tgt_world_from_tgt_cam.rotation()));
    error.proj_center_error = (tgt_world_from_src_cam.translation() -
                               tgt_world_from_tgt_cam.translation())
                                  .norm();
    errors.push_back(error);
    out.centre_error_m.push_back(error.proj_center_error);
    const bool inlier =
        error.proj_center_error * error.proj_center_error <= max_sq;
    out.inlier_all.push_back(inlier ? 1 : 0);
    if (inlier) {
      ++out.n_inliers_all;
    } else {
      out.outlier_frame_ids.push_back(p.frame_id);
    }
  }
  out.errors = colmap::AlignmentErrorSummary::Compute(errors);
  out.status = out.outlier_frame_ids.empty()
                   ? DeviceAlignStatusV1::kAligned
                   : DeviceAlignStatusV1::kAlignedGateTripped;  // [D4]
  return out;
}

}  // namespace aether::sfm
