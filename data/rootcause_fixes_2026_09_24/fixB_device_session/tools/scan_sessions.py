#!/usr/bin/python3
"""Scan every official capture dir under the step-1 backup roots for multi-session signatures.

Signatures (per capture, newest/most complete copy per cap id):
  back_jumps   photo sidecar `t` (ARKit uptime clock) decreases along the tap-N order
               (tap-N = our own monotonic shot order, photo_slot_naming.dart:70) => reboot between shots
  dead_stamps  distinct `.dead-<ms>` suffixes (sfm_resume.dart:843-866 sideline; one per extend start
               or whole-project refeed)
  live_ledgers fed-frame ledgers (current + .dead-*) whose photo sets are pairwise disjoint = distinct
               live SfM sessions = distinct capture-page ARKit runs
  orphan       official_capture_manifest.json recovered_from_orphan_capture (scan_record_store.dart:481)
  dup_fids     duplicate frameId in the current ledger (archived_photo_rebuild.dart projectCoverageFrom)
  reloc        photos whose sidecar tracking_state is limited_relocalizing (in-run relocalization)
Every file/dir is stat'ed for the `dataless` flag first; dataless entries are never opened.
"""
import json, os, re, subprocess, sys, collections

ROOTS = [
    '/Users/kaidongwang/Developer/device-backups',
    '/Users/kaidongwang/Developer/pocketworld_artifacts/device_backups',
    '/Users/kaidongwang/Developer/pw_backups',
    '/Users/kaidongwang/Documents/progecttwo/_artifacts.nosync',
    '/Users/kaidongwang/pw_device_backups',
    '/Users/kaidongwang/Developer/pocketworld/docs/progecttwo_archive_2026-08-24/_subdirs',
]
SEQ = re.compile(r'_(?:tap|cap)-(\d+)(?:\.[^.]*)?$')
DEAD = re.compile(r'\.dead-(\d+)$')
SKIPPED = []


def flags(paths):
    if not paths:
        return {}
    out = {}
    for i in range(0, len(paths), 400):
        chunk = paths[i:i + 400]
        r = subprocess.run(['/usr/bin/stat', '-f', '%Sf|%N'] + chunk, capture_output=True, text=True)
        for ln in r.stdout.splitlines():
            f, _, n = ln.partition('|')
            out[n] = f
    return out


def safe(path, fl):
    f = fl.get(path)
    if f is None or 'dataless' in f:
        SKIPPED.append(path)
        return False
    return True


def read_ledger(p, fl):
    if not safe(p, fl):
        return None
    rows = []
    for ln in open(p, errors='replace'):
        try:
            j = json.loads(ln)
        except Exception:
            continue
        if isinstance(j, dict):
            rows.append(j)
    return rows


def scan(d):
    ph = os.path.join(d, 'photos_highres')
    if not os.path.isdir(ph):
        ph = os.path.join(d, 'photos')
    if not os.path.isdir(ph):
        ph = d  # no photos dir at all: ledgers only
    top = [os.path.join(d, n) for n in os.listdir(d)]
    sidecars = [os.path.join(ph, n) for n in os.listdir(ph) if n.endswith('.json') and SEQ.search(n)] if ph != d else []
    fl = flags(top + sidecars + [ph, d])
    if 'dataless' in fl.get(d, '') or 'dataless' in fl.get(ph, ''):
        SKIPPED.append(d)
        return None
    shots = []
    for s in sidecars:
        if not safe(s, fl):
            continue
        try:
            j = json.load(open(s))
        except Exception:
            continue
        t = j.get('t', j.get('save_target_t'))
        if not isinstance(t, (int, float)):
            continue
        shots.append((int(SEQ.search(os.path.basename(s)).group(1)), float(t),
                      j.get('tracking_state') or j.get('trackingStateName'), os.path.basename(s)[:-5] + '.jpg'))
    have = {x[3] for x in shots}
    # photos pruned after sparse (sfm_resume.dart _prunePhotosAfterSparse): fall back to the fed-frame
    # ledgers' captureTimestamp (same ARKit clock as the sidecar `t`, sfm_live_recon.dart:1158-1169)
    for p in top:
        b = os.path.basename(p)
        if not b.startswith('official_sfm_fed_frames.jsonl'):
            continue
        for r in (read_ledger(p, fl) or []):
            n = os.path.basename(r.get('jpegPath', '') or '')
            m = SEQ.search(n)
            t = r.get('captureTimestamp')
            if m and isinstance(t, (int, float)) and n not in have:
                have.add(n)
                shots.append((int(m.group(1)), float(t), 'ledger_only', n))
    shots.sort()
    back = [(shots[i - 1][0], shots[i][0], round(shots[i - 1][1], 1), round(shots[i][1], 1))
            for i in range(1, len(shots)) if shots[i][1] < shots[i - 1][1]]
    gaps = [shots[i][1] - shots[i - 1][1] for i in range(1, len(shots)) if shots[i][1] >= shots[i - 1][1]]
    dead = sorted({DEAD.search(os.path.basename(p)).group(1) for p in top if DEAD.search(os.path.basename(p))})
    ledgers = {}
    for p in top:
        b = os.path.basename(p)
        if b.startswith('official_sfm_fed_frames.jsonl'):
            rows = read_ledger(p, fl)
            if rows is not None:
                ledgers[b] = rows
    sets = {k: frozenset(os.path.basename(r.get('jpegPath', '')) for r in v if r.get('jpegPath')) for k, v in ledgers.items()}
    nonempty = [s for s in sets.values() if s]
    # greedy count of pairwise-disjoint ledgers (live sessions); a refeed ledger overlaps the others
    disjoint = []
    for s in sorted(nonempty, key=len):
        if all(not (s & o) for o in disjoint):
            disjoint.append(s)
    cur = ledgers.get('official_sfm_fed_frames.jsonl') or []
    fc = collections.Counter(r.get('frameId') for r in cur if isinstance(r.get('frameId'), int))
    dup = sum(n - 1 for n in fc.values() if n > 1)
    orphan = False
    man = os.path.join(d, 'official_capture_manifest.json')
    if os.path.exists(man) and safe(man, fl):
        try:
            orphan = bool(json.load(open(man)).get('recovered_from_orphan_capture'))
        except Exception:
            pass
    states = collections.Counter(s[2] for s in shots)
    # clock-contiguous segments (split only at backward jumps)
    segs = [1]
    for i in range(1, len(shots)):
        if shots[i][1] < shots[i - 1][1]:
            segs.append(1)
        else:
            segs[-1] += 1
    return dict(dir=d, n_photos=len(shots), back_jumps=back, clock_segments=segs,
                max_fwd_gap_s=round(max(gaps), 1) if gaps else 0.0,
                dead_stamps=dead, n_ledgers=len(ledgers), live_ledgers=len(disjoint),
                live_ledger_sizes=sorted(len(s) for s in disjoint), orphan=orphan, dup_fids=dup,
                reloc=states.get('limited_relocalizing', 0),
                non_normal={k: v for k, v in states.items() if k != 'normal'})


