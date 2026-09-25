# 计算 Mach-O 64 各段(section)字节的 sha256,用于核对改标签后机器码不变
import struct, sys, hashlib
def sections(p):
    b = open(p, 'rb').read()
    magic, ct, cs, ft, ncmds, sz, fl, rs = struct.unpack_from('<IiiIIIII', b, 0)
    off = 32; out = {}
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', b, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            segname = b[off+8:off+24].rstrip(b'\0').decode()
            nsects = struct.unpack_from('<I', b, off+64)[0]
            so = off + 72
            for i in range(nsects):
                sect = b[so:so+16].rstrip(b'\0').decode(); seg = b[so+16:so+32].rstrip(b'\0').decode()
                addr, size, offset = struct.unpack_from('<QQI', b, so+32)
                if offset:
                    out[seg+','+sect] = hashlib.sha256(b[offset:offset+size]).hexdigest()
                so += 80
        off += cmdsize
    return out
a = sections(sys.argv[1]); c = sections(sys.argv[2])
diff = [k for k in a if a.get(k) != c.get(k)]
print('__TEXT,__text', a.get('__TEXT,__text'), c.get('__TEXT,__text'))
print('节数', len(a), '不同的节', diff)
