from PIL import Image, ImageDraw
import math
rows = [l.rstrip("\n").split("\t") for l in open("/root/ta_env_samples.txt") if l.strip()]
W, H = 320, 240
cols = 6
n = len(rows)
r = math.ceil(n / cols)
sheet = Image.new("RGB", (cols*W, r*(H+22)), (16,16,16))
d = ImageDraw.Draw(sheet)
for i, (env, path) in enumerate(rows):
    try: im = Image.open(path).convert("RGB").resize((W, H))
    except Exception: continue
    x, y = (i % cols)*W, (i//cols)*(H+22)
    sheet.paste(im, (x, y+22))
    d.rectangle([x, y, x+W, y+22], fill=(0,0,0))
    d.text((x+5, y+5), env, fill=(255,255,255))
sheet.save("/root/ta_contact.jpg", quality=88)
print("saved", sheet.size, n, "envs")
