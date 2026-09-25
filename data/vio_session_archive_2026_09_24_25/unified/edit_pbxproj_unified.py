#!/usr/bin/env python3
"""Adds the unified-bench files to arloopbench's Runner target (idempotent; refuses if already present)."""
import re, sys
P = sys.argv[1]
s = open(P).read()
if 'PwBenchUnifiedPlugin.swift' in s:
    sys.exit('already edited')

def rid(n):  # 24 hex, fixed prefix for this edit
    return 'D5B1E0000000000000%06X' % n

files = [  # (id#, name, path, filetype, group, flags)
    (1, 'PwBenchUnifiedPlugin.swift', 'PwBenchUnifiedPlugin.swift', 'sourcecode.swift', 'runner', None),
    (2, 'PwSplatABRunner.swift', 'PwSplatABRunner.swift', 'sourcecode.swift', 'runner', None),
    (3, 'bench.mm', 'bench.mm', 'sourcecode.cpp.objcpp', 'splat', '-std=gnu++17 -O3'),
    (4, 'bench_points.mm', 'bench_points.mm', 'sourcecode.cpp.objcpp', 'splat', '-std=gnu++17 -O3'),
    (5, 'bench_cloud.mm', 'bench_cloud.mm', 'sourcecode.cpp.objcpp', 'splat', '-std=gnu++17 -O3'),
    (6, 'pw_splat_ab.h', 'pw_splat_ab.h', 'sourcecode.c.h', 'splat', None),
    (7, 'wgsl_arms.h', 'wgsl_arms.h', 'sourcecode.c.h', 'splat', None),
]
fws = [  # embedded, not linked (loaded on demand by PwBenchUnifiedPlugin)
    (11, 'PWVIOBenchKit.framework'),
    (12, 'PWXRSLAMEngine.framework'),
    (13, 'PWBasaltEngine.framework'),
]
GROUP_SPLAT = rid(100)

bf, fr = [], []
for n, name, path, ft, grp, flags in files:
    fr.append(f'\t\t{rid(n)} /* {name} */ = {{isa = PBXFileReference; includeInIndex = 1; lastKnownFileType = {ft}; path = {path}; sourceTree = "<group>"; }};\n')
    if ft.endswith('.h'):
        continue
    st = f' settings = {{COMPILER_FLAGS = "{flags}"; }};' if flags else ''
    bf.append(f'\t\t{rid(n + 0x1000)} /* {name} in Sources */ = {{isa = PBXBuildFile; fileRef = {rid(n)} /* {name} */;{st} }};\n')
for n, name in fws:
    fr.append(f'\t\t{rid(n)} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = wrapper.framework; name = {name}; path = ../../vendor/pw_viobench_kit/{name}; sourceTree = "<group>"; }};\n')
    bf.append(f'\t\t{rid(n + 0x1000)} /* {name} in Embed Frameworks */ = {{isa = PBXBuildFile; fileRef = {rid(n)} /* {name} */; settings = {{ATTRIBUTES = (CodeSignOnCopy, RemoveHeadersOnCopy, ); }}; }};\n')

def insert_after(marker, text):
    global s
    i = s.index(marker) + len(marker)
    s = s[:i] + text + s[i:]

insert_after('/* Begin PBXBuildFile section */\n', ''.join(bf))
insert_after('/* Begin PBXFileReference section */\n', ''.join(fr))

# PwSplatAB group
splat_children = ''.join(f'\t\t\t\t{rid(n)} /* {name} */,\n' for n, name, _, _, g, _ in files if g == 'splat')
group = (f'\t\t{GROUP_SPLAT} /* PwSplatAB */ = {{\n\t\t\tisa = PBXGroup;\n\t\t\tchildren = (\n{splat_children}\t\t\t);\n'
         f'\t\t\tpath = PwSplatAB;\n\t\t\tsourceTree = "<group>";\n\t\t}};\n')
insert_after('/* Begin PBXGroup section */\n', group)

# Runner group children
m = re.search(r'\t\t97C146F01CF9000F007C117D /\* Runner \*/ = \{\n\t\t\tisa = PBXGroup;\n\t\t\tchildren = \(\n', s)
assert m, 'Runner group'
runner_children = ''.join(f'\t\t\t\t{rid(n)} /* {name} */,\n' for n, name, _, _, g, _ in files if g == 'runner')
runner_children += f'\t\t\t\t{GROUP_SPLAT} /* PwSplatAB */,\n'
runner_children += ''.join(f'\t\t\t\t{rid(n)} /* {name} */,\n' for n, name in fws)
s = s[:m.end()] + runner_children + s[m.end():]

# Runner Sources phase
m = re.search(r'\t\t97C146EA1CF9000F007C117D /\* Sources \*/ = \{\n\t\t\tisa = PBXSourcesBuildPhase;\n\t\t\tbuildActionMask = \d+;\n\t\t\tfiles = \(\n', s)
assert m, 'Sources phase'
src = ''.join(f'\t\t\t\t{rid(n + 0x1000)} /* {name} in Sources */,\n' for n, name, _, ft, _, _ in files if not ft.endswith('.h'))
s = s[:m.end()] + src + s[m.end():]

# Embed Frameworks phase
m = re.search(r'\t\t9705A1C41CF9048500538489 /\* Embed Frameworks \*/ = \{\n\t\t\tisa = PBXCopyFilesBuildPhase;\n\t\t\tbuildActionMask = \d+;\n\t\t\tdstPath = "";\n\t\t\tdstSubfolderSpec = 10;\n\t\t\tfiles = \(\n', s)
assert m, 'Embed phase'
emb = ''.join(f'\t\t\t\t{rid(n + 0x1000)} /* {name} in Embed Frameworks */,\n' for n, name in fws)
s = s[:m.end()] + emb + s[m.end():]

open(P, 'w').write(s)
print('edited', P)
