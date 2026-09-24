#!/usr/bin/env python3
"""Retag arm64 Mach-O relocatable objects built for iOS so the macOS linker
accepts them. Only the platform load command changes; section bytes (the
machine code of the vendored Lepton 0.5.8 staticlib) are untouched.
  LC_VERSION_MIN_IPHONEOS (0x25) -> LC_VERSION_MIN_MACOSX (0x24), version 11.0
  LC_BUILD_VERSION (0x32) platform IOS(2) -> MACOS(1), minos 11.0
Prints a per-file summary; exits non-zero on anything unexpected."""
import struct, sys, glob, os
MH_MAGIC_64 = 0xfeedfacf
n_vm = n_bv = n_other = 0
for path in sys.argv[1:]:
    b = bytearray(open(path, 'rb').read())
    if len(b) < 32:
        print('skip tiny', path); continue
    magic, cputype, cpusub, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from('<IiiIIIII', b, 0)
    if magic != MH_MAGIC_64:
        print('not macho64', path); n_other += 1; continue
    off = 32; changed = False
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', b, off)
        if cmd == 0x25:  # LC_VERSION_MIN_IPHONEOS
            struct.pack_into('<III', b, off, 0x24, cmdsize, 0x000B0000)  # LC_VERSION_MIN_MACOSX 11.0
            changed = True; n_vm += 1
        elif cmd == 0x32:  # LC_BUILD_VERSION
            platform, minos = struct.unpack_from('<II', b, off + 8)
            if platform != 2:
                raise SystemExit(f'unexpected platform {platform} in {path}')
            struct.pack_into('<II', b, off + 8, 1, 0x000B0000)
            changed = True; n_bv += 1
        off += cmdsize
    if changed:
        open(path, 'wb').write(bytes(b))
print(f'retagged: version_min={n_vm} build_version={n_bv} non_macho={n_other}')
