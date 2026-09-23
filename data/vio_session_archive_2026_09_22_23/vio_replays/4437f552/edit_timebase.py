import sys, os
P = os.path.expanduser("~/Developer/pocketworld")
def edit(rel, reps):
    p = os.path.join(P, rel); s = open(p, encoding="utf-8").read()
    for old, new in reps:
        n = s.count(old)
        assert n == 1, f"{rel}: 锚点命中 {n} 次(需恰 1):\n{old[:120]}"
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(s); print(f"✅ {rel}: {len(reps)} 处")

# ═══ E1 PwCameraSlot.swift ═══════════════════════════════════════════════
edit("ios/Runner/PwCameraSlot.swift", [
(
"""    fileprivate var latestFramePTSSeconds: Double = 0
""",
"""    fileprivate var latestFramePTSSeconds: Double = 0

    /// [pw 2026-09-22] 最新一帧的**曝光时长**(秒)。与 PTS 同一回调里读,喂给
    /// `PwXrslamLive.onCameraFrame` 做曝光中点换算(见那边文件头偏离 (d))。
    /// 读法抄 Huai 的 MARS logger(arXiv 2001.00470 §III.B):
    /// "the exposureDuration read from the AVCaptureDevice instance is recorded
    ///  for every frame" —— 回调时刻的设备状态,不是 EXIF 附件。自动曝光下它逐帧变。
    fileprivate var latestExposureSeconds: Double = 0
"""),
(
"""        latestFramePTSSeconds = CMTimeGetSeconds(
            CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
""",
"""        latestFramePTSSeconds = CMTimeGetSeconds(
            CMSampleBufferGetPresentationTimeStamp(sampleBuffer))

        // [pw 2026-09-22] 同一回调里读当帧曝光。`device` 在 start() 里存住,
        // 还没存住时为 0 ⇒ 下游按"无曝光信息"如实计数,不猜。
        if let d = device {
            let e = CMTimeGetSeconds(d.exposureDuration)
            latestExposureSeconds = (e.isFinite && e >= 0) ? e : 0
        } else {
            latestExposureSeconds = 0
        }
"""),
(
"""        PwXrslamLive.shared.onCameraFrame(pb, ptsSeconds: latestFramePTSSeconds)
""",
"""        PwXrslamLive.shared.onCameraFrame(
            pb, ptsSeconds: latestFramePTSSeconds,
            exposureSeconds: latestExposureSeconds)
"""),
])

