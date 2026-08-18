#!/usr/bin/env python3
"""稠密生长播放器:逐帧时间轴,不是四连拍。

数据 = 实测冻结调度(streaming_fuse_md5 的 schedule.json)+ 全量稠密的 per-ref 块
(块长 = 每帧 final mask 真像素数,拼装顺序与 dense_P16k.ply 逐字节一致,MD5 已证)。

做法:把显示点按 (冻结步, ref) 排序拼一条大缓冲,t 时刻只画前 cum[t] 个点
—— 一次 drawArrays 就是一个时刻,滑杆/播放随便扫,零重建。
未冻结的 23 帧记为 t=133(拍完收尾)。显示预算 45 万点,uint16 量化。
"""
import base64
import json
import numpy as np
from pathlib import Path
from PIL import Image

D = Path("/Users/kaidongwang/Documents/progecttwo/_host_experiments/streaming_fuse_md5_20260818")
P = Path("/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818")
BUDGET = 450_000

sched = json.load(open(D / "schedule.json"))
frozen = [(s if (s is not None and s >= 0) else 133) for s in sched["frozen_at"]]

lens = []
for i in range(132):
    m = np.array(Image.open(P / "out_P16k" / "mask" / f"{i:08d}_final.png"))
    lens.append(int((m > 0).sum()))
lens = np.array(lens)
assert lens.sum() == 30_640_053
offs = np.concatenate([[0], np.cumsum(lens)])

with open(P / "dense_P16k.ply", "rb") as f:
    while True:
        if f.readline().strip() == b"end_header":
            break
    dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                   ("r", "u1"), ("g", "u1"), ("b", "u1")])
    dense = np.fromfile(f, dtype=dt, count=int(lens.sum()))

rng = np.random.default_rng(20260818)
order = sorted(range(132), key=lambda i: (frozen[i], i))
chunks, steps = [], []
for i in order:
    take = max(200, int(BUDGET * lens[i] / lens.sum()))
    idx = np.arange(offs[i], offs[i + 1])
    if len(idx) > take:
        idx = rng.choice(idx, take, replace=False)
    chunks.append(dense[idx])
    steps.append((frozen[i], len(idx)))
allpts = np.concatenate(chunks)
print(f"显示点 {len(allpts):,}")

# 每步的累计可见点数 cum[t], t=0..133
cum = np.zeros(134, dtype=np.int64)
acc = 0
si = 0
flat = []
for (s, k) in steps:
    flat.append((s, k))
for t in range(134):
    acc = sum(k for (s, k) in flat if s <= t)
    cum[t] = acc
frames_at = [sum(1 for s in frozen if s <= t) for t in range(134)]

xyz = np.stack([allpts["x"], allpts["y"], allpts["z"]], 1).astype(np.float64)
lo = xyz.min(0); span = np.maximum(xyz.max(0) - lo, 1e-6)
q = np.round((xyz - lo) / span * 65535).clip(0, 65535).astype("<u2")
rgb = np.stack([allpts["r"], allpts["g"], allpts["b"]], 1).astype(np.uint8)
ctr = np.median(xyz, 0)
radius = float(np.percentile(np.linalg.norm(xyz - ctr, axis=1), 95))

meta = dict(cum=cum.tolist(), frames=frames_at,
            lo=lo.tolist(), span=span.tolist(),
            cx=float(ctr[0]), cy=float(ctr[1]), cz=float(ctr[2]), radius=radius,
            n=len(allpts))

