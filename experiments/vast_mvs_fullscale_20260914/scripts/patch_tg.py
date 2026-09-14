p = "/root/tartanground2mvsnet.py"
s = open(p).read()
old = 'DIFFMVS_DIR = "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs"'
new = ('DIFFMVS_DIR = os.environ.get("DIFFMVS_DIR",\n'
       '    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")\n'
       'print("[DIFFMVS_DIR]", DIFFMVS_DIR, "exists=", os.path.isdir(DIFFMVS_DIR), flush=True)')
assert s.count(old) == 1, s.count(old)
open(p, "w").write(s.replace(old, new))
print("patched")
