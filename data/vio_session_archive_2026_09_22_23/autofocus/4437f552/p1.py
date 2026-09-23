import io, sys
p = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/prod-af-20260923/ios/Runner/PwFocusArms.swift"
s = io.open(p, encoding="utf-8").read()

def rep(old, new):
    global s
    if old not in s:
        sys.exit("NOT FOUND:\n" + old[:400])
    if s.count(old) != 1:
        sys.exit("NOT UNIQUE (%d):\n%s" % (s.count(old), old[:200]))
    s = s.replace(old, new)

# ── (a) 文件头:三臂的定位改成「生产同款是默认,锁焦降为阴性对照」──────────
rep(
"""// PwFocusArms.swift — **对焦三臂**的 iOS 宿主侧。一次拿手机把三条路同场量完。
//
// ══ 三臂是什么(判决书附录 B.3,`docs/research/autofocus_algorithm_survey_20260922.md`)══
//   A(对照)= 现状 `setFocusModeLocked(lensPosition: 0.835)`,**一个字节不改**。
//   B(最省力)= 苹果自己的 AF:`.continuousAutoFocus` +
//               `autoFocusRangeRestriction = .near` + 对焦区域框住被扫物体。
//               它是唯一吃得到主摄「100% Focus Pixels」全阵列相位硬件的一臂
//               (iOS 不暴露相位数据,B.2)。
//   C(我们的 CDAF)= `vendor/pw_af/` 的状态机驱动 `setFocusModeLocked(lensPosition:)`,
//               每步调一次,用 completionHandler 的 `CMTime` 当「镜头已到位」硬信号。
//
// 选臂:启动参数 `-PWFocusArm a|b|c`,**默认 a** ⇒ 不传参数时行为与本刀之前
// 逐字节相同。读法与 `PwZeroArkitGate.swift` 的 `pw_vio_pose_source` 同一形状
// (NSArgumentDomain 优先、再自扫 argv 作第二证据)。""",
"""// PwFocusArms.swift — 零 ARKit 臂的对焦宿主侧。**默认 = 生产同款的苹果自动对焦**。
//
// ══ 🔴🔴 2026-09-23 用户拍板:「换掉锁定,照生产那套来」═════════════════════
// 生产采集页从来就用苹果自己的 AF(`OfficialAetherARKitPlugin.swift:2192`
// `configuration.isAutoFocusEnabled = true`),而零 ARKit 臂抄上游 XRSLAM 锁了
// 焦(`ViewController.swift:256` → `setFocusModeLocked(0.835)`)—— 那**正是**
// 生产注释里用血写着不许做的事。生产 `:2189-2191` 原文,逐字抄在这里:
//
//     "Let ARKit drive continuous autofocus. Important: do not later flip the
//      underlying AVCaptureDevice into one-shot focus/locked focus; that can
//      leave the preview stuck at a near lens distance after the user moves."
//
// 所以本刀把**默认臂从 A(锁焦)换成 B(生产同款)**。三个臂本身一个都不删:
//
// ══ 三臂是什么(判决书附录 B.3,`docs/research/autofocus_algorithm_survey_20260922.md`)══
//   A(🔴 **阴性对照,不再是默认**)= 现状 `setFocusModeLocked(lensPosition: 0.835)`,
//               **一个字节不改**。留着的唯一理由:它是「对焦这件事从没发生过」
//               的基线 —— 任何「新臂更清晰」的结论都要能跟它比,否则就是拿
//               一个没有失败可能的判据放行(feedback_verify_with_a_metric_that_can_fail)。
//               走 `-PWFocusArm a` 显式选它。
//   B(**默认 = 生产同款 + 两个生产没用的旋钮**)=
//               生产那三句:`isSmoothAutoFocusSupported ⇒ isSmoothAutoFocusEnabled
//               = true` + `focusMode = .continuousAutoFocus`(逐句对照
//               `OfficialAetherARKitPlugin.swift:2653-2661`),
//               **加**生产没用的两个:`autoFocusRangeRestriction = .near`
//               与「对焦区域 = 被扫物体框」(`focusRectOfInterest` iOS 26+,
//               回落 `focusPointOfInterest`)。
//               它是唯一吃得到主摄「100% Focus Pixels」全阵列相位硬件的一臂
//               (iOS 不暴露相位数据,B.2)。
//   C(我们的 CDAF)= `vendor/pw_af/` 的状态机驱动 `setFocusModeLocked(lensPosition:)`,
//               每步调一次,用 completionHandler 的 `CMTime` 当「镜头已到位」硬信号。
//
// ══ 对焦自愈环(生产 `[AF-SELFHEAL 2026-08-10 用户签]` 的移植)═════════════
// 病灶(生产注释原话):「糊掉的低纹理画面无相位信号无反差梯度 → 连续 AF 收不到
// 失焦证据」;「ARKit 又刻意压制对焦频率(对焦呼吸伤 VIO)」(`:1415`)。
// 分工与生产**同构**:判定循环全在 Dart(`lib/vio/capture/focus_self_heal.dart`,
// 对照生产 `lib/ui/official_capture/ar_capture_page.dart:512-563`),原生这边
// **只执行一脚** —— 见下面的 `nudge()`(对照生产 `:1418-1445` 的 `focusNudge`)。
//
// 选臂:启动参数 `-PWFocusArm a|b|c`,**默认 b**。读法与 `PwZeroArkitGate.swift`
// 的 `pw_vio_pose_source` 同一形状(NSArgumentDomain 优先、再自扫 argv 作第二
// 证据)。""")

