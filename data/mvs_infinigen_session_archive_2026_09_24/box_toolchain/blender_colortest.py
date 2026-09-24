# 色彩直通测试: 一个正对相机的方片, 贴一张已知纯色贴图, 看渲染出来的像素值等不等于贴图值。
import bpy, numpy as np, os
TEST=[(64,64,64),(128,128,128),(200,200,200),(180,90,45)]   # BGR 顺序写盘
os.makedirs('/root/cttest',exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc=bpy.context.scene
sc.render.engine='BLENDER_WORKBENCH'
sh=sc.display.shading; sh.light='FLAT'; sh.color_type='TEXTURE'
sh.show_object_outline=False; sh.show_specular_highlight=False
sc.render.resolution_x=128; sc.render.resolution_y=128
sc.view_settings.view_transform='Standard'; sc.view_settings.look='None'
sc.view_settings.exposure=0.0; sc.view_settings.gamma=1.0
sc.world=bpy.data.worlds.new('w'); sc.world.color=(0,0,0)
bpy.ops.mesh.primitive_plane_add(size=2)
ob=bpy.context.object
m=bpy.data.materials.new('m'); m.use_nodes=True; ob.data.materials.append(m)
bsdf=m.node_tree.nodes['Principled BSDF']
tex=m.node_tree.nodes.new('ShaderNodeTexImage')
m.node_tree.links.new(bsdf.inputs['Base Color'], tex.outputs['Color'])
cam_d=bpy.data.cameras.new('c'); cam=bpy.data.objects.new('c',cam_d); sc.collection.objects.link(cam); sc.camera=cam
cam_d.type='ORTHO'; cam_d.ortho_scale=2.0
cam.location=(0,0,5); cam.rotation_euler=(0,0,0)
for i,(b,g,r) in enumerate(TEST):
    p=f'/root/cttest/solid{i}.png'
    arr=np.zeros((16,16,3),np.uint8); arr[:,:, 0]=b; arr[:,:,1]=g; arr[:,:,2]=r
    import struct, zlib
    def wpng(path,a):
        h,w,_=a.shape
        raw=b''.join(b'\x00'+a[y,:,::-1].tobytes() for y in range(h))
        def chunk(t,d):
            c=t+d; return struct.pack('>I',len(d))+c+struct.pack('>I',zlib.crc32(c)&0xffffffff)
        open(path,'wb').write(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))
    wpng(p,arr)
    im=bpy.data.images.load(p); im.colorspace_settings.name='sRGB'
    tex.image=im
    sc.render.filepath=f'/root/cttest/render{i}.png'
    bpy.ops.render.render(write_still=True)
    print(f'TEST {i}: 贴图 BGR=({b},{g},{r})  ->  /root/cttest/render{i}.png', flush=True)