html = """<!doctype html>
<meta charset="utf-8">
<title>稠密生长播放器 — 逐帧</title>
<style>
:root{--bg:#0e0f12;--fg:#e8e8ea;--dim:#9aa0a6;--line:#26282e}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:13px/1.5 -apple-system,"PingFang SC",sans-serif}
header{padding:10px 14px;border-bottom:1px solid var(--line)}
h1{font-size:15px;margin:0 0 4px}.hint{color:var(--dim);font-size:12px}
#bar{display:flex;gap:12px;align-items:center;padding:8px 14px;border-bottom:1px solid var(--line)}
#t{flex:1}
button{background:#1b1d22;color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:4px 14px;font-size:13px;cursor:pointer}
#stat{min-width:300px;color:var(--dim)}#stat b{color:var(--fg)}
canvas{display:block;width:100%;height:calc(100% - 118px)}
</style>
<header><h1>稠密生长 — 逐帧重放(实测冻结调度)</h1>
<div class="hint">t=拍摄进度(第几帧)。每一步新冻结的帧,它的稠密块当步出现;t=133 是拍完收尾(23 帧尾融+59 帧重融,≈17s)。显示 __N__ 点(全量 30.6M 按帧比例抽)。拖拽旋转 · 滚轮缩放 · 右键平移。</div></header>
<div id="bar">
<button id="play">▶ 播放</button>
<input id="t" type="range" min="0" max="133" step="1" value="0">
<span id="stat"></span>
</div>
<canvas id="cv"></canvas>
<script>
const META=__META__;
const b64=s=>{const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u};
const XYZ=b64("__XYZ__"),RGB=b64("__RGB__");
const cv=document.getElementById('cv'),gl=cv.getContext('webgl',{antialias:true});
const VS=`attribute vec3 p;attribute vec3 c;uniform mat4 mvp;uniform vec3 lo,span;uniform float ps;varying vec3 vc;
void main(){vec3 w=lo+p*span/65535.0;gl_Position=mvp*vec4(w,1.0);gl_PointSize=ps;vc=c;}`;
const FS=`precision mediump float;varying vec3 vc;void main(){vec2 d=gl_PointCoord-vec2(0.5);if(dot(d,d)>0.25)discard;gl_FragColor=vec4(vc,1.0);}`;
function sh(t,s){const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);
if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(o);return o}
const pr=gl.createProgram();gl.attachShader(pr,sh(gl.VERTEX_SHADER,VS));gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,FS));
gl.linkProgram(pr);gl.useProgram(pr);
const bp=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bp);gl.bufferData(gl.ARRAY_BUFFER,new Uint16Array(XYZ.buffer,XYZ.byteOffset,META.n*3),gl.STATIC_DRAW);
const ap=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(ap);gl.vertexAttribPointer(ap,3,gl.UNSIGNED_SHORT,false,0,0);
const bc=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bc);gl.bufferData(gl.ARRAY_BUFFER,RGB,gl.STATIC_DRAW);
const ac=gl.getAttribLocation(pr,'c');gl.enableVertexAttribArray(ac);gl.vertexAttribPointer(ac,3,gl.UNSIGNED_BYTE,true,0,0);
gl.enable(gl.DEPTH_TEST);gl.clearColor(0.055,0.059,0.071,1);
gl.uniform3fv(gl.getUniformLocation(pr,'lo'),META.lo);gl.uniform3fv(gl.getUniformLocation(pr,'span'),META.span);
const uMvp=gl.getUniformLocation(pr,'mvp'),uPs=gl.getUniformLocation(pr,'ps');
const cam={az:0.6,el:0.35,dist:META.radius*2.4,tx:META.cx,ty:META.cy,tz:META.cz};
const sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]],dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const norm=a=>{const l=Math.hypot(...a)||1;return[a[0]/l,a[1]/l,a[2]/l]};
function mul(a,b){const o=new Float32Array(16);for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k];o[i*4+j]=s}return o}
function persp(f,as,n,fa){const t=1/Math.tan(f/2);return new Float32Array([t/as,0,0,0,0,t,0,0,0,0,(fa+n)/(n-fa),-1,0,0,2*fa*n/(n-fa),0])}
function lookAt(e,c,u){const z=norm(sub(e,c)),x=norm(cross(u,z)),y=cross(z,x);
return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,e),-dot(y,e),-dot(z,e),1])}
let T=0,playing=false;
const slider=document.getElementById('t'),stat=document.getElementById('stat'),btn=document.getElementById('play');
function setT(t){T=Math.max(0,Math.min(133,t));slider.value=T;
const full=30640053,pts=META.cum[T],fr=META.frames[T];
stat.innerHTML=`t=<b>${T===133?'收尾':T}</b> · 已融 <b>${fr}</b>/132 帧 · 可见 <b>${(pts/META.n*full/1e6).toFixed(1)}M</b> 点(显示 ${pts.toLocaleString()})`;}
slider.oninput=e=>{playing=false;btn.textContent='▶ 播放';setT(+e.target.value)};
btn.onclick=()=>{playing=!playing;btn.textContent=playing?'⏸ 暂停':'▶ 播放';if(playing&&T>=133)setT(0)};
let last=0;
function draw(ts){
if(playing&&ts-last>110){setT(T+1);last=ts;if(T>=133){playing=false;btn.textContent='▶ 播放'}}
const w=cv.clientWidth,h=cv.clientHeight,dpr=Math.min(devicePixelRatio,2);
if(cv.width!==w*dpr){cv.width=w*dpr;cv.height=h*dpr}
gl.viewport(0,0,cv.width,cv.height);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
const ce=[cam.tx+cam.dist*Math.cos(cam.el)*Math.sin(cam.az),cam.ty+cam.dist*Math.sin(cam.el),cam.tz+cam.dist*Math.cos(cam.el)*Math.cos(cam.az)];
gl.uniformMatrix4fv(uMvp,false,mul(persp(1.0,w/h,META.radius*0.005,META.radius*40),lookAt(ce,[cam.tx,cam.ty,cam.tz],[0,1,0])));
gl.uniform1f(uPs,2*dpr);
gl.drawArrays(gl.POINTS,0,META.cum[T]);
requestAnimationFrame(draw)}
let drag=0,px=0,py=0;
cv.onmousedown=e=>{drag=e.button===2?2:1;px=e.clientX;py=e.clientY};
window.onmouseup=()=>drag=0;window.oncontextmenu=e=>e.preventDefault();
window.onmousemove=e=>{if(!drag)return;const dx=e.clientX-px,dy=e.clientY-py;px=e.clientX;py=e.clientY;
if(drag===1){cam.az-=dx*0.006;cam.el=Math.max(-1.5,Math.min(1.5,cam.el+dy*0.006))}
else{const s=cam.dist*0.0015;cam.tx-=dx*s*Math.cos(cam.az);cam.tz+=dx*s*Math.sin(cam.az);cam.ty+=dy*s}};
cv.onwheel=e=>{e.preventDefault();cam.dist*=Math.exp(e.deltaY*0.001);cam.dist=Math.max(META.radius*0.2,Math.min(META.radius*10,cam.dist))};
setT(0);requestAnimationFrame(draw);
</script>"""

out = Path("grow_player.html")
out.write_text(html
    .replace("__META__", json.dumps(meta))
    .replace("__XYZ__", base64.b64encode(q.tobytes()).decode())
    .replace("__RGB__", base64.b64encode(rgb.tobytes()).decode())
    .replace("__N__", f"{len(allpts):,}"))
print(f"已写 {out}  {out.stat().st_size/1e6:.1f} MB")
