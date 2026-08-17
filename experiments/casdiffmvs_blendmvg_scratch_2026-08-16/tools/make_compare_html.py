#!/usr/bin/env python3
"""四栏真彩并排对比页 —— 复用 _artifacts/isolated_floaters_20260807/compare_tri_rgb.html
   的 viewer(共享相机 / 逐轴中位数定心 / 5-95 百分位定尺度 / 坐标轴带 10cm 刻度),
   只把三栏扩成四栏。不重写交互。

⚠️ 显示用降采样:全量是每份约 1700 万点,四栏内联进网页不可能。
   这里均匀随机抽 N 点**仅用于显示**。全量 PLY 另行交付,交付不降采样。
   均匀随机保持空间分布与飘点比例,肉眼判断噪声/飘点/面完整度不受影响。
"""
from __future__ import annotations
import sys, base64, io
import numpy as np
from plyfile import PlyData

N = int(sys.argv[1])
out = sys.argv[2]
jobs = [a.split("=", 1) for a in sys.argv[3:]]     # 标题=路径

blobs, labels = [], []
rng = np.random.default_rng(20260817)              # 固定种子 ⇒ 四栏抽样可复现
for title, path in jobs:
    d = PlyData.read(path)["vertex"]
    tot = len(d)
    idx = np.sort(rng.choice(tot, size=min(N, tot), replace=False))
    x, y, z = d["x"][idx], d["y"][idx], d["z"][idx]
    r, g, b = d["red"][idx], d["green"][idx], d["blue"][idx]
    n = len(idx)
    # 与 viewer 的 parsePly 约定一致:stride 15 = 3×float32 + 3×uint8
    rec = np.zeros(n, dtype=[("x","<f4"),("y","<f4"),("z","<f4"),
                             ("r","u1"),("g","u1"),("b","u1")])
    rec["x"],rec["y"],rec["z"] = x,y,z
    rec["r"],rec["g"],rec["b"] = r,g,b
    hdr = (f"ply\nformat binary_little_endian 1.0\nelement vertex {n}\n"
           "property float x\nproperty float y\nproperty float z\n"
           "property uchar red\nproperty uchar green\nproperty uchar blue\n"
           "end_header\n").encode()
    blobs.append(base64.b64encode(hdr + rec.tobytes()).decode())
    labels.append((title, tot, n))
    print(f"  {title:<16} 全量 {tot:>10,} → 显示 {n:,}", flush=True)

panes = "".join(
    f'<div class="pane"><div class="label">{t}<span id="n{i}"></span></div>'
    f'<canvas id="c{i}"></canvas></div>'
    for i, (t, _, _) in enumerate(labels))
head = " | ".join(f"{t} 全量 {tot:,}" for t, tot, _ in labels)

