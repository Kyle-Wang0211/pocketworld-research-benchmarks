# -*- coding: utf-8 -*-
"""在已打 --domain_balance 补丁的 train.py 上再加 --repeat_cap (UniMax 封顶, 默认 0 = 关 = 行为与现在完全相同)。
精确字符串替换, 保留 CRLF。"""
import sys
p = sys.argv[1]
raw = open(p, newline="").read()
nl = "\r\n" if "\r\n" in raw else "\n"
OLD1 = ("parser.add_argument('--domain_balance', type=int, default=0,\n"
        "                    help='>0: per epoch sample N tuples from EACH dataset (DUSt3R arXiv 2312.14132 Sec.4); 0 = official concat')\n")
NEW1 = OLD1 + ("parser.add_argument('--repeat_cap', type=int, default=0,\n"
               "                    help='UniMax (arXiv 2304.09151 Sec.3) max repeats per dataset over the whole run; 0 = off (pure equal sampling)')\n")
OLD2 = "        domain_sampler = EqualDomainSampler(train_dataset.metas, args.domain_balance, args.seed)\n"
NEW2 = ("        domain_sampler = EqualDomainSampler(train_dataset.metas, args.domain_balance, args.seed,\n"
        "                                            repeat_cap=args.repeat_cap, total_epochs=args.epochs)\n"
        "        print('domain_balance: repeat_cap', args.repeat_cap, 'per-epoch counts', domain_sampler.counts)\n")
s = raw
for old, new in ((OLD1, NEW1), (OLD2, NEW2)):
    old, new = old.replace("\n", nl), new.replace("\n", nl)
    if s.count(old) != 1:
        sys.exit("PATCH FAIL: %d matches for %r" % (s.count(old), old[:50]))
    s = s.replace(old, new)
open(p, "w", newline="").write(s)
print("repeat_cap patch ok")
