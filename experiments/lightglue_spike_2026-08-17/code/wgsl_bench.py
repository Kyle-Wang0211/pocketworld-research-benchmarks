#!/usr/bin/env python3
"""把 flash_attn.wgsl 真跑起来:先对拍,再计时。

⚠️ 顺序不能反。我们自己的旧账(APDe→WGSL):2741 行全编译通过、占用率满格、
   耗时正常,深度图与真值的相关却只有 0.033。**"能跑"不等于"算对"**,
   所以这里先用 PyTorch SDPA 做金标准逐元素比,差异不过关就不报速度。

量什么才是可迁移的:5090 的绝对毫秒对 A16 没有意义,但**达到峰值的百分比**
大致可迁移(都是现代分块 GPU)。所以同时报:
  · 与 PyTorch SDPA(cuDNN 融合实现)的相对速度 —— 这是"我这份手写 kernel 有多菜"
  · 有效 TFLOPS 与占峰值比 —— 这是能外推到 A16 的那个数
"""
import argparse, time
from pathlib import Path

import numpy as np
import wgpu


HEAD_DIM = 64


def run_wgsl(q, k, v, n_head, head, iters=1, kernel="flash_attn.wgsl", br=64, all_heads=False):
    """q,k,v: [N, n_head, 64] float32 (行主序)。返回 (out[N,64], 单次耗时秒)。"""
    n_q, n_kv = q.shape[0], k.shape[0]
    src = Path(kernel).read_text()

    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    device = adapter.request_device_sync()
    shader = device.create_shader_module(code=src)

    def buf(arr, usage):
        b = device.create_buffer_with_data(data=arr.tobytes(), usage=usage)
        return b
    S = wgpu.BufferUsage.STORAGE
    qb = buf(np.ascontiguousarray(q, np.float32), S)
    kb = buf(np.ascontiguousarray(k, np.float32), S)
    vb = buf(np.ascontiguousarray(v, np.float32), S)
    out_n = n_q * n_head * HEAD_DIM
    ob = device.create_buffer(size=out_n * 4, usage=S | wgpu.BufferUsage.COPY_SRC)
    dims = np.array([n_q, n_kv, n_head, head], dtype=np.uint32)
    db = buf(dims, wgpu.BufferUsage.UNIFORM)

    layout = device.create_bind_group_layout(entries=[
        dict(binding=i, visibility=wgpu.ShaderStage.COMPUTE,
             buffer=dict(type=t)) for i, t in enumerate([
                 wgpu.BufferBindingType.read_only_storage,
                 wgpu.BufferBindingType.read_only_storage,
                 wgpu.BufferBindingType.read_only_storage,
                 wgpu.BufferBindingType.storage])] +
        [dict(binding=4, visibility=wgpu.ShaderStage.COMPUTE,
              buffer=dict(type=wgpu.BufferBindingType.uniform))])
    bind = device.create_bind_group(layout=layout, entries=[
        dict(binding=0, resource=dict(buffer=qb, offset=0, size=qb.size)),
        dict(binding=1, resource=dict(buffer=kb, offset=0, size=kb.size)),
        dict(binding=2, resource=dict(buffer=vb, offset=0, size=vb.size)),
        dict(binding=3, resource=dict(buffer=ob, offset=0, size=ob.size)),
        dict(binding=4, resource=dict(buffer=db, offset=0, size=db.size)),
    ])
    pipe = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[layout]),
        compute=dict(module=shader, entry_point="main"))

    n_wg = (n_q + br - 1) // br
    n_y = n_head if all_heads else 1     # v2 把 head 铺到 dispatch 的 y 维

    def dispatch():
        enc = device.create_command_encoder()
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bind)
        cp.dispatch_workgroups(n_wg, n_y, 1)
        cp.end()
        device.queue.submit([enc.finish()])

    dispatch()
    device.queue.read_buffer(ob)          # 同步点:强制等 GPU 做完
    t0 = time.perf_counter()
    for _ in range(iters):
        dispatch()
    device.queue.read_buffer(ob)
    dt = (time.perf_counter() - t0) / iters

    raw = np.frombuffer(device.queue.read_buffer(ob), dtype=np.float32)
    out = raw.reshape(n_q, n_head, HEAD_DIM)[:, head, :]
    return out, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2048)
    ap.add_argument("--heads", type=int, default=4)
    ap.add_argument("--iters", type=int, default=5)
    ap.add_argument("--skip-torch", action="store_true")
    ap.add_argument("--kernel", default="flash_attn.wgsl")
    ap.add_argument("--br", type=int, default=64)
    ap.add_argument("--all-heads", action="store_true",
                    help="v2:head 走 dispatch y 维,一次算完全部 head")
    args = ap.parse_args()

    rng = np.random.default_rng(0)
    N, H = args.n, args.heads
    q = rng.standard_normal((N, H, HEAD_DIM), dtype=np.float32)
    k = rng.standard_normal((N, H, HEAD_DIM), dtype=np.float32)
    v = rng.standard_normal((N, H, HEAD_DIM), dtype=np.float32)

    out, dt = run_wgsl(q, k, v, H, 0, iters=args.iters,
                       kernel=args.kernel, br=args.br, all_heads=args.all_heads)

    # ---- 金标准:先对拍,不过关就不报速度 ----
    ok = True
    if not args.skip_torch:
        import torch, torch.nn.functional as F
        tq = torch.from_numpy(q[:, 0][None, None])
        tk = torch.from_numpy(k[:, 0][None, None])
        tv = torch.from_numpy(v[:, 0][None, None])
        ref = F.scaled_dot_product_attention(tq, tk, tv)[0, 0].numpy()
        diff = np.abs(out - ref)
        cos = (out * ref).sum(1) / (np.linalg.norm(out, axis=1) * np.linalg.norm(ref, axis=1) + 1e-12)
        ok = diff.max() < 1e-3
        print(f"对拍 N={N}: 最大绝对差 {diff.max():.3e}  余弦最小 {cos.min():.8f}  "
              f"{'✅ 通过' if ok else '❌ 不过关'}")
        if not ok:
            print("  ⇒ kernel 算错了,速度数字无意义,不报。")
            return

    # 单头的 FLOPs:QK^T + AV = 4·N²·Dh
    flops = 4 * N * N * HEAD_DIM * (H if args.all_heads else 1)
    print(f"WGSL {Path(args.kernel).stem:12s} {dt*1000:8.3f} ms   有效 {flops/dt/1e12:6.2f} TFLOPS")
    if not args.skip_torch:
        import torch
        if torch.cuda.is_available():
            import torch.nn.functional as F
            tq = torch.from_numpy(q[:, 0][None, None]).cuda()
            tk = torch.from_numpy(k[:, 0][None, None]).cuda()
            tv = torch.from_numpy(v[:, 0][None, None]).cuda()
            for _ in range(3):
                F.scaled_dot_product_attention(tq, tk, tv)
            torch.cuda.synchronize(); t0 = time.perf_counter()
            for _ in range(20):
                F.scaled_dot_product_attention(tq, tk, tv)
            torch.cuda.synchronize()
            t_t = (time.perf_counter() - t0) / 20
            print(f"PyTorch SDPA {t_t*1000:8.3f} ms   有效 {flops/t_t/1e12:6.2f} TFLOPS"
                  f"   ⇒ 我的 kernel 是它的 {t_t/dt:.2f}×")


if __name__ == "__main__":
    main()
