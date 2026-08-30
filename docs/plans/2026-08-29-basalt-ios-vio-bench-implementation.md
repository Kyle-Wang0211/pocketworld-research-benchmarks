# Unified iPhone VIO Replacement Bench Implementation Plan

> Execute test-first in the isolated `research/basalt-vio-phone-bench-20260829`
> worktree. Never touch PocketWorld.

1. Add a machine-readable experiment contract and schema tests. Freeze source,
   dependency, config, bundle and dataset identities before a run.
2. Vendor exact Basalt and XRSLAM sources/artifacts and notices, then place each
   candidate in a private dynamic framework with a minimal exported C API.
3. Add immutable runtime adapters and a process-wide lease. ARKit uses a separate
   production-reference ARSession path and can never enter either C++ session.
4. Implement Swift sensor transport with AVFoundation/Core Motion and an
   explicit one-clock mapping. Add drop, interruption and camera-pressure
   accounting before adding UI.
5. Implement replay-paced and replay-max readers plus SE(3)-only ATE/RPE
   evaluation. Reject missing or mismatched manifests, calibration or ground
   truth rather than manufacturing a metric.
6. Implement the minimal SwiftUI configuration, running and result screens.
   Keep UI refresh at 1 Hz and all run logging off the sensor callbacks.
7. Generate the Xcode project and run schema/unit tests, unsigned Release device
   build, symbol/dependency/bundle audits and independent read-only review.
8. Only after those gates pass, sign/install `com.kyle.viobench`; execute
   Basalt/XRSLAM replay and separate Basalt/XRSLAM/ARKit five-minute live runs;
   export artifacts and adjudicate the frozen gates.
