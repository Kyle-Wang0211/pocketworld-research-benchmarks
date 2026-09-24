import os
p = "/root/smoke_loader.py"
s = open(p).read()
old = 'ds = MVSDataset("/root/monotrain", "lists/full/train.txt", "train", 8, 384)\n'
new = ('LISTS = os.environ.get("LISTS", "full")\n'
       'ds = MVSDataset("/root/monotrain", "lists/%s/train.txt" % LISTS, "train", 8, 384)\n')
assert s.count(old) == 1, s.count(old)
open(p, "w").write(s.replace(old, new))
print("smoke_loader LISTS env ok")
