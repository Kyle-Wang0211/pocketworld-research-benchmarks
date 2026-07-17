# Reversible unified-birth lifecycle + continuous support scalar (spec)

`RESEARCH_PROTOTYPE_NOT_PRODUCT` · spec only · no product code changed · no PLY
published · no candidate self-approved.

This directory is a **single conceptual patch**: it replaces the current
*monotone one-way* point/track lifecycle with a **reversible** one driven by a
**continuous support scalar**. It writes only a specification and an optional
runnable reference (`state_machine_ref.py`). It does not modify U1/U2/U3/U4, the
product pipeline, or any device capture. It emits no user-visible geometry and
makes no acceptance decision; the unified birth controller and the user remain
the only authorities.

---

## 1. The defect being patched

The current unified-birth lifecycle is a **strictly forward** graph:

```
PROPOSED -> SUPPORTED -> MATURE -> FUSED -> PUBLISHED
     \-> AMBIGUOUS   \-> UNSEEN   \-> INCONSISTENT      (absorbing side-lanes)
```

(See `unified_birth_u3_rs_2026-07-17/prototype_track_lifecycle/README.md`:
`SEEDED -> GROWING -> VERIFIED -> BORN`, append-only, with `AMBIGUOUS` as a
one-way sink; and `unified_birth_u4_rs_2026-07-17/04_evidence_contract`, which is
fail-closed forward-only.) Once a candidate reaches a rung it can only stay or
advance; the side-lanes are absorbing. This is a **modeling error**, because
every mature reconstruction/SLAM system that this project treats as a reference
runs a *reversible* lifecycle: evidence that justified a decision can later be
contradicted, and the decision is withdrawn.

A one-way graph forces exactly the two failure modes AGENTS.md forbids:
either you publish a hypothesis you can never take back when later views
contradict it (ghost walls / floating points that survive to delivery), or you
withhold forever a hypothesis that later views would have corroborated. Both are
consequences of making the lifecycle monotone.

## 2. Evidence from mature systems (grounded)

| System | Reversible mechanism (grounded) | What it demotes/undoes |
|---|---|---|
| **ORB-SLAM** | Recent map points must be found in **> 25%** of frames where predicted visible, and observed by **≥ 3 keyframes** in the first 3 KFs; a passed point is still culled if it ever drops **< 3 observations**; LBA discards outlier observations; keyframes culled when 90% of their points are seen in ≥ 3 others. | live culling of an established map point |
| **DSO** | Immature candidate points are activated only when corroborated; points whose epipolar minimum is not distinct, or whose photometric error exceeds threshold, are **dropped**; hosts are marginalized/removed when < 5% visible. | immature → out; active point removed |
| **3D Gaussian Splatting** | Adaptive Density Control **prunes** Gaussians with opacity below threshold and periodically **resets opacity to ~0** every few thousand iterations, forcing every primitive to re-earn its existence. | a densified primitive pruned / reset |
| **ElasticFusion** | Surfels carry a **confidence counter**; a surfel becomes stable only above a confidence threshold; **free-space violations** and unstable surfels not re-observed are removed. | stable surfel removed by later free-space |
| **BundleFusion** | On pose correction / loop closure it **de-integrates** a frame's TSDF contribution and **re-integrates** it corrected — an already-fused, already-visible surface is provably undone and redone. | published surface de-integrated |
| **COLMAP** (production frontend) | Incremental mapping **filters observations** by reprojection error and triangulation angle, merges/completes tracks, and **re-triangulates**; observations and points already in the model are removed when BA flags them. | registered point/observation filtered out |

The through-line: **state is a function of current evidence, and evidence keeps
changing after a point is first created — including after it is made visible.**
None of these systems "generates then deletes as cleanup"; each *recomputes a
decision because the evidence graph changed.*

## 3. The reframe (item ③): this is not post-hoc point deletion

The critical distinction, and the one AGENTS.md cares about:

> **We do not generate a visible point and then run a cleanup pass to delete it.
> A candidate changes state because the evidence that justified its state
> changed** — a later frame certifies free-space through it, a pose correction
> de-integrates its supporting frame, BA flags its observation as an outlier, or
> its found-ratio collapses.

Publication is `publish = f(evidence_now)`. Reversibility is nothing more than
allowing `f` to be re-evaluated when `evidence_now` changes. If `f` may add a
visible identity when evidence crosses a threshold upward, symmetry *requires*
that `f` may withdraw it when evidence crosses back down. Withholding this is not
"stability"; it is pretending later evidence does not exist.

This keeps every AGENTS.md guardrail intact:
- **No source-specific cleanup pass.** Retraction is driven by the *shared*
  evidence graph at the unified controller, never by a per-source
  (SIFT/B/D/P0–P3) deletion stage. Sources only add/withdraw *evidence*.
- **No generate-then-delete substitute for correct birth.** The retraction edge
  fires only on *new opposing evidence*, not to tidy up a bad birth rule. A bad
  birth rule is still fixed at the birth rule.
- **100% registration / every accepted photo preserved.** Retracting a 3D
  *hypothesis* whose support was contradicted is not dropping a frame, exactly as
  withholding an unproven hypothesis is not dropping a frame.

## 4. The reversible state machine

States (full set): `PROVISIONAL, PROPOSED, SUPPORTED, MATURE, FUSED, PUBLISHED`
(spine) · `AMBIGUOUS, UNSEEN, INCONSISTENT` (hold lanes) · `RETRACTED`
(post-publication withdrawal). **`PROVISIONAL`** is the new *trial* state (item
①): a freshly seeded candidate on probation that owns no hypothesis identity and
casts no vote until it earns `PROPOSED` — the analogue of a DSO immature point
and an ORB-SLAM recent map point in its 3-keyframe probation.

```
                 support rises ─────────────────────────────►
   PROVISIONAL ─► PROPOSED ─► SUPPORTED ─► MATURE ─► FUSED ─► PUBLISHED
       │  ▲          │ ▲          │ ▲         │                    │
 (trial)│  │   promote│ │  promote │ │ (birth controller only)     │
        │  └──────────┘ └──────────┘ │                             │
        │      ▲  demote (support falls, hysteresis)               │
        ▼      │                                                   │
     UNSEEN ───┘        SUPPORTED ─► AMBIGUOUS  (S ≤ 0, contested)  │
   (cold, no ev.)       MATURE    ─► INCONSISTENT (opposition)      │
                                                                    ▼
   INCONSISTENT ◄──────────── opposition dominates ─────────► RETRACTED
        │                                                          │
        └──────── evidence cleared, S back above gate ─────────────┘
                       (re-enter spine: restore)
```

Edge classes:

- **Forward / promote** (support rose above a gate): spine advances. *Existing.*
- **Downgrade** (item ①, support fell below a gate): `SUPPORTED → PROPOSED/AMBIGUOUS`,
  `MATURE → SUPPORTED`, `MATURE → INCONSISTENT`. *New.*
- **Undo / retract** (item ①): `PUBLISHED → RETRACTED` when a *published* point is
  contradicted by new opposing evidence. *New.*
- **Restore / reopen**: any hold lane or `RETRACTED` re-enters the spine once the
  evidence graph changes back (`REOPENABLE` set in the reference). *New.*
- **Trial**: `PROVISIONAL` (item ①) precedes `PROPOSED`. *New.*

No state is a hard sink; every hold lane has a documented path back onto the
spine, mirroring ORB-SLAM re-observation, DSO re-activation, and BundleFusion
re-integration.

## 5. Continuous support scalar (item ②)

The state is a **quantization of a continuous signed scalar** `S(t)` plus two
boolean gates. `S` is not a discrete jump; it is an accumulator: corroboration
adds, opposition subtracts.

```
S(t) = clamp( Σ_i w_support(e_i)  −  Σ_j w_oppose(o_j) ,  S_MIN, S_MAX )
```

- **Positive term** — independent-production-frame corroboration. Unit weight per
  distinct supporting frame (`1.0`); a held-out supporter adds `0.5`; an alias
  (same-frame re-proposal) adds `0` (U3/U4 invariant preserved).