# ── (b) 枚举:标注默认与标签改名 ────────────────────────────────────────────
rep(
"""enum PwFocusArm: Int32 {
    case a = 0  // 对照:锁焦
    case b = 1  // 苹果 AF
    case c = 2  // 我们的 CDAF

    var label: String {
        switch self {
        case .a: return "a_locked_baseline"
        case .b: return "b_apple_af"
        case .c: return "c_pw_af_cdaf"
        }
    }""",
"""enum PwFocusArm: Int32 {
    // 🔴 rawValue 是**冻结**的(Dart 侧 `PwFocusArm` 与已归档的 manifest 都按它
    //    解读)⇒ 换默认臂只换 `PwFocusArms.arm` 的初值,不动这三个数。
    case a = 0  // 🔴 阴性对照:锁焦(**不再是默认**)
    case b = 1  // ✅ 默认:生产同款苹果 AF + 两个生产没用的旋钮
    case c = 2  // 我们的 CDAF

    var label: String {
        switch self {
        case .a: return "a_locked_baseline"
        case .b: return "b_production_af"
        case .c: return "c_pw_af_cdaf"
        }
    }""")

rep(
"""enum PwFocusArmSource: Int32 {
    case defaultArm = 0   // 没传参数 ⇒ A""",
"""enum PwFocusArmSource: Int32 {
    case defaultArm = 0   // 没传参数 ⇒ B(生产同款臂)""")

rep(
"""    case unsupported = 5  // A 臂:本来就不动镜头 ⇒ 无事可做""",
"""    case unsupported = 5  // A 臂(阴性对照):本来就不动镜头 ⇒ 无事可做""")

# ── (c) 默认臂 ──────────────────────────────────────────────────────────────
rep(
"""    // ── 臂 ──
    private(set) var arm: PwFocusArm = .a
    private(set) var armSource: PwFocusArmSource = .defaultArm""",
"""    // ── 臂 ──
    /// 🔴🔴 **默认 = B(生产同款苹果 AF)**。2026-09-23 用户拍板「换掉锁定,
    /// 照生产那套来」。改这一个字母就是「换掉锁定」的全部 —— A 臂那三行锁焦
    /// 代码在 `PwCameraSlot.swift` 里一个字节没动,只是条件 `focusArm == .a`
    /// 从此默认不成立(要它就显式 `-PWFocusArm a`)。
    private(set) var arm: PwFocusArm = .b
    private(set) var armSource: PwFocusArmSource = .defaultArm""")

rep(
"""            notes.append("-\\(Self.kLaunchArgumentKey) 值无法解析:「\\(raw)」⇒ 留在默认 A")""",
"""            notes.append("-\\(Self.kLaunchArgumentKey) 值无法解析:「\\(raw)」⇒ 留在默认 B(生产同款)")""")

io.open(p, "w", encoding="utf-8").write(s)
print("ok")
