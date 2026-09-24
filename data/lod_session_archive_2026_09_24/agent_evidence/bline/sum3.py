import json,sys
d=json.load(open(sys.argv[1]))
print(d['tag'], 'errors:', repr(d['wgpu_errors'])[:200])
for p in d['correctness']['poses']:
    ps=p['point_size']; st=ps['see_through_vs_fixed_ref']; a=p['async']; g=ps['getlod_check']
    print(f"{p['pose']:10s} ctrl_px {ps['px']:.2f} pts {ps['pts']} vn {ps['vn_entries']}")
    print(f"   see-through vs fixed ref: floor bad {st['floor_jitter']['bad']:.4f} | fixed bad {st['fixed']['bad']:.4f} (hole {st['fixed']['hole']:.4f} far {st['fixed']['farther']:.4f}) | adaptive bad {st['adaptive']['bad']:.4f} (hole {st['adaptive']['hole']:.4f} far {st['adaptive']['farther']:.4f})")
    print(f"   adaptive vs adaptive ref: bad {ps['adaptive_vs_adaptive_ref']['bad']:.4f}")
    cf=ps['color_fixed_vs_fixed_ref']; ca=ps['color_adaptive_vs_adaptive_ref']
    print(f"   color fixed: frac {cf['frac']:.4f} psnr {cf['psnr']:.2f} (floor {cf['floor_frac']:.4f}/{cf['floor_psnr']:.2f}) detail {cf['detail_preserved']} | adaptive: frac {ca['frac']:.4f} psnr {ca['psnr']:.2f} (floor {ca['floor_frac']:.4f}/{ca['floor_psnr']:.2f}) detail {ca['detail_preserved']}")
    print(f"   adaptive stat cov {ps['adaptive_stat']['coverage']:.3f} sat {ps['adaptive_stat']['sat_mean']:.3f} sdmin {min(ps['adaptive_stat']['sd_rgb']):.1f} nontrivial {ps['adaptive_nontrivial']}")
    print(f"   getLOD: nodes {g['nodes']} pts {g['points']} cpu!=bf {g['cpu_vs_bruteforce_mismatch']} gpu!=cpu {g['gpu_vs_cpu_mismatch']}/{g['gpu_checked']} maxabs {g['gpu_max_abs']:.3g} | NEG zeroed masks mismatch {g['neg_masks_zeroed_mismatch']}")
    print(f"   async: frames {a['frames_to_converge']} ms {a['ms_to_converge']} converged {a['converged']} ==sync {a['equals_sync_image']} maxUpl {a['max_uploads_per_frame']} maxFly {a['max_in_flight']} dropped {a['dropped_total']} ancClosed {a['gpu_set_ancestor_closed']} NEG minus1 differs {a['neg_minus_one_node_differs']}")
lc=[p for p in d['correctness']['poses'] if p['pose']=='leaf'][0]['leaf_check']
print('leaf_check', {k:lc[k] for k in ['selected','drawn','pixels_changed_by_leaf','neg_same_minus_leaf_pixels','leaf_only_px']}, 'no_origin matches', lc['neg_no_origin']['matches_ref'])
