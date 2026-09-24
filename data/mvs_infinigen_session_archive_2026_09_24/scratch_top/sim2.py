import math
D=48
def norm(v):
    s=sum(v); return [x/s for x in v]
def gauss(mu,s,w=1.0): return [w*math.exp(-0.5*((i-mu)/s)**2) for i in range(D)]
def add(a,b): return [x+y for x,y in zip(a,b)]

def sm_tol(p,k=2,tol=0.999):          # user's implementation as written
    t=max(p); mode=[i for i in range(D) if p[i]>=t*tol]
    nb=set(j for i in mode for j in range(max(0,i-k),min(D,i+k+1)))
    return sum(p[i] for i in range(D) if i not in nb)

def sm_argmax(p,k=2):                  # hard argmax, single mode
    m=p.index(max(p))
    nb=set(range(max(0,m-k),min(D,m+k+1)))
    return sum(p[i] for i in range(D) if i not in nb)

def one_minus_PRB(p): return 1.0-max(p)      # Hu&Mordohai Eq.6 complement (k=0)

def PER(p,s=1.0):                             # Merrell'07 Eq.1 sum / Haeusler PER, cost=-log p
    c=[-math.log(max(x,1e-30)) for x in p]; c1=min(c); d0=c.index(c1)
    return sum(math.exp(-((c[d]-c1)**2)/s**2) for d in range(D) if d!=d0)

def entropy(p): return -sum(x*math.log(max(x,1e-30)) for x in p)

cases={
 "A unimodal sharp (20)":        gauss(20,1.0),
 "B unimodal broad (20)":        gauss(20,4.0),
 "C bimodal 70/30 (20,34)":      add(gauss(20,1,.7),gauss(34,1,.3)),
 "D bimodal 50/50 (20,34)":      add(gauss(20,1,.5),gauss(34,1,.5)),
 "E bimodal near-tie":           add(gauss(20,1,.5000),gauss(34,1,.4999)),
 "F flat":                       [1.0]*D,
}
print(f"{'case':30s}{'sm(tol.999)':>12s}{'sm(argmax)':>11s}{'1-PRB':>8s}{'PER':>8s}{'entropy':>9s}")
for n,v in cases.items():
    p=norm(v)
    print(f"{n:30s}{sm_tol(p):12.4f}{sm_argmax(p):11.4f}{one_minus_PRB(p):8.4f}{PER(p):8.3f}{entropy(p):9.3f}")
