import sys
p=sys.argv[1]; s=open(p).read()
def rep(old,new,count=1):
    global s
    assert s.count(old)==count, (s.count(old), old[:100])
    s=s.replace(old,new)
P='FC168A00000000000000'
def fid(n): return P+('%04X'%n)
files=[
 ('AetherTexturePlugin.swift','AetherTexturePlugin.swift','"<group>"','sourcecode.swift','Sources',None),
 ('MetalRenderer.swift','MetalRenderer.swift','"<group>"','sourcecode.swift','Sources',None),
 ('OfficialAetherARKitPlugin.swift','OfficialAetherARKitPlugin.swift','"<group>"','sourcecode.swift','Sources',None),
 ('OfficialArchiveBackgroundTask.swift','OfficialArchiveBackgroundTask.swift','"<group>"','sourcecode.swift','Sources',None),
 ('OfficialReconUmbrella.swift','OfficialReconUmbrella.swift','"<group>"','sourcecode.swift','Sources',None),
 ('PwARCameraLease.swift','PwARCameraLease.swift','"<group>"','sourcecode.swift','Sources',None),
 ('PwVioCapability.swift','PwVioCapability.swift','"<group>"','sourcecode.swift','Sources',None),
 ('PwVioSlamFeeder.swift','PwVioSlamFeeder.swift','"<group>"','sourcecode.swift','Sources',None),
 ('PwVioThermal.swift','PwVioThermal.swift','"<group>"','sourcecode.swift','Sources',None),
 ('PwVioTimebase.swift','PwVioTimebase.swift','"<group>"','sourcecode.swift','Sources',None),
 ('pw_jxl_bridge.h','pw_jxl_bridge.h','"<group>"','sourcecode.c.h',None,None),
 ('pw_jxl_bridge.mm','pw_jxl_bridge.mm','"<group>"','sourcecode.cpp.objcpp','Sources',None),
 ('pw_zpaq_bridge.h','pw_zpaq_bridge.h','"<group>"','sourcecode.c.h',None,None),
 ('pw_zpaq_bridge.cpp','pw_zpaq_bridge.cpp','"<group>"','sourcecode.cpp.cpp','Sources','-DNOJIT -Dunix'),
 ('pw_sqlite_descriptor_transform.h','pw_sqlite_descriptor_transform.h','"<group>"','sourcecode.c.h',None,None),
 ('pw_sqlite_descriptor_transform.cpp','pw_sqlite_descriptor_transform.cpp','"<group>"','sourcecode.cpp.cpp',None,None),
 ('libzpaq.cpp','Vendor/Zpaq/src/libzpaq.cpp','SOURCE_ROOT','sourcecode.cpp.cpp','Sources','-DNOJIT -Dunix'),
 ('libzpaq.h','Vendor/Zpaq/include/libzpaq.h','SOURCE_ROOT','sourcecode.c.h',None,None),
 ('PrivacyInfo.xcprivacy','PrivacyInfo.xcprivacy','"<group>"','text.xml','Resources',None),
 ('test_scene.jpg','TestFixtures/test_scene.jpg','"<group>"','image.jpeg','Resources',None),
 ('Zpaq-LICENSE.txt','Vendor/Zpaq/Zpaq-LICENSE.txt','SOURCE_ROOT','text','Resources',None),
 ('Lepton-LICENSE.txt','../vendor/lepton_jpeg/licenses/Lepton-LICENSE.txt','SOURCE_ROOT','text','Resources',None),
 ('Lepton-NOTICE.txt','../vendor/lepton_jpeg/licenses/Lepton-NOTICE.txt','SOURCE_ROOT','text','Resources',None),
 ('Rust-Crate-THIRD-PARTY-NOTICES.txt','../vendor/lepton_jpeg/licenses/Rust-Crate-THIRD-PARTY-NOTICES.txt','SOURCE_ROOT','text','Resources',None),
 ('Rust-Standard-Library-COPYRIGHT.html','../vendor/lepton_jpeg/licenses/Rust-Standard-Library-COPYRIGHT.html','SOURCE_ROOT','text.html','Resources',None),
]
def qs(x): return f'"{x}"' if any(c in x for c in '-+ ') else x
bf_lines=[]; fr_lines=[]; grp=[]; src=[]; res=[]
for i,(name,path,tree,ftype,phase,flags) in enumerate(files):
    fr=fid(0x100+i); bf=fid(0x200+i)
    namepart = '' if name==path else f'name = {qs(name)}; '
    fr_lines.append(f'\t\t{fr} /* {name} */ = {{isa = PBXFileReference; includeInIndex = 1; lastKnownFileType = {ftype}; {namepart}path = {qs(path)}; sourceTree = {tree}; }};\n')
    grp.append(f'\t\t\t\t{fr} /* {name} */,\n')
    if phase:
        settings = f' settings = {{COMPILER_FLAGS = "{flags}"; }};' if flags else ''
        bf_lines.append(f'\t\t{bf} /* {name} in {phase} */ = {{isa = PBXBuildFile; fileRef = {fr} /* {name} */;{settings} }};\n')
        (src if phase=='Sources' else res).append(f'\t\t\t\t{bf} /* {name} in {phase} */,\n')
