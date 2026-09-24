// ── [REG-EVIDENCE-V1 / DEVICE-POSE-TRUST-V1 2026-09-24] ──────────────────────
// Upstream registration evidence for device-posed frames, and image-evidence
// registration for frames whose device pose the caller marked untrusted.
//
// WHY: the streaming route places every fed frame at its device pose
// (AddImageWithTrivialFrame) and never runs upstream COLMAP's registration
// checks, so a frame with too little image evidence is still "registered" and
// the prior-free BA can later push it arbitrarily far (host/phone evidence:
// 0.6 m in cap_1786013666212373, 6e6 / 2e7 units in cap_1786199789306631).
//
// COPIED (vendored COLMAP 3.14.0.dev0, glomap_vendor/colmap-src/colmap, file
// sha256 1481d48f… == Aether3D-cross copy):
//  [R1] Acceptance half of IncrementalMapper::RegisterNextImage,
//       sfm/incremental_mapper.cc:189-417 (EvaluateRegistrationEvidenceV1):
//         :209-227 generalized-rig branch (this route has trivial rigs only)
//         :232-237 NumVisiblePoints3D >= abs_pose_min_num_inliers
//         :243-294 2D-3D correspondence search, verbatim
//         :297-303 #2D-3D correspondences >= abs_pose_min_num_inliers
//         :313-383 AbsolutePoseEstimation/RefinementOptions, verbatim
//         :390-399 EstimateAbsolutePose (P3P LO-RANSAC, max_error
//                  abs_pose_max_error) must succeed
//         :401-404 num_inliers >= abs_pose_min_num_inliers
//         :411-417 RefineAbsolutePose must succeed
//       Values = IncrementalMapper::Options defaults, unchanged
//       (sfm/incremental_mapper.h:81-89): max_error 12 px, min inliers 30,
//       min_inlier_ratio 0.25. NOTE: upstream's abs_pose_min_inlier_ratio is
//       NOT an acceptance gate — it is RANSACOptions::min_inlier_ratio, "a
//       priori assumed minimum inlier ratio, which determines the maximum
//       number of iterations" (optim/ransac.h:55-57, used only at
//       ransac.h:167-176). It is copied with exactly that meaning; the
//       inlier ratio is logged, never gated on (a ratio gate would be
//       self-made).
//  [R2] Untrusted frames: IncrementalMapper::RegisterNextImage itself, called
//       unmodified (pose = P3P + refinement; continue tracks :425-443).
//  [R3] Retry loop = IncrementalPipeline::ReconstructSubModel's registration
//       loop, controllers/incremental_pipeline.cc:558-634: FindNextImages
//       ranking (:573), try in rank order until one registers (:575-615),
//       then TriangulateImage (:623-627) + IterativeLocalRefinement
//       (:628-633), repeat. Trial cap = FindNextImages' max_reg_trials filter
//       (sfm/incremental_mapper_impl.cc:358-361, max_reg_trials = 3,
//       incremental_mapper.h:128-129) applied with a caller-owned counter.
// DEVIATIONS (deliberate, listed so nothing is silently self-made):
//  [D1] A TRUSTED frame that passes [R1] is placed at its DEVICE pose (the
//       product's metric frame = "initial guess"), not at the P3P pose; the
//       P3P estimate is only the evidence test. RegisterNextImage's continue-
//       tracks step (:433-443) is replaced by the route's own triangulation
//       after placement (live growth at ingest; TriangulateImage in [R3]).
//  [D2] The acceptance half never mutates the model: it works on a copy of
//       the camera (upstream resets bogus params in place, :345 / :375-383).
//       On this route the reset is a no-op anyway: the per-image ARKit PINHOLE
//       cameras are never bogus, and focal/extra estimation is off because
//       the route's options set ba_refine_focal_length=false →
//       abs_pose_refine_focal_length=false (incremental_pipeline.cc:135-136).
//  [D3] The trial increment (:229) is kept by the caller's counter; a trusted
//       frame registered inside a mapper session uses the public
//       ObservationManager::RegisterFrame (:430) but not the private
//       RegisterFrameEvent (:431, stats only) — every session here is ended
//       right after, and the next BeginReconstruction rebuilds those stats
//       from RegFrameIds (incremental_mapper.cc:90-92).
//  [D4] Upstream bootstraps from a two-view initial pair
//       (InitializeReconstruction). This route bootstraps from device poses:
//       until the live model has >= 2 registered frames and >=
//       abs_pose_min_num_inliers 3D points (upstream's own "enough points to
//       register future images" test, incremental_pipeline.cc:485-489),
//       trusted frames are placed directly.
//  [D5] No periodic global BA inside the capture-time loop (upstream
//       CheckRunGlobalRefinement, :636-641): finalize's stage-2
//       IterativeGlobalRefinement is the global refinement, and one more
//       registration round follows it (upstream :665-671, "try a single final
//       global iterative bundle adjustment and try again").
//  [D6] Every RANSAC added here runs on a dedicated std::thread so the
//       production thread's thread_local PRNG stream (TVG RANSAC) is never
//       advanced (same isolation as the tail-shadow / pair-draft passes): with
//       every frame passing, the evidence arm is bit-identical to baseline.
//  [D7] Upstream's max_reg_trials counter lives in one mapper for a whole
//       sub-model; here the capture keeps one session counter
//       (reg_trials_v1), and finalize / resume start a fresh one — the same
//       reset upstream applies when a reconstruction is continued in a new
//       mapper (BeginReconstruction clears num_reg_trials, :99).
extern "C" void aether_ba_set_gravity_prior_exempt(const char* name);

