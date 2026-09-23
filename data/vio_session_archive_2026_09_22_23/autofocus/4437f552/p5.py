import io, sys
p = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/prod-af-20260923/lib/vio/ffi/pw_focus_ffi.dart"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    if old not in s: sys.exit("NOT FOUND:\n"+old[:300])
    if s.count(old) != 1: sys.exit("NOT UNIQUE")
    s = s.replace(old, new)

rep("""// pw_focus_ffi.dart —— **对焦三臂**的 Dart 侧绑定。
//
// 对应 `ios/Runner/PwFocusArms.swift` 的五个 C ABI 出口:
//   `pw_camera_slot_focus_arm(int32 arm) -> int32`
//   `pw_camera_slot_focus_state(double* out16) -> int32`
//   `pw_camera_slot_focus_prepare(int32 mode) -> int32`
//   `pw_camera_slot_focus_series(double* out, int32 capSamples) -> int32`
//   `pw_camera_slot_focus_report(char* out, int32 cap) -> int32`
//
// ══ 三臂是什么 ═══════════════════════════════════════════════════════════
//   A 对照 = 现状锁焦 0.835(默认臂;不传 `-PWFocusArm` 就是它)
//   B 苹果 AF = `.continuousAutoFocus` + `.near` + 对焦区域框住物体
//   C 我们的 CDAF = `vendor/pw_af/` 的状态机驱动 `setFocusModeLocked`
// 判决书附录 B.3:`docs/research/autofocus_algorithm_survey_20260922.md`。""",
"""// pw_focus_ffi.dart —— 零 ARKit 臂对焦的 Dart 侧绑定。
//
// 对应 `ios/Runner/PwFocusArms.swift` 的六个 C ABI 出口:
//   `pw_camera_slot_focus_arm(int32 arm) -> int32`
//   `pw_camera_slot_focus_state(double* out16) -> int32`
//   `pw_camera_slot_focus_prepare(int32 mode) -> int32`
//   `pw_camera_slot_focus_series(double* out, int32 capSamples) -> int32`
//   `pw_camera_slot_focus_report(char* out, int32 cap) -> int32`
//   `pw_camera_slot_focus_nudge() -> int32`(自愈的那一脚,2026-09-23 加)
//
// ══ 🔴 2026-09-23 用户拍板「换掉锁定,照生产那套来」⇒ 默认臂换成 B ═══════
//   A 阴性对照 = 现状锁焦 0.835(**不再是默认**;要它就 `-PWFocusArm a`)
//   B **默认 = 生产同款** = `isSmoothAutoFocusEnabled` + `.continuousAutoFocus`
//     (逐句对照生产 `OfficialAetherARKitPlugin.swift:2653-2661`)
//     **加**生产没用的两个旋钮:`.near` 近端限制 + 对焦区域框住被扫物体
//   C 我们的 CDAF = `vendor/pw_af/` 的状态机驱动 `setFocusModeLocked`
// 判决书附录 B.3:`docs/research/autofocus_algorithm_survey_20260922.md`。""")

rep("""enum PwFocusArm {
  a(0, 'a', 'a_locked_baseline', 'A 对照:锁焦 0.835'),
  b(1, 'b', 'b_apple_af', 'B 苹果 AF:continuousAutoFocus + near + 对焦区域'),
  c(2, 'c', 'c_pw_af_cdaf', 'C 我们的 CDAF:pw_af 驱动 setFocusModeLocked');""",
"""enum PwFocusArm {
  a(0, 'a', 'a_locked_baseline', 'A 阴性对照:锁焦 0.835(不再是默认)'),
  b(1, 'b', 'b_production_af',
      'B 默认=生产同款:smoothAutoFocus + continuousAutoFocus,加 near + 物体框'),
  c(2, 'c', 'c_pw_af_cdaf', 'C 我们的 CDAF:pw_af 驱动 setFocusModeLocked');""")

rep("""/// 臂是从哪儿来的。与 Swift 的 `PwFocusArmSource` 对应。
enum PwFocusArmSource {
  defaultNoArgument(0, 'default_no_argument'),""",
"""/// 臂是从哪儿来的。与 Swift 的 `PwFocusArmSource` 对应。
/// `default_no_argument` 现在是 **B(生产同款)**,不再是 A。
enum PwFocusArmSource {
  defaultNoArgument(0, 'default_no_argument'),""")

