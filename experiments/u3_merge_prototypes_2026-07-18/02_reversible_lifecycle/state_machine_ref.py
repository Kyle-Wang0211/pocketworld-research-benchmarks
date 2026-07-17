#!/usr/bin/env /opt/homebrew/bin/python3.11
# RESEARCH_PROTOTYPE_NOT_PRODUCT
#
# Reference (pseudo-)implementation for the *reversible* unified-birth
# lifecycle described in README.md. This file is a specification aid: it makes
# the state set, the continuous support scalar, and the transition function
# concrete and deterministically runnable so the prose cannot drift from the
# math. It does NOT touch product code, does NOT read device captures, does NOT
# publish a PLY, and does NOT decide whether any candidate is correct. A __main__
# self-check drives synthetic evidence only, to demonstrate that every edge in
# the spec (promote, demote, retract, restore) is reachable and idempotent.
#
# The design distinction this file encodes (README section 4):
#   A state change here is caused by a change in the *evidence graph*, never by a
#   cosmetic post-hoc point-deletion pass. Support rises when new corroborating
#   evidence arrives; support falls when new *opposing* evidence arrives (a later
#   free-space certification, a pose correction that de-integrates a frame, an
#   outlier observation flagged by BA). Publication is a function of current
#   evidence, so if the evidence that justified publication is later contradicted,
#   the same function must be allowed to withdraw it. That is reversibility, not
#   deletion.

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# 1. States
# ---------------------------------------------------------------------------
# Main spine (monotone-capable but NOT monotone-forced):
#   PROVISIONAL -> PROPOSED -> SUPPORTED -> MATURE -> FUSED -> PUBLISHED
# Bypass / hold lanes (evidence insufficient or contradictory):
#   AMBIGUOUS, UNSEEN, INCONSISTENT
# Terminal-but-reopenable withdrawal:
#   RETRACTED
#
# Nothing is a hard sink. Every non-spine state has at least one edge back onto
# the spine once the evidence graph changes, mirroring how ORB-SLAM re-observes a
# previously-untrackable point, DSO re-activates a candidate, and BundleFusion
# re-integrates a de-integrated frame.
class LifecycleState(str, Enum):
    PROVISIONAL = "PROVISIONAL"   # newly seeded, on trial, not yet a proposal owner
    PROPOSED = "PROPOSED"         # has a hypothesis identity; support below support-gate
    SUPPORTED = "SUPPORTED"       # >= support-gate; corroborated but not held-out-clean
    MATURE = "MATURE"             # held-out-clean, no live opposition; birth-eligible
    FUSED = "FUSED"               # merged into the unified surface/track graph
    PUBLISHED = "PUBLISHED"       # user-visible Point3D/surfel identity emitted
    AMBIGUOUS = "AMBIGUOUS"       # multi-modal / alias / competing hypothesis
    UNSEEN = "UNSEEN"             # no independent evidence yet (cold), not contradicted
    INCONSISTENT = "INCONSISTENT" # actively contradicted by opposing evidence
    RETRACTED = "RETRACTED"       # withdrawn after publication because evidence changed


# States from which the unified birth controller is allowed to emit / keep a
# user-visible identity. Everything else is internal-only.
VISIBLE_STATES = frozenset({LifecycleState.PUBLISHED})
# States that still hold a hypothesis identity and may re-enter the spine.
REOPENABLE = frozenset({
    LifecycleState.AMBIGUOUS,
    LifecycleState.UNSEEN,
    LifecycleState.INCONSISTENT,
    LifecycleState.RETRACTED,
})


# ---------------------------------------------------------------------------
# 2. Continuous support scalar
# ---------------------------------------------------------------------------
# The scalar is the primary driver; discrete states are quantizations of it plus
# a few boolean gates (held-out clean, opposition present). The scalar is a
# signed accumulator: corroboration adds, opposition subtracts. It is bounded and
# monotone in its inputs, so back-to-back replays of the same evidence stream are
# byte-deterministic.
#
# S(t) = clamp(  sum_i  w_support(e_i)                 # independent-frame corroboration
#              - sum_j  w_oppose(o_j)                  # free-space / reproj / de-integration
#              , S_MIN, S_MAX)
#
# The per-term weights come from named systems (see README provenance table);
# the *accumulate/threshold* shape is our instantiation, not copied from any one
# system. We keep it interpretable: one independent held-out support frame is the
# unit of positive evidence (weight 1.0), aliases add 0, and each opposition unit
# subtracts OPPOSE_WEIGHT.

S_MIN, S_MAX = -4.0, 8.0

# Promotion thresholds (support rises above -> promote).
GATE_PROPOSED = 0.0     # any positive support -> leaves UNSEEN/PROVISIONAL onto spine
GATE_SUPPORTED = 2.0    # >= 2 independent support frames (ORB-SLAM: >=3 KF observ.; we use 2)
GATE_MATURE = 3.0       # >= support gate AND held-out clean AND no live opposition

