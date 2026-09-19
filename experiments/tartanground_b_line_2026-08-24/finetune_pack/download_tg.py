#!/usr/bin/env python3.11
"""TartanGround 补齐下载(House/Office 的 depth + metadata(pose) + 缺的 image)。

数据源:HuggingFace dataset repo `theairlabcmu/TartanGround`
(出处:tartanairpy/tartanair/downloader.py:148-149 HuggingfaceDownloader,
 bucket_name='tartanground' -> repo_id="theairlabcmu/TartanGround")

用 hf_hub_download 逐文件下载(自带断点续传),下载完成后与 repo 侧
的 size(HfApi.get_paths_info)逐字节核对,不一致直接报错并重试。

用法:
    python3.11 download_tg.py --out <dir> [--tier 1|2] [--retries 5]
"""
import argparse
import os
import sys
import time

from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "theairlabcmu/TartanGround"

# tier 1 = 转换第一版弹药包的最小必要集合
TIER1 = [
    # House P0000:image 已在 step0/unzipped/House,但为自洽起见一并重下(仅 0.13G)
    "House/Data_omni/P0000/image_lcam_front.zip",
    "House/Data_omni/P0000/depth_lcam_front.zip",
    "House/Data_omni/P0000/metadata.zip",
    # Office 第二条轨迹,增加多样性
    "Office/Data_omni/P0001/image_lcam_front.zip",
    "Office/Data_omni/P0001/depth_lcam_front.zip",
    "Office/Data_omni/P0001/metadata.zip",
]

# tier 2 = 多样性追加(仍在 10GB 预算内)
TIER2 = [
    "House/Data_omni/P0001/image_lcam_front.zip",
    "House/Data_omni/P0001/depth_lcam_front.zip",
    "House/Data_omni/P0001/metadata.zip",
    "House/Data_omni/P0002/image_lcam_front.zip",
    "House/Data_omni/P0002/depth_lcam_front.zip",
    "House/Data_omni/P0002/metadata.zip",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tier", type=int, default=2, choices=[1, 2])
    ap.add_argument("--retries", type=int, default=6)
    a = ap.parse_args()

    files = list(TIER1) + (list(TIER2) if a.tier >= 2 else [])
    os.makedirs(a.out, exist_ok=True)

    api = HfApi()
    infos = api.get_paths_info(REPO_ID, files, repo_type="dataset")
    want = {}
    for it in infos:
        sz = getattr(it, "size", None)
        lfs = getattr(it, "lfs", None)
        if lfs is not None and getattr(lfs, "size", None):
            sz = lfs.size
        want[it.path] = sz
    missing = [f for f in files if f not in want]
    if missing:
        print("[fatal] repo 中不存在: %s" % missing, file=sys.stderr)
        sys.exit(2)

    total = sum(want[f] for f in files)
    print("[info] 计划下载 %d 个文件, 合计 %.3f GB" % (len(files), total / 1e9), flush=True)

    ok, bad = [], []
    for f in files:
        exp = want[f]
        dst = os.path.join(a.out, f)
        if os.path.exists(dst) and os.path.getsize(dst) == exp:
            print("[skip] %s 已完整 (%d B)" % (f, exp), flush=True)
            ok.append(f)
            continue
        for k in range(a.retries):
            try:
                t0 = time.time()
                p = hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename=f,
                                    local_dir=a.out)
                got = os.path.getsize(p)
                if got != exp:
                    raise IOError("size mismatch: got %d expect %d" % (got, exp))
                print("[ok] %s %d B in %.1fs" % (f, got, time.time() - t0), flush=True)
                ok.append(f)
                break
            except Exception as e:  # noqa: BLE001
                print("[retry %d/%d] %s: %s" % (k + 1, a.retries, f, e), flush=True)
                time.sleep(5 * (k + 1))
        else:
            bad.append(f)

    print("[done] ok=%d bad=%d" % (len(ok), len(bad)), flush=True)
    if bad:
        print("[fatal] 失败: %s" % bad, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
