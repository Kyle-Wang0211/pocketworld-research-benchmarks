import json, sys
s = json.load(open(sys.argv[1]))
print('order', s['order'], 'seconds/arm', s['seconds_per_arm'])
cap = s.get('capability', {})
print('free_bytes', cap.get('free_bytes'), 'thermal@start', cap.get('thermal_state'), 'device', cap.get('device_model'))
for i, a in enumerate(s['arms']):
    tm = ((a.get('status') or {}).get('result') or {}).get('timing') or {}
    ps = tm.get('per_second') or []
    first_loss = next((r['s'] for r in ps if r.get('lost_queue_full', 0) > 0), None)
    peak_s = max(ps, key=lambda r: r.get('peak_in_flight', 0)) if ps else {}
    mb = [r.get('written_mb', 0) for r in ps[1:-1]]
    wmax = [r.get('write_ms_max', 0) for r in ps]
    print(f"arm{i} {a['record_hz']:.0f}Hz {a['write_sync']:<15} frames {a['frame_count']} loss {a['loss_count']} "
          f"peak {a['peak_in_flight']}/64 (at s{peak_s.get('s')}) write p50 {a['frame_write_ms_p50']:.1f} p99 {a['frame_write_ms_p99']:.1f} "
          f"max {a['frame_write_ms_max']:.0f} ms | MB/s interior min {min(mb) if mb else 0:.0f} max {max(mb) if mb else 0:.0f} "
          f"| first loss s{first_loss} | arkit missed {a['arkit_frames_missed_estimate']} | thermal {a['thermal_start']}->{a['thermal_end']} "
          f"| gated {tm.get('gated_out_frames')} admitted {tm.get('admitted_frames')} depth {a['depth_frames']} barrier_fb {tm.get('barrier_fallbacks')} err {a.get('error')}")
    worst = sorted(ps, key=lambda r: -r.get('write_ms_max', 0))[:3]
    print('      worst seconds:', [(r['s'], round(r.get('write_ms_max', 0)), r.get('peak_in_flight')) for r in worst])
