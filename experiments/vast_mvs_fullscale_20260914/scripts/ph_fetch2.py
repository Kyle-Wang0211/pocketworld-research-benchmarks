"""拉 Poly Haven 室内 HDRI + 地面材质(CC0)。带 UA,否则 API 返回 403。"""
import json, os, random, time
import urllib.request as U
OUT = "/root/ph_assets"
os.makedirs(f"{OUT}/hdri", exist_ok=True); os.makedirs(f"{OUT}/tex", exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) dataset-fetch/1.0"}

def jget(u, tries=3):
    for i in range(tries):
        try:
            return json.loads(U.urlopen(U.Request(u, headers=UA), timeout=60).read())
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(1.5)

def dl(u, dst, tries=3):
    for i in range(tries):
        try:
            with U.urlopen(U.Request(u, headers=UA), timeout=180) as r, open(dst, "wb") as f:
                f.write(r.read())
            return True
        except Exception:
            if i == tries - 1: return False
            time.sleep(1.5)

hd = json.load(open("/root/ph_hdris.json"))
indoor = [k for k, v in hd.items() if "indoor" in (v.get("categories") or [])]
print("indoor HDRI 候选:", len(indoor), flush=True)
random.Random(7).shuffle(indoor)
N1 = int(os.environ.get("N_HDRI", "24")); ok = 0
for s in indoor:
    if ok >= N1: break
    dst = f"{OUT}/hdri/{s}.hdr"
    if os.path.exists(dst) and os.path.getsize(dst) > 1000: ok += 1; continue
    try:
        u = jget(f"https://api.polyhaven.com/files/{s}")["hdri"]["2k"]["hdr"]["url"]
    except Exception as e:
        print("  meta fail", s, str(e)[:40]); continue
    if dl(u, dst):
        ok += 1
        if ok % 6 == 0 or ok <= 2: print("  HDRI", ok, s, os.path.getsize(dst)//1024, "KB", flush=True)

tx = jget("https://api.polyhaven.com/assets?t=textures")
want = [k for k, v in tx.items() if any(c in (v.get("categories") or []) for c in ("floor","wood","concrete","fabric"))]
print("地面材质候选:", len(want), flush=True)
random.Random(7).shuffle(want)
N2 = int(os.environ.get("N_TEX", "8")); ok2 = 0
for s in want:
    if ok2 >= N2: break
    dst = f"{OUT}/tex/{s}.jpg"
    if os.path.exists(dst) and os.path.getsize(dst) > 1000: ok2 += 1; continue
    try:
        fl = jget(f"https://api.polyhaven.com/files/{s}")
        u = (fl.get("Diffuse") or fl.get("diffuse") or fl.get("albedo"))["2k"]["jpg"]["url"]
    except Exception as e:
        print("  tex meta fail", s, str(e)[:40]); continue
    if dl(u, dst):
        ok2 += 1; print("  TEX", ok2, s, os.path.getsize(dst)//1024, "KB", flush=True)
print("完成: HDRI", ok, "| 地面材质", ok2)
