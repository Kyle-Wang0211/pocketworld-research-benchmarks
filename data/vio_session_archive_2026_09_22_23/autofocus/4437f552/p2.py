import io, sys
p = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/prod-af-20260923/ios/Runner/PwFocusArms.swift"
s = io.open(p, encoding="utf-8").read()

def rep(old, new):
    global s
    if old not in s: sys.exit("NOT FOUND:\n" + old[:400])
    if s.count(old) != 1: sys.exit("NOT UNIQUE (%d)" % s.count(old))
    s = s.replace(old, new)

# ── B 臂:补上生产那两句 smoothAutoFocus,并把生产行号逐句标上 ─────────────
rep(
"""    /// B 臂 —— 逐条按 `AVCaptureDevice.h`(iPhoneOS26.2.sdk)原文。
    private func configureAppleAf(device: AVCaptureDevice) {
        // (1) 近端限制。`AVCaptureDevice.h:1215` 原文:""",
"""    /// B 臂 = **生产同款** + 两个生产没用的旋钮。
    ///
    /// ══ 哪几句是逐句抄生产的 ═══════════════════════════════════════════════
    /// 生产 `OfficialAetherARKitPlugin.swift` 的 `restoreContinuousExposureFocus`:
    ///   `:2653-2655`  `if device.isSmoothAutoFocusSupported {
    ///                     device.isSmoothAutoFocusEnabled = true }`   → 本函数 (0)
    ///   `:2659-2661`  `if device.isFocusModeSupported(.continuousAutoFocus) {
    ///                     device.focusMode = .continuousAutoFocus }`  → 本函数 (3)
    /// 生产 `:2192` `configuration.isAutoFocusEnabled = true` 是 ARKit 配置层的
    /// 同一件事(ARKit 替我们把底下那台 AVCaptureDevice 设成连续 AF);零 ARKit
    /// 臂没有 ARKit 配置,直接对 AVCaptureDevice 做,落点是同一个属性。
    ///
    /// ⚠️ 生产那个函数里还有一句 `exposureMode = .continuousAutoExposure`
    ///    (`:2656-2658`)—— **本函数刻意不抄**:曝光归 `PwCameraSlot` 管
    ///    (`pw_camera_slot_exposure` 那条路),对焦臂只碰 focus*,否则两处
    ///    争同一个属性,谁最后写谁赢,现场没法归因。
    ///
    /// ══ 🔴 生产 `:2189-2191` 的警告原文(必须留在这里)═════════════════════
    ///     "Let ARKit drive continuous autofocus. Important: do not later flip
    ///      the underlying AVCaptureDevice into one-shot focus/locked focus;
    ///      that can leave the preview stuck at a near lens distance after the
    ///      user moves."
    ///   ⇒ 本臂**任何路径都不许**落到 `setFocusModeLocked` / 常驻 `.autoFocus`。
    ///     唯一一次 `.autoFocus` 是快门前那一下(`prepareBegin`)与自愈那一脚
    ///     (`nudge()`),两处都**限时回 `.continuousAutoFocus`**(生产 `focusNudge`
    ///     也是 1.2 s 回连续,`:1432-1443`)。
    ///
    /// 下面 (1)(2) 是生产**没用**的两个旋钮,逐条按 `AVCaptureDevice.h`
    /// (iPhoneOS26.2.sdk)原文。
    private func configureAppleAf(device: AVCaptureDevice) {
        // (0) 🔴 生产同款:平滑对焦。`OfficialAetherARKitPlugin.swift:2653-2655`
        //     逐句。`AVCaptureDevice.h` 原文:"Smooth autofocus is appropriate
        //     for movie recording … lens movements are slower and less visually
        //     distracting." —— 对我们不是「好看」而是**承重**:生产 `:1415` 注释
        //     写着「ARKit 又刻意压制对焦频率(对焦呼吸伤 VIO)」,平滑对焦正是
        //     把镜头位移摊慢、少给 VIO 灌对焦呼吸的那一档。
        if device.isSmoothAutoFocusSupported {
            device.isSmoothAutoFocusEnabled = true
            appendNote("B:isSmoothAutoFocusEnabled = true(生产 :2653-2655 同款)")
        } else {
            appendNote("🔴 B:isSmoothAutoFocusSupported = false ⇒ 没开平滑对焦")
        }

        // (1) 近端限制。`AVCaptureDevice.h:1215` 原文:""")

