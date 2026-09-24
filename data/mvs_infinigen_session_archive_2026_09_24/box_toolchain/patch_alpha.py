import sys
p = "/root/sp2mvsnet.py"; s = open(p).read()
old = ('            a = np.asarray(im)[:, :, 3]\n'
       '            assert (a == 255).all(), "%s f%d 存在非不透明像素(alpha min=%d)" % (scene, fid, a.min())\n')
new = ('            a = np.asarray(im)[:, :, 3]\n'
       '            # 官方 mvsanywhere fork generic_mvs_dataset.py:465 `image = image[:3]` 直接丢 alpha, 不看值\n'
       '            # (09-14 scene_28608 f0 83% 像素 alpha 251-254 撞上原断言) -> 只记录, 照官方丢掉\n'
       '            if (a != 255).any():\n'
       '                print("[alpha<255] %s f%d min=%d frac=%.3f" % (scene, fid, a.min(), (a != 255).mean()), flush=True)\n')
assert s.count(old) == 1, s.count(old)
open(p, "w").write(s.replace(old, new)); print("alpha patch ok on", __import__("socket").gethostname())
