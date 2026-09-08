G='/Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl/'; out='/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/tools/pw_gpufe_wgsl.h'
names=['gftt_common', 'sobel_dxdy', 'harris_box', 'harris_fused', 'gftt_max', 'gftt_thr', 'gftt_find', 'lk_common', 'clahe_hist', 'clahe_lut', 'clahe_interp', 'pad_reflect101', 'pyrdown', 'scharr', 'pack_u8', 'unpack_u8', 'lk_track', 'lk_track_wg', 'fp_selfcheck']
with open(out,'w') as f:
    f.write('// GENERATED from xrslam-gpu-detect/wgsl/*.wgsl — do not edit; regenerate (tools/gen_wgsl_header.py).\n#pragma once\nnamespace pw::gpufe::wgsl {\n')
    for n in names: f.write('static const char* const k_%s = R"WGSL(\n%s\n)WGSL";\n' % (n, open(G+n+'.wgsl').read()))
    f.write('}\n')
print('ok', len(names), 'kernels')
