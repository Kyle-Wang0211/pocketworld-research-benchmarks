import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
sc=bpy.context.scene
print('默认视图变换:', sc.view_settings.view_transform, '| look:', sc.view_settings.look, '| exposure:', sc.view_settings.exposure, '| gamma:', sc.view_settings.gamma)
print('可选视图变换:', [e.identifier for e in sc.view_settings.bl_rna.properties['view_transform'].enum_items])
bpy.ops.wm.ply_import(filepath='/root/cmp_poisson_vcol.ply')
o=[x for x in bpy.data.objects if x.type=='MESH'][0]
me=o.data
print('顶点数', len(me.vertices))
print('color_attributes:', [(a.name,a.domain,a.data_type) for a in me.color_attributes])
print('active_color:', me.color_attributes.active_color.name if me.color_attributes.active_color else None)
print('attributes 全部:', [(a.name,a.domain,a.data_type) for a in me.attributes][:8])
