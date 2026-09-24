import numpy as np, cv2
B="/root/igq2/%s/frames/Image/camera_0/Image_0_0_0001_0.png"
src={k:cv2.imread(B%k) for k in ["b0768x576","b1024x768","b1536x1152","b2048x1536"]}
def hf(img):
    g=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(cv2.Laplacian(g,cv2.CV_32F)).mean())
def psnr(a,b):
    m=((a.astype(np.float32)-b.astype(np.float32))**2).mean(); return 99.0 if m<1e-9 else float(10*np.log10(255**2/m))
n=src["b0768x576"]
print("全部降采样到 768x576 (INTER_AREA) 后比较, 基准 = 原生 768x576 渲染")
print(f"{'渲染分辨率':>14} {'相对GPU代价':>10} {'高频(Lap均值)':>13} {'高频比':>7} {'vs原生PSNR':>11}")
cost={"b0768x576":1.00,"b1024x768":1.43,"b1536x1152":3.20,"b2048x1536":5.18}  # 用 Actual rendering 秒数比 (74.6/106.3/247.3/386.6 /74.6)
for k in ["b0768x576","b1024x768","b1536x1152","b2048x1536"]:
    d=src[k] if k=="b0768x576" else cv2.resize(src[k],(768,576),interpolation=cv2.INTER_AREA)
    print(f"{k[1:]:>14} {cost[k]:>10.2f}x {hf(d):>13.3f} {hf(d)/hf(n):>7.3f} {psnr(n,d):>11.2f}")
print()
print("阴性对照(必须能报警): 把 2048 先高斯糊 sigma=1.5 再降采样 => 高频必须明显降")
bl=cv2.resize(cv2.GaussianBlur(src["b2048x1536"],(0,0),1.5),(768,576),interpolation=cv2.INTER_AREA)
print(f"   糊过的2048->768: 高频={hf(bl):.3f} 高频比={hf(bl)/hf(n):.3f}  (<1 才算指标有效)")
# 逐级差: 高分辨率之间互比, 看收益是否饱和
a15=cv2.resize(src["b1536x1152"],(768,576),interpolation=cv2.INTER_AREA)
a20=cv2.resize(src["b2048x1536"],(768,576),interpolation=cv2.INTER_AREA)
print(f"   1536降采样 vs 2048降采样 PSNR = {psnr(a15,a20):.2f} dB  (越高说明 1536 往上已无新信息)")