# ── 自愈那一脚(原生只执行,判定在 Dart)────────────────────────────────────
rep(
"""    private func appendNote(_ s: String) {
        lock.lock(); notes.append(s); lock.unlock()
    }""",
"""    private func appendNote(_ s: String) {
        lock.lock(); notes.append(s); lock.unlock()
    }

    // ════════════════════════════════════════════════════════════════════════
    // MARK: 对焦自愈的那一脚(生产 `focusNudge` 的移植)
    // ════════════════════════════════════════════════════════════════════════

    /// 生产 `OfficialAetherARKitPlugin.swift:1418-1445` 的 `focusNudge`,逐条移植。
    ///
    /// 生产那边的三句动作:
    ///   `:1425-1427`  `focusPointOfInterest = CGPoint(x: 0.5, y: 0.5)`(硬中心)
    ///   `:1428-1430`  `focusMode = .autoFocus`(中心一次性,强制扫描打破死锁)
    ///   `:1432-1443`  `DispatchQueue.main.asyncAfter(deadline: .now() + 1.2)`
    ///                 → `focusMode = .continuousAutoFocus`(**1.2 s 后回连续**)
    ///
    /// 🔴 一处**有意的偏离**:生产打的是**硬中心**,我们打的是**被扫物体框**
    ///    (`applyFocusRegion`,即 B 臂那两个「生产没用的旋钮」之一)。理由:
    ///    任务书「最上游输入必须清晰 —— 目标是被扫物体清晰」;ROI 与度量用的
    ///    是同一个矩形,否则「踢一脚」和「量有没有变清晰」量的不是同一块地方。
    ///    物体框还没定(第一帧没来)时 `applyFocusRegion` 自己回落到画面中心的
    ///    同比例矩形 ⇒ 退化成与生产逐句相同。
    ///
    /// 只有 B 臂受理:
    ///   · A 臂是**阴性对照**——「对焦这件事从没发生过」是它的定义,踢它就把
    ///     对照毁了 ⇒ 返回 0(不适用),并计一次拒绝。
    ///   · C 臂自己的状态机里就有重触发(`af_scan.cpp:226-241`,libcamera
    ///     `retriggerRatio`/`retriggerDelay`),再从外面踢一脚是两个控制器抢
    ///     同一个镜头 ⇒ 同样返回 0。
    ///
    /// 返回:1 = 已下发;0 = 本臂不适用;-1 = 相机没起来;-2 = 锁设备失败。
    @discardableResult
    func nudge() -> Int32 {
        lock.lock()
        resolveArmLocked()
        let a = arm
        let d = device
        lock.unlock()

        guard a == .b else {
            lock.lock()
            nudgeRejectedNonAppleArm &+= 1
            lock.unlock()
            return 0
        }
        guard let dev = d else { return -1 }
        do {
            try dev.lockForConfiguration()
        } catch {
            appendNote("🔴 自愈 nudge:lockForConfiguration 失败 \\(error)")
            return -2
        }
        // 区域(生产是硬中心;我们是物体框,理由见上)。原文:设完区域不触发
        // 对焦,要再 setFocusMode: —— 下一句就是。
        applyFocusRegion(device: dev)
        if dev.isFocusModeSupported(.autoFocus) {
            dev.focusMode = .autoFocus
        } else if dev.isFocusModeSupported(.continuousAutoFocus) {
            dev.focusMode = .continuousAutoFocus
        }
        dev.unlockForConfiguration()

        // 🔴 1.2 s 后**必须**回连续 —— 生产 `:2189-2191` 的警告:不许把底下那台
        //    AVCaptureDevice 留在一次性/锁定档上。数字 1.2 抄生产 `:1432`。
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.kNudgeRestoreSeconds) {
            [weak self] in
            guard let self = self else { return }
            self.lock.lock()
            let back = self.device
            self.lock.unlock()
            guard let d2 = back, d2.isFocusModeSupported(.continuousAutoFocus)
            else { return }
            do { try d2.lockForConfiguration() } catch { return }
            d2.focusMode = .continuousAutoFocus
            d2.unlockForConfiguration()
            self.lock.lock()
            self.nudgeRestored &+= 1
            self.lock.unlock()
        }

        lock.lock()
        nudgeExecuted &+= 1
        nudgeLastAtSeconds = CACurrentMediaTime()
        lock.unlock()
        NSLog("[AF-SELFHEAL] one-shot nudge fired (arm=\\(a.label), roi box)")
        return 1
    }""")

