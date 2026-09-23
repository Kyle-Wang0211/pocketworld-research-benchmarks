import io, sys
p = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/prod-af-20260923/lib/vio/render/zero_arkit_capture_probe_page.dart"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    if old not in s: sys.exit("NOT FOUND:\n"+old[:300])
    if s.count(old) != 1: sys.exit("NOT UNIQUE (%d)" % s.count(old))
    s = s.replace(old, new)

rep("""    final PwFocusState? f = _focusState;
    // C 臂的 armState 是 PwAfState;A/B 臂是「是否在调焦」。分开显示,不混。""",
"""    final PwFocusState? f = _focusState;
    final FocusSelfHeal? heal = _selfHeal;
    final int nowMs = DateTime.now().millisecondsSinceEpoch;
    // C 臂的 armState 是 PwAfState;A/B 臂是「是否在调焦」。分开显示,不混。""")

rep("""      if (f != null)
        '快门对焦 ${f.prepareState.label} ${f.prepareElapsedMs.toStringAsFixed(0)}ms'
            ' · 流水 ${_focusSeries.length}+${f.seriesPending}'
            '${f.seriesDropped > 0 ? ' 🔴丢${f.seriesDropped}' : ''}'
            ' · ROI ${f.roiWidth}x${f.roiHeight}@${f.roiX},${f.roiY}',""",
"""      if (f != null)
        '快门对焦 ${f.prepareState.label} ${f.prepareElapsedMs.toStringAsFixed(0)}ms'
            ' · 流水 ${_focusSeries.length}+${f.seriesPending}'
            '${f.seriesDropped > 0 ? ' 🔴丢${f.seriesDropped}' : ''}'
            ' · ROI ${f.roiWidth}x${f.roiHeight}@${f.roiX},${f.roiY}',
      // ── 自愈环(判定在 Dart,原生只执行一脚)──────────────────────────
      if (heal != null)
        '自愈 踢${heal.nudgeCount}次(受理${heal.dispatchedCount})'
            ' · 距上次 ${heal.msSinceLastNudge(nowMs) == null
                ? '从没踢过'
                : '${heal.msSinceLastNudge(nowMs)}ms'}'
            ' · 持续糊 ${heal.blurHeldMs(nowMs)}ms/${FocusSelfHeal.kBlurHoldMs}',
      if (heal != null)
        '自愈判据 糊=${heal.lastBlurred} 静止=${heal.lastStationary}'
            ' · 度量 ${heal.lastMeasure.toStringAsFixed(1)}'
            ' vs 参考 ${heal.sceneReference.toStringAsFixed(1)}'
            ' × ${FocusSelfHeal.kRetriggerRatio}'
            ' = ${(heal.sceneReference * FocusSelfHeal.kRetriggerRatio).toStringAsFixed(1)}',""")

io.open(p, "w", encoding="utf-8").write(s)
print("ok part3")
