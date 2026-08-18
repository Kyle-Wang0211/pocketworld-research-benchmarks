#!/usr/bin/env python3
"""白墙翘起法医 — 墙区放大并排页(自包含 HTML)。

四窗:P16k 稠密 / P8k 稠密 / GTO 稠密 / LightGlue 稀疏(全部已在 P16k gauge,
P8k/GTO 用 aligned_*.ply)。裁剪 = 旅行箱正后方白色镶板墙的定向包围盒。
坐标写成墙局部系 (u=沿墙水平, v=沿墙竖直, r=离面):纯刚性旋转+平移,不缩放。
真彩 / 离面热力 双模式;热力 = 蓝(墙后)-灰(贴面)-红(墙前),±0.25 gauge 截断。
"""
import base64, json
from pathlib import Path
import numpy as np

S = Path("/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/wall_forensics_20260818")
OUT = Path("/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/compare_wall.html")
DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])

def stream(p, chunk=3_000_000):
    with open(p,"rb") as f:
        hdr=b""
        while True:
            l=f.readline(); hdr+=l
            if l.strip()==b"end_header": break
        n=int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1]); off=len(hdr)
    M=np.memmap(p,dtype=DT,mode="r",offset=off,shape=(n,))
    for s in range(0,n,chunk):
        d=np.array(M[s:s+chunk])
        yield np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)

nfl=np.load(S/"floor.npy"); up=nfl[:3]
nw=np.array([0.46,-0.679,-0.572]); nw/=np.linalg.norm(nw)
u_=np.cross(up,nw); u_/=np.linalg.norm(u_); v_=np.cross(nw,u_)
DW=4.734
ULO,UHI,VLO,VHI,RLO,RHI=-4.4,2.0,-2.1,2.6,-0.7,0.8

paths = {
 "P16k 稠密":  "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/dense_P16k.ply",
 "P8k 稠密":   "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/aligned_P8k.ply",
 "GTO 稠密":   "/Users/kaidongwang/Documents/progecttwo/_host_experiments/gto_dense_20260818/aligned_GTO.ply",
 "LightGlue 稀疏":"/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/ply_P16KH.ply",
}
CAP=170_000
rng=np.random.default_rng(20260818)
keep=[]
for name,p in paths.items():
    xs=[]; cs=[]
    for xyz,rgb in stream(p):
        r=xyz@nw+DW; pu=xyz@u_; pv=xyz@v_
        m=(pu>ULO)&(pu<UHI)&(pv>VLO)&(pv<VHI)&(r>RLO)&(r<RHI)
        xs.append(np.stack([pu[m],pv[m],r[m]],1)); cs.append(rgb[m])
    X=np.concatenate(xs); C=np.concatenate(cs)
    ntot=len(X)
    if ntot>CAP:
        sel=rng.choice(ntot,CAP,replace=False); X=X[sel]; C=C[sel]
    # 热力色
    t=np.clip(X[:,2]/0.25,-1,1)   # r 离面
    heat=np.empty_like(C)
    # 蓝(-1) -> 灰(0) -> 红(+1)
    neg=np.clip(-t,0,1); pos=np.clip(t,0,1)
    heat[:,0]=np.round(200 - 160*neg + 55*pos).clip(0,255)
    heat[:,1]=np.round(200 - 140*neg - 150*pos).clip(0,255)
    heat[:,2]=np.round(200 + 55*neg - 160*pos).clip(0,255)
    keep.append((name,X,C,heat.astype(np.uint8),ntot))
    print(name,"裁剪内",ntot,"显示",len(X))

lo=np.min([x.min(0) for _,x,_,_,_ in keep],axis=0)
span=np.maximum(np.max([x.max(0) for _,x,_,_,_ in keep],axis=0)-lo,1e-6)
print("量化步长(gauge/轴):",(span/65535).round(6).tolist())