def main():
    dirs = []
    for r in ROOTS:
        for root, subdirs, _ in os.walk(r):
            depth = root[len(r):].count('/')
            if depth > 7:
                subdirs[:] = []
                continue
            for s in list(subdirs):
                if re.fullmatch(r'cap_\d+', s):
                    dirs.append(os.path.join(root, s))
                    subdirs.remove(s)
    by = collections.defaultdict(list)
    for d in dirs:
        by[os.path.basename(d)].append(d)
    step1 = set()
    tsv = sys.argv[1] if len(sys.argv) > 1 else None
    if tsv:
        for ln in open(tsv).read().splitlines()[1:]:
            step1.add(ln.split('\t')[0])
    rows = []
    for cid, ds in sorted(by.items()):
        best = None
        for d in ds:
            try:
                r = scan(d)
            except Exception as e:  # noqa
                r = None
            if r is None:
                continue
            key = (r['n_photos'], r['n_ledgers'], len(r['dead_stamps']), d)
            if best is None or key > best[0]:
                best = (key, r)
        if best:
            row = best[1]
            row['cap'] = cid
            row['in_step1'] = cid in step1
            row['copies'] = len(ds)
            rows.append(row)
    for r in rows:
        r['multi_session_certain'] = bool(r['back_jumps']) or r['live_ledgers'] >= 2
        r['extend_or_refeed_trace'] = bool(r['dead_stamps']) or r['orphan'] or r['dup_fids'] > 0
    json.dump(dict(rows=rows, skipped=SKIPPED[:200], n_skipped=len(SKIPPED)), open(sys.argv[2], 'w'), indent=1)
    allr = [r for r in rows if r['n_photos'] > 0]
    s1 = [r for r in allr if r['in_step1']]
    for name, rs in (('step1-90', s1), ('all-unique', allr)):
        print(f'== {name}: captures={len(rs)}')
        print('  certain multi-session (clock reversal or >=2 disjoint live ledgers):', sum(r['multi_session_certain'] for r in rs))
        print('    of which clock reversal (reboot):', sum(bool(r['back_jumps']) for r in rs))
        print('    of which >=2 disjoint live ledgers:', sum(r['live_ledgers'] >= 2 for r in rs))
        print('  any extend/refeed trace (.dead-*, orphan manifest, dup frameIds):', sum(r['extend_or_refeed_trace'] for r in rs))
        print('  photos shot while limited_relocalizing:', sum(r['reloc'] > 0 for r in rs))
    print('skipped dataless entries:', len(SKIPPED))
    for r in allr:
        if r['multi_session_certain'] or r['extend_or_refeed_trace'] or r['reloc']:
            print(r['cap'], 'step1' if r['in_step1'] else '     ', 'n=%d' % r['n_photos'], 'segs', r['clock_segments'],
                  'back', r['back_jumps'][:3], 'dead', len(r['dead_stamps']), 'ledgers', r['n_ledgers'],
                  'live', r['live_ledger_sizes'], 'orphan', r['orphan'], 'dup', r['dup_fids'], 'reloc', r['reloc'],
                  'gap', r['max_fwd_gap_s'], r['dir'].replace('/Users/kaidongwang/', '~/'))


if __name__ == '__main__':
    main()
