# Full-stack visual assembler

`assemble_full_stack.py` produces the review cloud in this exact order:

1. ghost-gated replay sparse cloud, robustly Sim3-aligned into device/raw gauge;
2. pure-A B floor births;
3. pure-A B wall births;
4. D true-colour births.

The old device sparse cloud is read only to certify its identity and point count.
It is **never** copied into the output, because that would re-introduce the old
ghost layers. Every B and D PLY has an explicit `metric_replay` or `device_raw`
gauge. The former receives the same replay-to-device Sim3 as the ghost sparse;
the latter explicitly skips it. RGB bytes never change. The manifest records layer and
RGB hashes, registration counts, the four exact ghost-owner environment values, robust
Sim3 residuals, missing inputs, exact vertex offsets, and the C backend identity.

For the user-visible final review, pass `--strict-final`. It additionally
requires bound provenance for the full-set true-colour ghost-gated sparse arm,
one provenance JSON per B PLY proving a pure-A <=1cm resweep, and a newly
computed D certificate containing the SHA-256 identities of the exact ghost,
B-floor, B-wall, and D PLYs. This prevents a black replay cloud, a 5/10cm owner
selection sample, or a stale D certificate from being labelled FULL.

Strict FULL also requires non-empty G/B-floor/B-wall/D layers, >=95% non-black
true-colour coverage, a verified C backend artifact plus bound floor/wall execution
records containing the actual effective tile parameters and zero output mismatches,
a structured commercial-clean D certificate
bound to the exact native library, exact D PLY, birth count, and zero-mismatch
scheduler parity, Sim3
inlier fraction >=80% with inlier p95 <=3cm, and 100% replay registration for
cap41/50/51. cap40 can only proceed with an explicit
`pw_cap40_registration_exception_v1`; its manifest remains labelled as a
historical input exception rather than a registration pass.

Strict registration is derived from the immutable fed-frame JSONL ledger, not
from the pose CSV row count. cap41/50/51 require exact pose-ID = ledger-ID sets.
cap40 permits only the replay-proven missing set `79,80,81,82`; omitted CSV rows
and the exception certificate must agree with the ledger-derived set exactly.
Device/raw Sim3 residuals are retained in raw units and normalized by the Sim3
scale before applying the 3cm metric gate.

Strict FULL also compares the transformed ghost sparse arm against the actual
device baseline point cloud. Camera-centre agreement alone is insufficient: a
host replay may be non-rigidly different even when its poses admit a good Sim3.
The gate recomputes symmetric nearest-neighbour distances in metres and requires
a bbox-diagonal ratio in `[0.80, 1.25]`, at least 50% coverage within 3cm in both
directions, median <=10cm, and p90 <=20cm. The current cap41 host ghost transform
fails this gate (diagonal ratio 1.42856; 3cm fractions 5.07%/6.33%) and therefore
cannot be labelled device-raw or STRICT_FULL.

B certificates are not accepted from aggregate labels alone. Every retained B
birth must bind its exact float32 output XYZ/order, its source evidence JSONL
row and ZNCC value, and a unit-normal plane equation. The assembler recomputes
the retained median ZNCC and maximum plane residual from those rows and the
exact PLY. A configured `ncc_min` lower bound cannot be reported as the measured
retained-birth median.

`runs/research_candidate/cap41/all_algorithms_truecolor_device_raw.ply` is now
explicitly **rejected** after the device-baseline geometry check; its manifest is
labelled `REJECTED_GEOMETRY_MISMATCH`. It and the older
`runs/final_assembled/cap41` pose-fit attempt must not be used for final visual
review.

Run the synthetic contract tests with:

```sh
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
/opt/homebrew/bin/python3.11 -m unittest -v experiments/full_stack_visual_2026-07-16/test_assemble_full_stack.py
```