rep("""  unsupported(5, 'unsupported_arm_a'),""",
"""  unsupported(5, 'unsupported_arm_a'), // A 阴性对照:本来就不动镜头""")

rep("""typedef _ReportNative = ffi.Int32 Function(ffi.Pointer<ffi.Char>, ffi.Int32);
typedef _ReportDart = int Function(ffi.Pointer<ffi.Char>, int);""",
"""typedef _ReportNative = ffi.Int32 Function(ffi.Pointer<ffi.Char>, ffi.Int32);
typedef _ReportDart = int Function(ffi.Pointer<ffi.Char>, int);
typedef _NudgeNative = ffi.Int32 Function();
typedef _NudgeDart = int Function();""")

rep("""  static _ReportDart? _report;

  static void _lookup() {""",
"""  static _ReportDart? _report;
  static _NudgeDart? _nudge;

  static void _lookup() {""")

rep("""      _report = _lib.lookupFunction<_ReportNative, _ReportDart>(
          'pw_camera_slot_focus_report');
    } catch (_) {""",
"""      _report = _lib.lookupFunction<_ReportNative, _ReportDart>(
          'pw_camera_slot_focus_report');
      _nudge = _lib.lookupFunction<_NudgeNative, _NudgeDart>(
          'pw_camera_slot_focus_nudge');
    } catch (_) {""")

rep("""  /// 五个符号是否都在。
  static bool get available {
    _lookup();
    return _arm != null &&
        _state != null &&
        _prepare != null &&
        _series != null &&
        _report != null;
  }""",
"""  /// 六个符号是否都在。
  static bool get available {
    _lookup();
    return _arm != null &&
        _state != null &&
        _prepare != null &&
        _series != null &&
        _report != null &&
        _nudge != null;
  }""")

rep("""  /// 原生侧的 report JSON 原文(能力位 / 注释 / ROI / 臂来源)。""",
"""  /// 对焦自愈的那一脚。**判定不在这里** —— 判定循环在
  /// `lib/vio/capture/focus_self_heal.dart`(与生产
  /// `ar_capture_page.dart:512-563` 同式);这里只是把「踢」这个动作转给原生。
  ///
  /// 返回原生的受理码:1 = 已下发;0 = 本臂不适用(A 阴性对照 / C 自带重触发);
  /// -1 = 相机没起来;-2 = 锁设备失败;**null = 符号不在**(不抛)。
  static int? nudge() {
    _lookup();
    return _nudge?.call();
  }

  /// 原生侧的 report JSON 原文(能力位 / 注释 / ROI / 臂来源)。""")

# 文件末尾加执行器适配
s = s.rstrip("\n") + """

/// 把 [PwFocus.nudge] 包成跨端的 [FocusNudger]。
///
/// 🔴 这是**四端里 iOS 的那一个实现**;判定循环那一份
/// (`lib/vio/capture/focus_self_heal.dart`)四端共用,一行都不该按平台分叉。
/// Android / HarmonyOS / Web 各自写一个同形状的类即可(MethodChannel 或 JS
/// 互操作),把 `nudge()` 接到各自平台的「一次性对焦 → 限时回连续」上。
class PwFocusFfiNudger implements FocusNudger {
  const PwFocusFfiNudger();

  /// 原生上一次返回的受理码(诊断用;见 [PwFocus.nudge] 的取值表)。
  static int? lastReturnCode;

  @override
  bool nudge() {
    final int? rc = PwFocus.nudge();
    lastReturnCode = rc;
    return rc == 1;
  }

  @override
  String get describe =>
      'PwFocusFfiNudger → pw_camera_slot_focus_nudge → PwFocusArms.nudge()'
      '(物体框一次性对焦 → 1.2 s 回 .continuousAutoFocus;'
      '移植自生产 OfficialAetherARKitPlugin.swift:1418-1445)';
}
"""

# import
rep("""import 'dart:ffi' as ffi;

import 'package:ffi/ffi.dart';""",
"""import 'dart:ffi' as ffi;

import 'package:ffi/ffi.dart';

import '../capture/focus_self_heal.dart';""")

io.open(p, "w", encoding="utf-8").write(s)
print("ok")