# ── 计数器字段 ──────────────────────────────────────────────────────────────
rep(
"""    // ── 快门前那一次(表 A)──""",
"""    // ── 自愈那一脚(判定在 Dart,这里只记执行事实)──
    private var nudgeExecuted: Int64 = 0
    private var nudgeRestored: Int64 = 0
    private var nudgeRejectedNonAppleArm: Int64 = 0
    private var nudgeLastAtSeconds: Double = -1

    // ── 快门前那一次(表 A)──""")

rep(
"""    /// 表 A 的上限(任务书):B 臂 2 s、C 臂 3 s。
    private static let kPrepareTimeoutB: Double = 2.0
    private static let kPrepareTimeoutC: Double = 3.0""",
"""    /// 表 A 的上限(任务书):B 臂 2 s、C 臂 3 s。
    private static let kPrepareTimeoutB: Double = 2.0
    private static let kPrepareTimeoutC: Double = 3.0

    /// 自愈踢一脚之后多久回 `.continuousAutoFocus`。**抄生产**
    /// `OfficialAetherARKitPlugin.swift:1432` 的 `.now() + 1.2`。
    private static let kNudgeRestoreSeconds: Double = 1.2""")

# ── report 里记自愈执行事实 ────────────────────────────────────────────────
rep(
"""            "capabilities": capabilities,
            "notes": notes,""",
"""            "capabilities": capabilities,
            "self_heal_executor": [
                "what": "只执行不判定 —— 判定循环在 Dart(跨端同式,生产 :1418 注释原话)",
                "ported_from":
                    "OfficialAetherARKitPlugin.swift:1418-1445 focusNudge",
                "deviation_focus_region":
                    "生产打硬中心 (0.5,0.5);我们打被扫物体框(与度量 ROI 同一个矩形)",
                "restore_seconds": Self.kNudgeRestoreSeconds,
                "nudges_executed": nudgeExecuted,
                "nudges_restored_to_continuous": nudgeRestored,
                "nudges_rejected_non_apple_arm": nudgeRejectedNonAppleArm,
                "last_nudge_media_time_s": nudgeLastAtSeconds,
            ],
            "notes": notes,""")

# ── C ABI ──────────────────────────────────────────────────────────────────
rep(
"""/// 取走时间序列。`out` 至少要有 `capSamples * 6` 个 double 的空间。""",
"""/// 对焦自愈的那一脚(生产 `focusNudge` 的移植)。**判定不在这里** —— 判定循环
/// 在 Dart `lib/vio/capture/focus_self_heal.dart`(与生产
/// `ar_capture_page.dart:512-563` 同式,四端各自只实现这一个执行器)。
///
/// 返回:1 = 已下发;0 = 本臂不适用(A 阴性对照 / C 自带重触发);
///      -1 = 相机没起来;-2 = 锁设备失败。
@_cdecl("pw_camera_slot_focus_nudge")
public func pw_camera_slot_focus_nudge() -> Int32 {
    return PwFocusArms.shared.nudge()
}

/// 取走时间序列。`out` 至少要有 `capSamples * 6` 个 double 的空间。""")

io.open(p, "w", encoding="utf-8").write(s)
print("ok")