bool RegEvidenceGateEnabled() {
  static const bool cached = [] {
    const char* e = std::getenv("OFFICIAL_AETHER_REG_EVIDENCE");
    return e && e[0] == '1' && e[1] == '\0';
  }();
  return cached;
}

bool FinalizeViaResumeEnabled() {
  static const bool cached = [] {
    const char* e = std::getenv("OFFICIAL_AETHER_FINALIZE_VIA_RESUME");
    return e && e[0] == '1' && e[1] == '\0';
  }();
  return cached;
}

struct RegEvidenceV1 {
  size_t visible = 0;
  size_t corrs = 0;
  size_t inliers = 0;
  bool pass = false;
  const char* reason = "not_run";
};

// [R1] — see the block comment above. Must be called inside a mapper session
// (BeginReconstruction .. EndReconstruction) whose cache is `database_cache`.
RegEvidenceV1 EvaluateRegistrationEvidenceV1(
    const colmap::IncrementalMapper& mapper,
    const colmap::DatabaseCache& database_cache,
    const colmap::IncrementalMapper::Options& options,
    const colmap::image_t image_id) {
  RegEvidenceV1 ev;
  const colmap::Reconstruction& reconstruction = *mapper.Reconstruction();
  const colmap::ObservationManager& obs_manager = mapper.ObservationManager();
  const colmap::Image& image = reconstruction.Image(image_id);
  colmap::Camera camera = *image.CameraPtr();  // [D2] local copy

  // :209-227 — only trivial (single-sensor) rigs exist on this route.
  if (image.FramePtr()->RigPtr()->NumSensors() > 1) {
    ev.reason = "non_trivial_rig";
    return ev;
  }

  // :232-237 Check if enough 2D-3D correspondences.
  ev.visible = obs_manager.NumVisiblePoints3D(image_id);
  if (ev.visible < static_cast<size_t>(options.abs_pose_min_num_inliers)) {
    ev.reason = "visible_points";
    return ev;
  }

  // :243-294 Search for 2D-3D correspondences (verbatim).
  std::vector<std::pair<colmap::point2D_t, colmap::point3D_t>> tri_corrs;
  std::vector<Eigen::Vector2d> tri_points2D;
  std::vector<Eigen::Vector3d> tri_points3D;
  const std::shared_ptr<const colmap::CorrespondenceGraph>
      correspondence_graph = database_cache.CorrespondenceGraph();
  std::unordered_set<colmap::point3D_t> corr_point3D_ids;
  for (colmap::point2D_t point2D_idx = 0; point2D_idx < image.NumPoints2D();
       ++point2D_idx) {
    const colmap::Point2D& point2D = image.Point2D(point2D_idx);
    corr_point3D_ids.clear();
    const auto corr_range =
        correspondence_graph->FindCorrespondences(image_id, point2D_idx);
    for (const auto* corr = corr_range.beg; corr < corr_range.end; ++corr) {
      const colmap::Image& corr_image = reconstruction.Image(corr->image_id);
      if (!corr_image.HasPose()) continue;
      const colmap::Point2D& corr_point2D =
          corr_image.Point2D(corr->point2D_idx);
      if (!corr_point2D.HasPoint3D()) continue;
      // Avoid duplicate correspondences.
      if (corr_point3D_ids.count(corr_point2D.point3D_id) > 0) continue;
      const colmap::Camera& corr_camera = *corr_image.CameraPtr();
      // Avoid correspondences to images with bogus camera parameters.
      if (corr_camera.HasBogusParams(options.min_focal_length_ratio,
                                     options.max_focal_length_ratio,
                                     options.max_extra_param)) {
        continue;
      }
      const colmap::Point3D& point3D =
          reconstruction.Point3D(corr_point2D.point3D_id);
      tri_corrs.emplace_back(point2D_idx, corr_point2D.point3D_id);
      corr_point3D_ids.insert(corr_point2D.point3D_id);
      tri_points2D.push_back(point2D.xy);
      tri_points3D.push_back(point3D.xyz);
    }
  }

  // :297-303
  ev.corrs = tri_points2D.size();
  if (ev.corrs < static_cast<size_t>(options.abs_pose_min_num_inliers)) {
    ev.reason = "correspondences";
    return ev;
  }

  // :313-370 2D-3D estimation options (verbatim; see [D2]).
  colmap::AbsolutePoseEstimationOptions abs_pose_options;
  abs_pose_options.ransac_options.max_error = options.abs_pose_max_error;
  abs_pose_options.ransac_options.min_inlier_ratio =
      options.abs_pose_min_inlier_ratio;
  abs_pose_options.ransac_options.random_seed = options.random_seed;
  colmap::AbsolutePoseRefinementOptions abs_pose_refinement_options;
  if (options.constant_cameras.count(image.CameraId()) > 0) {
    abs_pose_options.estimate_focal_length = false;
    abs_pose_refinement_options.refine_focal_length = false;
    abs_pose_refinement_options.refine_extra_params = false;
  } else {
    const auto& per_camera = mapper.NumRegImagesPerCamera();
    const auto per_camera_it = per_camera.find(image.CameraId());
    const size_t num_reg_images_for_camera =
        per_camera_it == per_camera.end() ? 0 : per_camera_it->second;
    if (num_reg_images_for_camera > 0) {
      if (camera.HasBogusParams(options.min_focal_length_ratio,
                                options.max_focal_length_ratio,
                                options.max_extra_param)) {
        abs_pose_options.estimate_focal_length = !camera.has_prior_focal_length;
        abs_pose_refinement_options.refine_focal_length = true;
        abs_pose_refinement_options.refine_extra_params = true;
      } else {
        abs_pose_options.estimate_focal_length = false;
        abs_pose_refinement_options.refine_focal_length = false;
        abs_pose_refinement_options.refine_extra_params = false;
      }
    } else {
      camera.params = database_cache.Camera(image.CameraId()).params;
      abs_pose_options.estimate_focal_length = !camera.has_prior_focal_length;
      abs_pose_refinement_options.refine_focal_length = true;
      abs_pose_refinement_options.refine_extra_params = true;
    }
    if (!options.abs_pose_refine_focal_length) {
      abs_pose_options.estimate_focal_length = false;
      abs_pose_refinement_options.refine_focal_length = false;
    }
    if (!options.abs_pose_refine_extra_params) {
      abs_pose_refinement_options.refine_extra_params = false;
    }
    if (!camera.IsPerspective()) {
      abs_pose_options.estimate_focal_length = false;
      abs_pose_refinement_options.refine_focal_length = false;
      abs_pose_refinement_options.refine_extra_params = false;
    }
  }
  // :375-383 bogus-parameter reset — applied to the local copy only [D2].
  if (camera.HasBogusParams(options.min_focal_length_ratio,
                            options.max_focal_length_ratio,
                            options.max_extra_param)) {
    camera.params = database_cache.Camera(image.CameraId()).params;
  }

  // :385-417 on a dedicated thread [D6].
  size_t num_inliers = 0;
  std::vector<char> inlier_mask;
  colmap::Rigid3d cam_from_world;
  bool estimated = false;
  bool refined = false;
  std::thread ransac_thread([&] {
    try {
      estimated = colmap::EstimateAbsolutePose(
          abs_pose_options, tri_points2D, tri_points3D, &cam_from_world,
          &camera, &num_inliers, &inlier_mask);
      if (estimated &&
          num_inliers >=
              static_cast<size_t>(options.abs_pose_min_num_inliers)) {
        refined = colmap::RefineAbsolutePose(
            abs_pose_refinement_options, inlier_mask, tri_points2D,
            tri_points3D, &cam_from_world, &camera);
      }
    } catch (...) {
      estimated = false;
    }
  });
  ransac_thread.join();
  ev.inliers = num_inliers;
  if (!estimated) {
    ev.reason = "pnp_failed";
    return ev;
  }
  if (num_inliers < static_cast<size_t>(options.abs_pose_min_num_inliers)) {
    ev.reason = "pnp_inliers";
    return ev;
  }
  if (!refined) {
    ev.reason = "pnp_refine";
    return ev;
  }
  ev.pass = true;
  ev.reason = "ok";
  return ev;
}

