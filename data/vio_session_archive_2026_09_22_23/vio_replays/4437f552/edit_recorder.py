import os
T = os.path.expanduser("~/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench")
def edit(rel, reps):
    p = os.path.join(T, rel); s = open(p, encoding="utf-8").read()
    for old, new in reps:
        n = s.count(old); assert n == 1, f"{rel}: 锚点命中 {n} 次:\n{old[:120]}"
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(s); print(f"✅ {rel}: {len(reps)} 处")

# ── R1 写入器 ──────────────────────────────────────────────────────────────
edit("Replay/DeviceRecordingWriter.swift", [
(
"""    /// 640x480, so the native path passes the unscaled values instead.
    func recordIntrinsics(
        _ reported: CameraIntrinsics,
        timestampSeconds: Double,
        source: String = "ARFrame.camera.intrinsics",
        expected: CameraIntrinsics = ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics
    ) throws {
""",
"""    /// 640x480, so the native path passes the unscaled values instead.
    ///
    /// `exposureSeconds` is this frame's exposure duration, written as
    /// `exposure_s` on the same row. It is recorded because the frame timestamp
    /// (`ARFrame.timestamp` / `CMSampleBufferGetPresentationTimeStamp`) marks
    /// the *start* of exposure while a VIO wants the exposure midpoint, so a
    /// replay must shift each frame by exposure/2 to match what the live path
    /// now feeds the engine (Huai et al., arXiv 2001.00470 §IV.B: images are
    /// "timestamped at the beginning of exposure"; the correction is half the
    /// exposure plus half the rolling-shutter readout). The ARKit arm passes
    /// `ARFrame.camera.exposureDuration`, the AVFoundation transport passes
    /// `AVCaptureDevice.exposureDuration` -- the MARS logger's practice of
    /// reading the device value in the frame callback. `nil` means the caller
    /// cannot report it and the key is omitted; a reader must treat a missing
    /// key as unknown, never as 0 (`pwvi_to_euroc.py --exposure-half` refuses
    /// such recordings instead of silently shifting by nothing).
    func recordIntrinsics(
        _ reported: CameraIntrinsics,
        timestampSeconds: Double,
        exposureSeconds: Double? = nil,
        source: String = "ARFrame.camera.intrinsics",
        expected: CameraIntrinsics = ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics
    ) throws {
"""),
(
"""        intrinsicsRows.append(
            "{\\"t\\":\\(timestampSeconds),\\"intrinsics_fxfycxcy\\":"
                + "[\\(reported.fx),\\(reported.fy),\\(reported.cx),\\(reported.cy)]}"
        )
""",
"""        // `exposure_s` only when the caller could report a finite, non-negative
        // value; the key's absence is the documented "unknown".
        let exposureField: String
        if let e = exposureSeconds, e.isFinite, e >= 0 {
            exposureField = ",\\"exposure_s\\":\\(e)"
        } else {
            exposureField = ""
        }
        intrinsicsRows.append(
            "{\\"t\\":\\(timestampSeconds),\\"intrinsics_fxfycxcy\\":"
                + "[\\(reported.fx),\\(reported.fy),\\(reported.cx),\\(reported.cy)]"
                + exposureField + "}"
        )
"""),
])

# ── R2 ARKit 臂 ────────────────────────────────────────────────────────────
edit("BasaltVIOBench/ARKitReference/ARKitReferenceSession.swift", [
(
"""                    // Same frame the pose below is taken from, so intrinsics and
                    // pose stay frame-exact the way production pins them.
                    timestampSeconds: frame.timestamp
                )
""",
"""                    // Same frame the pose below is taken from, so intrinsics and
                    // pose stay frame-exact the way production pins them.
                    timestampSeconds: frame.timestamp,
                    // This frame's exposure, so a replay can move the timestamp
                    // from exposure start to exposure midpoint the way the live
                    // feed does (see DeviceRecordingWriter.recordIntrinsics).
                    exposureSeconds: frame.camera.exposureDuration
                )
"""),
])

# ── R4 测试:记录时有键、不给时无键(不是静默 0) ──────────────────────────
edit("BasaltVIOBenchTests/ReplayTests/DeviceRecordingTests.swift", [
(
"""        try writer.recordIntrinsics(base, timestampSeconds: 1.0)
        // A later frame with the lens at a different focus position.
        try writer.recordIntrinsics(
            CameraIntrinsics(fx: base.fx * 1.02, fy: base.fy * 1.02, cx: base.cx, cy: base.cy),
            timestampSeconds: 1.5
        )
""",
"""        try writer.recordIntrinsics(base, timestampSeconds: 1.0, exposureSeconds: 0.0125)
        // A later frame with the lens at a different focus position, from a
        // caller that cannot report exposure.
        try writer.recordIntrinsics(
            CameraIntrinsics(fx: base.fx * 1.02, fy: base.fy * 1.02, cx: base.cx, cy: base.cy),
            timestampSeconds: 1.5
        )
"""),
(
"""        XCTAssertTrue(rows[0].contains("intrinsics_fxfycxcy"), "production's key name")
""",
"""        XCTAssertTrue(rows[0].contains("intrinsics_fxfycxcy"), "production's key name")
        // Exposure rides on the same row so a replay can shift this frame to its
        // exposure midpoint; when the caller cannot report it the key is absent,
        // never a silent 0 that would look like a global-shutter zero exposure.
        XCTAssertTrue(rows[0].contains("\\"exposure_s\\":0.0125"), "per-frame exposure key")
        XCTAssertFalse(rows[1].contains("exposure_s"), "unknown exposure omits the key")
"""),
])
print("录制器三处落地")
