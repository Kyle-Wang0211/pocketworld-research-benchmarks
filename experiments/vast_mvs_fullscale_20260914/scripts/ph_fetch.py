"""拉 Poly Haven 的室内 HDRI + 地面材质(全部 CC0,商用无需署名)。
判据:只取 categories 含 'indoor' 的 HDRI(产品场景=室内桌面拍手办)。
"""
import json, os, urllib.request, random
OUT = "/root/ph_assets"
os.makedirs(f"{OUT}/hdri", exist_ok=True)
os.makedirs(f"{OUT}/tex", exist_ok=True)

def get(u):
    return json.loads(urllib.request.urlopen(u, timeout=60).read())

hd = json.load(open("/root/ph_hdris.json"))
indoor = [k for k, v in hd.items() if "indoor" in (v.get("categories") or [])]
print("indoor HDRI:", len(indoor))
random.Random(7).shuffle(indoor)
N_HDRI = int(os.environ.get("N_HDRI", "24"))
ok = 0
for s in indoor:
    if ok >= N_HDRI: break
    dst = f"{OUT}/hdri/{s}.hdr"
    if os.path.exists(dst): ok += 1; continue
    try:
        f = get(f"https://api.polyhaven.com/files/{s}")
        url = f["hdri"]["2k"]["hdr"]["url"]          # 2k 够用,文件小
        urllib.request.urlretrieve(url, dst); ok += 1
        print("  HDRI", ok, s, os.path.getsize(dst) // 1024, "KB", flush=True)
    except Exception as e:
        print("  skip", s, str(e)[:50])
# 地面材质:取 'floor'/'wood'/'concrete' 类
tx = get("https://api.polyhaven.com/assets?t=textures")
want = [k for k, v in tx.items()
        if any(c in (v.get("categories") or []) for c in ("floor", "wood", "concrete", "fabric"))]
print("候选地面材质:", len(want))
random.Random(7).shuffle(want)
N_TEX = int(os.environ.get("N_TEX", "8"))
ok2 = 0
for s in want:
    if ok2 >= N_TEX: break
    dst = f"{OUT}/tex/{s}_diff.jpg"
    if os.path.exists(dst): ok2 += 1; continue
    try:
        f = get(f"https://api.polyhaven.com/files/{s}")
        url = f["Diffuse"]["2k"]["jpg"]["url"]
        urllib.request.urlretrieve(url, dst); ok2 += 1
        print("  TEX", ok2, s, os.path.getsize(dst) // 1024, "KB", flush=True)
    except Exception as e:
        print("  skip tex", s, str(e)[:50])
print("完成: HDRI", ok, "地面材质", ok2)
