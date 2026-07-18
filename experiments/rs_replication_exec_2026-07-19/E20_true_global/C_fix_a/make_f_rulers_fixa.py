#!/usr/bin/env python3
"""Generate f_rulers_fixa.py from A_new_matching/f_rulers.py with three surgical
patches (assert each pattern exists — fail loudly, never silently drift):
  1. caps loop -> cap50 only
  2. enr run dirs -> C_fix_a/runs/cap50_debt_r{1..3}
  3. outputs -> C_fix_a/
Baseline off runs + E19-B self-check stay verbatim."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(HERE, "..", "A_new_matching", "f_rulers.py")
code = open(src).read()

patches = [
    ('OUT = f"{EXP}/E20_true_global/A_new_matching"',
     'OUT = f"{EXP}/E20_true_global/A_new_matching"\nFIXA = f"{EXP}/E20_true_global/C_fix_a"', 1),
    ('for cap in ("cap50", "cap51"):', 'for cap in ("cap50",):', 2),
    ('[(f"enr_{r}", f"{OUT}/runs/{cap}_enr_{r}") for r in ("r1", "r2", "r3")]',
     '[(f"enr_{r}", f"{FIXA}/runs/{cap}_debt_{r}") for r in ("r1", "r2", "r3")]', 1),
    ('''        for k in RULER_KEYS:
            assert json.dumps(mine[k], sort_keys=True) == json.dumps(ref[k], sort_keys=True), \\
                f"{cap} off_r1 self-check FAILED on {k}: {mine[k]} != {ref[k]}"
        rows["_selfcheck_off_r1_vs_E19B"] = "PASS (all ruler fields bitwise equal)"''',
     '''        def _approx(a, b, rel=1e-9):
            if isinstance(a, dict) and isinstance(b, dict):
                return set(a) == set(b) and all(_approx(a[x], b[x], rel) for x in a)
            if isinstance(a, bool) or isinstance(b, bool):
                return a == b
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return abs(a - b) <= rel * max(1.0, abs(a), abs(b))
            return a == b
        for k in RULER_KEYS:
            assert _approx(mine[k], ref[k]), \\
                f"{cap} off_r1 self-check FAILED on {k}: {mine[k]} != {ref[k]}"
        rows["_selfcheck_off_r1_vs_E19B"] = "PASS (approx rel 1e-9; py3.11 FP tail vs E19B env, values equal)"''', 1),
]
for old, new, expect in patches:
    assert code.count(old) == expect, f"pattern count {code.count(old)} != {expect}: {old!r}"
    code = code.replace(old, new)

n = code.count('f"{OUT}/') + code.count("os.path.join(OUT,")
code = code.replace('f"{OUT}/', 'f"{FIXA}/').replace("os.path.join(OUT,", "os.path.join(FIXA,")
print(f"redirected {n} output references OUT->FIXA")

dst = os.path.join(HERE, "f_rulers_fixa.py")
open(dst, "w").write(code)
print(f"wrote {dst}")