# ═══ E2 PwXrslamLive.swift ═══════════════════════════════════════════════
edit("ios/Runner/PwXrslamLive.swift", [
# (d) 文件头偏离
(
"""// (c) 算法不在回调里跑,搬到 worker(见上)。依据是生产 `PwVioSlamFeeder`,
//     不是我的设计。
//
""",
"""// (c) 算法不在回调里跑,搬到 worker(见上)。依据是生产 `PwVioSlamFeeder`,
//     不是我的设计。
// (d) [2026-09-22] 相机时间戳在推给传输层之前换算到**曝光中点**:
//     `t_canonical = PTS + exposureDuration/2`。上游 `Camera.swift:150-151` 把
//     `presentationTimeStamp` 原样推、19 份 iPhone yaml 里 18 份 `time_offset: 0.0`
//     —— 上游没做,我们此前忠实复刻了这个缺口。
//     依据(不是自研):
//       · Huai arXiv 2001.00470 §IV.B:iOS 帧 "timestamped at the beginning of
//         exposure";修正是 "subtracting half of the sum of [rolling shutter +
//         exposure]"。同一套硬件改曝光 td 就跟着动(Kalibr #267),斜率≈0.5
//         (MDPI Sensors 2026 26(18):5849)。
//       · 我们自己的契约 `xrslam-interface/include/XRSLAM.h` 条目 09:canonical =
//         中心行曝光中点;`XRSLAMManager.cpp:92-99` 的换算就是 `+0.5·exposure+0.5·readout`。
//     为什么不走 `timestamp_convention` 字段让库换算:**出货 vendor 头是 40 字节
//     旧 `XRSLAMImage`**(`vendor/xrslam/include/XRSLAM.h:40-47`),没有那几个字段;
//     头注释对 iOS 的建议本来就是"填 0 并自己换算到 canonical"。
//     卷帘读出时间 iOS 不公开 ⇒ 它的一半连同管线固定延迟一起进**每机常量 c**,
//     由 `PWXrslamTransportCreateWithCameraTimeOffset` 在传输层施加。
//     🔴 自证:`runOneFrame` 推完当帧立刻从 C 账本读 `PWXrslamTimestampTrace`
//     (同一条串行 worker ⇒ 一定是本帧):raw 必须 == 我们推的 canonical,
//     effective − raw 必须 == applied_offset。`timebase(into:)` 把它们报出去。
//
"""),
# 状态
(
"""    private var maxObservedPendingFrames = 0
""",
"""    private var maxObservedPendingFrames = 0

    // ── [pw 2026-09-22] 时基自证账本(见文件头偏离 (d)) ──────────────────
    /// create 时传给传输层的每机常量 c(秒)。只作对照;报出的以 C 账本为准。
    private var cameraTimeOffsetSeconds: Double = 0
    private var tbFrames: UInt64 = 0
    /// 曝光 > 0 的帧数。== tbFrames ⇒ 每帧都拿到了曝光;< ⇒ 有帧按 0 换算过。
    private var tbFramesWithExposure: UInt64 = 0
    private var tbExposureSum: Double = 0
    private var tbExposureMin: Double = .infinity
    private var tbExposureMax: Double = 0
    /// 实际加到时间戳上的 exposure/2 之和。
    private var tbHalfAppliedSum: Double = 0
    private var lastCanonicalPts: Double = 0
    /// 以下来自 C 账本 `PWXrslamTransportGetLastTimestampTrace`,不是 Swift 合成。
    private var tbTraceReads: UInt64 = 0
    private var tbLastAppliedOffset: Double = 0
    /// 引擎实际收到的时刻 − 原始 PTS(最近一帧)。应 ≈ exposure/2 + c。
    private var tbLastEffectiveMinusPts: Double = 0
    /// |C 收到的 raw − 我们推的 canonical| 峰值。**必须恒 0**。
    private var tbMaxAbsRawResidual: Double = 0
    /// |(effective − raw) − applied_offset| 峰值。**必须恒 0**。
    private var tbMaxAbsOffsetResidual: Double = 0
"""),
# create 签名 + 重置
(
"""    /// 返回沿用冻结的 `XRSLAMCreate` 口径:**1 成功 / 0 失败**。
    func create(slamConfigPath: String, deviceConfigPath: String) -> Int32 {
        lock.lock(); defer { lock.unlock() }
        if created { return 1 }
""",
"""    /// 返回沿用冻结的 `XRSLAMCreate` 口径:**1 成功 / 0 失败**。
    ///
    /// [cameraTimeOffsetSeconds] = 每机常量 c(见文件头偏离 (d)),由传输层在推相机
    /// 样本前加到时间戳上(`PwXrslamTransportCore.cpp` `ValidateTimestampLocked`:
    /// `effective = raw + offset`),IMU 不动。0 = 不加。
    func create(slamConfigPath: String, deviceConfigPath: String,
                cameraTimeOffsetSeconds: Double) -> Int32 {
        lock.lock(); defer { lock.unlock() }
        if created { return 1 }
        self.cameraTimeOffsetSeconds =
            cameraTimeOffsetSeconds.isFinite ? cameraTimeOffsetSeconds : 0
        tbFrames = 0; tbFramesWithExposure = 0
        tbExposureSum = 0; tbExposureMin = .infinity; tbExposureMax = 0
        tbHalfAppliedSum = 0; lastCanonicalPts = 0
        tbTraceReads = 0; tbLastAppliedOffset = 0; tbLastEffectiveMinusPts = 0
        tbMaxAbsRawResidual = 0; tbMaxAbsOffsetResidual = 0
"""),
(
"""        let rc = PWXrslamTransportCreate(slamConfigPath, deviceConfigPath)
        if rc == 1 { created = true }
        return rc
""",
"""        // [pw 2026-09-22] 换成带相机时间偏移的版本 —— 同一个 C 入口,多一个 c。
        // 生产 `PwVioSlamFeeder.swift:937` 用的就是它;此前这里传的是不带 offset 的
        // `PWXrslamTransportCreate`(等价于 c=0)。
        let rc = PWXrslamTransportCreateWithCameraTimeOffset(
            slamConfigPath, deviceConfigPath, self.cameraTimeOffsetSeconds)
        if rc == 1 { created = true }
        return rc
"""),
# onCameraFrame
(
"""    func onCameraFrame(_ pixelBuffer: CVPixelBuffer, ptsSeconds: Double) {
        lock.lock()
        guard running else { lock.unlock(); return }
        framesOffered &+= 1
        lastCameraPts = ptsSeconds
""",
"""    /// [ptsSeconds] 是**原始** presentationTimeStamp(曝光起点);[exposureSeconds]
    /// 是当帧曝光时长(0 = 未知)。这里换算到曝光中点再推(文件头偏离 (d))。
    func onCameraFrame(_ pixelBuffer: CVPixelBuffer, ptsSeconds: Double,
                       exposureSeconds: Double) {
        // 曝光中点换算。exposure 非法/未知按 0:等价于"没换算",并计数暴露出来。
        let exposure = (exposureSeconds.isFinite && exposureSeconds >= 0)
            ? exposureSeconds : 0
        let half = 0.5 * exposure
        let canonical = ptsSeconds + half

        lock.lock()
        guard running else { lock.unlock(); return }
        framesOffered &+= 1
        lastCameraPts = ptsSeconds   // 保持原始 PTS:timing() 比的是时钟域,不是换算
        lastCanonicalPts = canonical
        tbFrames &+= 1
        if exposure > 0 {
            tbFramesWithExposure &+= 1
            tbExposureSum += exposure
            if exposure < tbExposureMin { tbExposureMin = exposure }
            if exposure > tbExposureMax { tbExposureMax = exposure }
        }
        tbHalfAppliedSum += half
"""),
(
"""        workQueue.async { [weak self] in
            self?.runOneFrame(pixelBuffer, ptsSeconds: ptsSeconds)
        }
""",
"""        workQueue.async { [weak self] in
            self?.runOneFrame(pixelBuffer, canonical: canonical, rawPts: ptsSeconds)
        }
"""),
(
"""    private func runOneFrame(_ pixelBuffer: CVPixelBuffer, ptsSeconds: Double) {
""",
"""    private func runOneFrame(_ pixelBuffer: CVPixelBuffer, canonical: Double,
                             rawPts: Double) {
"""),
(
"""        let rc = PWXrslamTransportPushCameraAndRunRaw(
            base.assumingMemoryBound(to: UInt8.self),
            ptsSeconds, Int32(stride), /*camera_id=*/0, /*channel=*/4,
            &state, &pose)

        lock.lock()
        cameraCallbacks &+= 1
""",
"""        let rc = PWXrslamTransportPushCameraAndRunRaw(
            base.assumingMemoryBound(to: UInt8.self),
            canonical, Int32(stride), /*camera_id=*/0, /*channel=*/4,
            &state, &pose)

        // [pw 2026-09-22] 时基自证(文件头偏离 (d)):刚推完就读 C 账本里相机流的
        //   最近一条 trace。workQueue 是串行的、只有这里推相机 ⇒ 读到的必是本帧。
        //   `tr.stream` 的内容校验不依赖返回码语义。
        var tr = PWXrslamTimestampTrace()
        let trc = PWXrslamTransportGetLastTimestampTrace(
            Int32(PW_XRSLAM_STREAM_CAMERA.rawValue), &tr)
        if trc == PW_XRSLAM_OK.rawValue,
           tr.stream == Int32(PW_XRSLAM_STREAM_CAMERA.rawValue) {
            let rRaw = abs(tr.raw_timestamp - canonical)
            let rOff = abs((tr.effective_timestamp - tr.raw_timestamp) - tr.applied_offset)
            lock.lock()
            tbTraceReads &+= 1
            tbLastAppliedOffset = tr.applied_offset
            tbLastEffectiveMinusPts = tr.effective_timestamp - rawPts
            if rRaw > tbMaxAbsRawResidual { tbMaxAbsRawResidual = rRaw }
            if rOff > tbMaxAbsOffsetResidual { tbMaxAbsOffsetResidual = rOff }
            lock.unlock()
        }

        lock.lock()
        cameraCallbacks &+= 1
"""),
# timebase(into:) 放在 timing 后面
(
"""    /// 写 9 个 double:state t qx qy qz qw px py pz。
    /// 0 = 有位姿;-1 = 还没有(state 仍写出,供诊断)。
    func latest(into out: UnsafeMutablePointer<Double>) -> Int32 {
""",
"""    /// [pw 2026-09-22] 写 12 个 double —— 相机时间戳换算的运行期自证(文件头偏离 (d)):
    ///   0 c 传入值(秒)          1 c 实际施加值(C 账本 applied_offset)
    ///   2 帧数                   3 其中曝光>0 的帧数
    ///   4 曝光均值  5 曝光最小  6 曝光最大(秒;3 为 0 时 4/5 写 0)
    ///   7 平均实际加上的 exposure/2(秒)
    ///   8 |C 收到的 raw − 我们推的 canonical| 峰值   **必须 0**
    ///   9 |(effective−raw) − applied_offset| 峰值     **必须 0**
    ///  10 引擎收到的时刻 − 原始 PTS(最近一帧,秒)= exposure/2 + c
    ///  11 trace 读取次数
    /// 返回 0 = 已有 trace;-1 = 还没推过帧。
    func timebase(into out: UnsafeMutablePointer<Double>) -> Int32 {
        lock.lock(); defer { lock.unlock() }
        out[0] = cameraTimeOffsetSeconds
        out[1] = tbLastAppliedOffset
        out[2] = Double(tbFrames)
        out[3] = Double(tbFramesWithExposure)
        out[4] = tbFramesWithExposure > 0
            ? tbExposureSum / Double(tbFramesWithExposure) : 0
        out[5] = tbFramesWithExposure > 0 ? tbExposureMin : 0
        out[6] = tbExposureMax
        out[7] = tbFrames > 0 ? tbHalfAppliedSum / Double(tbFrames) : 0
        out[8] = tbMaxAbsRawResidual
        out[9] = tbMaxAbsOffsetResidual
        out[10] = tbLastEffectiveMinusPts
        out[11] = Double(tbTraceReads)
        return tbTraceReads > 0 ? 0 : -1
    }

    /// 写 9 个 double:state t qx qy qz qw px py pz。
    /// 0 = 有位姿;-1 = 还没有(state 仍写出,供诊断)。
    func latest(into out: UnsafeMutablePointer<Double>) -> Int32 {
"""),
# cdecl create
(
"""@_cdecl("pw_xrslam_live_create")
public func pw_xrslam_live_create(
    _ slamConfigPath: UnsafePointer<CChar>,
    _ deviceConfigPath: UnsafePointer<CChar>
) -> Int32 {
    return PwXrslamLive.shared.create(
        slamConfigPath: String(cString: slamConfigPath),
        deviceConfigPath: String(cString: deviceConfigPath))
}
""",
"""@_cdecl("pw_xrslam_live_create")
public func pw_xrslam_live_create(
    _ slamConfigPath: UnsafePointer<CChar>,
    _ deviceConfigPath: UnsafePointer<CChar>,
    _ cameraTimeOffsetSeconds: Double
) -> Int32 {
    return PwXrslamLive.shared.create(
        slamConfigPath: String(cString: slamConfigPath),
        deviceConfigPath: String(cString: deviceConfigPath),
        cameraTimeOffsetSeconds: cameraTimeOffsetSeconds)
}
"""),
# cdecl timebase
(
"""@_cdecl("pw_xrslam_live_timing")
public func pw_xrslam_live_timing(_ out: UnsafeMutablePointer<Double>) -> Int32 {
    return PwXrslamLive.shared.timing(into: out)
}
""",
"""@_cdecl("pw_xrslam_live_timing")
public func pw_xrslam_live_timing(_ out: UnsafeMutablePointer<Double>) -> Int32 {
    return PwXrslamLive.shared.timing(into: out)
}

/// [pw 2026-09-22] 写 12 个 double,见 `PwXrslamLive.timebase`。0 有样本 / -1 还没推过帧。
@_cdecl("pw_xrslam_live_timebase")
public func pw_xrslam_live_timebase(_ out: UnsafeMutablePointer<Double>) -> Int32 {
    return PwXrslamLive.shared.timebase(into: out)
}
"""),
])

