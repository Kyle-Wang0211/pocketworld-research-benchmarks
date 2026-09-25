#!/usr/bin/env python3
"""Analyse one lod_<tag>.json from the LOD bench (pw_lod_bench.cpp).

Implements the verdict rules pre-registered in LOD_DEVICE_PLAN_20260923.md §5.
Every threshold used below is quoted from that file; do not tune them after
seeing device data.

usage: analyze_lod.py lod_<tag>.json [--json out.json]
"""
import json
import statistics as st
import sys

TARGET = 1000.0 / 30.0
WARM_IN = 30            # first frames of every block = in-block cold start, reported apart
IO_FRAME_MS = 8.0       # a load > 1/4 frame counts as an I/O hitch
SEGS = [("hold_overview", 0.00, 0.10), ("push_in", 0.10, 0.30), ("hold_leaf", 0.30, 0.40),
        ("pull_out", 0.40, 0.48), ("orbit", 0.48, 0.73), ("to_pan", 0.73, 0.78),
        ("pan", 0.78, 0.93), ("back_to_overview", 0.93, 1.00)]


def q(v, f):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, round(f * (len(v) - 1))))] if v else float("nan")


def seg_frames(n, a, b):
    return [i for i in range(n) if a <= i / n < b]


def time_to_full(b, idx):
    """Frames/ms from segment start until what is drawn stops changing: points
    drawn stay within +-1% of the end-of-segment value AND nothing more is
    uploaded, for the rest of the (static) segment. (px alone is not usable:
    once the budget binds the controller keeps lowering px with no effect.)"""
    if not idx:
        return None
    pts, up, wall = b["pts"], b["uploads_f"], b["wall_ms"]
    pf = pts[idx[-1]]
    ok = lambda k: abs(pts[k] - pf) <= 0.01 * max(pf, 1) and up[k] == 0
    first = None
    for k in reversed(idx):
        if ok(k):
            first = k
        else:
            break
    if first is None:
        return {"frames": None, "ms": None, "reached": False, "pts_final": pf}
    ms = sum(max(wall[k], TARGET) for k in idx if k < first)   # paced: a frame lasts >= 33.3 ms
    return {"frames": first - idx[0], "ms": round(ms, 1), "reached": True, "pts_final": pf,
            "px_final": round(b["px"][idx[-1]], 2)}


def block_summary(b):
    n = len(b["wall_ms"])
    rng = range(WARM_IN, n) if b["label"] != "COLD" else range(n)
    w = [b["wall_ms"][i] for i in rng]
    g = [b["gpu_ms"][i] for i in rng if b["gpu_ms"][i] > 0]
    ld = [b["load_ms"][i] for i in rng]
    io_miss = sum(1 for i in rng if b["wall_ms"][i] > TARGET and
                  (b["load_ms"][i] + b["upload_ms"][i]) > 0.5 * b["wall_ms"][i])
    # A miss is "I/O-removable" if the frame would have met 33.3 ms without its
    # in-frame load+upload time. (The >half rule above undercounts: on the Mac
    # 36M sync run I/O pushed 191 frames over the line and dominated only 2.)
    io_removable = sum(1 for i in rng if b["wall_ms"][i] > TARGET and
                       b["wall_ms"][i] - (b["load_ms"][i] + b["upload_ms"][i]) <= TARGET)
    io_ms = [b["load_ms"][i] + b["upload_ms"][i] for i in rng]
    s = {
        "label": b["label"], "round": b["round"], "order": b["order"], "frames": n,
        "wall_p50": q(w, .5), "wall_p95": q(w, .95), "wall_p99": q(w, .99), "wall_max": max(w),
        "frac_over_33": sum(x > TARGET for x in w) / len(w),
        "frac_over_50": sum(x > 50 for x in w) / len(w),
        "gpu_p50": q(g, .5) if g else None, "gpu_p95": q(g, .95) if g else None,
        "pts_mean": st.mean(b["pts"][i] for i in rng),
        "px_median": q([b["px"][i] for i in rng], .5), "px_max": max(b["px"][i] for i in rng),
        "io_hitch_frames": sum(x > IO_FRAME_MS for x in ld), "load_max": max(ld),
        "io_caused_misses": io_miss,
        "io_removable_misses": io_removable,
        "io_ms_p95": q(io_ms, .95), "io_ms_p99": q(io_ms, .99), "io_ms_max": max(io_ms),
        "bytes_read": sum(b["bytes_read"]),
        "first_frame_ms": b["wall_ms"][0], "first_frame_load_ms": b["load_ms"][0],
        "first_frame_bytes": b["bytes_read"][0],
        "dropped": sum(b["dropped"]), "truncated": sum(b.get("truncated", [0])),
        "thermal_max": max(b["thermal"]) if b["thermal"] else -1,
        "footprint_max_mb": max(b["footprint_mb"]) if b["footprint_mb"] else -1,
        "end_cache": b["end_cache"],
        "mode": b.get("mode", "sync"), "psize": b.get("psize", 0),
    }
    if "pending_pts" in b:
        pp = [b["pending_pts"][i] for i in rng]
        dr = [b["pts"][i] for i in rng]
        s["pending_frac_mean"] = st.mean(p / (p + d) if (p + d) else 0.0 for p, d in zip(pp, dr))
        s["frames_with_pending"] = sum(1 for p in pp if p > 0) / len(pp)
        s["in_flight_max"] = max(b["in_flight"][i] for i in rng)
        s["uploads_per_frame_max"] = max(b["uploads_f"][i] for i in rng)
    if b["label"] != "COLD":
        segs = {}
        for name, a, c in SEGS:
            idx = seg_frames(n, a, c)
            segs[name] = {"pts_mean": round(st.mean(b["pts"][i] for i in idx)),
                          "px_median": round(q([b["px"][i] for i in idx], .5), 2),
                          "max_level": max(b["max_level"][i] for i in idx),
                          "wall_p95": round(q([b["wall_ms"][i] for i in idx], .95), 2),
                          "frac_over_33": round(sum(b["wall_ms"][i] > TARGET for i in idx) / len(idx), 4)}
        s["segments"] = segs
        s["ttf_hold_overview"] = time_to_full(b, seg_frames(n, 0.0, 0.10))
        s["ttf_hold_leaf"] = time_to_full(b, seg_frames(n, 0.30, 0.40))
        hl = seg_frames(n, 0.30, 0.40)
        s["leaf_selected_frac"] = sum(b["target_selected"][i] for i in hl) / len(hl)
        s["leaf_drawn_frac"] = sum(b["target_drawn"][i] for i in hl) / len(hl)
    else:
        s["ttf_cold"] = time_to_full(b, list(range(n)))
    return s