stats=json.load(open(S/"measure_wall.json"))
blob=json.load(open(S/"blob_stats.json"))
key={"P16k 稠密":"P16k","P8k 稠密":"P8k","GTO 稠密":"GTO","LightGlue 稀疏":"sparse"}
ns=np.array(stats["sparse"]["nv"])
STATS={}
for name in paths:
    k=key[name]
    a=np.degrees(np.arccos(min(abs(np.array(stats[k]["nv"])@ns),1.0)))
    STATS[name]=dict(
        pts=f"{stats[k]['n']:,}",
        ang=f"{a:.2f}°",
        rms=f"{stats[k]['rms']*0.42*1000:.1f} mm",
        blob=f"{blob[k]['pct']:.2f}%  ({blob[k]['blob']:,} 点)")
SUB={
 "P16k 稠密":"ALIKED+LightGlue @16384 位姿 → CasDiffMVS+官方融合",
 "P8k 稠密":"@8192 位姿(独立重建,aligned 到 P16k gauge)",
 "GTO 稠密":"GTO 门控位姿(重投影 1.156 全场最佳,aligned)",
 "LightGlue 稀疏":"同族位姿的三角化稀疏点 — 不经过深度网络",
}
clouds=[]
for name,X,C,Hc,ntot in keep:
    q=np.round((X-lo)/span*65535).clip(0,65535).astype("<u2")
    clouds.append(dict(name=name,sub=SUB[name],n=len(X),
        xyz=base64.b64encode(q.tobytes()).decode(),
        rgb=base64.b64encode(np.ascontiguousarray(C).tobytes()).decode(),
        heat=base64.b64encode(np.ascontiguousarray(Hc).tobytes()).decode()))

ctr=np.array([-1.2,0.3,0.0])
view=dict(cx=float(ctr[0]),cy=float(ctr[1]),cz=float(ctr[2]),radius=3.4,
          lo=lo.tolist(),span=span.tolist())

ev1=base64.b64encode(open(S/"blob_src_small.jpg","rb").read()).decode()
ev2=base64.b64encode(open(S/"view_oblique_small.jpg","rb").read()).decode()

