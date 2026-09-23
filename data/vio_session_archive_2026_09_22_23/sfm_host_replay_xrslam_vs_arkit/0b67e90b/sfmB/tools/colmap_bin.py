import struct, numpy as np
def read_images_bin(p):
    out = {}
    with open(p, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack('<I', f.read(4))[0]
            q = struct.unpack('<4d', f.read(32)); t = struct.unpack('<3d', f.read(24))
            cam = struct.unpack('<I', f.read(4))[0]
            name = b''
            while True:
                c = f.read(1)
                if c == b'\x00': break
                name += c
            n2 = struct.unpack('<Q', f.read(8))[0]
            f.read(n2 * 24)
            out[iid] = (np.array(q), np.array(t), name.decode())
    return out