rep('/* End PBXBuildFile section */', ''.join(bf_lines)+'/* End PBXBuildFile section */')
rep('/* End PBXFileReference section */', ''.join(fr_lines)+'/* End PBXFileReference section */')
rep('\t\t\t\t74858FAD1ED2DC5600515810 /* Runner-Bridging-Header.h */,\n\t\t\t);\n\t\t\tpath = Runner;',
    '\t\t\t\t74858FAD1ED2DC5600515810 /* Runner-Bridging-Header.h */,\n'+''.join(grp)+'\t\t\t);\n\t\t\tpath = Runner;')
rep('\t\t\t\t7884E8682EC3CC0700C636F2 /* SceneDelegate.swift in Sources */,\n',
    '\t\t\t\t7884E8682EC3CC0700C636F2 /* SceneDelegate.swift in Sources */,\n'+''.join(src))
rep('\t\t\t\t97C146FC1CF9000F007C117D /* Main.storyboard in Resources */,\n',
    '\t\t\t\t97C146FC1CF9000F007C117D /* Main.storyboard in Resources */,\n'+''.join(res))
SP=fid(0x300)
script=('# [pw][full-chain 2026-09-24] 台架自有。把 Dart 侧 const 开关 PW_FULL_CHAIN_BENCH(--dart-define)的取值\\n'
        '# 盖进产物 Info.plist 的 PWFullChainBench,AppDelegate 据此决定是否注册生产 168 的 Runner 内插件。\\n'
        '# 单一真源 = DART_DEFINES(Generated.xcconfig,base64 逗号分隔),不另设原生开关,两边不会各说各话。\\n'
        'v=NO\\n'
        'for d in $(printf %s \\"${DART_DEFINES:-}\\" | tr , \' \'); do\\n'
        '  if [ \\"$(printf %s \\"$d\\" | /usr/bin/base64 -D 2>/dev/null)\\" = PW_FULL_CHAIN_BENCH=true ]; then v=YES; fi\\n'
        'done\\n'
        'plist=\\"$TARGET_BUILD_DIR/$INFOPLIST_PATH\\"\\n'
        '/usr/libexec/PlistBuddy -c \\"Delete :PWFullChainBench\\" \\"$plist\\" >/dev/null 2>&1 || true\\n'
        '/usr/libexec/PlistBuddy -c \\"Add :PWFullChainBench bool $v\\" \\"$plist\\"\\n'
        'echo \\"PW_FULL_CHAIN_BENCH native switch = $v\\"\\n')
phase=(f'\t\t{SP} /* Stamp Full Chain Switch */ = {{\n'
       '\t\t\tisa = PBXShellScriptBuildPhase;\n\t\t\talwaysOutOfDate = 1;\n\t\t\tbuildActionMask = 2147483647;\n'
       '\t\t\tfiles = (\n\t\t\t);\n\t\t\tinputPaths = (\n\t\t\t\t"${TARGET_BUILD_DIR}/${INFOPLIST_PATH}",\n\t\t\t);\n'
       '\t\t\tname = "Stamp Full Chain Switch";\n\t\t\toutputPaths = (\n\t\t\t);\n'
       '\t\t\trunOnlyForDeploymentPostprocessing = 0;\n\t\t\tshellPath = /bin/sh;\n'
       f'\t\t\tshellScript = "{script}";\n\t\t\tshowEnvVarsInLog = 0;\n\t\t}};\n')
