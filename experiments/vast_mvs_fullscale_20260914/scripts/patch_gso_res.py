p = "/root/gso_stage1.py"
s = open(p).read()

old = "W, H = 768, 576"
new = ("WR, HR = 1024, 768          # 渲染分辨率(4:3,留余地,存档用)\n"
       "W,  H  = 768, 576           # 训练分辨率(官方 BlendedMVS 口径),两轴同为 0.75 缩放")
assert s.count(old) == 1, ("A", s.count(old))
s = s.replace(old, new)

s = s.replace("sc.render.resolution_x = W; sc.render.resolution_y = H",
              "sc.render.resolution_x = WR; sc.render.resolution_y = HR")

old2 = """def K_from_cam():
    # Blender 透视相机 -> OpenCV K。判据:水平视场角
    f_mm = cam_d.lens; sw = cam_d.sensor_width
    fx = W * f_mm / sw; fy = fx            # 方形像素
    return np.array([[fx, 0, W / 2.0], [0, fy, H / 2.0], [0, 0, 1]], dtype=np.float64)"""
new2 = """def K_from_cam():
    # Blender 透视相机 -> OpenCV K(渲染分辨率下)。判据:水平视场角
    f_mm = cam_d.lens; sw = cam_d.sensor_width
    fx = WR * f_mm / sw; fy = fx           # 方形像素
    return np.array([[fx, 0, WR / 2.0], [0, fy, HR / 2.0], [0, 0, 1]], dtype=np.float64)

SCALE = W / float(WR)                      # 0.75
assert abs(SCALE - H / float(HR)) < 1e-9, "宽高缩放比必须一致,否则几何被拉变形"
def K_to_train(K):
    return np.diag([SCALE, SCALE, 1.0]) @ K"""
assert s.count(old2) == 1, ("B", s.count(old2))
s = s.replace(old2, new2)

# 渲染循环:读 EXR 后先存档,再降采样到训练分辨率
old3 = """    z = np.frombuffer(f.channel(zname, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(H, W).copy()"""
new3 = """    z = np.frombuffer(f.channel(zname, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(HR, WR).copy()"""
assert s.count(old3) == 1, ("C", s.count(old3))
s = s.replace(old3, new3)

old4 = """    rgb = np.stack([np.frombuffer(f.channel(c, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(H, W)
                    for c in rgbn], -1)
    img = (np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    from PIL import Image as PILImage
    PILImage.fromarray(img).save(f"{OUT_ROOT}/{SCAN}/blended_images/{i:08d}.jpg", quality=95)"""
new4 = """    rgb = np.stack([np.frombuffer(f.channel(c, Imath.PixelType(Imath.PixelType.FLOAT)), np.float32).reshape(HR, WR)
                    for c in rgbn], -1)
    img = (np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    from PIL import Image as PILImage
    import cv2 as _cv2
    # 存档:渲染分辨率的 RGB + 深度(以后想提高训练分辨率不用重渲)
    os.makedirs(f"{OUT_ROOT}/{SCAN}/_archive", exist_ok=True)
    PILImage.fromarray(img).save(f"{OUT_ROOT}/{SCAN}/_archive/{i:08d}.jpg", quality=95)
    np.savez_compressed(f"{OUT_ROOT}/{SCAN}/_archive/{i:08d}_depth.npz", depth=z)
    # 降采样到训练分辨率:RGB 用面积平均,深度用最近邻(与 blend.py 的 stage 降采样同约定)
    img = np.array(PILImage.fromarray(img).resize((W, H), PILImage.LANCZOS))
    z = _cv2.resize(z, (W, H), interpolation=_cv2.INTER_NEAREST)
    PILImage.fromarray(img).save(f"{OUT_ROOT}/{SCAN}/blended_images/{i:08d}.jpg", quality=95)"""
assert s.count(old4) == 1, ("D", s.count(old4))
s = s.replace(old4, new4)

old5 = "    K = K_from_cam()\n    Ks.append(K); Es.append(E); Ds.append(z)"
new5 = "    Ks.append(K_to_train(K_from_cam())); Es.append(E); Ds.append(z)   # K 与深度都落在训练分辨率"
assert s.count(old5) == 1, ("E", s.count(old5))
s = s.replace(old5, new5)

open(p, "w").write(s)
print("patched OK")