def verdict(d, blocks, gates, labels):
    """§5.2 of the plan. `labels`: ("C","C2") = repeat flight, ("FIRST",) = first flight."""
    pooled = []
    for b in d["blocks"]:
        if b["label"] in labels:
            pooled += b["wall_ms"][WARM_IN:]
    if not pooled:
        return None
    thermal_c = max((b["thermal_max"] for b in blocks if b["label"] in labels), default=-1)
    px_med_c = q([x for b in d["blocks"] if b["label"] in labels for x in b["px"][WARM_IN:]], .5)
    v = {
        "p95_le_33": q(pooled, .95) <= TARGET,
        "frac_over_33_le_5pct": sum(x > TARGET for x in pooled) / len(pooled) <= 0.05,
        "p99_le_50": q(pooled, .99) <= 50.0,
        "max_le_100": max(pooled) <= 100.0,
        "thermal_below_serious": thermal_c < 2,
        "not_by_drawing_nothing": px_med_c < 4000.0,
    }
    v["values"] = {"p95": q(pooled, .95), "p99": q(pooled, .99), "max": max(pooled),
                   "frac_over_33": sum(x > TARGET for x in pooled) / len(pooled),
                   "thermal_max": thermal_c, "px_median": px_med_c, "n_frames": len(pooled)}
    valid = all(gates.values())
    stable = all(v[k] for k in v if k != "values")
    return {"labels": list(labels), "valid_run": valid, "stable": stable if valid else None, "checks": v}