void LogRegEvidenceV1(aether_sfm_session* s, const char* stage, int frame_id,
                      bool trusted, const RegEvidenceV1& ev,
                      const char* action) {
  char line[512];
  std::snprintf(line, sizeof(line),
                "{\"t\":%lld,\"type\":\"reg_evidence_v1\",\"stage\":\"%s\","
                "\"fid\":%d,\"trusted\":%d,\"visible\":%zu,\"corrs\":%zu,"
                "\"inliers\":%zu,\"inlier_ratio\":%.4f,\"pass\":%d,"
                "\"reason\":\"%s\",\"action\":\"%s\"}",
                static_cast<long long>(EpochMs()), stage, frame_id,
                trusted ? 1 : 0, ev.visible, ev.corrs, ev.inliers,
                ev.corrs > 0 ? static_cast<double>(ev.inliers) /
                                   static_cast<double>(ev.corrs)
                             : 0.0,
                ev.pass ? 1 : 0, ev.reason, action);
  AppendMatchFailJsonl(s, line);
}

bool FrameRegisteredInV1(const colmap::Reconstruction& recon,
                         colmap::image_t image_id) {
  return image_id != 0 && recon.ExistsImage(image_id) &&
         recon.Image(image_id).HasPose();
}

// Active (not withdrawn) frames that `recon` does not hold registered.
size_t CountPendingFramesV1(const aether_sfm_session& s,
                            const colmap::Reconstruction& recon) {
  size_t n = 0;
  for (const FrameRecord& f : s.frames) {
    if (f.image_id != 0 && !FrameRegisteredInV1(recon, f.image_id)) ++n;
  }
  return n;
}

