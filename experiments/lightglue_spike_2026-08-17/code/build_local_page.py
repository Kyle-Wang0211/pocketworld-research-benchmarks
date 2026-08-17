#!/usr/bin/env python3
"""本地拼并排页 —— 不再从租的机器搬整页。

背景:那台实例的**下行只有 ~25 KB/s**(上行 3.1 MB/s,严重不对称),
搬一个 7MB 的页要 5 分钟。而本地那份 compare_cuda_5090.html 里已经嵌着
CONTROL / B2 / B2+剪枝 / RaCo 四朵云的 base64,只有 P16k 是新的
⇒ 只搬 P16k(量化+莫顿序 delta+gzip,1.6MB),其余就地复用。

坐标一律量化成 uint16 交给 GPU 反量化(normalized 属性),页面体积对半砍。
⚠️ 这**不是降采样**:一个点都没少,只是坐标精度降到亚毫米,肉眼和我们的
重投影口径都远在其上。
"""
import base64, gzip, json, re, sys
from pathlib import Path

import numpy as np

SRC = Path("compare_cuda_5090.html")      # 已在本地、能打开的那份(含四朵云)

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--set", default="coverage", choices=["coverage", "raco", "ship"])
_cli = _ap.parse_args()

# 每页最多 4 窗:查看器在 9MB 与 14.4MB 之间有个上限,4 窗量化后约 6.6MB 是安全区
SETS = {
    # 覆盖之争:预算翻倍 vs 换检测器
    "coverage": ("compare_5arm.html", [
        ("基线",           "html:基线",      "DSP-SIFT 点 + 暴力匹配 ratio 0.8"),
        ("B2+剪枝 8192",   "html:B2+剪枝",   "ALIKED 8192 + 自适应剪枝 — 21.4 ms/对,覆盖 1.00×(基准)"),
        ("RaCo 8192",      "html:RaCo",      "RaCo 检测器 + ALIKED 描述 — 覆盖 1.16×,轨迹 4.74 更薄"),
        ("B2+剪枝 16384",  "bin:p16k",       "只把关键点预算翻倍 — 覆盖 1.35× 且轨迹升到 5.44"),
    ]),
    # RaCo 三兄弟:原版 / 协方差选点 / 排序器
    # 产品视角:能上机的两条 + 上不了机的天花板参照
    "ship": ("compare_ship.html", [
        ("基线(生产)",      "html:基线",   "同样的 SIFT 点 + 暴力匹配 ratio 0.8 —— 现在出货的样子"),
        ("臂A SIFT+LG",     "bin:armA",    "同样的 SIFT 点,只换匹配器 —— 覆盖 1.66×,28.4ms/对,✅能上机"),
        ("B2 ALIKED 8192",  "html:B2+剪枝", "换 ALIKED 前端 —— 覆盖 1.51×(反而不如臂A),❌前端 6.38GB"),
        ("RaCo 16384 天花板", "bin:r16kp",  "内存不是问题时的上限 —— 覆盖 2.55×,❌上不了机"),
    ]),
    "raco": ("compare_raco.html", [
        ("B2+剪枝 8192",   "html:B2+剪枝",   "参照系 — 覆盖 1.00×,轨迹 5.21,重投影 1.5266"),
        ("RaCo 8192",      "html:RaCo",      "bypass 取前 8192 — 覆盖 1.16×,轨迹 4.74"),
        ("RaCo+协方差",    "bin:rcov",       "16384 候选取 σ 最小的 8192 — 重投影最低 1.5106,覆盖回落 1.08×"),
        ("RaCo+排序器",    "bin:rrank",      "开 dense ranker — 轨迹跌到 4.57,观测 −5.4%,四项全跌"),
    ]),
}
OUT_NAME, PLAN = SETS[_cli.set]
OUT = Path(OUT_NAME)