TEMPLATE=r"""<!doctype html>
<meta charset="utf-8">
<title>白墙翘起法医 — 墙区四窗</title>
<style>
  :root{--bg:#0e0f12;--fg:#e8e8ea;--dim:#9aa0a6;--line:#26282e}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
    font:13px/1.5 -apple-system,"PingFang SC",sans-serif}
  header{padding:10px 14px;border-bottom:1px solid var(--line)}
  h1{font-size:15px;margin:0 0 6px}
  .hint{color:var(--dim);font-size:12px}
  .ctl{display:flex;gap:18px;align-items:center;margin-top:8px;flex-wrap:wrap}
  .ctl label{color:var(--dim)}
  #grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);
    height:calc(100% - 148px)}
  .pane{position:relative;background:var(--bg);overflow:hidden}
  canvas{display:block;width:100%;height:100%}
  .cap{position:absolute;top:0;left:0;right:0;padding:8px 10px;
    background:linear-gradient(#0e0f12ee,#0e0f1200);pointer-events:none}
  .cap b{font-size:13px}
  .cap div{color:var(--dim);font-size:11px}
  table{position:absolute;bottom:8px;left:10px;background:#0e0f12cc;padding:6px 8px;
    border-radius:4px;font-size:11px;color:var(--dim);border-collapse:collapse;pointer-events:none}
  td{padding:1px 8px 1px 0} td.v{color:var(--fg)}
  details{margin-top:6px} summary{cursor:pointer;color:var(--dim);font-size:12px}
  details img{max-height:260px;margin:6px 8px 0 0;border:1px solid var(--line)}
</style>
<header>
  <h1>白墙"翘起"法医 — 旅行箱正后方白色镶板墙(墙区定向裁剪,四窗同一包围盒)</h1>
  <div class="hint">结论:三条不同位姿臂的稠密云在墙后共享同一片致密偏移层(4.1–8.3%),同族位姿的三角化稀疏墙面干净(0.65%,44 点)⇒ <b style="color:#ff7b72">深度网络无纹理盲区,不是位姿</b>。
  坐标已转墙局部系(x=沿墙水平·旅行箱在 +x 端,y=竖直,z=离面·+z 朝房间):纯刚性变换不缩放。拖拽旋转 · 滚轮缩放 · 右键平移,四窗同步。</div>
  <div class="ctl">
    <label>点大小 <input id="ps" type="range" min="1" max="6" step="0.5" value="2"></label>
    <label><input id="hm" type="checkbox"> 离面热力(蓝=缩进墙后 · 灰=贴面 · 红=凸出墙前,±0.25 gauge≈±10cm 截断)</label>
  </div>
  <details><summary>证据图:溯源(墙后团块的源像素=空白墙面/纯黑箱衬)与斜视渲染(用户看到的"翘")</summary>
    <img src="data:image/jpeg;base64,__EV1__"><img src="data:image/jpeg;base64,__EV2__">
  </details>
</header>
<div id="grid"></div>
<script>
const CLOUDS=__DATA__, VIEW=__VIEW__, STATS=__STATS__;
const b64=s=>{const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u};
const cam={az:0.55,el:0.18,dist:VIEW.radius*1.9,tx:VIEW.cx,ty:VIEW.cy,tz:VIEW.cz};
const VS=`attribute vec3 p;attribute vec3 c;uniform mat4 mvp;uniform float ps;
uniform vec3 lo;uniform vec3 span;varying vec3 vc;
void main(){gl_Position=mvp*vec4(lo+p*span,1.0);gl_PointSize=ps;vc=c;}`;
const FS=`precision mediump float;varying vec3 vc;
void main(){vec2 d=gl_PointCoord-vec2(0.5);if(dot(d,d)>0.25)discard;gl_FragColor=vec4(vc,1.0);}`;
function sh(gl,t,s){const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);
  if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(o);return o}
function mul(a,b){const o=new Float32Array(16);
  for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k];o[i*4+j]=s}return o}
function persp(f,as,n,fa){const t=1/Math.tan(f/2);return new Float32Array(
  [t/as,0,0,0, 0,t,0,0, 0,0,(fa+n)/(n-fa),-1, 0,0,2*fa*n/(n-fa),0])}
function lookAt(e,c,u){const z=norm(sub(e,c)),x=norm(cross(u,z)),y=cross(z,x);
  return new Float32Array([x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0,
    -dot(x,e),-dot(y,e),-dot(z,e),1])}
const sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]], dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const norm=a=>{const l=Math.hypot(...a)||1;return [a[0]/l,a[1]/l,a[2]/l]};
const panes=CLOUDS.map(cl=>{
  const d=document.createElement('div');d.className='pane';
  const s=STATS[cl.name]||{};
  d.innerHTML=`<canvas></canvas><div class="cap"><b>${cl.name}</b><div>${cl.sub}</div></div>
   <table>
    <tr><td>墙区点数(白墙口径)</td><td class="v">${s.pts||cl.n}</td></tr>
    <tr><td>法向 vs 稀疏</td><td class="v">${s.ang||''}</td></tr>
    <tr><td>离面 RMS(截尾)</td><td class="v">${s.rms||''}</td></tr>
    <tr><td>墙后偏移层 / 墙面</td><td class="v">${s.blob||''}</td></tr>
   </table>`;
  document.getElementById('grid').appendChild(d);
  const cv=d.querySelector('canvas'), gl=cv.getContext('webgl',{antialias:true});
  const pr=gl.createProgram();
  gl.attachShader(pr,sh(gl,gl.VERTEX_SHADER,VS));gl.attachShader(pr,sh(gl,gl.FRAGMENT_SHADER,FS));
  gl.linkProgram(pr);gl.useProgram(pr);
  const xyz=new Uint16Array(b64(cl.xyz).buffer);
  const bp=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bp);gl.bufferData(gl.ARRAY_BUFFER,xyz,gl.STATIC_DRAW);
  const ap=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(ap);
  gl.vertexAttribPointer(ap,3,gl.UNSIGNED_SHORT,true,0,0);
  const rgb=b64(cl.rgb), heat=b64(cl.heat);
  const bc=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bc);gl.bufferData(gl.ARRAY_BUFFER,rgb,gl.STATIC_DRAW);
  const bh=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bh);gl.bufferData(gl.ARRAY_BUFFER,heat,gl.STATIC_DRAW);
  const ac=gl.getAttribLocation(pr,'c');gl.enableVertexAttribArray(ac);
  gl.uniform3fv(gl.getUniformLocation(pr,'lo'),VIEW.lo);
  gl.uniform3fv(gl.getUniformLocation(pr,'span'),VIEW.span);
  gl.enable(gl.DEPTH_TEST);gl.clearColor(0.055,0.059,0.071,1);
  return {cv,gl,pr,n:cl.n,ac,bc,bh,uMvp:gl.getUniformLocation(pr,'mvp'),uPs:gl.getUniformLocation(pr,'ps')};
});
let ps=2, hm=false;
document.getElementById('ps').oninput=e=>ps=+e.target.value;
document.getElementById('hm').onchange=e=>hm=e.target.checked;
function draw(){
  const ce=[cam.tx+cam.dist*Math.cos(cam.el)*Math.sin(cam.az),
            cam.ty+cam.dist*Math.sin(cam.el),
            cam.tz+cam.dist*Math.cos(cam.el)*Math.cos(cam.az)];
  for(const p of panes){
    const w=p.cv.clientWidth,h=p.cv.clientHeight,dpr=Math.min(devicePixelRatio,2);
    if(p.cv.width!==w*dpr){p.cv.width=w*dpr;p.cv.height=h*dpr}
    p.gl.viewport(0,0,p.cv.width,p.cv.height);
    p.gl.clear(p.gl.COLOR_BUFFER_BIT|p.gl.DEPTH_BUFFER_BIT);
    p.gl.useProgram(p.pr);
    p.gl.bindBuffer(p.gl.ARRAY_BUFFER, hm?p.bh:p.bc);
    p.gl.vertexAttribPointer(p.ac,3,p.gl.UNSIGNED_BYTE,true,0,0);
    const mvp=mul(persp(1.0,w/h,VIEW.radius*0.005,VIEW.radius*40),
                  lookAt(ce,[cam.tx,cam.ty,cam.tz],[0,1,0]));
    p.gl.uniformMatrix4fv(p.uMvp,false,mvp);p.gl.uniform1f(p.uPs,ps*dpr);
    p.gl.drawArrays(p.gl.POINTS,0,p.n);
  }
  requestAnimationFrame(draw);
}
let drag=null;
addEventListener('mousedown',e=>{if(e.target.tagName==='CANVAS'){drag={x:e.clientX,y:e.clientY,b:e.button};e.preventDefault()}});
addEventListener('mouseup',()=>drag=null);
addEventListener('contextmenu',e=>{if(e.target.tagName==='CANVAS')e.preventDefault()});
addEventListener('mousemove',e=>{
  if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
  if(drag.b===2){const k=cam.dist*0.0015;
    cam.tx-=k*(dx*Math.cos(cam.az)); cam.tz+=k*(dx*Math.sin(cam.az)); cam.ty+=k*dy;}
  else{cam.az-=dx*0.006;cam.el=Math.max(-1.5,Math.min(1.5,cam.el+dy*0.006));}
});
addEventListener('wheel',e=>{if(e.target.tagName==='CANVAS'){
  cam.dist*=Math.exp(e.deltaY*0.001);e.preventDefault()}},{passive:false});
draw();
</script>
"""
html=(TEMPLATE.replace("__DATA__",json.dumps(clouds))
      .replace("__VIEW__",json.dumps(view))
      .replace("__STATS__",json.dumps(STATS,ensure_ascii=False))
      .replace("__EV1__",ev1).replace("__EV2__",ev2))
OUT.write_text(html)
print("写出",OUT, f"{OUT.stat().st_size/1e6:.1f} MB")
