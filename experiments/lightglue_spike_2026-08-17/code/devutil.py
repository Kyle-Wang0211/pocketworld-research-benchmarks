"""设备无关的同步/显存工具 —— 同一份臂脚本要能在 MPS(Mac)和 CUDA(租的 5090)上跑。

⚠️ `sync` 不是可选项:两个后端都是异步下发,不同步就把 kernel 排队时间当成了执行时间。
   我们量的是逐对耗时,漏掉同步会直接量出假的加速比。
"""
import torch


def sync(dev):
    if dev.type == "mps":
        torch.mps.synchronize()
    elif dev.type == "cuda":
        torch.cuda.synchronize()


def pool_gb(dev):
    """驱动向系统要走的显存(含缓存池),不是活跃张量。"""
    if dev.type == "mps":
        return torch.mps.driver_allocated_memory() / 2 ** 30
    if dev.type == "cuda":
        return torch.cuda.memory_reserved() / 2 ** 30
    return 0.0


def live_gb(dev):
    """活跃张量占用。"""
    if dev.type == "mps":
        return torch.mps.current_allocated_memory() / 2 ** 30
    if dev.type == "cuda":
        return torch.cuda.memory_allocated() / 2 ** 30
    return 0.0


def empty(dev):
    if dev.type == "mps":
        torch.mps.empty_cache()
    elif dev.type == "cuda":
        torch.cuda.empty_cache()


def strict_fp32(enable: bool = True):
    """默认把 CUDA 上一切 TF32 关掉。

    ⚠️ torch 出厂时 `cudnn.allow_tf32` 是 **True** —— 卷积会悄悄走 TF32。
       matmul 那边默认已是 False(匹配器的算力都在 matmul,所以匹配本来就是严格 fp32),
       但 ALIKED/RaCo 的主干是卷积,不关就等于在提取端偷偷降了精度。
       我们的口径是「质量必须无损」⇒ 默认全关;TF32 要用必须是一次显式的 A/B 实验。
    """
    import torch
    if not torch.cuda.is_available():
        return
    torch.backends.cuda.matmul.allow_tf32 = not enable
    torch.backends.cudnn.allow_tf32 = not enable
