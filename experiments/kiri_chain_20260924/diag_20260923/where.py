import numpy as np, json, open3d as o3d
C = np.load("bedges_prod_smallloop_centroids.npy").astype(np.float64)
R = json.load(open("regions_planes.json")); nw = np.array(R["wall"]["n"]); dw = R["wall"]["d"]; nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]
h = C @ nf + df; sw = C @ nw + dw
print("n small loops", len(C))
print("height-above-floor (CD) hist:", np.histogram(h, bins=[-1, -0.05, 0.05, 0.5, 1.0, 1.5, 2, 3, 4, 5, 7, 12])[0].tolist())
print("signed dist to fabric-wall plane hist:", np.histogram(sw, bins=[-3, -0.1, 0.1, 0.3, 0.6, 1, 2, 4, 8, 12])[0].tolist())
pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(C)); rest = pc; tot = len(C)
for k in range(6):
    mdl, inl = rest.segment_plane(0.03, 3, 3000); Q = np.asarray(rest.points)[inl]
    n = np.array(mdl[:3]); ang_w = np.degrees(np.arccos(min(1, abs(n @ nw)))); ang_f = np.degrees(np.arccos(min(1, abs(n @ nf))))
    print(f"plane{k}: {len(inl)} loops ({100*len(inl)/tot:.1f}%) n={n.round(3)} d={mdl[3]:.3f} angle_to_fabricwall={ang_w:.1f} angle_to_floor={ang_f:.1f} "
          f"offset_from_fabricwall_along_n={np.median(Q@nw+dw):.3f} height p5/50/95={np.percentile(Q@nf+df,[5,50,95]).round(2)}")
    rest = rest.select_by_index(inl, invert=True)
json.dump({}, open("where_done.json", "w"))
