# Run outputs — Basalt / XRSLAM / ARKit phone bench

Every run this experiment produced, as the app wrote it: receipts, diagnostics, telemetry, poses and
the chain logs. Until now these lived only on the bench operator's Mac
(`~/Developer/viobench-recordings`); the code that produced them was in the repo, the evidence was not.

## Layout

- `run-<uuid>/` — one benchmark run. `receipt.json` (engine, channel, state, engine sha, metrics),
  `diagnostics.json` (queue depths, drop counters, per-engine counters), `telemetry.jsonl` (1 Hz
  thermal / footprint / CPU / battery), `poses.tum`, `SHA256SUMS`, and the input manifest.
- `eval-*/` — an arm's evaluation: the run's artifacts plus the chain log and, where one was written,
  `RESULTS.md`.
- `run-*_gpufe_stats_*.json` — the GPU front end's own per-run statistics (kernel times, audit
  counters, fallbacks) pulled off the device after each run.
- `ate.py` — the trajectory error tool the chains call (Sim3 and SE3 against ARKit).

## The two reference runs

| run | what it is |
|---|---|
| `run-f3d525c9` | ARKit reference, live soak 600 s at production pixels. Every "not worse than ARKit" verdict in this experiment is computed against this run. |
| `run-5966aec0`, `run-6e2d4b99` | the device recordings every replay run is fed from |

## Raw frames stay local

The recordings' `frames.bin` are excluded, per this repo's rule that heavy artifacts stay local and are
tracked by manifest. Everything else from those runs (calibration, config, ARKit poses, the camera
index, the `.pwvi` header) is here.

| sha256 | bytes | path on the bench Mac |
|---|---|---|
| `f29cf37d0e1cd7e8e2e934899bd16d700627b226025c9ed8d6a78c1140f70ada` | 4476211200 | `~/Developer/viobench-recordings/run-5966aec0-cbf1-4abc-af0e-c1fc559da44c/frames.bin` |
| `f4d98254a08399a3135f8ea49243f846324a1c43108e61a763fb94a6388b8632` | 4705689600 | `~/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/frames.bin` |

## Reading a run

A receipt's `state` is `invalid` for most runs here and that is expected, not a failure: replaying a
device recording has no ground truth, and a live soak ends with the camera released
(`platform_camera_loss`). The gate reads the metrics, not the state. Check `eng_sha` in the receipt
against the build you meant to test before drawing any conclusion from a run — one live run was read
off the previous app before that check existed.

Basalt's two replay arms are `eval-basalt-640-unpaced` (109 fps at 640×480) and
`eval-basalt-full-unpaced` (17.2 fps at production pixels); the XRSLAM arms and the whole GPU
front-end campaign are the `eval-xrslam-*` directories, with the campaign's own log at
`../../../tools/xrslam_gpu_frontend/docs/CAMPAIGN_RESULTS.md`.
