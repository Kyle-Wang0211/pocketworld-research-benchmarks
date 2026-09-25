import sys, numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob
def line(sc, xr, lab):
    s = wob.summarize(sc, xr, lab)
    print('%-5s %-22s n %4d k %.4f ATE %.2f cm Q %s | win4 sim3 sd %.3f [%.3f,%.3f] disp sd %.3f' % (
        sc, lab, s['n'], s['k_global'], s['ate_cm'], ' '.join('%.3f' % x for x in s['quarters_abs']),
        s['win_sim3_rel_sd'], *s['win_sim3_rel_minmax'], s['win_disp_rel_sd']))
    return s
if __name__ == '__main__':
    for a in sys.argv[1:]:
        sc, tag = a.split(':')
        line(sc, wob.load_xr_phone(sc) if tag == 'phone' else wob.load_xr_mac(tag), tag)
