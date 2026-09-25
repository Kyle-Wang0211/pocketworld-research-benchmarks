#!/usr/bin/python3
"""cmp_tests.py base.json new.json —— flutter test --reporter json 两次运行逐条对比(文件 + 用例名)。"""
import json, sys, os
def load(p):
    suites, tests, res = {}, {}, {}
    for line in open(p, errors='replace'):
        line = line.strip()
        if not line.startswith('{'): continue
        try: e = json.loads(line)
        except Exception: continue
        t = e.get('type')
        if t == 'suite': suites[e['suite']['id']] = os.path.relpath(e['suite']['path'], os.getcwd()) if e['suite'].get('path') else '?'
        elif t == 'testStart':
            tt = e['test']; sp = suites.get(tt['suiteID'], '?'); i = sp.find('test/'); tests[tt['id']] = (sp[i:] if i >= 0 else sp, tt['name'])
        elif t == 'testDone':
            if e.get('hidden'): continue
            k = tests.get(e['testID'])
            if k is None: continue
            res[k] = 'skip' if e.get('skipped') else e['result']
    return res
b, n = load(sys.argv[1]), load(sys.argv[2])
def summ(r):
    c = {}
    for v in r.values(): c[v] = c.get(v, 0) + 1
    return c
print('基线', summ(b)); print('新  ', summ(n))
common = set(b) & set(n)
changed = sorted(k for k in common if b[k] != n[k])
print('共同', len(common), '条;结果不同', len(changed), '条')
for k in changed: print('  变化', b[k], '→', n[k], k)
only_b = sorted(set(b) - set(n)); only_n = sorted(set(n) - set(b))
print('只在基线', len(only_b)); [print('  -', b[k], k) for k in only_b]
print('只在新  ', len(only_n)); [print('  +', n[k], k) for k in only_n]