# 窗口左下角那张小表(数字来自各臂 metrics.json / coverage_metric.py,手抄一次集中在这里)
STATS = {
    "基线(生产)":      dict(pts="64,059",  obs="263,589", tl="4.11", rp="1.4191", cov="1.00×"),
    "臂A SIFT+LG":     dict(pts="126,508", obs="527,495", tl="4.17", rp="1.4206", cov="1.66×"),
    "B2 ALIKED 8192":  dict(pts="133,646", obs="695,664", tl="5.21", rp="1.5266", cov="1.51×"),
    "RaCo 16384 天花板": dict(pts="269,716", obs="1,265,896", tl="4.69", rp="1.5236", cov="2.55×"),
    "基线":          dict(pts="64,059",  obs="263,589",   tl="4.11", rp="1.4191", cov="0.66×"),
    "B2+剪枝 8192":  dict(pts="133,646", obs="695,664",   tl="5.21", rp="1.5266", cov="1.00×"),
    "RaCo 8192":     dict(pts="141,642", obs="671,739",   tl="4.74", rp="1.5266", cov="1.16×"),
    "RaCo+协方差":   dict(pts="139,479", obs="665,549",   tl="4.77", rp="1.5106", cov="1.08×"),
    "RaCo+排序器":   dict(pts="139,041", obs="635,403",   tl="4.57", rp="1.5261", cov="1.20×"),
    "B2+剪枝 16384": dict(pts="238,980", obs="1,299,449", tl="5.44", rp="1.5502", cov="1.35×"),
}


def clouds_from_html(p: Path):
    m = re.search(r"const CLOUDS=(\[.*?\]), VIEW=", p.read_text(), re.S)
    if not m:
        sys.exit(f"没能从 {p} 里解析出 CLOUDS")
    out = []
    for c in json.loads(m.group(1)):
        xyz = np.frombuffer(base64.b64decode(c["xyz"]), dtype="<f4").reshape(-1, 3)
        rgb = np.frombuffer(base64.b64decode(c["rgb"]), dtype=np.uint8).reshape(-1, 3)
        out.append((c["name"], c["sub"], xyz, rgb))
    return out


def load_new(p: Path):
    """远端打包格式:lo(3f4) span(3f4) n(i4) + uint16 delta 坐标 + rgb。"""
    b = gzip.decompress(p.read_bytes())
    lo = np.frombuffer(b[0:12], dtype="<f4")
    span = np.frombuffer(b[12:24], dtype="<f4")
    n = int(np.frombuffer(b[24:28], dtype="<i4")[0])
    d = np.frombuffer(b[28:28 + n * 6], dtype="<u2").reshape(n, 3)
    rgb = np.frombuffer(b[28 + n * 6:28 + n * 9], dtype=np.uint8).reshape(n, 3)
    q = np.cumsum(d.astype(np.int64), axis=0).astype(np.uint16)   # delta 还原
    return lo + q.astype(np.float64) / 65535.0 * span, rgb


def main():
    from_html = {c[0]: (c[2], c[3]) for c in clouds_from_html(SRC)}
    keep = []
    for label, src, _sub in PLAN:
        kind, key = src.split(":", 1)
        if kind == "html":
            if key not in from_html:
                sys.exit(f"源页里没有 “{key}”,现有:{list(from_html)}")
            xyz, rgb = from_html[key]
        else:
            xyz, rgb = load_new(Path(key + ".bin.gz"))
        keep.append((label, xyz, rgb))

    lo = np.min([x.min(0) for _, x, _ in keep], axis=0)
    span = np.maximum(np.max([x.max(0) for _, x, _ in keep], axis=0) - lo, 1e-6)
    print(f"量化步长 {(span / 65535 * 1000).round(3).tolist()} mm/轴")

    SUB = {l: d for l, _s, d in PLAN}
    clouds = []
    for nm, x, c in keep:
        q = np.round((x - lo) / span * 65535).clip(0, 65535).astype("<u2")
        clouds.append(dict(name=nm, sub=SUB[nm], n=len(x),
                           xyz=base64.b64encode(q.tobytes()).decode(),
                           rgb=base64.b64encode(np.ascontiguousarray(c).tobytes()).decode()))
        print(f"{nm}: {len(x):,} 点")

    ref = keep[min(1, len(keep) - 1)][1]
    ctr = np.median(ref, 0)
    view = dict(cx=float(ctr[0]), cy=float(ctr[1]), cz=float(ctr[2]),
                radius=float(np.percentile(np.linalg.norm(ref - ctr, axis=1), 95)),
                lo=lo.astype(float).tolist(), span=span.astype(float).tolist())

    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(clouds))
                   .replace("__VIEW__", json.dumps(view))
                   .replace("__NCOL__", str(len(clouds)))
                   .replace("__STATS__", json.dumps(STATS)))
    print(f"已写出 {OUT}  {OUT.stat().st_size / 1e6:.1f} MB")


