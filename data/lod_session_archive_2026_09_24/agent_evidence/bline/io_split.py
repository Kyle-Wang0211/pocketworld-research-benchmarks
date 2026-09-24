import json,sys,statistics as st
d=json.load(open(sys.argv[1]))
def q(v,f):
    v=sorted(v); return v[min(len(v)-1,max(0,round(f*(len(v)-1))))]
arms={}
for b in d['blocks']:
    lab=b['label'].rstrip('2') if b['label'] not in ('COLD','FIRST') else b['label']
    if lab in ('COLD',): continue
    io=[b['load_ms'][i]+b['upload_ms'][i] for i in range(30,len(b['wall_ms']))]
    rest=[b['wall_ms'][i]-b['load_ms'][i]-b['upload_ms'][i] for i in range(30,len(b['wall_ms']))]
    wall=b['wall_ms'][30:]
    pts=b['pts'][30:]
    a=arms.setdefault(lab,{'io':[],'rest':[],'wall':[],'pts':[]})
    a['io']+=io; a['rest']+=rest; a['wall']+=wall; a['pts']+=pts
for k,a in arms.items():
    n=len(a['io'])
    over=[i for i in range(n) if a['wall'][i]>1000/30]
    ioover=[i for i in over if a['io'][i]>0.5*a['wall'][i]]
    # frames that would be under 33.3 without their io part
    rescued=[i for i in over if a['wall'][i]-a['io'][i]<=1000/30]
    print(f"{k:5s} n={n} io_ms p50 {q(a['io'],.5):5.2f} p95 {q(a['io'],.95):5.2f} p99 {q(a['io'],.99):6.2f} max {max(a['io']):6.1f} | io>8ms {sum(x>8 for x in a['io'])/n*100:5.2f}% | rest p95 {q(a['rest'],.95):5.2f} | >33ms {len(over)/n*100:5.2f}% of which io>half {len(ioover)}, io-removable {len(rescued)} | pts mean {st.mean(a['pts'])/1e6:.2f}M")