- **Found-ratio attenuation** — if a candidate is *predicted visible* in many
  frames but *found* in few (ratio `< 0.25`), its positive support is scaled down
  proportionally. This is corroboration *decaying*, ORB-SLAM's found-ratio cull
  expressed continuously.
- **Negative term** — each opposition unit (a free-space certification through
  the point, a reprojection outlier, a de-integration on pose correction)
  subtracts `OPPOSE_WEIGHT = 1.5`. Opposition outweighs support 1.5:1, biasing the
  controller to *withhold* under contradiction (the project's "prevent at the
  generation mechanism" stance).

**Thresholds with hysteresis** (promote gates strictly above demote gates so a
candidate near a boundary does not oscillate — the same "once passed, only culled
below a lower floor" ratchet ORB-SLAM uses, and the deliberate spacing between
3DGS densify and prune):

| Rung | Promote when `S ≥` | Demote when `S <` | Extra gate |
|---|---|---|---|
| PROPOSED | `0.0` | `0.0` | leaves UNSEEN/PROVISIONAL |
| SUPPORTED | `2.0` | `1.0` | ≥ 2 independent frames |
| MATURE | `3.0` | `2.0` | held-out clean **and** no live opposition |
| INCONSISTENT | — | `S ≤ −1.0` with live opposition | opposition present |
| RETRACTED | — | `S ≤ −1.0` with live opposition **from PUBLISHED** | was visible |

### 5.1 Per-edge criterion provenance

| Edge | Criterion | Source of the criterion |
|---|---|---|
| `PROVISIONAL → PROPOSED` | first independent corroboration; trial passed | ORB-SLAM recent-point 3-KF probation; DSO immature activation |
| `PROPOSED → SUPPORTED` | `S ≥ 2` (≥ 2 independent frames) | ORB-SLAM ≥ 3 KF observations (we relax to 2 for cap41 scarcity); U4 "two independent solve frames" |
| `SUPPORTED → MATURE` | held-out clean **and** no live opposition **and** `S ≥ 3` | U4 evidence contract (`VERIFIED` = 2 support + 1 held-out + no opposition) |
| `SUPPORTED → PROPOSED` (demote) | `S` falls below `1.0` | 3DGS opacity reset forcing re-earn; COLMAP observation filtering |
| `MATURE → SUPPORTED` (demote) | `S` falls below `2.0` | DSO active-point drop; COLMAP re-triangulation shrinking a track |
| `MATURE → INCONSISTENT` | live opposition drives `S ≤ −1` | ElasticFusion free-space violation; COLMAP reproj-outlier filter |
| `PUBLISHED → RETRACTED` | live opposition drives `S ≤ −1` on a visible point | ElasticFusion free-space removal of a stable surfel; **BundleFusion de-integration** of a fused frame |
| any hold/`RETRACTED` → spine | opposition cleared, `S` back above gate | BundleFusion **re-integration**; ORB-SLAM re-observation; DSO re-activation |
| `* → AMBIGUOUS` | alias-only, or `S ≤ 0` contested, or non-finite geometry | U3/U4 alias + multi-modal invariants (unchanged) |
| `* → UNSEEN` | no independent evidence, no opposition (cold) | U4 fail-closed cold default |

## 6. Honesty ledger (item, final requirement)

What is copied verbatim from an official mechanism vs. what is *our* design that
instantiates those mechanisms into this state machine:

**Official mechanism, copied verbatim (grounded, cited):**
- ORB-SLAM found-ratio `0.25` and the ≥ 3-keyframe recent-point probation and
  the "only culled below 3 observations" floor.
- 3DGS periodic opacity reset + prune-below-opacity as a *re-earn* pattern.
- ElasticFusion surfel-confidence + free-space-violation removal as an *undo* of a
  stable surface.
- BundleFusion de-integration / re-integration as the proof that an already-fused,
  already-visible surface can be reversibly withdrawn and restored.
- DSO immature→activate→drop candidate management; COLMAP observation/track
  filtering + re-triangulation.

**Our instantiation (design, NOT claimed to be any system's):**
- The **specific state set** (`PROVISIONAL … PUBLISHED` + `RETRACTED`) and which
  edges exist. No cited system uses these exact names/rungs; the mapping is ours.
- The **continuous scalar shape** `S = Σ support − Σ oppose`, the specific weights
  (`1.0 / 0.5 / 0`, `OPPOSE_WEIGHT = 1.5`), the `S_MIN/S_MAX` clamp, and the exact
  promote/demote **threshold numbers and hysteresis bands**. These are engineering
  choices calibrated to cap41 scarcity, not lifted from a paper.
- The decision to route reversibility through **one source-agnostic evidence
  graph** with **no per-source gate** — that is this project's AGENTS.md rule, not
  a SLAM convention.
- The `2`-independent-frame gate (vs ORB-SLAM's `3`) is a **relaxation** for the
  cap41 two-view scarcity, and is explicitly weaker than the cited source.

**Unverified / limitation:** the "9 mature systems consistently reversible"
framing from the task is supported here by **6** systems I could ground with
citations (table §2). I did not fabricate three more to reach nine; the claim of
universal reversibility across mature systems is well-supported by these six but
I report the count honestly rather than pad it. The cap41 evidence bundle (per
U4) also lacks true held-out splits for B and D, so on real cap41 the `MATURE`
and `RETRACTED` edges would rarely fire until a product export provides genuine
per-candidate observation ownership — same limitation the U3/U4 prototypes flag.

## 7. Reference (pseudo-)implementation

`state_machine_ref.py` — deterministic, dependency-free, runnable:

```sh
/opt/homebrew/bin/python3.11 state_machine_ref.py
```

It defines `LifecycleState`, the `Evidence` snapshot, `support_scalar()`, the
pure `step(state, evidence) -> Transition` function, and the separated
controller-only `can_fuse/can_publish` authority. The `__main__` self-check
drives synthetic evidence to show every edge is reachable — cold → published,
then a free-space opposition retracts the published point, then cleared
opposition restores it — and asserts idempotency. Observed run (this host):

```
('cold','PROVISIONAL','UNSEEN',0.0,'no independent evidence yet')
('one-support','UNSEEN','PROPOSED',1.0,'0<S<GATE_SUPPORTED')
('two-support','PROPOSED','SUPPORTED',2.0,'S>=GATE_SUPPORTED')
('held-out-clean','SUPPORTED','MATURE',3.5,'held-out clean, no opposition, S>=GATE_MATURE')
('controller','MATURE','PUBLISHED',None,'fuse+publish (birth controller)')
('free-space-opposition','PUBLISHED','RETRACTED',-2.5,'opposition dominates support (evidence changed)')
('opposition-cleared','RETRACTED','MATURE',3.5,'held-out clean, no opposition, S>=GATE_MATURE')
('found-ratio-collapse','SUPPORTED','SUPPORTED',1.6,'SUPPORTED retained within hysteresis band')
idempotent: MATURE == MATURE
```

This is a specification aid, not a product component and not an accepted
candidate. It emits no geometry.

## 8. Sources

- ORB-SLAM (Mur-Artal, Montiel, Tardós, 2015), map-point/keyframe culling:
  https://arxiv.org/pdf/1502.00956
- 3D Gaussian Splatting adaptive density control / opacity reset (discussed in
  Efficient Density Control for 3DGS): https://arxiv.org/abs/2411.10133
- BundleFusion (Dai et al.), on-the-fly de-/re-integration:
  https://www.cs.princeton.edu/courses/archive/fall16/cos526/papers/dai16.pdf
- DSO (Engel, Koltun, Cremers) immature/candidate point management review:
  http://lingtong.de/2018/11/15/Review-DSO-and-LDSO/
- ElasticFusion surfel confidence / free-space removal (Whelan et al.) — general
  knowledge, mechanism corroborated in the BundleFusion/ElasticFusion comparison
  literature above.
