# Proposal: unified three-arm mobile VIO replacement benchmark

Build Basalt, XRSLAM, and an ARKit production-reference arm in one iPhone bench
app over one metric, receipt, and evaluation harness. A process-wide lease makes
the selected arm immutable and exclusive for the whole run.

Basalt and XRSLAM each live in a private embedded dynamic framework so their
pinned OpenCV versions cannot collide. ARKit uses a dedicated ARSession adapter
and never enters either C++ session. The research-only app must never use the
`com.kyle.PocketWorld` bundle/container.

## Amendment v2 — 2026-08-30 (user decision)

Schema v1 scored Basalt/XRSLAM at 640x480 against an ARKit arm at 1920x1440, and
asked the operator to hand-hold three separate 300 s soaks.

Both are withdrawn.

**Production already runs ARKit at 1920x1440 on this device.** That is the
requirement, not a cost to negotiate; a 640x480 candidate declared faster or
cooler than a 1920x1440 ARKit is a false comparison. All three arms now score at
1920x1440. 640x480 survives only as a non-scoring diagnostic, to separate "the
algorithm cannot carry 9x the pixels" from "we ported its pixel-unit parameters
wrong".

**Three hand-held soaks were never an A/B.** They cannot share speed, angle,
lighting or time. iOS grants the rear camera to one session, so ARSession and
AVCaptureSession cannot coexist — but once every arm wants 1920x1440, the shared
input can simply be ARKit's own frames. One capture runs the ARKit arm live while
persisting `ARFrame.capturedImage` and CoreMotion; the candidates replay those
exact frames. One capture, byte-identical input, and every later iteration
replays at zero further capture cost.

The replacement bar rises from *not worse than* ARKit to **strictly better on
accuracy**, with resources held at *not worse* — running cooler is not a product
goal. Live camera preview becomes mandatory: an operator who cannot see the
viewfinder cannot execute a real capture trajectory.
