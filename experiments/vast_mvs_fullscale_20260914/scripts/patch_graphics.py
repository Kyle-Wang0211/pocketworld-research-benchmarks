import re, pathlib
p = pathlib.Path("/root/lf_probe/dep_graphics/src/graphics/utils.py")
s = p.read_text()
old = "from skimage.measure import marching_cubes_lewiner"
new = ("try:\n    from skimage.measure import marching_cubes_lewiner\n"
       "except ImportError:  # skimage >= 0.19 renamed it; same signature\n"
       "    from skimage.measure import marching_cubes as marching_cubes_lewiner")
if old in s and "except ImportError" not in s:
    p.write_text(s.replace(old, new)); print("patched graphics/utils.py")
else:
    print("already patched or pattern missing")
