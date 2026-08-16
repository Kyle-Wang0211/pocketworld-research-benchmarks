"""BlendedMVS/MVG 的 mmap 缓存版数据集 —— 装到 diffmvs/datasets/blend_cached.py。

用法:训练时传 `--dataset=blend_cached`,**train.py 一行都不用改**
      (train.py:352 的 find_dataset_def 按名字 import datasets.<name>.MVSDataset)。

它只把 `read_img` / `read_depth` 换成从 predecode_blend.py 产出的 mmap 里取,
**其余逻辑逐字继承原版** —— 邻居选取、随机源视图抽样、多尺度 resize、
mask 生成、投影矩阵缩放全部不动。⇒ 喂给模型的张量与原版**逐位相同**。

环境变量:
    BLEND_CACHE   预解码目录(predecode_blend.py 的 out)。**必须设**,否则退回原版行为。

设计要点:
🔴 缓存**不能**用 Python 字典 —— num_workers>0 时每个 worker 是独立进程,
   字典会被逐个复制。20GB × 16 worker 当场打爆内存。
   mmap 单文件则所有 worker 共享同一份 OS page cache,零复制。
🔴 mmap **延迟到 worker 里首次访问时才开** —— 在 __init__ 里开好再 fork 也能用,
   但延迟开是更稳的通用写法(避免某些平台上 fork 后句柄状态怪异)。
"""
from __future__ import annotations

import json
import os
import numpy as np

from datasets.blend import MVSDataset as _Base


class MVSDataset(_Base):
    def __init__(self, datapath, listfile, mode="train", nviews=5, ndepths=384):
        super().__init__(datapath, listfile, mode, nviews, ndepths)
        self._cache_dir = os.environ.get("BLEND_CACHE", "").strip()
        self._img_idx = None      # 延迟加载
        self._img_mm = None
        self._dep_idx = None
        self._dep_mm = None
        self._warned = set()
        if not self._cache_dir:
            print("[blend_cached] ⚠️ 未设 BLEND_CACHE,退回逐样本 JPEG 解码"
                  "(等同原版 blend,CPU 会成为瓶颈)", flush=True)
        else:
            print(f"[blend_cached] 缓存目录 {self._cache_dir}", flush=True)

    # ── 延迟初始化:在每个 worker 进程内各开一次 mmap(共享同一份页缓存)──
    def _ensure(self):
        if self._img_idx is not None or not self._cache_dir:
            return
        d = self._cache_dir
        with open(os.path.join(d, "images.json")) as f:
            self._img_idx = json.load(f)
        self._img_mm = np.memmap(os.path.join(d, "images.u8"), dtype=np.uint8, mode="r")
        dj = os.path.join(d, "depths.json")
        if os.path.isfile(dj):
            with open(dj) as f:
                self._dep_idx = json.load(f)
            self._dep_mm = np.memmap(os.path.join(d, "depths.f32"),
                                     dtype=np.float32, mode="r")

    def _rel(self, filename: str) -> str:
        # 原版传的是绝对路径(blend.py:94-105 用 os.path.join(self.datapath, ...))
        return os.path.relpath(filename, self.datapath)

    # 🔴 索引里存的是**字节**偏移,memmap 切片按**元素**计 ⇒ 必须除以 itemsize。
    #    uint8 恰好 1 字节/元素,所以图像路径看不出问题;float32 深度就直接
    #    reshape 失败。实测抓到的 —— 一个只在一半路径上显形的错。
    @staticmethod
    def _el(byte_off: int, itemsize: int) -> int:
        assert byte_off % itemsize == 0, f"字节偏移 {byte_off} 不是 {itemsize} 的整数倍"
        return byte_off // itemsize

    def read_img(self, filename):
        self._ensure()
        if self._img_idx is not None:
            rel = self._rel(filename)
            e = self._img_idx.get(rel)
            if e is not None:
                off, h, w, c = e
                s = self._el(off, self._img_mm.dtype.itemsize)   # uint8 ⇒ 1
                a = self._img_mm[s:s + h * w * c].reshape(h, w, c)
                # ⚠️ 与原版逐位相同:原版是 np.array(PIL,f32)/255.,
                #    预解码时同样用 PIL 出 uint8 ⇒ 这里只差一次除法,结果一致
                return a.astype(np.float32) / 255.0
            if rel not in self._warned:
                self._warned.add(rel)
                print(f"[blend_cached] ⚠️ 缓存缺 {rel},该图退回 JPEG 解码", flush=True)
        return super().read_img(filename)

    def read_depth(self, filename):
        self._ensure()
        if self._dep_idx is not None:
            rel = self._rel(filename)
            e = self._dep_idx.get(rel)
            if e is not None:
                off, h, w = e
                s = self._el(off, self._dep_mm.dtype.itemsize)   # float32 ⇒ 4
                # np.array(...) 做拷贝:下游 cv2.resize 需要可写且连续的数组,
                # 而 mmap 切片是只读视图
                return np.array(self._dep_mm[s:s + h * w].reshape(h, w),
                                dtype=np.float32)
        return super().read_depth(filename)
