"""给定 scan 名单,每个 scan 抽中间那张图,拼接触印样。用法: contact_any.py <bucket> <out.jpg> [cols] [thumb_w]"""
import sys, os, glob, json, math
from PIL import Image, ImageDraw
ROOT = "/root/monotrain"
pool = json.load(open("/root/indoor_pool.json"))
which = sys.argv[1]; out = sys.argv[2]
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 24
W = int(sys.argv[4]) if len(sys.argv) > 4 else 130
H = W * 3 // 4
if which in pool: scans = pool[which]
else:
    import re
    scans = sorted(d for d in os.listdir(ROOT) if d.startswith(which))
LAB = 12
r = math.ceil(len(scans) / cols)
sheet = Image.new("RGB", (cols*W, r*(H+LAB)), (20,20,20))
d = ImageDraw.Draw(sheet)
ok = 0
for i, s in enumerate(scans):
    g = sorted(glob.glob(f"{ROOT}/{s}/blended_images/*.jpg"))
    if not g: continue
    try: im = Image.open(g[len(g)//2]).convert("RGB").resize((W, H))
    except Exception: continue
    x, y = (i % cols)*W, (i//cols)*(H+LAB)
    sheet.paste(im, (x, y+LAB))
    d.text((x+2, y+1), str(i), fill=(200,200,200))
    ok += 1
sheet.save(out, quality=85)
print("saved", out, sheet.size, ok, "/", len(scans))
json.dump(scans, open(out + ".idx.json", "w"))
