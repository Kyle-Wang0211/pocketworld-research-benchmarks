#!/usr/bin/env python3
"""把 BA-ORDERING / BA-NOSAFETY 两把 env 臂打进出货 TU。
目标文件:aether_cpp/official_pipeline/src/official_bundle_adjustment_ceres.cc
🔴 不要打到 vendored 的 colmap-src/.../bundle_adjustment_ceres.cc —— 那是平行同名实现,不进出货核。
用法: apply_two_knives.py <path-to-official_bundle_adjustment_ceres.cc>
"""
import sys
p = sys.argv[1]
s = open(p).read()

A = """  ceres::Solver::Options solver_options =
      options.ceres->CreateSolverOptions(config, *problem);
  const aether::official::ba::SolveScopeV1 scope ="""
B = """  ceres::Solver::Options solver_options =
      options.ceres->CreateSolverOptions(config, *problem);
  // [AETHER BA-ORDERING 2026-09-07] 出处:Ceres examples/bundle_adjuster.cc SetOrdering()
  // (点=消元组 0、相机=组 1);同款先例在本仓 glomap global_positioning.cc:277。
  // COLMAP 的 BA 从不设 linear_solver_ordering ⇒ Ceres 每次 Solve() 重推 Schur 消元序
  // (= ilr_pre,每帧付两次)。同样的数学,只是把答案直接递给它。
  if (std::getenv("OFFICIAL_AETHER_BA_ORDERING") != nullptr) {
    auto ordering = std::make_shared<ceres::ParameterBlockOrdering>();
    std::vector<double*> blocks;
    problem->GetParameterBlocks(&blocks);
    size_t n_pts = 0, n_cam = 0;
    for (double* pb : blocks) {
      if (problem->IsParameterBlockConstant(pb)) continue;
      if (problem->ParameterBlockSize(pb) == 3) {
        ordering->AddElementToGroup(pb, 0);
        ++n_pts;
      } else {
        ordering->AddElementToGroup(pb, 1);
        ++n_cam;
      }
    }
    static std::atomic<int> ord_logged{0};
    if (ord_logged.fetch_add(1) < 3) {
      std::fprintf(stderr,
                   "[AETHER BA-ORDERING] blocks=%zu pts(g0)=%zu cams(g1)=%zu\\n",
                   blocks.size(), n_pts, n_cam);
    }
    if (n_pts > 0 && n_cam > 0) {
      solver_options.linear_solver_ordering = std::move(ordering);
    }
  }
  const aether::official::ba::SolveScopeV1 scope ="""

C = """    ceres::Problem::Options problem_options;
    problem_options.loss_function_ownership = ceres::DO_NOT_TAKE_OWNERSHIP;
    problem_ = std::make_shared<ceres::Problem>(problem_options);"""
D = """    ceres::Problem::Options problem_options;
    problem_options.loss_function_ownership = ceres::DO_NOT_TAKE_OWNERSHIP;
    // [AETHER BA-NOSAFETY 2026-09-07] Ceres 文档的性能开关:跳过 36k 次
    // AddResidualBlock 的逐次校验。同样的数学。
    if (std::getenv("OFFICIAL_AETHER_BA_NOSAFETY") != nullptr) {
      problem_options.disable_all_safety_checks = true;
    }
    problem_ = std::make_shared<ceres::Problem>(problem_options);"""

assert s.count(A) == 1, ("ordering anchor", s.count(A))
assert s.count(C) == 1, ("nosafety anchor", s.count(C))
s = s.replace(A, B).replace(C, D)
for inc in ("#include <atomic>", "#include <cstdio>", "#include <cstdlib>",
            "#include <memory>", "#include <vector>"):
    if inc + "\n" not in s:
        s = s.replace("#include <glog/logging.h>", "#include <glog/logging.h>\n" + inc, 1)
open(p, "w").write(s)
print("两处都打上了")
