import os
p = os.path.expanduser("~/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/BasaltVIOBench/SensorTransport/LiveSensorTransport.swift")
s = open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    n = s.count(old); assert n == 1, f"锚点命中 {n} 次:\n{old[:120]}"
    s = s.replace(old, new, 1)
rep(
"""    var recorder: DeviceRecordingWriter?
""",
"""    var recorder: DeviceRecordingWriter?

    /// The capture device, kept so the frame callback can read
    /// `exposureDuration` for the recording (MARS logger practice: the device
    /// value at callback time, per frame). Set in `configureCamera()`; nil
    /// before it, and the recording then carries no `exposure_s` for those
    /// frames rather than a guessed 0.
    private var cameraDevice: AVCaptureDevice?
""")
rep(
"""        ) else {
            throw TransportError.cameraUnavailable
        }

        let input: AVCaptureDeviceInput
""",
"""        ) else {
            throw TransportError.cameraUnavailable
        }
        cameraDevice = device

        let input: AVCaptureDeviceInput
""")
rep(
"""        try? recorder.recordIntrinsics(
            reported,
            timestampSeconds: CMTimeGetSeconds(
                CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
            ),
            source: "AVCaptureConnection.cameraIntrinsicMatrixDelivery",
""",
"""        try? recorder.recordIntrinsics(
            reported,
            timestampSeconds: CMTimeGetSeconds(
                CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
            ),
            // Same callback, same frame: the PTS above is exposure start, this
            // is how long it lasted, so a replay can move to the midpoint.
            exposureSeconds: cameraDevice.map { CMTimeGetSeconds($0.exposureDuration) },
            source: "AVCaptureConnection.cameraIntrinsicMatrixDelivery",
""")
open(p, "w", encoding="utf-8").write(s); print("✅ LiveSensorTransport.swift: 3 处")