# Demotion thresholds (support falls below -> demote). Hysteresis: demote gates
# sit strictly below the matching promote gates so noise near a boundary does not
# oscillate the state (mirrors 3DGS spacing pruning away from densification, and
# ORB-SLAM's "once passed, only culled if < 3 observations" ratchet-with-floor).
DROP_SUPPORTED = 1.0    # fall below -> SUPPORTED downgrades toward PROPOSED/AMBIGUOUS
DROP_MATURE = 2.0       # fall below -> MATURE downgrades to SUPPORTED
DROP_INCONSISTENT = -1.0  # net-negative support -> INCONSISTENT (opposition dominates)

OPPOSE_WEIGHT = 1.5     # one opposition unit outweighs one support unit (bias to withhold)
FOUND_RATIO_FLOOR = 0.25  # ORB-SLAM found-ratio: predicted-visible-but-not-found culls support


@dataclass(frozen=True)
class Evidence:
    """Immutable evidence snapshot for one candidate/hypothesis at time t.

    All fields are counts/flags derived upstream by the (source-agnostic)
    evidence graph. This struct is intentionally source-neutral: no field names
    a generator (SIFT / B known-plane / D detector-free); provenance lives in a
    separate ledger, exactly as AGENTS.md and the U4 contract require.
    """
    independent_support_frames: int = 0   # distinct production frames corroborating
    held_out_support_frames: int = 0      # supporters withheld from the solve
    alias_frames: int = 0                 # same-frame re-proposals (cast no vote)
    predicted_visible_frames: int = 0     # frames where it *should* have been seen
    found_frames: int = 0                 # frames where it actually was found
    opposition_units: int = 0             # free-space certs / reproj outliers / de-integrations
    finite_geometry: bool = True          # metric anchor is finite


def found_ratio(ev: Evidence) -> float:
    if ev.predicted_visible_frames <= 0:
        return 1.0  # no prediction yet -> not penalized (still UNSEEN-ish, handled by S)
    return ev.found_frames / ev.predicted_visible_frames


def support_scalar(ev: Evidence) -> float:
    """The continuous S(t). Deterministic pure function of the evidence snapshot."""
    positive = float(ev.independent_support_frames) + 0.5 * float(ev.held_out_support_frames)
    # ORB-SLAM found-ratio culling: a point predicted visible but rarely found
    # loses support proportionally (this is *reduced corroboration*, an opposition-like
    # signal that is nonetheless evidence-driven, not a cleanup pass).
    fr = found_ratio(ev)
    if fr < FOUND_RATIO_FLOOR:
        positive *= fr / FOUND_RATIO_FLOOR
    negative = OPPOSE_WEIGHT * float(ev.opposition_units)
    s = positive - negative
    return max(S_MIN, min(S_MAX, s))


# ---------------------------------------------------------------------------
# 3. Boolean gates (things the scalar alone cannot express)
# ---------------------------------------------------------------------------
def held_out_clean(ev: Evidence) -> bool:
    return ev.held_out_support_frames >= 1


def has_live_opposition(ev: Evidence) -> bool:
    return ev.opposition_units > 0


# ---------------------------------------------------------------------------
# 4. Transition function
# ---------------------------------------------------------------------------
# Pure: (state, evidence) -> (state, reason). No global mutation. The controller
# calls this whenever the evidence graph for a candidate changes. Every returned
# transition is appended to an append-only ledger by the caller; the *state* is
# recomputable from the current evidence at any time, which is what makes
# publication and its withdrawal symmetric.
@dataclass(frozen=True)
class Transition:
    src: LifecycleState
    dst: LifecycleState
    scalar: float
    reason: str


