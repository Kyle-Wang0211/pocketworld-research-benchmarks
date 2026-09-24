#!/usr/bin/env python3
# largest numPoints of any node in an octree (premise check for the dbgAccepted stress test)
import sys, importlib.util
spec = importlib.util.spec_from_file_location('c', sys.argv[2] if len(sys.argv) > 2 else '/root/aline_lodbuild/compare_octrees.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
meta, bpp, nodes = c.load_tree(sys.argv[1])
top = sorted(nodes.items(), key=lambda kv: -kv[1]['n'])[:5]
print('nodes', len(nodes), 'largest', [(k, v['n']) for k, v in top])