struct PendingPassResultV1 {
  int attempted = 0;
  int registered = 0;
  int untrusted_registered = 0;
  std::vector<colmap::image_t> registered_ids;
};

// [R3] — must run inside a mapper session on `mapper` (cache =
// `database_cache`); the caller runs it on a dedicated thread [D6].
PendingPassResultV1 RunPendingRegistrationPassV1(
    aether_sfm_session* s, colmap::IncrementalMapper& mapper,
    const colmap::DatabaseCache& database_cache,
    const colmap::IncrementalPipelineOptions& popts, const char* stage,
    std::unordered_map<colmap::image_t, size_t>* trials) {
  PendingPassResultV1 out;
  std::unordered_map<colmap::image_t, const FrameRecord*> by_image;
  for (const FrameRecord& f : s->frames) {
    if (f.image_id != 0) by_image[f.image_id] = &f;  // withdrawn never retried
  }
  const colmap::IncrementalMapper::Options mapper_options = popts.Mapper();
  const colmap::IncrementalTriangulator::Options tri_options =
      popts.Triangulation();
  const size_t max_reg_trials =
      static_cast<size_t>(mapper_options.max_reg_trials);
  colmap::Reconstruction& reconstruction = *mapper.Reconstruction();
  while (true) {
    colmap::image_t next_image_id = colmap::kInvalidImageId;
    const std::vector<colmap::image_t> next_images =
        mapper.FindNextImages(mapper_options, /*structure_less=*/false);
    for (const colmap::image_t image_id : next_images) {
      const auto it = by_image.find(image_id);
      if (it == by_image.end()) continue;
      size_t& num_trials = (*trials)[image_id];
      if (num_trials >= max_reg_trials) continue;  // impl.cc:358-361
      ++num_trials;
      ++out.attempted;
      const FrameRecord& f = *it->second;
      bool registered = false;
      if (f.device_pose_trusted) {
        const RegEvidenceV1 ev = EvaluateRegistrationEvidenceV1(
            mapper, database_cache, mapper_options, image_id);
        ++s->stat_regev_checked;
        if (ev.pass) {
          colmap::Image& image = reconstruction.Image(image_id);
          // [D1] device pose; incremental_mapper.cc:428-430 otherwise.
          image.FramePtr()->SetCamFromWorld(image.CameraId(),
                                            f.cam_from_world);
          mapper.ObservationManager().RegisterFrame(image.FrameId());
          registered = true;
        } else {
          ++s->stat_regev_failed;
        }
        LogRegEvidenceV1(s, stage, f.frame_id, true, ev,
                         registered ? "registered_at_device_pose" : "pending");
      } else {
        RegEvidenceV1 ev;
        ev.visible = mapper.ObservationManager().NumVisiblePoints3D(image_id);
        registered = mapper.RegisterNextImage(mapper_options, image_id);  // [R2]
        ev.pass = registered;
        ev.reason = registered ? "ok" : "register_next_image_false";
        if (registered) ev.inliers = reconstruction.Image(image_id).NumPoints3D();
        LogRegEvidenceV1(s, stage, f.frame_id, false, ev,
                         registered ? "registered_by_image_evidence"
                                    : "pending");
      }
      if (registered) {
        next_image_id = image_id;
        break;
      }
    }
    if (next_image_id == colmap::kInvalidImageId) break;
    // incremental_pipeline.cc:623-633
    mapper.TriangulateImage(tri_options, next_image_id);
    mapper.IterativeLocalRefinement(
        popts.ba_local_max_refinements, popts.ba_local_max_refinement_change,
        mapper_options, popts.LocalBundleAdjustment(), tri_options,
        next_image_id);
    ++out.registered;
    if (!by_image[next_image_id]->device_pose_trusted) {
      ++out.untrusted_registered;
    }
    out.registered_ids.push_back(next_image_id);
  }
  return out;
}

