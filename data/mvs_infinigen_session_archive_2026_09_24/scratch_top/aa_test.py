# 量化「渲 2x 再降采样」对 768x576 训练输入的收益。
# 同一场景 同一相机 同一 8192spp: 原生 768x576  vs  1536x1152 面积降采样到 768x576
# 🔴 判据必须能报警: 带一个【阴性对照】—— 把 1536 用最近邻抽点降到 768 (这是真的有锯齿)。
#    如果指标分不出 面积降采样 和 最近邻抽点, 那这个指标就是废的, 不许用它下结论。
import numpy as np, cv2, sys
n = cv2.imread("/root/igq2/b0768x576/frames/Image/camera_0/Image_0_0_0001_0.png")
h = cv2.imread("/root/igq2/b1536x1152/frames/Image/camera_0/Image_0_0_0001_0.png")
print("native", n.shape, " 2x", h.shape)
area = cv2.resize(h, (768,576), interpolation=cv2.INTER_AREA)   # 正确降采样
near = h[::2, ::2]                                              # 阴性对照: 抽点(有锯齿)

def hf(img):    # 高频能量 = Laplacian 绝对值均值 (锯齿 = 多余高频)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(cv2.Laplacian(g, cv2.CV_32F)).mean())
def psnr(a,b):
    m = ((a.astype(np.float32)-b.astype(np.float32))**2).mean()
    return 99.0 if m<1e-9 else float(10*np.log10(255**2/m))
def sat(img):
    return float(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:,:,1].mean())
def chstd(img):
    return [round(float(img[:,:,c].std()),2) for c in range(3)]

for name, im in [("原生768", n), ("2x面积降采样", area), ("2x最近邻抽点(阴性对照)", near)]:
    print(f"  {name:26s} 高频(Laplacian均值)={hf(im):7.3f}  饱和度={sat(im):6.2f}  通道std={chstd(im)}")
print()
print(f"  PSNR 原生768 vs 2x面积降采样        = {psnr(n,area):6.2f} dB")
print(f"  PSNR 原生768 vs 2x最近邻(阴性对照)   = {psnr(n,near):6.2f} dB")
print(f"  PSNR 2x面积 vs 2x最近邻 (指标灵敏度) = {psnr(area,near):6.2f} dB")
print()
d = np.abs(n.astype(np.float32)-area.astype(np.float32))
print(f"  |原生768 - 2x面积| : 均值={d.mean():.3f}/255  中位={np.median(d):.3f}  99分位={np.percentile(d,99):.1f}  最大={d.max():.0f}")
print(f"  高频比 2x面积/原生768 = {hf(area)/hf(n):.4f}   (=1 说明原生已经不糊不锐, 超采样没带来额外信息)")
print(f"  高频比 最近邻/原生768 = {hf(near)/hf(n):.4f}   (阴性对照应该明显 >1, 否则指标废了)")