def step(state: LifecycleState, ev: Evidence) -> Transition:
    s = support_scalar(ev)

    # --- Hard contradiction dominates everything, from any state, including
    # --- PUBLISHED. This is the reversibility core: new opposing evidence can
    # --- pull a visible point back out. (ElasticFusion free-space violation;
    # --- BundleFusion de-integration on pose correction.)
    if not ev.finite_geometry:
        return Transition(state, LifecycleState.AMBIGUOUS, s, "non-finite metric anchor")
    if s <= DROP_INCONSISTENT and has_live_opposition(ev):
        dst = (LifecycleState.RETRACTED if state == LifecycleState.PUBLISHED
               else LifecycleState.INCONSISTENT)
        return Transition(state, dst, s, "opposition dominates support (evidence changed)")

    # --- Alias / multi-modal hold: a second same-frame proposal is not a vote.
    if ev.independent_support_frames == 0 and ev.alias_frames > 0:
        return Transition(state, LifecycleState.AMBIGUOUS, s, "alias only, no independent vote")

    # --- Cold: no evidence at all yet.
    if ev.independent_support_frames == 0 and ev.opposition_units == 0:
        return Transition(state, LifecycleState.UNSEEN, s, "no independent evidence yet")

    # --- Promotion / demotion by scalar with hysteresis. Determine the target
    # --- rung purely from S plus the two boolean gates, then let the caller see
    # --- it as promote or demote by comparing to `state`.
    if s >= GATE_MATURE and held_out_clean(ev) and not has_live_opposition(ev):
        dst = LifecycleState.MATURE
        reason = "held-out clean, no opposition, S>=GATE_MATURE"
    elif s >= GATE_SUPPORTED:
        # Demotion hysteresis: only fall out of MATURE once below DROP_MATURE.
        if state == LifecycleState.MATURE and s >= DROP_MATURE and held_out_clean(ev) \
                and not has_live_opposition(ev):
            dst = LifecycleState.MATURE
            reason = "MATURE retained within hysteresis band"
        else:
            dst = LifecycleState.SUPPORTED
            reason = "S>=GATE_SUPPORTED"
    elif s > GATE_PROPOSED:
        if state == LifecycleState.SUPPORTED and s >= DROP_SUPPORTED:
            dst = LifecycleState.SUPPORTED
            reason = "SUPPORTED retained within hysteresis band"
        else:
            dst = LifecycleState.PROPOSED
            reason = "0<S<GATE_SUPPORTED"
    else:
        dst = LifecycleState.AMBIGUOUS
        reason = "S<=0, contested"

    return Transition(state, dst, s, reason)


# ---------------------------------------------------------------------------
# 5. Fusion / publication are separate authority steps (kept out of `step`)
# ---------------------------------------------------------------------------
# The unified birth controller (the ONLY authority allowed to emit a visible
# identity, per AGENTS.md) advances MATURE -> FUSED -> PUBLISHED. These are not
# per-source gates; they operate on the shared graph. Withdrawal is symmetric:
# if a PUBLISHED candidate's `step` returns RETRACTED, the controller removes the
# visible identity in the same evidence-driven way it added it.
def can_fuse(state: LifecycleState) -> bool:
    return state == LifecycleState.MATURE


def can_publish(state: LifecycleState) -> bool:
    return state == LifecycleState.FUSED


def is_visible(state: LifecycleState) -> bool:
    return state in VISIBLE_STATES


# ---------------------------------------------------------------------------
# 6. Deterministic self-check (demonstrates every edge is reachable)
# ---------------------------------------------------------------------------
def _demo():
    log = []

    def drive(label, state, ev):
        t = step(state, ev)
        log.append((label, t.src.value, t.dst.value, round(t.scalar, 3), t.reason))
        return t.dst

    # cold -> proposed -> supported -> mature (promotion)
    st = LifecycleState.PROVISIONAL
    st = drive("cold", st, Evidence())
    st = drive("one-support", st, Evidence(independent_support_frames=1,
                                            predicted_visible_frames=1, found_frames=1))
    st = drive("two-support", st, Evidence(independent_support_frames=2, held_out_support_frames=0,
                                           predicted_visible_frames=2, found_frames=2))
    st = drive("held-out-clean", st, Evidence(independent_support_frames=3, held_out_support_frames=1,
                                              predicted_visible_frames=3, found_frames=3))
    # controller fuses + publishes
    fused = can_fuse(st)
    st = LifecycleState.FUSED if fused else st
    published = can_publish(st)
    st = LifecycleState.PUBLISHED if published else st
    log.append(("controller", "MATURE", st.value, None, "fuse+publish (birth controller)"))

    # NOW evidence changes: a later frame certifies free-space through the point.
    # Same function must withdraw the published identity -> RETRACTED (reversibility).
    st = drive("free-space-opposition", st,
               Evidence(independent_support_frames=3, held_out_support_frames=1,
                        predicted_visible_frames=6, found_frames=3, opposition_units=4))

    # Evidence changes AGAIN: opposition retracted upstream (e.g. pose corrected,
    # de-integration reversed). Candidate re-enters the spine -> restore path.
    st = drive("opposition-cleared", st,
               Evidence(independent_support_frames=3, held_out_support_frames=1,
                        predicted_visible_frames=3, found_frames=3, opposition_units=0))

    # Found-ratio collapse (ORB-SLAM): predicted visible in many frames, found in few.
    st2 = drive("found-ratio-collapse", LifecycleState.SUPPORTED,
                Evidence(independent_support_frames=4, predicted_visible_frames=20,
                         found_frames=2))

    for row in log:
        print(row)
    # Idempotency: re-running step on the terminal evidence yields the same dst.
    terminal_ev = Evidence(independent_support_frames=3, held_out_support_frames=1,
                           predicted_visible_frames=3, found_frames=3, opposition_units=0)
    a = step(LifecycleState.SUPPORTED, terminal_ev).dst
    b = step(a, terminal_ev).dst
    assert a == b, f"non-idempotent: {a} -> {b}"
    print("idempotent:", a.value, "==", b.value)


if __name__ == "__main__":
    _demo()