rep('/* End PBXShellScriptBuildPhase section */', phase+'/* End PBXShellScriptBuildPhase section */')
rep('\t\t\t\t33CAB5EADD18D54FB7022F7E /* [CP] Copy Pods Resources */,\n\t\t\t);',
    f'\t\t\t\t33CAB5EADD18D54FB7022F7E /* [CP] Copy Pods Resources */,\n\t\t\t\t{SP} /* Stamp Full Chain Switch */,\n\t\t\t);')
hs_old='\t\t\t\t\t"$(PROJECT_DIR)/../vendor/aether_lod/include",\n\t\t\t\t);\n\t\t\t\tINFOPLIST_FILE = Runner/Info.plist;\n'
hs_new=('\t\t\t\t\t"$(PROJECT_DIR)/../vendor/aether_lod/include",\n'
        '\t\t\t\t\t"$(PROJECT_DIR)/Vendor/JXL/include",\n\t\t\t\t\t"$(PROJECT_DIR)/Vendor/Zpaq/include",\n'
        '\t\t\t\t);\n\t\t\t\tINFOPLIST_FILE = Runner/Info.plist;\n'
        '\t\t\t\t"LIBRARY_SEARCH_PATHS[sdk=iphoneos*]" = (\n\t\t\t\t\t"$(inherited)",\n\t\t\t\t\t"$(PROJECT_DIR)/Vendor/JXL/lib",\n\t\t\t\t);\n'
        '\t\t\t\t"LIBRARY_SEARCH_PATHS[sdk=iphonesimulator*]" = (\n\t\t\t\t\t"$(inherited)",\n\t\t\t\t\t"$(PROJECT_DIR)/Vendor/JXL/lib-simulator",\n\t\t\t\t);\n')
rep(hs_old, hs_new, count=3)
gp_old='\t\t\t\tENABLE_BITCODE = NO;\n\t\t\t\tHEADER_SEARCH_PATHS = (\n'
gp_new=('\t\t\t\tENABLE_BITCODE = NO;\n\t\t\t\tGCC_PREPROCESSOR_DEFINITIONS = (\n\t\t\t\t\t"$(inherited)",\n'
        '\t\t\t\t\t"JXL_STATIC_DEFINE=1",\n\t\t\t\t\t"JXL_CMS_STATIC_DEFINE=1",\n\t\t\t\t\t"JXL_THREADS_STATIC_DEFINE=1",\n\t\t\t\t);\n'
        '\t\t\t\tHEADER_SEARCH_PATHS = (\n')
rep(gp_old, gp_new, count=3)
ld_old='\t\t\t\t\t"-Wl,-u,_pw_bench_replay_cancel",\n\t\t\t\t);\n'
flags=['-ljxl','-ljxl_cms','-ljxl_threads','-lhwy','-lbrotlienc','-lbrotlidec','-lbrotlicommon','-lc++','-lz',
 '-Wl,-u,_pw_jxl_version','-Wl,-u,_pw_jxl_revision','-Wl,-u,_pw_jxl_error_message','-Wl,-u,_pw_jxl_encode_jpeg_file',
 '-Wl,-u,_pw_jxl_reconstruct_jpeg_file','-Wl,-u,_pw_jxl_cancellation_generation','-Wl,-u,_pw_jxl_request_cancel',
 '-Wl,-u,_pw_jxl_encode_jpeg_file_cancellable','-Wl,-u,_pw_jxl_reconstruct_jpeg_file_cancellable',
 '-Wl,-u,_pw_zpaq_version','-Wl,-u,_pw_zpaq_revision','-Wl,-u,_pw_zpaq_error_message','-Wl,-u,_pw_zpaq_last_error',
 '-Wl,-u,_pw_zpaq_compress_file','-Wl,-u,_pw_zpaq_decompress_file','-Wl,-u,_pw_zpaq_cancellation_generation',
 '-Wl,-u,_pw_zpaq_request_cancel']
def q(f): return f'"{f}"' if (',' in f or '+' in f) else f
ld_new='\t\t\t\t\t"-Wl,-u,_pw_bench_replay_cancel",\n'+''.join(f'\t\t\t\t\t{q(f)},\n' for f in flags)+'\t\t\t\t);\n'
rep(ld_old, ld_new, count=3)
open(p,'w').write(s)
print("ok")
