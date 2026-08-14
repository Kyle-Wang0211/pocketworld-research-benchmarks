#!/usr/bin/env python3
"""生成 per-kernel binding remap 表。

🔴 为什么必须有这个(单帧闭环踩出来的真事故):
   naga 与 spirv-cross 都会**剥掉 kernel 未使用的 binding 并重新紧凑编号**。
   例如 depth_and_normal_kernel 只用 P/cams/plane_hypotheses ⇒ MSL 里是
   buffer(0,1,2);而 black_pixel_update_strong 用 7 个 ⇒ buffer(0..6)。
   host 若用一张固定表按 index 绑,前者就会把 packed_maps 当 plane_hypotheses 读 ——
   不报错、不崩溃,只是结果错。实测表现:传播后与真值相关系数 0.825,
   过一遍 depth_and_normal 掉到 0.208。

   这就是 C5「binding 布局必须在转译期冻结」的具体含义:
   **不是"写死顺序"就够了,必须导出一张 per-kernel 的名字→索引表给 host。**

做法:naga 的 MSL 输出保留变量名且按 entry point 生成,顺序就是
      spirv-cross 分配 MSL index 的顺序(两者都按原始 binding 升序)。
      唯一差异是 naga 会额外加 _mslBufferSizes,spirv-cross 不加 ⇒ 剔掉它。
"""
import json, re, subprocess, sys, os

wgsl, out_json = sys.argv[1], sys.argv[2]
entries = [m.group(1) for m in re.finditer(
    r'@compute[^\n]*\n\s*fn\s+(\w+)', open(wgsl, encoding='utf-8').read())]

SKIP = {"_buffer_sizes", "_mslBufferSizes"}
result = {}
for k in entries:
    tmp = f"/tmp/_bm_{k}.metal"
    subprocess.run(["naga", "--entry-point", k, "--shader-stage", "comp", wgsl, tmp],
                   check=True, capture_output=True)
    src = open(tmp, encoding='utf-8').read()
    m = re.search(r'kernel void ' + k + r'\((.*?)\n\) \{', src, re.S)
    if not m:
        print(f"⚠️  {k}: 未能解析签名"); continue
    bufs, texs, samps = [], [], []
    for line in m.group(1).split("\n"):
        line = line.strip().lstrip(",").strip()
        # ⚠️ naga 会给重名变量加后缀(costs → costs_2),必须剥掉再匹配
        def strip_suffix(n):
            return re.sub(r'_\d+$', '', n)
        mm = re.match(r'(?:constant|device)\s+.*?&\s*(\w+)\s*\[\[', line)
        if mm and strip_suffix(mm.group(1)) not in SKIP:
            bufs.append(strip_suffix(mm.group(1))); continue
        # ⚠️ 纹理类型里有模板参数(含空格),不能用 \S* —— 抓 [[ 之前的最后一个标识符
        mm = re.match(r'metal::texture.*?\s(\w+)\s*\[\[', line)
        if mm: texs.append(strip_suffix(mm.group(1))); continue
        mm = re.match(r'metal::sampler\s+(\w+)\s*\[\[', line)
        if mm: samps.append(strip_suffix(mm.group(1)))
    result[k] = {"buffers": bufs, "textures": texs, "samplers": samps}
    os.remove(tmp)

json.dump(result, open(out_json, "w"), indent=2)
# 同时出一份 host 好解析的扁平文本:kernel|buf,buf,..|tex,..|smp,..
with open(out_json.replace(".json", ".txt"), "w") as fh:
    for k, v in result.items():
        fh.write(f"{k}|{','.join(v['buffers'])}|{','.join(v['textures'])}|{','.join(v['samplers'])}\n")
print(f"→ {out_json}  ({len(result)} 个 kernel)")
for k, v in result.items():
    print(f"   {k:<28} buf={len(v['buffers'])} tex={len(v['textures'])} smp={len(v['samplers'])}")
