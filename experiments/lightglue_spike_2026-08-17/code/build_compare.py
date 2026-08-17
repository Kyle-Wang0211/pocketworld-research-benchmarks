#!/usr/bin/env python3
"""把三份真彩 PLY 打成一个自包含的并排对比网页(三窗同步轨道相机)。

全量点,不降采样。数据直接内嵌 base64,便于离线/换机打开。
"""
import base64, json
import numpy as np
from pathlib import Path

import argparse as _argparse
_ap = _argparse.ArgumentParser()
_ap.add_argument("--set", default="mac", choices=["mac", "cuda"],
                 help="mac=本机那批工作目录;cuda=租的 5090 上重跑的那批")
_ap.add_argument("--title", default="")
_cli = _ap.parse_args()

_SETS = {
    "mac": [("基线", "ply_CONTROL.ply", "work_b28_control",
             "DSP-SIFT 点 + SIFT 描述 + 暴力匹配 ratio 0.8"),
            ("A", "ply_ARM_A_SIFT_LG.ply", "work_b28_armA",
             "DSP-SIFT 点 + SIFT 描述 + LightGlue"),
            ("B2", "ply_ARM_B2_ALIKED_TUNED.ply", "work_b28_armB2",
             "ALIKED 点(阈值0.02) + ALIKED 描述 + LightGlue,剪枝全关"),
            ("B2+剪枝", "ply_ARM_P_B2_PRUNED.ply", "work_b28_armP",
             "与 B2 逐字相同,只开 depth 0.95 / width 0.99 自适应剪枝"),
            ("D", "ply_ARM_D_HYBRID.ply", "work_b28_armD",
             "DSP-SIFT 点 + ALIKED 描述 + LightGlue")],
    # 5090 上全部重跑:跨后端的关键点序号不可比,所以四臂必须同机产出才互相可比
    "cuda": [("基线", "ply_CONTROL.ply", "work_control",
              "DSP-SIFT 点 + 暴力匹配 ratio 0.8 — 64,059 点"),
             ("B2+剪枝 8192", "ply_P.ply", "work_P",
              "ALIKED 8192 + LightGlue + 自适应剪枝 — 21.4 ms/对,覆盖 1.00×(基准)"),
             ("RaCo 8192", "ply_R.ply", "work_R",
              "RaCo 检测器 + ALIKED 描述 — 33.6 ms/对,覆盖 1.16×,但轨迹 4.74 更薄"),
             ("B2+剪枝 16384", "ply_P16k.ply", "work_P16k",
              "只把关键点预算翻倍 — 50.5 ms/对,覆盖 1.35×且轨迹升到 5.44")],
}
_ALL = _SETS[_cli.set]
# 只画已经导出 PLY 的臂
ARMS = [(n, p, s) for n, p, _w, s in _ALL if Path(p).exists()]

# 指标由 metrics.json 读取,避免手抄出错
import json as _json
STATS = {}
for _lab, _p, _w, _s in _ALL:
    try:
        _m = _json.load(open(f"{_w}/metrics.json"))
        STATS[_lab] = dict(pts=f"{_m['points']:,}", obs=f"{_m['obs']:,}",
                           ge8=f"{_m.get('ge8',0):,}", tl=f"{_m['track_mean']:.2f}",
                           rp=f"{_m['reproj']:.4f}", inl=f"{_m['inliers']:.1f}")
    except Exception as _e:
        STATS[_lab] = {}


def read_ply(p):
    with open(p, "rb") as f:
        hdr = b""
        while not hdr.endswith(b"end_header\n"):
            hdr += f.read(1)
        n = int([l for l in hdr.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.frombuffer(f.read(), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                             ("r", "u1"), ("g", "u1"), ("b", "u1")], count=n)
    xyz = np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float32)
    rgb = np.stack([rec["r"], rec["g"], rec["b"]], 1).astype(np.uint8)
    return xyz, rgb


def main():
    raw = [(name, sub) + read_ply(path) for name, path, sub in ARMS]
    allxyz = [x for *_, x, _ in raw]
    # ⚠️ 坐标量化成 uint16 再交给 GPU 解码(normalized 属性),页面体积对半砍。
    #    这**不是降采样**——一个点都没少,只是坐标精度降到量化步长;
    #    全场跨度约 span/65535,亚毫米量级,远在肉眼与我们重投影口径之下。
    lo = np.min([x.min(0) for x in allxyz], axis=0)
    hi = np.max([x.max(0) for x in allxyz], axis=0)
    span = np.maximum(hi - lo, 1e-6)
    print(f"量化步长 {(span/65535*1000).round(3).tolist()} mm/轴")
    clouds = []
    for name, sub, xyz, rgb in raw:
        q = np.round((xyz - lo) / span * 65535).clip(0, 65535).astype("<u2")
        clouds.append(dict(name=name, sub=sub, n=len(xyz),
                           xyz=base64.b64encode(q.tobytes()).decode(),
                           rgb=base64.b64encode(rgb.tobytes()).decode()))
        print(f"{name}: {len(xyz):,} 点")

    # 用中位数与稳健半径定视图中心(避免离群浮点把相机推飞)
    ref = allxyz[0]
    c = np.median(ref, 0)
    r = float(np.percentile(np.linalg.norm(ref - c, axis=1), 95))
    view = dict(cx=float(c[0]), cy=float(c[1]), cz=float(c[2]), radius=r,
                lo=lo.astype(float).tolist(), span=span.astype(float).tolist())
    print(f"视图中心 {c.round(3).tolist()}  半径(p95) {r:.3f}")

    html = TEMPLATE.replace("__DATA__", json.dumps(clouds)) \
                   .replace("__VIEW__", json.dumps(view)) \
                   .replace("__NCOL__", str(len(clouds))) \
                   .replace("__STATS__", json.dumps(STATS))
    out = Path("compare_lightglue.html")
    out.write_text(html)
    print(f"已写出 {out}  {out.stat().st_size/1e6:.1f} MB")


