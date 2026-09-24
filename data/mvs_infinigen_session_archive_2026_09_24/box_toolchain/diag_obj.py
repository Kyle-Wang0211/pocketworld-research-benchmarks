import bpy, numpy as np
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath='/root/texrecon_out/poisson.obj')
objs=[o for o in bpy.data.objects if o.type=='MESH']
nv=sum(len(o.data.vertices) for o in objs); nf=sum(len(o.data.polygons) for o in objs)
print(f'物体 {len(objs)} 个, 顶点 {nv:,}, 面 {nf:,}')
allc=[]
for o in objs:
    for c in o.bound_box: allc.append(o.matrix_world @ __import__('mathutils').Vector(c))
A=np.array([[v.x,v.y,v.z] for v in allc])
print('世界包围盒', np.round(A.min(0),3).tolist(), np.round(A.max(0),3).tolist())
print('图像数据块', len(bpy.data.images), ' 已加载像素的:', sum(1 for i in bpy.data.images if i.has_data))
mats=[m for m in bpy.data.materials]
print('材质', len(mats))
m=mats[0] if mats else None
if m and m.use_nodes:
    for n in m.node_tree.nodes: print('  节点', n.type, getattr(getattr(n,'image',None),'name','-'), getattr(getattr(n,'image',None),'size',None)[:] if getattr(n,'image',None) else '')
