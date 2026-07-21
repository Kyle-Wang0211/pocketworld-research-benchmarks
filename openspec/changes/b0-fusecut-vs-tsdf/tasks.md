## 1. Freeze Intent and Inputs

- [x] 1.1 Validate the real cap50 universe and freeze the 115/93/22 split.
- [x] 1.2 Generate and attest the complete common cache without held-out leakage.
- [x] 1.3 Implement and test route input contracts, adapter, meshers, evaluator,
  preregistration, and monitored runner.
- [x] 1.4 Record controlled behavior and thresholds in OpenSpec.
- [x] 1.5 Create and validate a repository-local Python dependency lock.
- [x] 1.6 Record external data/model identities and phase dependencies in DVC.
- [x] 1.7 Create an MLflow parent run and log preregistered inputs before meshing.
- [x] 1.8 Re-freeze the formal contract after all environment records exist.
- [x] 1.9 Preserve the failed v2 evaluator attempt, diagnose its zero-area-face
  trigger before any quality metric exists, and specify/test the symmetric
  sanitation correction.

## 2. Execute cap50 Sequentially

- [x] 2.1 Prepare the common held-out evaluation input in preserved v2.
- [x] 2.2 Run the frozen 6 mm TSDF route under resource monitoring in preserved v2.
- [x] 2.3 Export the same reconstruction evidence for FuseCut in preserved v2.
- [x] 2.4 Run the frozen FuseCut route under resource monitoring in preserved v2.
- [x] 2.5 Preserve the v2 evaluator failure and freeze a new v3 contract, source
  bundle, run root, DVC graph, and MLflow parent before producing any v3 output.
- [x] 2.6 Prepare the v3 common held-out evaluation input.
- [x] 2.7 Rerun the v3 frozen 6 mm TSDF route.
- [x] 2.8 Rerun the v3 common FuseCut export.
- [x] 2.9 Rerun the v3 frozen FuseCut route.
- [x] 2.10 Evaluate both v3 meshes against the same held-out observations.
- [x] 2.11 Compare v3 results with the strict preregistered gates and bootstrap rule.
- [x] 2.12 Do not run the conditional 413-frame gate because cap50 verdict is
  `FAIL` (`nonmanifold=0.0010739577820133583 > 0.0001`).

## 3. Verify and Report

- [ ] 3.1 Verify all hashes, monitor statuses, resource evidence, and route-input
  equivalence; preserve all failed or invalid attempts.
- [ ] 3.2 Obtain a fresh read-only review of code, evidence, and verdict.
- [ ] 3.3 Write `B0_MESHING_AB_REPORT.md` and the B0 section of the combined
  execution report with calibrated observation-consistency claims.
- [ ] 3.4 Run the 413-frame gate only if the strict cap50 verdict is PASS.
