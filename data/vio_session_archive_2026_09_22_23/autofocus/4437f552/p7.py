import io, sys
p = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/prod-af-20260923/lib/vio/render/zero_arkit_capture_probe_page.dart"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    if old not in s: sys.exit("NOT FOUND:\n"+old[:300])
    if s.count(old) != 1: sys.exit("NOT UNIQUE (%d)" % s.count(old))
    s = s.replace(old, new)

# ── 状态字段 ──
rep("""  // ── 对焦三臂 ────────────────────────────────────────────────────────────
  /// 整场的逐帧对焦流水(验收表 B)。每秒从原生取空一次,写 manifest 时再降采样。
  final List<PwFocusSample> _focusSeries = <PwFocusSample>[];
  Timer? _focusDrainTimer;
  PwFocusState? _focusState;
  PwFocusArm? _focusArm;""",
"""  // ── 对焦 ────────────────────────────────────────────────────────────────
  /// 整场的逐帧对焦流水(验收表 B)。每秒从原生取空一次,写 manifest 时再降采样。
  final List<PwFocusSample> _focusSeries = <PwFocusSample>[];
  Timer? _focusDrainTimer;
  PwFocusState? _focusState;
  PwFocusArm? _focusArm;

  /// 🔴 对焦自愈环。判定全在这一份纯 Dart 里(跨端同式,移植自生产
  /// `ar_capture_page.dart:512-563`),原生只执行一脚。`_boot()` 里按「符号
  /// 在不在」装真执行器还是 noop —— 符号不在时它照样跑判定、照样记事件,
  /// 只是 `dispatched=false`,这样 manifest 里能看出「判了但没人执行」。
  FocusSelfHeal? _selfHeal;""")

# ── _boot 里建 ──
rep("""    _focusArm = PwFocus.currentArm();
    _log('对焦臂 ${_focusArm?.describe ?? '🔴 pw_camera_slot_focus_* 符号不在'}'
        ' available=${PwFocus.available}');""",
"""    _focusArm = PwFocus.currentArm();
    _log('对焦臂 ${_focusArm?.describe ?? '🔴 pw_camera_slot_focus_* 符号不在'}'
        ' available=${PwFocus.available}');
    // 🔴 自愈环:判定这一份四端共用,执行器按端注入。符号不在就装 noop ——
    //    判定照跑、事件照记(dispatched=false),别把「判据没跑」和「执行器
    //    不在」混成一件事。
    _selfHeal = FocusSelfHeal(
      nudger: PwFocus.available
          ? const PwFocusFfiNudger()
          : const NoopFocusNudger(
              '🔴 pw_camera_slot_focus_nudge 符号不在 ⇒ 只判不踢'),
    );""")

# ── _onPose 喂判定 ──
rep("""    if (_poseFrames % kZeroArkitProbeLogEveryFrames == 0) {""",
"""    // ── 🔴 对焦自愈环:每帧位姿喂一次(与生产同构 —— 生产也是在位姿流里
    //    调 `_afSelfHealCheck(p)`,`ar_capture_page.dart` 的位姿回调)。
    //    度量从原生现读一次(16 个 double,一次 NSLock,30–60 Hz 可忽略);
    //    **不用 1 Hz 的 `_drainFocus` 那份快照** —— 判「持续糊 1.8 s」要的是
    //    样本密度,1 Hz 只给 ~2 个样本,一帧噪声就能翻盘。
    //    快门期间不喂:那一段镜头正被 `prepareBegin` 的一次性对焦驱动,
    //    自愈再踢一脚就是两个控制器抢同一个镜头。
    _feedFocusSelfHeal(pose);

    if (_poseFrames % kZeroArkitProbeLogEveryFrames == 0) {""")

rep("""  int get _savedCount => _shots.where((ZeroArkitProbeShot s) => s.saved).length;""",
"""  /// 喂一帧给自愈环。见 `_onPose` 里的注释。
  void _feedFocusSelfHeal(ARPose pose) {
    final FocusSelfHeal? heal = _selfHeal;
    if (heal == null || _shutterBusy || _finished) return;
    final PwFocusState? fs = PwFocus.state();
    if (fs == null) return;
    _focusState = fs;
    final int nowMs = DateTime.now().millisecondsSinceEpoch;
    final bool fired = heal.onSample(
      nowMs: nowMs,
      focusMeasure: fs.focusMeasure,
      isAdjustingFocus: fs.isAdjustingFocus,
      position: pose.position,
      orientation: pose.orientation,
    );
    if (!fired) return;
    final FocusNudgeEvent ev = heal.events.last;
    _log('af-selfheal: nudge #${ev.index} fired '
        'fm=${ev.measureAtTrigger.toStringAsFixed(1)} '
        'ref=${ev.referenceAtTrigger.toStringAsFixed(1)} '
        '(ratio=${(ev.referenceAtTrigger > 0 ? ev.measureAtTrigger / ev.referenceAtTrigger : 0).toStringAsFixed(3)}'
        ' < ${FocusSelfHeal.kRetriggerRatio}) '
        '持续糊=${ev.blurHeldMs}ms 受理=${ev.dispatched}'
        ' rc=${PwFocusFfiNudger.lastReturnCode}');
  }

  int get _savedCount => _shots.where((ZeroArkitProbeShot s) => s.saved).length;""")

# ── _finish:日志 + manifest 参数 ──
rep("""        focusNativeReportJson: focusReport,
        focusSeries: _focusSeries,
      );""",
"""        focusNativeReportJson: focusReport,
        focusSeries: _focusSeries,
        focusSelfHeal: _selfHeal,
      );""")

rep("""    _log('对焦收尾:臂=${_focusState?.arm?.label ?? '?'} '
        '流水=${_focusSeries.length} 条 '
        '(降采样后 ${downsampleFocusSeries(_focusSeries).length} 条)'
        ' 丢=${_focusState?.seriesDropped ?? 0}');""",
"""    _log('对焦收尾:臂=${_focusState?.arm?.label ?? '?'} '
        '流水=${_focusSeries.length} 条 '
        '(降采样后 ${downsampleFocusSeries(_focusSeries).length} 条)'
        ' 丢=${_focusState?.seriesDropped ?? 0}');
    final FocusSelfHeal? heal = _selfHeal;
    if (heal != null) {
      _log('自愈环收尾:喂样 ${heal.toJson()['samples_fed']} '
          '踢 ${heal.nudgeCount} 次(受理 ${heal.dispatchedCount})'
          ' 参考值=${heal.sceneReference.toStringAsFixed(1)}'
          ' 见过落定=${heal.toJson()['saw_focus_settle']}');
    }""")

io.open(p, "w", encoding="utf-8").write(s)
print("ok part2")