VIEWER = r"""
function parsePly(b64){
 const bin=atob(b64); const bytes=new Uint8Array(bin.length);
 for(let i=0;i<bin.length;i++)bytes[i]=bin.charCodeAt(i);
 const headEnd=(function(){const t=new TextDecoder().decode(bytes.slice(0,4096));
   const k=t.indexOf("end_header\n");return k+11;})();
 const head=new TextDecoder().decode(bytes.slice(0,headEnd));
 const n=parseInt(head.match(/element vertex (\d+)/)[1]);
 const dv=new DataView(bytes.buffer,headEnd);
 const pos=new Float32Array(n*3), col=new Float32Array(n*3);
 const stride=15;
 for(let i=0;i<n;i++){const o=i*stride;
  pos[3*i]=dv.getFloat32(o,true);pos[3*i+1]=dv.getFloat32(o+4,true);pos[3*i+2]=dv.getFloat32(o+8,true);
  col[3*i]=dv.getUint8(o+12)/255;col[3*i+1]=dv.getUint8(o+13)/255;col[3*i+2]=dv.getUint8(o+14)/255;}
 return {n,pos,col};
}
const cam={rx:-0.6,ry:0.6,dist:2.5};
const views=[];
let scale=1,scaleSet=false;let sharedCenter=null;let PS=1.5;
DATAS.forEach((b64,i)=>{
 const cloud=parsePly(b64);
 document.getElementById("n"+i).textContent=" — 显示 "+cloud.n.toLocaleString()+" 点";
 const center=[0,0,0]; const ext=[0,0,0];
 {const tmp=new Float32Array(cloud.n);
  for(let a=0;a<3;a++){
   for(let p=0;p<cloud.n;p++)tmp[p]=cloud.pos[3*p+a];
   tmp.sort();
   center[a]=tmp[Math.floor(cloud.n/2)];
   ext[a]=tmp[Math.floor(cloud.n*0.95)]-tmp[Math.floor(cloud.n*0.05)];}}
 if(!scaleSet){scale=2/Math.max(ext[0],ext[1],ext[2],1e-6);scaleSet=true;sharedCenter=center.slice();}
 else{center[0]=sharedCenter[0];center[1]=sharedCenter[1];center[2]=sharedCenter[2];}
 const cv=document.getElementById("c"+i);
 const gl=cv.getContext("webgl",{antialias:false});
 const vs=`attribute vec3 p;attribute vec3 c;uniform mat4 mvp;uniform float ps;varying vec3 vc;
  void main(){gl_Position=mvp*vec4(p,1.0);gl_PointSize=ps;vc=c;}`;
 const fs=`precision mediump float;varying vec3 vc;void main(){gl_FragColor=vec4(vc,1.0);}`;
 function sh(t,s){const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);return o;}
 const pr=gl.createProgram();gl.attachShader(pr,sh(gl.VERTEX_SHADER,vs));
 gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,fs));gl.linkProgram(pr);gl.useProgram(pr);
 function buf(arr){const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);
  gl.bufferData(gl.ARRAY_BUFFER,arr,gl.STATIC_DRAW);return b;}
 const cent=new Float32Array(cloud.n*3);
 for(let p=0;p<cloud.n*3;p+=3){cent[p]=(cloud.pos[p]-center[0])*scale;
  cent[p+1]=(cloud.pos[p+1]-center[1])*scale;cent[p+2]=(cloud.pos[p+2]-center[2])*scale;}
 const pb=buf(cent), cb=buf(cloud.col);
 const AX=[[1,0,0,[1,.35,.35]],[0,1,0,[.35,1,.35]],[0,0,1,[.42,.55,1]]];
 const av=[],ac=[],mv=[],mc=[];
 AX.forEach(([x,y,z,c])=>{
  av.push((0-center[0])*scale,(0-center[1])*scale,(0-center[2])*scale,
          (x-center[0])*scale,(y-center[1])*scale,(z-center[2])*scale);
  ac.push(...c,...c);
  for(let t=1;t<=10;t++){const f=t/10;
   mv.push((x*f-center[0])*scale,(y*f-center[1])*scale,(z*f-center[2])*scale);
   mc.push(...c);}
 });
 const ab=buf(new Float32Array(av)), acb=buf(new Float32Array(ac));
 const mb=buf(new Float32Array(mv)), mcb=buf(new Float32Array(mc));
 views.push({gl,cv,pr,pb,cb,ab,acb,mb,mcb,n:cloud.n,
  la:gl.getAttribLocation(pr,"p"),lc:gl.getAttribLocation(pr,"c"),
  um:gl.getUniformLocation(pr,"mvp"),ups:gl.getUniformLocation(pr,"ps")});
});
function draw(){
 views.forEach(v=>{
  const {gl,cv}=v;
  const w=cv.clientWidth,h=cv.clientHeight;
  if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;}
  const bgv=window.lightBg?0.82:0.07;
  gl.viewport(0,0,w,h);gl.clearColor(bgv,bgv,bgv,1);gl.enable(gl.DEPTH_TEST);
  gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  const a=w/h,f=1.5,zn=0.01,zf=100;
  const cr=Math.cos(cam.rx),sr=Math.sin(cam.rx),cy=Math.cos(cam.ry),sy=Math.sin(cam.ry);
  const R=[cy,sy*sr,sy*cr,0, 0,cr,-sr,0, -sy,cy*sr,cy*cr,0, 0,0,0,1];
  const T=[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,-cam.dist,1];
  const P=[f/a,0,0,0, 0,f,0,0, 0,0,(zf+zn)/(zn-zf),-1, 0,0,2*zf*zn/(zn-zf),0];
  function mul(A,B){const O=new Array(16).fill(0);
   for(let r=0;r<4;r++)for(let c=0;c<4;c++)for(let k2=0;k2<4;k2++)O[c*4+r]+=A[k2*4+r]*B[c*4+k2];return O;}
  const mvp=new Float32Array(mul(P,mul(T,R)));
  gl.useProgram(v.pr);
  gl.uniformMatrix4fv(v.um,false,mvp);
  gl.uniform1f(v.ups,PS);
  gl.bindBuffer(gl.ARRAY_BUFFER,v.pb);gl.vertexAttribPointer(v.la,3,gl.FLOAT,false,0,0);gl.enableVertexAttribArray(v.la);
  gl.bindBuffer(gl.ARRAY_BUFFER,v.cb);gl.vertexAttribPointer(v.lc,3,gl.FLOAT,false,0,0);gl.enableVertexAttribArray(v.lc);
  gl.drawArrays(gl.POINTS,0,v.n);
  gl.bindBuffer(gl.ARRAY_BUFFER,v.ab);gl.vertexAttribPointer(v.la,3,gl.FLOAT,false,0,0);
  gl.bindBuffer(gl.ARRAY_BUFFER,v.acb);gl.vertexAttribPointer(v.lc,3,gl.FLOAT,false,0,0);
  gl.drawArrays(gl.LINES,0,6);
  gl.uniform1f(v.ups,4.0);
  gl.bindBuffer(gl.ARRAY_BUFFER,v.mb);gl.vertexAttribPointer(v.la,3,gl.FLOAT,false,0,0);
  gl.bindBuffer(gl.ARRAY_BUFFER,v.mcb);gl.vertexAttribPointer(v.lc,3,gl.FLOAT,false,0,0);
  gl.drawArrays(gl.POINTS,0,30);
 });
 requestAnimationFrame(draw);
}
let drag=false,px=0,py=0;
document.querySelectorAll("canvas").forEach(cv=>{
 cv.addEventListener("mousedown",e=>{drag=true;px=e.clientX;py=e.clientY;});
 cv.addEventListener("wheel",e=>{e.preventDefault();cam.dist*=Math.exp(e.deltaY*0.001);},{passive:false});
});
window.addEventListener("mousemove",e=>{if(!drag)return;
 const dx=e.clientX-px,dy=e.clientY-py;px=e.clientX;py=e.clientY;
 cam.ry+=dx*0.01;cam.rx+=dy*0.01;});
window.addEventListener("mouseup",()=>drag=false);
document.getElementById("bg").addEventListener("click",()=>{window.lightBg=!window.lightBg;});
document.getElementById("ps").addEventListener("input",e=>{PS=parseFloat(e.target.value);});
draw();
"""