TEMPLATE = r"""<!doctype html>
<meta charset="utf-8">
<title>LightGlue 四臂并排</title>
<style>
  :root{--bg:#0e0f12;--fg:#e8e8ea;--dim:#9aa0a6;--line:#26282e}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
    font:13px/1.5 -apple-system,"PingFang SC",sans-serif}
  header{padding:10px 14px;border-bottom:1px solid var(--line)}
  h1{font-size:15px;margin:0 0 6px}
  .hint{color:var(--dim);font-size:12px}
  .ctl{display:flex;gap:16px;align-items:center;margin-top:8px;flex-wrap:wrap}
  .ctl label{color:var(--dim)}
  #grid{display:grid;grid-template-columns:repeat(__NCOL__,1fr);gap:1px;background:var(--line);
    height:calc(100% - 128px)}
  .pane{position:relative;background:var(--bg);overflow:hidden}
  canvas{display:block;width:100%;height:100%}
  .cap{position:absolute;top:0;left:0;right:0;padding:8px 10px;
    background:linear-gradient(#0e0f12ee,#0e0f1200);pointer-events:none}
  .cap b{font-size:13px}
  .cap div{color:var(--dim);font-size:11px}
  table{position:absolute;bottom:8px;left:10px;background:#0e0f12cc;padding:6px 8px;border-radius:4px;font-size:11px;color:var(--dim);
    border-collapse:collapse;pointer-events:none}
  td{padding:1px 8px 1px 0}
  td.v{color:var(--fg)}
</style>
<header>
  <h1>真彩点云并排 — b28(132 帧,同一场拍摄)</h1>
  <div class="hint">拖拽旋转 · 滚轮缩放 · 右键平移 —— 所有窗口相机同步。各份重建已用相机光心统一 gauge(相似变换保形,云内几何未改)。</div>
  <div class="ctl">
    <label>点大小 <input id="ps" type="range" min="1" max="6" step="0.5" value="2"></label>
    <label><input id="sync" type="checkbox" checked> 相机同步</label>
    <span class="hint" id="fps"></span>
  </div>
</header>
<div id="grid"></div>
<script>
const CLOUDS=__DATA__, VIEW=__VIEW__, STATS=__STATS__;
const b64=s=>{const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u};
const cam={az:0.6,el:0.35,dist:VIEW.radius*2.4,tx:VIEW.cx,ty:VIEW.cy,tz:VIEW.cz};
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
    <tr><td>点数</td><td class="v">${s.pts||cl.n}</td></tr>
    <tr><td>观测</td><td class="v">${s.obs||''}</td></tr>
    <tr><td>≥8 观测的点</td><td class="v">${s.ge8||''}</td></tr>
    <tr><td>轨迹均值</td><td class="v">${s.tl||''}</td></tr>
    <tr><td>验证内点/对</td><td class="v">${s.inl||''}</td></tr>
    <tr><td>重投影 px</td><td class="v">${s.rp||''}</td></tr>
   </table>`;
  document.getElementById('grid').appendChild(d);
  const cv=d.querySelector('canvas'), gl=cv.getContext('webgl',{antialias:true});
  const pr=gl.createProgram();
  gl.attachShader(pr,sh(gl,gl.VERTEX_SHADER,VS));gl.attachShader(pr,sh(gl,gl.FRAGMENT_SHADER,FS));
  gl.linkProgram(pr);gl.useProgram(pr);
  const xyz=new Uint16Array(b64(cl.xyz).buffer), rgb=b64(cl.rgb);
  const bp=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bp);gl.bufferData(gl.ARRAY_BUFFER,xyz,gl.STATIC_DRAW);
  const ap=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(ap);gl.vertexAttribPointer(ap,3,gl.UNSIGNED_SHORT,true,0,0);
  const bc=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bc);gl.bufferData(gl.ARRAY_BUFFER,rgb,gl.STATIC_DRAW);
  const ac=gl.getAttribLocation(pr,'c');gl.enableVertexAttribArray(ac);gl.vertexAttribPointer(ac,3,gl.UNSIGNED_BYTE,true,0,0);
  gl.enable(gl.DEPTH_TEST);gl.clearColor(0.055,0.059,0.071,1);
  gl.uniform3fv(gl.getUniformLocation(pr,'lo'),VIEW.lo);
  gl.uniform3fv(gl.getUniformLocation(pr,'span'),VIEW.span);
  return {cv,gl,pr,n:cl.n,uMvp:gl.getUniformLocation(pr,'mvp'),uPs:gl.getUniformLocation(pr,'ps')};
});

let ps=2;
document.getElementById('ps').oninput=e=>ps=+e.target.value;
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

if __name__ == "__main__":
    main()
