import math
D=48
def norm(v): s=sum(v); return [x/s for x in v]
def g(mu,s,w=1.0): return [w*math.exp(-0.5*((i-mu)/s)**2) for i in range(D)]
def add(a,b): return [x+y for x,y in zip(a,b)]

def E(p): return sum(i*p[i] for i in range(D))

def win_mass(p, center, k):           # symmetric +-k window, sum
    lo,hi=max(0,int(center)-k),min(D,int(center)+k+1)
    return sum(p[lo:hi])

def visnet_w2(p):                     # Vis-MVSNet soft_argmin(window=2): |i - E| <= 2, E continuous
    e=E(p); return sum(p[i] for i in range(D) if abs(i-e)<=2)

cases={
 "A unimodal sharp (20)":        g(20,1.0),
 "B unimodal broad (20)":        g(20,4.0),
 "C bimodal 70/30 (20,34)":      add(g(20,1,.7),g(34,1,.3)),
 "D bimodal 50/50 (20,34)":      add(g(20,1,.5),g(34,1,.5)),
 "F flat":                       [1.0]*D,
}
print(f"{'case':28s}{'1-conf(n=5,E)':>14s}{'1-VisMVS(w2,E)':>15s}{'1-win(argmax,2)':>16s}")
for n,v in cases.items():
    p=norm(v); e=int(math.floor(E(p))); m=p.index(max(p))
    print(f"{n:28s}{1-win_mass(p,e,2):14.4f}{1-visnet_w2(p):15.4f}{1-win_mass(p,m,2):16.4f}")