def main():
    d = json.load(open(sys.argv[1]))
    out = {"tag": d["tag"], "adapter": d["adapter"], "octree": d["octree"], "config": d["config"]}
    gates = {}
    gates["wgpu_errors_empty"] = d.get("wgpu_errors", "") == ""
    pc = d.get("positive_control")
    gates["positive_control_ok"] = bool(pc) and 0.35 <= pc["gpu_ratio"] <= 0.70
    blocks = [block_summary(b) for b in d["blocks"]]
    gates["no_dropped_nodes"] = all(b["dropped"] == 0 for b in blocks)
    gates["no_truncation"] = all(b["truncated"] == 0 for b in blocks)
    gates["no_critical_thermal"] = all(b["thermal_max"] < 3 for b in blocks)
    out["gates"] = gates
    out["positive_control"] = pc
    out["blocks"] = blocks

    # paired, per round
    rounds = sorted({b["round"] for b in blocks if b["round"] >= 0})
    pairs = []
    for r in rounds:
        by = {b["label"]: b for b in blocks if b["round"] == r}
        row = {"round": r}
        for a, c in (("C2", "C"), ("F", "C"), ("S2", "S"), ("A2", "A"), ("A", "S"), ("AP", "A")):
            if a in by and c in by:
                for k in ("wall_p50", "wall_p95", "wall_p99", "pts_mean"):
                    row[f"{a}/{c}_{k}"] = by[a][k] / by[c][k] if by[c][k] else float("nan")
                row[f"{a}-{c}_frac_over_33"] = by[a]["frac_over_33"] - by[c]["frac_over_33"]
                row[f"{a}-{c}_io_caused_misses"] = by[a]["io_caused_misses"] - by[c]["io_caused_misses"]
                row[f"{a}-{c}_io_removable_misses"] = by[a]["io_removable_misses"] - by[c]["io_removable_misses"]
        pairs.append(row)
    out["paired"] = pairs
    out["noise_floor"] = {}
    nf_all = []
    for a, c in (("C2", "C"), ("S2", "S"), ("A2", "A")):
        nf = [abs(p[f"{a}/{c}_wall_p50"] - 1) for p in pairs if f"{a}/{c}_wall_p50" in p]
        nf95 = [abs(p[f"{a}/{c}_wall_p95"] - 1) for p in pairs if f"{a}/{c}_wall_p95" in p]
        if nf:
            out["noise_floor"][f"{a}_vs_{c}_wall_p50_median_abs"] = st.median(nf)
            out["noise_floor"][f"{a}_vs_{c}_wall_p95_median_abs"] = st.median(nf95)
            nf_all.append(st.median(nf))
    gates["noise_floor_ok"] = bool(nf_all) and max(nf_all) <= 0.05

    out["verdict_stable_30fps"] = verdict(d, blocks, gates, ("C", "C2"))       # repeat flight
    out["verdict_first_flight"] = verdict(d, blocks, gates, ("FIRST",))       # cold disk
    out["verdict_sync_S"] = verdict(d, blocks, gates, ("S", "S2"))
    out["verdict_async_A"] = verdict(d, blocks, gates, ("A", "A2"))
    out["verdict_async_adaptive_AP"] = verdict(d, blocks, gates, ("AP", "AP2"))

    if "correctness" in d:
        cc = []
        for p in d["correctness"]["poses"]:
            cc.append({"pose": p["pose"], "ref_pts": p["ref"]["pts"], "ref_hit_budget": p["ref"]["hit_budget"],
                       "floor": p["jitter_floor_0p25px"],
                       "controller": {k: p["controller"][k] for k in
                                      ("px_final", "pts", "max_level", "detail_preserved", "diff_vs_ref")},
                       "fixed150": {k: p["fixed"][0][k] for k in
                                    ("pts", "max_level", "detail_preserved", "diff_vs_ref")}})
        out["detail"] = cc

    js = json.dumps(out, indent=1, default=float)
    if "--json" in sys.argv:
        open(sys.argv[sys.argv.index("--json") + 1], "w").write(js)
    # human summary
    print(f"== {d['tag']}  {d['adapter']}")
    print("gates:", gates)
    if pc:
        print(f"positive control: gpu {pc['gpu_ratio']:.3f} for pts {pc['pts_ratio']:.3f}")
    for b in blocks:
        extra = ""
        if b["label"] != "COLD":
            t1, t2 = b["ttf_hold_overview"], b["ttf_hold_leaf"]
            extra = (f" ttf_over {t1['ms']}ms ttf_leaf {t2['ms']}ms leafsel {b['leaf_selected_frac']:.2f}"
                     f" ioMiss {b['io_caused_misses']} ioRemovable {b['io_removable_misses']}"
                     f" io p99 {b['io_ms_p99']:.1f}")
        else:
            extra = f" first {b['first_frame_ms']:.1f}ms (load {b['first_frame_load_ms']:.1f}ms, {b['first_frame_bytes']/1e6:.1f}MB) ttf {b['ttf_cold']['ms']}ms"
        if "pending_frac_mean" in b and b["mode"] == "async":
            extra += (f" | pending {b['pending_frac_mean']*100:.2f}% of pts, frames w/ pending "
                      f"{b['frames_with_pending']*100:.1f}%, fly<={b['in_flight_max']} upl<={b['uploads_per_frame_max']}")
        print(f"{b['label']:4s} r{b['round']:>2} o{b['order']} p50 {b['wall_p50']:6.2f} p95 {b['wall_p95']:6.2f} "
              f"p99 {b['wall_p99']:6.2f} max {b['wall_max']:6.1f} >33 {b['frac_over_33']*100:5.1f}% "
              f"pts {b['pts_mean']/1e6:5.2f}M px~{b['px_median']:7.1f} io {b['io_hitch_frames']} "
              f"th {b['thermal_max']} fp {b['footprint_max_mb']:.0f}MB{extra}")
    print("noise floor:", out["noise_floor"])
    for p in pairs:
        print("  round", p)
    for k in ("verdict_stable_30fps", "verdict_first_flight", "verdict_sync_S", "verdict_async_A",
              "verdict_async_adaptive_AP"):
        if out.get(k):
            v = out[k]
            print(f"VERDICT {k} {v['labels']}: valid={v['valid_run']} stable={v['stable']} "
                  + json.dumps(v["checks"]["values"], default=float))


if __name__ == "__main__":
    main()
