import sys, collections
sys.path.insert(0,"/root/MonoMVSNet")
import os; os.chdir("/root/MonoMVSNet")
from models.monomvsnet import MonoMVSNet
m = MonoMVSNet()
g = collections.Counter(); t = collections.Counter()
for n,p in m.named_parameters():
    top = n.split(".")[0]
    g[top] += p.numel()
    if p.requires_grad: t[top] += p.numel()
print("%-18s %12s %12s" % ("module", "params", "trainable"))
for k,v in g.most_common():
    print("  %-16s %10.2fM %10.2fM" % (k, v/1e6, t[k]/1e6))
print("  %-16s %10.2fM %10.2fM" % ("TOTAL", sum(g.values())/1e6, sum(t.values())/1e6))