# ═══ E3 xrslam_live_ffi.dart ═════════════════════════════════════════════
edit("lib/vio/ffi/xrslam_live_ffi.dart", [
(
"""typedef _CreateNative = ffi.Int32 Function(
    ffi.Pointer<ffi.Char>, ffi.Pointer<ffi.Char>);
typedef _CreateDart = int Function(
    ffi.Pointer<ffi.Char>, ffi.Pointer<ffi.Char>);
""",
"""typedef _CreateNative = ffi.Int32 Function(
    ffi.Pointer<ffi.Char>, ffi.Pointer<ffi.Char>, ffi.Double);
typedef _CreateDart = int Function(
    ffi.Pointer<ffi.Char>, ffi.Pointer<ffi.Char>, double);
"""),
(
"""  static int? create({
    required String slamConfigPath,
    required String deviceConfigPath,
  }) {
""",
"""  ///
  /// [cameraTimeOffsetSeconds] = 每机常量 c,传输层只加在相机时间戳上
  /// (`PWXrslamTransportCreateWithCameraTimeOffset`)。曝光/2 那一项**不在这里**,
  /// 它在原生侧逐帧算(`PwXrslamLive.swift` 文件头偏离 (d))。
  static int? create({
    required String slamConfigPath,
    required String deviceConfigPath,
    double cameraTimeOffsetSeconds = 0.0,
  }) {
"""),
(
"""    try {
      return f(a, b);
    } finally {
""",
"""    try {
      return f(a, b, cameraTimeOffsetSeconds);
    } finally {
"""),
(
"""    return (
      cameraPts: _timingOut[0],
      imuTs: _timingOut[1],
      delta: _timingOut[2],
      maxAbsDelta: _timingOut[3],
    );
  }
""",
"""    return (
      cameraPts: _timingOut[0],
      imuTs: _timingOut[1],
      delta: _timingOut[2],
      maxAbsDelta: _timingOut[3],
    );
  }

  static _OutDoubleDart? _timebase;
  static final ffi.Pointer<ffi.Double> _timebaseOut = calloc<ffi.Double>(12);

  /// [pw 2026-09-22] 相机时间戳换算的**运行期自证**(`PwXrslamLive.timebase`)。
  /// `null` = 符号不在或还没推过帧。
  ///
  /// 判读(见 `PwXrslamLive.swift` 文件头偏离 (d)):
  ///   · `framesWithExposure == frames` ⇒ 每帧都拿到了曝光时长;差的那些是按 0
  ///     换算的(没猜,如实计数)。
  ///   · `maxAbsRawResidual` **必须为 0** —— C 账本收到的 raw 就是我们推的
  ///     PTS+exposure/2;非 0 = 推的不是换算值。
  ///   · `maxAbsOffsetResidual` **必须为 0** —— 传输层加的就是 applied_offset。
  ///   · `appliedOffsetSeconds` 应等于 create 时传的 [cameraTimeOffsetSeconds]。
  ///   · `effectiveMinusPtsSeconds` = 引擎实际收到的时刻 − 原始 PTS
  ///     = exposure/2 + c,是这条链**唯一**的端到端读数。
  static ({
    double cameraTimeOffsetSeconds,
    double appliedOffsetSeconds,
    int frames,
    int framesWithExposure,
    double meanExposureSeconds,
    double minExposureSeconds,
    double maxExposureSeconds,
    double meanHalfAppliedSeconds,
    double maxAbsRawResidual,
    double maxAbsOffsetResidual,
    double effectiveMinusPtsSeconds,
    int traceReads,
  })? timebase() {
    _lookup();
    _timebase ??= () {
      try {
        return _lib.lookupFunction<_OutDoubleNative, _OutDoubleDart>(
            'pw_xrslam_live_timebase');
      } catch (_) {
        return null;
      }
    }();
    final _OutDoubleDart? f = _timebase;
    if (f == null) return null;
    if (f(_timebaseOut) != 0) return null;
    return (
      cameraTimeOffsetSeconds: _timebaseOut[0],
      appliedOffsetSeconds: _timebaseOut[1],
      frames: _timebaseOut[2].toInt(),
      framesWithExposure: _timebaseOut[3].toInt(),
      meanExposureSeconds: _timebaseOut[4],
      minExposureSeconds: _timebaseOut[5],
      maxExposureSeconds: _timebaseOut[6],
      meanHalfAppliedSeconds: _timebaseOut[7],
      maxAbsRawResidual: _timebaseOut[8],
      maxAbsOffsetResidual: _timebaseOut[9],
      effectiveMinusPtsSeconds: _timebaseOut[10],
      traceReads: _timebaseOut[11].toInt(),
    );
  }
"""),
])

