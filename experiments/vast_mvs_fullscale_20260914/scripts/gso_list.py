"""拉 GSO 全量模型清单(Gazebo Fuel 公开 API,无需登录)。"""
import json, urllib.request, time
out = []
for page in range(1, 60):
    u = f"https://fuel.gazebosim.org/1.0/GoogleResearch/models?page={page}&per_page=100"
    try:
        d = json.loads(urllib.request.urlopen(u, timeout=30).read())
    except Exception as e:
        print("  page", page, "err", str(e)[:50]); break
    if not d: break
    out += [m["name"] for m in d]
    print("  page %2d  累计 %d" % (page, len(out)), flush=True)
    if len(d) < 100: break
    time.sleep(0.3)
json.dump(out, open("/root/gso_models.json", "w"))
print("共", len(out), "个模型 -> /root/gso_models.json")
