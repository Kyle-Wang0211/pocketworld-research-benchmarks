# Blender 4.2 无头渲染: 从真实拍摄相机位姿渲染 ③(Poisson 顶点色) 与 texrecon 官方贴图输出。
# 引擎 = Workbench,不打光的平面着色(与判决页「默认不打光 = 商用 App 贴图视图」同口径)。
# texrecon 的 obj+mtl+309 png 由 Blender 原生 OBJ 导入器加载, 数据零改动。
import bpy, sys, json, math, os
import numpy as np
from mathutils import Matrix
argv=sys.argv[sys.argv.index('--')+1:]
WHICH=argv[0]            # 'vcol' 或 'tex'
OUTDIR=argv[1]
W,H=2688,2004
SFM='/root/av_ep0_off/scene_dense.sfm'
bpy.ops.wm.read_factory_settings(use_empty=True)
sc=bpy.context.scene
sc.render.engine='BLENDER_WORKBENCH'
sh=sc.display.shading
sh.light='FLAT'                    # 不打光
sh.color_type='VERTEX' if WHICH=='vcol' else 'TEXTURE'
sh.show_object_outline=False; sh.show_specular_highlight=False
sc.render.resolution_x=W; sc.render.resolution_y=H; sc.render.resolution_percentage=100
sc.render.film_transparent=False
# 🔴 Blender 4.x 默认视图变换是 AgX(胶片色调映射, 会改颜色)。贴图对照必须关掉。
try:
    sc.view_settings.view_transform='Standard'
except Exception as e: print('view_transform 设置失败:', e)
sc.view_settings.look='None'; sc.view_settings.exposure=0.0; sc.view_settings.gamma=1.0
print('视图变换 =', sc.view_settings.view_transform, flush=True)
sc.world=bpy.data.worlds.new('w'); sc.world.color=(0,0,0)
if WHICH=='vcol':
    bpy.ops.wm.ply_import(filepath='/root/cmp_poisson_vcol.ply')
else:
    # 🔴 OBJ 导入器默认做 Y-up -> Z-up 轴转换(实测把 y,z 换了位还取负), PLY 导入器不做。
    #    这里显式关掉, 两边都保持原数据坐标, 才能共用同一套 SfM 相机。
    bpy.ops.wm.obj_import(filepath=os.environ.get('TEXOBJ','/root/texrecon_out/poisson.obj'), forward_axis='Y', up_axis='Z')
# Workbench 的 VERTEX 模式要有 active 颜色属性
for o in bpy.data.objects:
    if o.type=='MESH' and o.data.color_attributes:
        o.data.color_attributes.active_color=o.data.color_attributes[0]
        print('  激活颜色属性', o.data.color_attributes[0].name, flush=True)
print('导入完成, 物体数', len(bpy.data.objects), flush=True)
d=json.load(open(SFM))
I=d['intrinsics'][0]; W0=int(I['width']); H0=int(I['height'])
poses={p['poseId']:p['pose']['transform'] for p in d['poses']}
views=sorted([v for v in d['views'] if v['poseId'] in poses], key=lambda v:v['path'])
cam_data=bpy.data.cameras.new('c'); cam=bpy.data.objects.new('c',cam_data); sc.collection.objects.link(cam); sc.camera=cam
cam_data.sensor_fit='HORIZONTAL'; cam_data.sensor_width=float(I['sensorWidth']); cam_data.lens=float(I['focalLength'])
CV2BL=np.diag([1.0,-1.0,-1.0])     # CV 相机(+Z 前,+Y 下) -> Blender 相机(-Z 前,+Y 上)
for k in [33]:
    v=views[k]; t=poses[v['poseId']]
    R=np.array([float(x) for x in t['rotation']]).reshape(3,3)
    C=np.array([float(x) for x in t['center']])
    Rb=R.T@CV2BL                   # 相机->世界
    M=np.eye(4); M[:3,:3]=Rb; M[:3,3]=C
    cam.matrix_world=Matrix(M.tolist())
    sc.render.filepath=f'{OUTDIR}/{WHICH}_view{k:03d}.png'
    bpy.ops.render.render(write_still=True)
    print(f'  view {k:3d} -> {sc.render.filepath}', flush=True)
