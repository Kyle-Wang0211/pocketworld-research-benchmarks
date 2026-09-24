import bpy, numpy as np
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath='/root/texrecon_out/poisson.obj', forward_axis='Y', up_axis='Z')
cs={}
for im in bpy.data.images: cs[im.colorspace_settings.name]=cs.get(im.colorspace_settings.name,0)+1
print('贴图色彩空间统计:', cs)
sc=bpy.context.scene
print('场景 display_device:', sc.display_settings.display_device, '| view_transform:', sc.view_settings.view_transform)
sh=sc.display.shading
print('workbench light:', sh.light, '| color_type:', sh.color_type, '| studio_light:', sh.studio_light)
print('use_scene_lights:', sh.use_scene_lights, '| use_scene_world:', sh.use_scene_world)
