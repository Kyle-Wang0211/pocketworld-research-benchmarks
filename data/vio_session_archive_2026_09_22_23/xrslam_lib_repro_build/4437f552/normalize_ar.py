#!/usr/bin/env python3
"""把 BSD(Mach-O)静态库的成员头里的 mtime/uid/gid 清零,使归档逐字节可复现。
只改 60 字节定长头里的三个字段,成员内容、顺序、大小、__.SYMDEF 的偏移表全不动。"""
import sys
def normalize(path):
    d=bytearray(open(path,'rb').read())
    assert d[:8]==b'!<arch>\n', 'not a BSD ar archive'
    p=8; n=0
    while p+60<=len(d):
        hdr=d[p:p+60]
        assert hdr[58:60]==b'`\n', f'bad member magic at {p}'
        size=int(bytes(hdr[48:58]).decode().strip())
        d[p+16:p+28]=b'0'.ljust(12)   # mtime
        d[p+28:p+34]=b'0'.ljust(6)    # uid
        d[p+34:p+40]=b'0'.ljust(6)    # gid
        n+=1
        p+=60+size
        if p%2: p+=1                  # 2 字节对齐
    open(path,'wb').write(bytes(d))
    return n
for f in sys.argv[1:]:
    print(f'normalized {normalize(f)} members: {f}')
