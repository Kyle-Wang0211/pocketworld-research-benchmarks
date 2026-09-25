#!/usr/bin/env python3
"""arcmp.py A.a B.a [--norm OLD=NEW ...] : member-by-position comparison of two BSD ar archives."""
import sys
def members(path):
    d=open(path,'rb').read(); assert d[:8]==b'!<arch>\n'; i=8; out=[]
    while i<len(d):
        h=d[i:i+60]; name=h[:16].decode().strip(); size=int(h[48:58]); i+=60
        body=d[i:i+size]
        if name.startswith('#1/'):
            n=int(name[3:]); name=body[:n].rstrip(b'\0').decode(); body=body[n:]
        out.append((name,body)); i+=size+(size&1)
    return out
a=members(sys.argv[1]); b=members(sys.argv[2])
norms=[]
for arg in sys.argv[3:]:
    if '=' in arg:
        o,n=arg.split('=',1); norms.append((n.encode(),o.encode()))
def norm(x):
    for n,o in norms: x=x.replace(n,o)
    return x
a=[m for m in a if not m[0].startswith('__.SYMDEF')]; b=[m for m in b if not m[0].startswith('__.SYMDEF')]
print('count',len(a),len(b),'order_equal',[m[0] for m in a]==[m[0] for m in b])
same=0
for (na,xa),(nb,xb) in zip(a,b):
    if xa==norm(xb): same+=1
    else: print('DIFF',na,nb,len(xa),len(xb))
print('identical',same,'of',min(len(a),len(b)))