TEMPLATE = r"""<!doctype html>
<meta charset="utf-8">
<title>覆盖对比 — 四臂并排</title>
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
    height:calc(100% - 118px)}
  .pane{position:relative;background:var(--bg);overflow:hidden}
  canvas{display:block;width:100%;height:100%}
  .cap{position:absolute;top:0;left:0;right:0;padding:8px 10px;
    background:linear-gradient(#0e0f12ee,#0e0f1200);pointer-events:none}
  .cap b{font-size:13px}
  .cap div{color:var(--dim);font-size:11px}
  table{position:absolute;bottom:8px;left:10px;background:#0e0f12cc;padding:6px 8px;
    border-radius:4px;font-size:11px;color:var(--dim);border-collapse:collapse;pointer-events:none}
  td{padding:1px 8px 1px 0} td.v{color:var(--fg)}
</style>
<header>
  <h1>覆盖对比 — b28(132 帧,同一场拍摄,全部在同一张 5090 上产出)</h1>
  <div class="hint">拖拽旋转 · 滚轮缩放 · 右键平移 —— 四窗相机同步。已用相机光心统一 gauge(相似变换保形)。坐标按亚毫米量化以压体积,点一个没少。</div>
  <div class="ctl"><label>点大小 <input id="ps" type="range" min="1" max="6" step="0.5" value="2"></label></div>
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
    <tr><td>轨迹均值</td><td class="v">${s.tl||''}</td></tr>
    <tr><td>覆盖(0.2m 体素)</td><td class="v">${s.cov||''}</td></tr>
    <tr><td>重投影 px</td><td class="v">${s.rp||''}</td></tr>
   </table>`;
  document.getElementById('grid').appendChild(d);
  const cv=d.querySelector('canvas'), gl=cv.getContext('webgl',{antialias:true});
  const pr=gl.createProgram();
  gl.attachShader(pr,sh(gl,gl.VERTEX_SHADER,VS));gl.attachShader(pr,sh(gl,gl.FRAGMENT_SHADER,FS));
  gl.linkProgram(pr);gl.useProgram(pr);
  const xyz=new Uint16Array(b64(cl.xyz).buffer), rgb=b64(cl.rgb);
  const bp=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bp);gl.bufferData(gl.ARRAY_BUFFER,xyz,gl.STATIC_DRAW);
  const ap=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(ap);
  gl.vertexAttribPointer(ap,3,gl.UNSIGNED_SHORT,true,0,0);
  const bc=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bc);gl.bufferData(gl.ARRAY_BUFFER,rgb,gl.STATIC_DRAW);
  const ac=gl.getAttribLocation(pr,'c');gl.enableVertexAttribArray(ac);
  gl.vertexAttribPointer(ac,3,gl.UNSIGNED_BYTE,true,0,0);
  gl.uniform3fv(gl.getUniformLocation(pr,'lo'),VIEW.lo);
  gl.uniform3fv(gl.getUniformLocation(pr,'span'),VIEW.span);
  gl.enable(gl.DEPTH_TEST);gl.clearColor(0.055,0.059,0.071,1);
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