html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CasDiffMVS 四权重真彩并排</title>
<style>
 body{{margin:0;background:#111;color:#ddd;font:13px -apple-system,sans-serif}}
 #bar{{padding:6px 10px;background:#1c1c1c}}
 #row{{display:flex;flex-wrap:wrap}}
 .pane{{flex:1 1 49%;min-width:420px;position:relative;border:1px solid #333}}
 .pane canvas{{width:100%;height:44vh;display:block}}
 .label{{position:absolute;top:6px;left:8px;z-index:2;background:#000a;padding:2px 8px;border-radius:4px}}
</style></head><body>
<div id="bar">CasDiffMVS 段① 四权重真彩并排 · 138 帧 / 896×512 / 官方 filter.py 融合(photo 0.3/0.5/0.5,geo 默认)。
四栏共享相机与坐标系,拖拽旋转、滚轮缩放。坐标轴每 10cm 一刻度。<br>
{head}<br>
⚠️ 显示用均匀随机降采样(仅影响本页渲染,全量 PLY 另行交付)。
<button id="bg" style="margin-left:12px">切换背景</button>
点大小 <input id="ps" type="range" min="1" max="6" step="0.5" value="1.5">
</div>
<div id="row">{panes}</div>
<script>
const DATAS=[{",".join('"'+b+'"' for b in blobs)}];
{VIEWER}
</script></body></html>"""
open(out, "w").write(html)
import os
print(f"\n→ {out}  {os.path.getsize(out)/2**20:.1f} MB")
