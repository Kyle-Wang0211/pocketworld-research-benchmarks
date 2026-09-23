import io, sys
p = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/prod-af-20260923/ios/Runner/PwCameraSlot.swift"
s = io.open(p, encoding="utf-8").read()
old = """            // 🔴 **锁镜头**。上游 `ViewController.swift:256` 是
            //    `camera.setFocus(0.835)` → `setFocusModeLocked(lensPosition:)`。
            //    为什么是承重的:整条管线的内参 `frame->K` 来自 yaml
            //    (`detail.cpp:107`),**没有任何一处按实际图像重算**。而连续
            //    自动对焦会让 fx 全程游走 —— 我们自己实测过一场 1280.37–1385.30、
            //    跨度 7.7%、1429 个唯一值。镜头不锁 = 拿一个定值内参去解一台
            //    焦距在变的相机。
            //    [lensPosition] < 0 表示"不锁"(保留给需要对比的实验)。
            //
            // 🔴 [pw 2026-09-23 对焦三臂] 下面这三行**一个字节没动**,只在 if
            //    的条件上多加了 `&& focusArm == .a`。A 臂 = 默认臂 ⇒ 不传
            //    `-PWFocusArm` 时条件与改之前完全相同,行为逐字节不变。
            //    B/C 臂不走这一段,走 `PwFocusArms.configureAtStart`(见下),
            //    各自的做法与 Apple 头文件引文都在 PwFocusArms.swift 里。
            let focusArm = PwFocusArms.shared.currentArm()
            if lensPosition >= 0 && focusArm == .a {"""
new = """            // 🔴🔴 [pw 2026-09-23 用户拍板「换掉锁定,照生产那套来」]
            //    **下面这段锁焦不再是默认路径**。默认臂已从 A 换成 B
            //    (生产同款苹果 AF,见 `PwFocusArms.swift` 的 `arm = .b`)⇒
            //    不传 `-PWFocusArm` 时下面这个 `if` 条件**不成立**,一行都不跑。
            //
            //    为什么非换不可 —— 生产 `OfficialAetherARKitPlugin.swift:2189-2191`
            //    的注释原文(血的教训,逐字抄在这里):
            //
            //      "Let ARKit drive continuous autofocus. Important: do not
            //       later flip the underlying AVCaptureDevice into one-shot
            //       focus/locked focus; that can leave the preview stuck at a
            //       near lens distance after the user moves."
            //
            //    而下面这一句 `setFocusModeLocked` **正是**那句话点名禁止的动作;
            //    用户实测本机 `minimumFocusDistance = 200 mm`,锁在 0.835(0=最近
            //    1=最远 ⇒ 0.835 几乎锁在远端)拍 10–30 cm 的小物体,成片必糊。
            //
            //    代码**一个字节没删**:它是**阴性对照臂** —— 「对焦这件事从没
            //    发生过」的基线。要它就显式 `-PWFocusArm a`。
            //
            // ── 原来的理由存档(仍然是真的,只是被「先要清晰」压过)──────────
            //    上游 `ViewController.swift:256` 是 `camera.setFocus(0.835)` →
            //    `setFocusModeLocked(lensPosition:)`。整条管线的内参 `frame->K`
            //    来自 yaml(`detail.cpp:107`),**没有任何一处按实际图像重算**;
            //    连续自动对焦会让 fx 全程游走 —— 实测一场 1280.37–1385.30、
            //    跨度 7.7%、1429 个唯一值。镜头不锁 = 拿一个定值内参去解一台
            //    焦距在变的相机。🔴 换成连续 AF 之后这笔账没有消失,只是搬了家:
            //    逐帧 K 那条路(`reference_adaptive_focus_vio_survey_20260922`:
            //    平台逐帧供 K、引擎逐帧消费)是它的正解,尚未接。**本刀不解决它**,
            //    但用户原则在前:「最上游输入必须清晰;模糊的素材后面就完了」。
            //    [lensPosition] < 0 表示"不锁"(保留给需要对比的实验)。
            let focusArm = PwFocusArms.shared.currentArm()
            if lensPosition >= 0 && focusArm == .a {"""
if old not in s: sys.exit("NOT FOUND")
s = s.replace(old, new)

old2 = """            //    三臂都调:A 臂只读能力位与建度量 context,不碰任何设备设置。"""
new2 = """            //    三臂都调:A 臂(阴性对照)只读能力位与建度量 context,不碰任何
            //    设备设置;**默认的 B 臂就是在这里装上生产同款的连续 AF**
            //    (`isSmoothAutoFocusEnabled` + `.continuousAutoFocus`,逐句对照
            //    `OfficialAetherARKitPlugin.swift:2653-2661`)。"""
if old2 not in s: sys.exit("NOT FOUND 2")
s = s.replace(old2, new2)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