// Opens a mapper session over `recon` with `cache`, runs [R3] on a dedicated
// thread [D6], closes the session (TearDown drops frames still unregistered).
PendingPassResultV1 RunPendingRegistrationSessionV1(
    aether_sfm_session* s,
    const std::shared_ptr<colmap::Reconstruction>& recon,
    const std::shared_ptr<const colmap::DatabaseCache>& cache,
    const colmap::IncrementalPipelineOptions& popts, const char* stage,
    std::unordered_map<colmap::image_t, size_t>* trials) {
  PendingPassResultV1 out;
  std::string error;
  std::thread pass_thread([&] {
    aether::official::ba::ScopedBaSessionAggregateBindingV1 ba_session_binding(
        &s->ba_ptol_aggregate, &s->ba_ptol_receipts);
    try {
      colmap::IncrementalMapper mapper(cache);
      mapper.BeginReconstruction(recon);
      try {
        out = RunPendingRegistrationPassV1(s, mapper, *cache, popts, stage,
                                           trials);
      } catch (const std::exception& e) {
        error = e.what();
      }
      mapper.EndReconstruction(/*discard=*/false);
    } catch (const std::exception& e) {
      error = e.what();
    } catch (...) {
      error = "unknown";
    }
  });
  pass_thread.join();
  s->stat_regev_late_registered +=
      out.registered - out.untrusted_registered;
  s->stat_untrusted_registered += out.untrusted_registered;
  char line[320];
  std::snprintf(line, sizeof(line),
                "{\"t\":%lld,\"type\":\"reg_pending_pass_v1\",\"stage\":\"%s\","
                "\"attempted\":%d,\"registered\":%d,\"untrusted_registered\":"
                "%d,\"still_pending\":%zu,\"error\":\"%.80s\"}",
                static_cast<long long>(EpochMs()), stage, out.attempted,
                out.registered, out.untrusted_registered,
                CountPendingFramesV1(*s, *recon), error.c_str());
  AppendMatchFailJsonl(s, line);
  return out;
}

