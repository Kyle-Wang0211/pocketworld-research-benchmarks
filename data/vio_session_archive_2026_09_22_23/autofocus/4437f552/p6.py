import io, sys
p = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/prod-af-20260923/lib/vio/render/zero_arkit_capture_probe_page.dart"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    if old not in s: sys.exit("NOT FOUND:\n"+old[:300])
    if s.count(old) != 1: sys.exit("NOT UNIQUE (%d):\n%s" % (s.count(old), old[:200]))
    s = s.replace(old, new)

# ── import ──
rep("""import '../capture/camera_time_offset.dart';
import '../capture/zero_arkit_capture_runtime.dart';""",
"""import '../capture/camera_time_offset.dart';
import '../capture/focus_self_heal.dart';
import '../capture/zero_arkit_capture_runtime.dart';""")

# ── schema ──
rep("""/// manifest 的 schema 标签。
/// `/2` = 2026-09-23 加了对焦三臂那一块(`focus` 与 `focus_acceptance_tables`)。
const String kZeroArkitProbeManifestSchema = 'pw.bench.zero_arkit_capture_probe/2';""",
"""/// manifest 的 schema 标签。
/// `/2` = 2026-09-23 加了对焦三臂那一块(`focus` 与 `focus_acceptance_tables`)。
/// `/3` = 2026-09-23 换默认臂(锁焦 → 生产同款 AF)+ 加对焦自愈环
///        (`focus.self_heal`,含 nudge 事件序列)。
const String kZeroArkitProbeManifestSchema = 'pw.bench.zero_arkit_capture_probe/3';""")

# ── manifest 参数 ──
rep("""  required String? focusNativeReportJson,
  required List<PwFocusSample> focusSeries,
}) {""",
"""  required String? focusNativeReportJson,
  required List<PwFocusSample> focusSeries,
  required FocusSelfHeal? focusSelfHeal,
}) {""")

rep("""    'focus': _focusBlock(
      focusAvailable: focusAvailable,
      stateAtFinish: focusStateAtFinish,
      nativeReportJson: focusNativeReportJson,
      series: focusSeries,
    ),""",
"""    'focus': _focusBlock(
      focusAvailable: focusAvailable,
      stateAtFinish: focusStateAtFinish,
      nativeReportJson: focusNativeReportJson,
      series: focusSeries,
      selfHeal: focusSelfHeal,
    ),""")

rep("""      'table_b_video_stream': <String, Object?>{
        'what': '视频流持续对焦(判决书 §6.3 表 B)',
        'series_ref': 'focus.video_stream_series',
      },""",
"""      'table_b_video_stream': <String, Object?>{
        'what': '视频流持续对焦(判决书 §6.3 表 B)',
        'series_ref': 'focus.video_stream_series',
        'self_heal_ref': 'focus.self_heal(自愈环踢的每一脚:时刻 / 触发时度量 / '
            '动作后 2 s 内的度量变化)',
      },""")

# ── _focusBlock ──
rep("""Map<String, Object?> _focusBlock({
  required bool focusAvailable,
  required PwFocusState? stateAtFinish,
  required String? nativeReportJson,
  required List<PwFocusSample> series,
}) {""",
"""Map<String, Object?> _focusBlock({
  required bool focusAvailable,
  required PwFocusState? stateAtFinish,
  required String? nativeReportJson,
  required List<PwFocusSample> series,
  required FocusSelfHeal? selfHeal,
}) {""")

rep("""    'arm_launch_argument': '-PWFocusArm a|b|c(默认 a = 现状锁焦对照臂)',""",
"""    'arm_launch_argument':
        '-PWFocusArm a|b|c(🔴 2026-09-23 起**默认 b = 生产同款苹果 AF**;'
        'a = 锁焦,已降为阴性对照,要它必须显式传)',
    'default_arm_change_note':
        '用户拍板「换掉锁定,照生产那套来」。新默认臂 = 生产 '
        'OfficialAetherARKitPlugin.swift:2653-2661 那两句(isSmoothAutoFocusEnabled '
        '+ .continuousAutoFocus)+ 生产没用的两个旋钮(autoFocusRangeRestriction '
        '= .near、对焦区域 = 被扫物体框)。生产 :2189-2191 的警告原文已抄进 '
        'PwFocusArms.swift / PwCameraSlot.swift 的注释里。',""")

rep("""      'samples': kept.map((PwFocusSample x) => x.toJson()).toList(),
    },
  };
}""",
"""      'samples': kept.map((PwFocusSample x) => x.toJson()).toList(),
    },
    'self_heal': selfHeal?.toJson(),
  };
}""")

io.open(p, "w", encoding="utf-8").write(s)
print("ok part1")
