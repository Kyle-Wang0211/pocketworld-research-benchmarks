"""共视裁剪:用位姿把一对之内几何上不可能配上的关键点先剔掉。

原理:图 i 里的一个关键点,深度未知,但在 [dmin, dmax] 区间内它在图 j 上
扫出一条极线段。**若这条线段整个落在图 j 之外(或全在相机背后),这个点在
图 j 里不可能有对应** —— 剔掉它不损失任何真匹配,是几何意义上的无损。

为什么现在才值得做:生产的暴力匹配只要 0.0172 TFLOP/对,裁剪的开销可能比省下的还多;
LightGlue 是 1.381 TFLOP/对(80 倍)且同样 N² 缩放 ⇒ 同一刀在这里是量级收益。
生产已经在**配对层**用位姿(spatial_guided_pairs / K=12/帧),但**关键点层**没用。

⚠️ 位姿有噪声(端上是 ARKit,比重建位姿差),所以图 j 的边界要外扩 margin 像素。
   probe-gate 那次的教训:"看起来该扔的其实有用" —— 余量必须留够,验收必须到重建层。
"""
import numpy as np


class CovisMasker:
    def __init__(self, npz_path, n_depth: int = 8):
        z = np.load(npz_path)
        self.idx = {int(i): k for k, i in enumerate(z["ids"])}
        self.K, self.R, self.t = z["K"], z["R"], z["t"]
        self.dlo, self.dhi, self.wh = z["dlo"], z["dhi"], z["wh"]
        self.n_depth = n_depth

    def mask(self, iid_from: int, iid_to: int, kpts: np.ndarray,
             margin: float) -> np.ndarray:
        """返回 bool 掩码:kpts(图 from 的原图像素坐标)在图 to 里可能可见。

        沿深度对数采样若干个点做投影,任一落进(外扩后的)图 to 且在相机前方即保留。
        """
        a, b = self.idx.get(iid_from), self.idx.get(iid_to)
        if a is None or b is None:
            return np.ones(len(kpts), dtype=bool)

        Ka, Ra, ta = self.K[a], self.R[a], self.t[a]
        Kb, Rb, tb = self.K[b], self.R[b], self.t[b]
        W, H = self.wh[b]

        # 像素 → 相机 a 的单位方向
        uv1 = np.concatenate([kpts, np.ones((len(kpts), 1))], 1)          # [N,3]
        ray = uv1 @ np.linalg.inv(Ka).T                                    # [N,3]
        ray /= np.linalg.norm(ray, axis=1, keepdims=True)
        C_a = -Ra.T @ ta                                                   # 相机 a 光心(世界)

        depths = np.geomspace(self.dlo[a], self.dhi[a], self.n_depth)
        keep = np.zeros(len(kpts), dtype=bool)
        for d in depths:
            X = (Ra.T @ (d * ray).T).T + C_a                                # [N,3] 世界点
            xc = X @ Rb.T + tb                                              # → 相机 b
            z = xc[:, 2]
            ok = z > 1e-6
            uv = (xc @ Kb.T)
            with np.errstate(invalid="ignore", divide="ignore"):
                u = uv[:, 0] / z
                v = uv[:, 1] / z
            inside = ok & (u > -margin) & (u < W + margin) \
                        & (v > -margin) & (v < H + margin)
            keep |= inside
            if keep.all():
                break
        return keep
