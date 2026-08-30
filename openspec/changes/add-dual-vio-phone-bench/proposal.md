# Proposal: unified three-arm mobile VIO replacement benchmark

Build Basalt, XRSLAM, and an ARKit production-reference arm in one iPhone bench
app over one metric, receipt, and evaluation harness. A process-wide lease makes
the selected arm immutable and exclusive for the whole run.

Basalt and XRSLAM each live in a private embedded dynamic framework so their
pinned OpenCV versions cannot collide. ARKit uses a dedicated ARSession adapter
and never enters either C++ session. The research-only app must never use the
`com.kyle.PocketWorld` bundle/container.
