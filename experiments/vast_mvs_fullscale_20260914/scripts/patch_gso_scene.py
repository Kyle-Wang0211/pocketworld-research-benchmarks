p = "/root/gso_stage1.py"
s = open(p).read()

# ① dist: 2.6 -> 2.31 (Wonder3D radius=2.0 on unit cube; 2.0/(sqrt(3)/2)=2.309)
old = "dist = rad * 2.6"
new = ("# 相机距离有出处:Objaverse-XL/Wonder3D 把物体归一化到单位立方体后 radius=2.0,\n"
       "# 单位立方体外接球半径=sqrt(3)/2=0.866 ⇒ 等价于 2.0/0.866 = 2.309 倍包围球半径。\n"
       "# (Zero-1-to-3 的 radius_min=1.5/max=2.2 对应 1.73~2.54,2.309 落在区间内)\n"
       "dist = rad * 2.309")
assert s.count(old) == 1, ("A", s.count(old))
s = s.replace(old, new)

# ② 世界背景:平灰 -> Poly Haven 室内 HDRI(CC0)
old2 = """sc.render.film_transparent = False
sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.35, 0.38, 1)"""
new2 = """sc.render.film_transparent = False
# 世界:Poly Haven 室内 HDRI(CC0,商用无需署名)。提供真实光照与背景色。
# 🔴 HDRI 是无限远环境贴图,不提供深度真值 —— 深度监督来自下面的地面平面。
import glob as _g, random as _rnd
_hdris = sorted(_g.glob("/root/ph_assets/hdri/*.hdr"))
assert _hdris, "🔴 没有 HDRI 素材,背景会退回虚空"
_rng = _rnd.Random(abs(hash(SCAN)) % (2**31))
_hdr = _rng.choice(_hdris)
sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
_wt = sc.world.node_tree
for n in list(_wt.nodes):
    if n.type != "OUTPUT_WORLD": _wt.nodes.remove(n)
_env = _wt.nodes.new("ShaderNodeTexEnvironment")
_env.image = bpy.data.images.load(_hdr)
_bg = _wt.nodes.new("ShaderNodeBackground")
_wt.links.new(_env.outputs["Color"], _bg.inputs["Color"])
_wt.links.new(_bg.outputs["Background"], _wt.nodes["World Output"].inputs["Surface"])
assert _env.image is not None and tuple(_env.image.size)[0] > 0, "🔴 HDRI 未加载"
print(f"[HDRI] {os.path.basename(_hdr)} {tuple(_env.image.size)}", flush=True)

# 地面平面:给背景真实几何与深度真值(产品场景=手办放在桌面上拍)
_texs = sorted(_g.glob("/root/ph_assets/tex/*.jpg"))
assert _texs, "🔴 没有地面材质"
_tex = _rng.choice(_texs)
bpy.ops.mesh.primitive_plane_add(size=rad * 40, location=(ctr[0], ctr[1], float(pts[:, 2].min())))
_plane = bpy.context.active_object
_m = bpy.data.materials.new("ground"); _m.use_nodes = True
_bsdf = _m.node_tree.nodes["Principled BSDF"]
_ti = _m.node_tree.nodes.new("ShaderNodeTexImage")
_ti.image = bpy.data.images.load(_tex)
_mp = _m.node_tree.nodes.new("ShaderNodeMapping")
_tc = _m.node_tree.nodes.new("ShaderNodeTexCoord")
_mp.inputs["Scale"].default_value = (8.0, 8.0, 8.0)
_m.node_tree.links.new(_tc.outputs["UV"], _mp.inputs["Vector"])
_m.node_tree.links.new(_mp.outputs["Vector"], _ti.inputs["Vector"])
_m.node_tree.links.new(_ti.outputs["Color"], _bsdf.inputs["Base Color"])
_plane.data.materials.append(_m)
assert tuple(_ti.image.size)[0] > 0, "🔴 地面材质未加载"
print(f"[GROUND] {os.path.basename(_tex)} 平面边长 {rad*40:.2f}", flush=True)"""
assert s.count(old2) == 1, ("B", s.count(old2))
s = s.replace(old2, new2)

open(p, "w").write(s)
print("patched: dist=2.309 / HDRI / 地面平面")
