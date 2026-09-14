# -*- coding: utf-8 -*-
"""往官方 train.py 打两处最小补丁 (只在 --domain_balance>0 时改变行为):
  ① argparse 加 --domain_balance
  ② DataLoader 构造: sampler 分支 / 官方 shuffle=True 分支
精确字符串替换, 找不到原句就报错退出; 保留原文件的换行符 (CRLF/LF), 让 git diff 只有这几行。"""
import sys
p = sys.argv[1]
raw = open(p, newline="").read()
nl = "\r\n" if "\r\n" in raw else "\n"

OLD1 = "parser.add_argument('--trainviews', type=int, default=3,  help='trainviews')\n"
NEW1 = OLD1 + ("parser.add_argument('--domain_balance', type=int, default=0,\n"
               "                    help='>0: per epoch sample N tuples from EACH dataset (DUSt3R arXiv 2312.14132 Sec.4); 0 = official concat')\n")

OLD2 = ("    TrainImgLoader = DataLoader(train_dataset, args.batch_size,\n"
        "                                shuffle=True, num_workers=8, drop_last=True)\n")
NEW2 = ("    if args.domain_balance > 0:\n"
        "        from datasets.domain_sampler import EqualDomainSampler\n"
        "        domain_sampler = EqualDomainSampler(train_dataset.metas, args.domain_balance, args.seed)\n"
        "        print('domain_balance: sizes', domain_sampler.sizes(), '-> per epoch', args.domain_balance, 'each')\n"
        "        TrainImgLoader = DataLoader(train_dataset, args.batch_size,\n"
        "                                    sampler=domain_sampler, num_workers=8, drop_last=True)\n"
        "    else:\n"
        "        TrainImgLoader = DataLoader(train_dataset, args.batch_size,\n"
        "                                    shuffle=True, num_workers=8, drop_last=True)\n")

s = raw
for old, new in ((OLD1, NEW1), (OLD2, NEW2)):
    old, new = old.replace("\n", nl), new.replace("\n", nl)
    if s.count(old) != 1:
        sys.exit("PATCH FAIL: 原句出现 %d 次: %r" % (s.count(old), old[:60]))
    s = s.replace(old, new)
open(p, "w", newline="").write(s)
print("patched", p, "newline=%r" % nl)
