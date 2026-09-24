#!/usr/bin/python3
# fixA: add devicePoseTrusted to AetherSfmStreamSession.addJpegFrame (FFI stub
# for agent C's core-side ABI).
import sys
p = sys.argv[1]
s = open(p).read()


def rep(old, new, count=1):
    global s
    n = s.count(old)
    assert n == count, (n, old[:120])
    s = s.replace(old, new)


rep("""// [EXTRACT-PREFETCH 2026-08-09] JPEG 版预取:非阻塞,壳层解码后交核内专属""", """// [DEVICE-POSE-TRUST 2026-09-24] 带「设备位姿可信」位的喂帧 ABI(核侧由
// agent C 实现,契约见 lib/official_capture/device_pose_trust.dart)。
// 与 v1 逐参同序,只在 pose_t 之后多一个 int32 device_pose_trusted(0/1)。
// 0 ⇒ 核不得把该帧摆在设备位姿上、不得拿它做 Sim3 对齐对/位姿先验,按上游
// 无先验图像从图像证据注册(证据不够则不注册)。位姿指针照传(审计/诊断)。
// 🔴 符号名/签名是本侧提案;若 C 定名不同,只改这里与 _lookupAddJpegFrameV2。
typedef _AddJpegFrameV2C =
    Int32 Function(
      Pointer<Void> session,
      Pointer<Utf8> jpegPath,
      Double captureTimestamp,
      Float fx,
      Float fy,
      Float cx,
      Float cy,
      Pointer<Double> poseQwxyz, // may be nullptr
      Pointer<Double> poseT, // may be nullptr
      Int32 devicePoseTrusted, // 1 = trusted, 0 = untrusted
      Pointer<Int32> outFrameId,
    );
typedef _AddJpegFrameV2Dart =
    int Function(
      Pointer<Void> session,
      Pointer<Utf8> jpegPath,
      double captureTimestamp,
      double fx,
      double fy,
      double cx,
      double cy,
      Pointer<Double> poseQwxyz,
      Pointer<Double> poseT,
      int devicePoseTrusted,
      Pointer<Int32> outFrameId,
    );

// [EXTRACT-PREFETCH 2026-08-09] JPEG 版预取:非阻塞,壳层解码后交核内专属""")

rep("""  // [EXTRACT-PREFETCH] 懒绑定;旧 framework 无此符号时首次调用抛错,调用方
  // catch(与 repairStats 同一契约)。""", """  // [DEVICE-POSE-TRUST 2026-09-24] 懒绑定、可缺:旧 framework 没有 v2 符号时
  // 为 null,addJpegFrame 回退 v1(核按旧行为使用设备位姿),并在返回值里
  // 报告 devicePoseTrustHonored=false,由 fed 记录如实落盘。
  static final _AddJpegFrameV2Dart? _addJpegFrameV2 = _lookupAddJpegFrameV2();
  static _AddJpegFrameV2Dart? _lookupAddJpegFrameV2() {
    try {
      return _lib.lookupFunction<_AddJpegFrameV2C, _AddJpegFrameV2Dart>(
        'pwofficial_add_jpeg_frame_v2',
      );
    } catch (_) {
      return null;
    }
  }

  /// 当前链接的核是否实现了带设备位姿可信位的喂帧 ABI。
  static bool get supportsDevicePoseTrust => _addJpegFrameV2 != null;

  // [EXTRACT-PREFETCH] 懒绑定;旧 framework 无此符号时首次调用抛错,调用方
  // catch(与 repairStats 同一契约)。""")

rep("""    List<double>? quatWxyz,
    List<double>? translation,
  }) {
    _checkLive();
    final pathPtr = jpegPath.toNativeUtf8();
    final idPtr = malloc<Int32>();""", """    List<double>? quatWxyz,
    List<double>? translation,
    // [DEVICE-POSE-TRUST 2026-09-24] 追踪器是否承认这帧的设备位姿。缺省 true
    // 只为兼容既有调用;拍摄期喂帧路径一律显式传入。
    bool devicePoseTrusted = true,
  }) {
    _checkLive();
    final pathPtr = jpegPath.toNativeUtf8();
    final idPtr = malloc<Int32>();""")

rep("""      idPtr.value = -1;
      final rc = AetherSfm._addJpegFrame(
        _session,
        pathPtr,
        captureTimestamp,
        fx,
        fy,
        cx,
        cy,
        qPtr,
        tPtr,
        idPtr,
      );
      final result = _resultFromCode(rc);
      return AetherSfmAddFrameResult(
        result,
        result == AetherSfmResult.ok ? idPtr.value : -1,
      );""", """      idPtr.value = -1;
      final v2 = AetherSfm._addJpegFrameV2;
      final rc = v2 != null
          ? v2(
              _session,
              pathPtr,
              captureTimestamp,
              fx,
              fy,
              cx,
              cy,
              qPtr,
              tPtr,
              devicePoseTrusted ? 1 : 0,
              idPtr,
            )
          : AetherSfm._addJpegFrame(
              _session,
              pathPtr,
              captureTimestamp,
              fx,
              fy,
              cx,
              cy,
              qPtr,
              tPtr,
              idPtr,
            );
      final result = _resultFromCode(rc);
      return AetherSfmAddFrameResult(
        result,
        result == AetherSfmResult.ok ? idPtr.value : -1,
        devicePoseTrustHonored: v2 != null,
      );""")

rep("""class AetherSfmAddFrameResult {
  final AetherSfmResult result;
  final int frameId; // -1 unless result == ok
  const AetherSfmAddFrameResult(this.result, this.frameId);
}""", """class AetherSfmAddFrameResult {
  final AetherSfmResult result;
  final int frameId; // -1 unless result == ok

  /// [DEVICE-POSE-TRUST 2026-09-24] true = 经带信任位的 v2 ABI 喂入(核按
  /// devicePoseTrusted 处理);false = 旧核回退 v1(核按旧行为用设备位姿)。
  final bool devicePoseTrustHonored;
  const AetherSfmAddFrameResult(
    this.result,
    this.frameId, {
    this.devicePoseTrustHonored = false,
  });
}""")
open(p, 'w').write(s)
print('ok')
