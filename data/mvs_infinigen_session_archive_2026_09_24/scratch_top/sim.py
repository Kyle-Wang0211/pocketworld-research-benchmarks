import math
D=48
def norm(v):
    s=sum(v); return [x/s for x in v]
def gauss(mu,s,w=1.0):
    return [w*math.exp(-0.5*((i-mu)/s)**2) for i in range(D)]
def add(a,b): return [x+y for x,y in zip(a,b)]

def second_mass(p,k=2,tol=0.999):
    top1=max(p)
    mode=[i for i in range(D) if p[i]>=top1*tol]
    nb=set()
    for i in mode:
        for j in range(max(0,i-k),min(D,i+k+1)): nb.add(j)
    return sum(p[i] for i in range(D) if i not in nb), len(mode)

def photo_conf(p):
    e=sum(i*p[i] for i in range(D))
    idx=min(max(int(math.floor(e)),0),D-1)
    return sum(p[i] for i in range(max(0,idx-1),min(D,idx+3))), idx

cases={
 "A unimodal sharp  (mode 20)":      gauss(20,1.0),
 "B unimodal broad  (mode 20)":      gauss(20,4.0),
 "C bimodal 70/30   (20 & 34)":      add(gauss(20,1.0,0.7),gauss(34,1.0,0.3)),
 "D bimodal 50/50   (20 & 34)":      add(gauss(20,1.0,0.5),gauss(34,1.0,0.5)),
 "E bimodal near-tie (0.500/0.4999)":add(gauss(20,1.0,0.5000),gauss(34,1.0,0.4999)),
 "F flat":                           [1.0]*D,
}
print(f"{'case':36s}{'2nd_mass':>10s}{'#modepl':>9s}{'photoconf':>11s}{'1-photo':>9s}{'E_idx':>7s}")
for n,v in cases.items():
    p=norm(v); sm,nm=second_mass(p); pc,idx=photo_conf(p)
    print(f"{n:36s}{sm:10.4f}{nm:9d}{pc:11.4f}{1-pc:9.4f}{idx:7d}")
