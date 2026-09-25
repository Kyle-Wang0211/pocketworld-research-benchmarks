import sys
# EuRoC state_groundtruth_estimate0/data.csv (t_ns, p, q_wxyz, ...) -> TUM (t_s x y z qx qy qz qw); body = IMU frame
out = open(sys.argv[2], 'w')
for ln in open(sys.argv[1]):
    if ln.startswith('#') or not ln.strip(): continue
    f = ln.strip().split(',')
    t = int(f[0]) * 1e-9
    x, y, z, qw, qx, qy, qz = map(float, f[1:8])
    out.write(f"{t:.9f} {x:.6f} {y:.6f} {z:.6f} {qx:.9f} {qy:.9f} {qz:.9f} {qw:.9f}\n")