# ═══ E4 xrslam_session.dart ══════════════════════════════════════════════
edit("lib/vio/ffi/xrslam_session.dart", [
(
"""  static XrslamSessionStart start({CameraIntrinsics? intrinsics}) {
""",
"""  ///
  /// [cameraTimeOffsetSeconds] = 每机常量 c,原样交给原生 create(传输层只加在
  /// 相机时间戳上)。默认 0。见 `PwXrslamLive.swift` 文件头偏离 (d)。
  static XrslamSessionStart start({
    CameraIntrinsics? intrinsics,
    double cameraTimeOffsetSeconds = 0.0,
  }) {
"""),
(
"""    final int? rc = XrslamLive.create(
      slamConfigPath: _slamPath!,
      deviceConfigPath: _devPath!,
    );
""",
"""    final int? rc = XrslamLive.create(
      slamConfigPath: _slamPath!,
      deviceConfigPath: _devPath!,
      cameraTimeOffsetSeconds: cameraTimeOffsetSeconds,
    );
"""),
])

# ═══ E5 ar_minimal_loop_page.dart ════════════════════════════════════════
edit("lib/vio/render/ar_minimal_loop_page.dart", [
(
"""  void _ensureSession() {
    if (_sessionAttempted || XrslamSession.current != null) return;
""",
"""  /// [pw 2026-09-22] 每机常量 c,`--dart-define=PW_CAM_TD_MS=<毫秒>`,默认 0。
  /// 传给 `PWXrslamTransportCreateWithCameraTimeOffset`,只加在相机时间戳上。
  /// 它**不是**曝光/2 —— 那一项在 `PwCameraSlot`→`PwXrslamLive` 里逐帧算;
  /// c 是剩下的(卷帘读出/2 + 管线固定延迟),用回放扫描定一次。
  static const String _camTdMsRaw =
      String.fromEnvironment('PW_CAM_TD_MS', defaultValue: '0');
  static final double _camTdSeconds =
      (double.tryParse(_camTdMsRaw) ?? 0.0) / 1000.0;

  void _ensureSession() {
    if (_sessionAttempted || XrslamSession.current != null) return;
"""),
(
"""    _session = XrslamSession.start(
      intrinsics: CameraIntrinsics(
""",
"""    _session = XrslamSession.start(
      cameraTimeOffsetSeconds: _camTdSeconds,
      intrinsics: CameraIntrinsics(
"""),
(
"""          debugPrint('[arloop] 时钟 camPTS=${t.cameraPts.toStringAsFixed(3)}s '
              'imuTS=${t.imuTs.toStringAsFixed(3)}s '
              'delta=${(t.delta * 1000).toStringAsFixed(1)}ms '
              '|delta|峰值=${(t.maxAbsDelta * 1000).toStringAsFixed(1)}ms');
        }
""",
"""          debugPrint('[arloop] 时钟 camPTS=${t.cameraPts.toStringAsFixed(3)}s '
              'imuTS=${t.imuTs.toStringAsFixed(3)}s '
              'delta=${(t.delta * 1000).toStringAsFixed(1)}ms '
              '|delta|峰值=${(t.maxAbsDelta * 1000).toStringAsFixed(1)}ms');
        }
        // [pw 2026-09-22] 时基自证 —— 相机时间戳是不是真的按"曝光中点 + c"进了引擎。
        //    两个 residual 必须恒 0;`有曝光` 应等于 `帧`;`引擎收到−PTS` ≈ 曝光/2 + c。
        //    这是把"改了两行"变成"引擎确实吃到了换算值"的唯一现场证据。
        final tb = XrslamLive.timebase();
        if (tb != null) {
          debugPrint('[arloop] 时基 '
              'c传入=${(tb.cameraTimeOffsetSeconds * 1000).toStringAsFixed(2)}ms '
              'c施加=${(tb.appliedOffsetSeconds * 1000).toStringAsFixed(2)}ms '
              '帧=${tb.frames} 有曝光=${tb.framesWithExposure} '
              '曝光ms[min/mean/max]=${(tb.minExposureSeconds * 1000).toStringAsFixed(2)}/'
              '${(tb.meanExposureSeconds * 1000).toStringAsFixed(2)}/'
              '${(tb.maxExposureSeconds * 1000).toStringAsFixed(2)} '
              '平均加=${(tb.meanHalfAppliedSeconds * 1000).toStringAsFixed(2)}ms '
              '引擎收到−PTS=${(tb.effectiveMinusPtsSeconds * 1000).toStringAsFixed(2)}ms '
              'residual[raw/offset]=${tb.maxAbsRawResidual.toStringAsExponential(1)}/'
              '${tb.maxAbsOffsetResidual.toStringAsExponential(1)} '
              'trace读=${tb.traceReads}');
        }
"""),
])
print("全部改动落地(pocketworld = 真源)")
