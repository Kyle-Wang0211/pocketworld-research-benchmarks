
XRSLAMManager.cpp.o:	file format mach-o arm64

Disassembly of section __TEXT,__text:

0000000000000000 <ltmp0>:
       0:      	adrp	x8, 0x0 <ltmp0>
       4:      	add	x8, x8, #0x0
       8:      	ldarb	w8, [x8]
       c:      	tbz	w8, #0x0, 0x1c <ltmp0+0x1c>
      10:      	adrp	x0, 0x0 <ltmp0>
      14:      	add	x0, x0, #0x0
      18:      	ret
      1c:      	stp	x29, x30, [sp, #-0x10]!
      20:      	mov	x29, sp
      24:      	bl	0x24 <ltmp0+0x24>
      28:      	ldp	x29, x30, [sp], #0x10
      2c:      	adrp	x0, 0x0 <ltmp0>
      30:      	add	x0, x0, #0x0
      34:      	ret

0000000000000038 <__ZN12xrslam_0_5_013XRSLAMManagerC1Ev>:
      38:      	stp	xzr, xzr, [x0]
      3c:      	mov	w8, #0xaba7             ; =43943
      40:      	movk	w8, #0x32aa, lsl #16
      44:      	stp	xzr, x8, [x0, #0x10]
      48:      	movi.16b	v0, #0x0
      4c:      	stp	q0, q0, [x0, #0x20]
      50:      	stp	q0, q0, [x0, #0x40]
      54:      	stp	xzr, x8, [x0, #0x60]
      58:      	stp	q0, q0, [x0, #0x70]
      5c:      	str	q0, [x0, #0x90]
      60:      	str	xzr, [x0, #0xa0]
      64:      	stp	xzr, xzr, [x0, #0xb0]
      68:      	mov	x9, #0x3ff0000000000000 ; =4607182418800017408
      6c:      	stp	xzr, x9, [x0, #0xc0]
      70:      	stp	xzr, xzr, [x0, #0xd8]
      74:      	str	xzr, [x0, #0xd0]
      78:      	str	xzr, [x0, #0xf0]
      7c:      	strb	wzr, [x0, #0xf8]
      80:      	str	x8, [x0, #0x100]
      84:      	add	x8, x0, #0x108
      88:      	stp	q0, q0, [x8]
      8c:      	stp	q0, q0, [x8, #0x20]
      90:      	str	q0, [x8, #0x40]
      94:      	stur	q0, [x8, #0x49]
      98:      	ret

000000000000009c <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev>:
      9c:      	b	0x9c <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev>

00000000000000a0 <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv>:
      a0:      	ldr	x8, [x0, #0x10]
      a4:      	cbz	x8, 0xc0 <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv+0x20>
      a8:      	ldr	x9, [x8, #0x8]
      ac:      	cbz	x9, 0xc8 <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv+0x28>
      b0:      	ldr	x0, [x9, #0xa0]
      b4:      	ldr	x8, [x8, #0x10]
      b8:      	cbnz	x8, 0xd4 <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv+0x34>
      bc:      	ret
      c0:      	mov	w0, #0x0                ; =0
      c4:      	ret
      c8:      	mov	x0, #0x0                ; =0
      cc:      	ldr	x8, [x8, #0x10]
      d0:      	cbz	x8, 0xbc <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv+0x1c>
      d4:      	ldr	x8, [x8, #0x88]
      d8:      	add	x0, x8, x0
      dc:      	ret

00000000000000e0 <__ZN12xrslam_0_5_013XRSLAMManagerC2Ev>:
      e0:      	stp	xzr, xzr, [x0]
      e4:      	mov	w8, #0xaba7             ; =43943
      e8:      	movk	w8, #0x32aa, lsl #16
      ec:      	stp	xzr, x8, [x0, #0x10]
      f0:      	movi.16b	v0, #0x0
      f4:      	stp	q0, q0, [x0, #0x20]
      f8:      	stp	q0, q0, [x0, #0x40]
      fc:      	stp	xzr, x8, [x0, #0x60]
     100:      	stp	q0, q0, [x0, #0x70]
     104:      	str	q0, [x0, #0x90]
     108:      	str	xzr, [x0, #0xa0]
     10c:      	stp	xzr, xzr, [x0, #0xb0]
     110:      	mov	x9, #0x3ff0000000000000 ; =4607182418800017408
     114:      	stp	xzr, x9, [x0, #0xc0]
     118:      	stp	xzr, xzr, [x0, #0xd8]
     11c:      	str	xzr, [x0, #0xd0]
     120:      	str	xzr, [x0, #0xf0]
     124:      	strb	wzr, [x0, #0xf8]
     128:      	str	x8, [x0, #0x100]
     12c:      	add	x8, x0, #0x108
     130:      	stp	q0, q0, [x8]
     134:      	stp	q0, q0, [x8, #0x20]
     138:      	str	q0, [x8, #0x40]
     13c:      	stur	q0, [x8, #0x49]
     140:      	ret

0000000000000144 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev>:
     144:      	stp	x20, x19, [sp, #-0x20]!
     148:      	stp	x29, x30, [sp, #0x10]
     14c:      	add	x29, sp, #0x10
     150:      	ldr	x19, [x0, #0x8]
     154:      	cbz	x19, 0x170 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev+0x2c>
     158:      	add	x8, x19, #0x8
     15c:      	ldaxr	x9, [x8]
     160:      	sub	x10, x9, #0x1
     164:      	stlxr	w11, x10, [x8]
     168:      	cbnz	w11, 0x15c <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev+0x18>
     16c:      	cbz	x9, 0x17c <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev+0x38>
     170:      	ldp	x29, x30, [sp, #0x10]
     174:      	ldp	x20, x19, [sp], #0x20
     178:      	ret
     17c:      	ldr	x8, [x19]
     180:      	ldr	x8, [x8, #0x10]
     184:      	mov	x20, x0
     188:      	mov	x0, x19
     18c:      	blr	x8
     190:      	mov	x0, x19
     194:      	bl	0x194 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev+0x50>
     198:      	mov	x0, x20
     19c:      	ldp	x29, x30, [sp, #0x10]
     1a0:      	ldp	x20, x19, [sp], #0x20
     1a4:      	ret

00000000000001a8 <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev>:
     1a8:      	stp	x20, x19, [sp, #-0x20]!
     1ac:      	stp	x29, x30, [sp, #0x10]
     1b0:      	add	x29, sp, #0x10
     1b4:      	ldr	x19, [x0, #0x8]
     1b8:      	cbz	x19, 0x1d4 <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev+0x2c>
     1bc:      	add	x8, x19, #0x8
     1c0:      	ldaxr	x9, [x8]
     1c4:      	sub	x10, x9, #0x1
     1c8:      	stlxr	w11, x10, [x8]
     1cc:      	cbnz	w11, 0x1c0 <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev+0x18>
     1d0:      	cbz	x9, 0x1e0 <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev+0x38>
     1d4:      	ldp	x29, x30, [sp, #0x10]
     1d8:      	ldp	x20, x19, [sp], #0x20
     1dc:      	ret
     1e0:      	ldr	x8, [x19]
     1e4:      	ldr	x8, [x8, #0x10]
     1e8:      	mov	x20, x0
     1ec:      	mov	x0, x19
     1f0:      	blr	x8
     1f4:      	mov	x0, x19
     1f8:      	bl	0x1f8 <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev+0x50>
     1fc:      	mov	x0, x20
     200:      	ldp	x29, x30, [sp, #0x10]
     204:      	ldp	x20, x19, [sp], #0x20
     208:      	ret

000000000000020c <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev>:
     20c:      	stp	x20, x19, [sp, #-0x20]!
     210:      	stp	x29, x30, [sp, #0x10]
     214:      	add	x29, sp, #0x10
     218:      	mov	x19, x0
     21c:      	add	x0, x0, #0x100
     220:      	bl	0x220 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x14>
     224:      	add	x0, x19, #0x68
     228:      	bl	0x228 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x1c>
     22c:      	ldr	x20, [x19, #0x60]
     230:      	cbz	x20, 0x264 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x58>
     234:      	add	x8, x20, #0x8
     238:      	ldaxr	x9, [x8]
     23c:      	sub	x10, x9, #0x1
     240:      	stlxr	w11, x10, [x8]
     244:      	cbnz	w11, 0x238 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x2c>
     248:      	cbnz	x9, 0x264 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x58>
     24c:      	ldr	x8, [x20]
     250:      	ldr	x8, [x8, #0x10]
     254:      	mov	x0, x20
     258:      	blr	x8
     25c:      	mov	x0, x20
     260:      	bl	0x260 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x54>
     264:      	add	x0, x19, #0x18
     268:      	bl	0x268 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x5c>
     26c:      	ldr	x0, [x19, #0x10]
     270:      	str	xzr, [x19, #0x10]
     274:      	cbz	x0, 0x284 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x78>
     278:      	ldr	x8, [x0]
     27c:      	ldr	x8, [x8, #0x8]
     280:      	blr	x8
     284:      	ldr	x20, [x19, #0x8]
     288:      	cbz	x20, 0x2a4 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x98>
     28c:      	add	x8, x20, #0x8
     290:      	ldaxr	x9, [x8]
     294:      	sub	x10, x9, #0x1
     298:      	stlxr	w11, x10, [x8]
     29c:      	cbnz	w11, 0x290 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x84>
     2a0:      	cbz	x9, 0x2b4 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0xa8>
     2a4:      	mov	x0, x19
     2a8:      	ldp	x29, x30, [sp, #0x10]
     2ac:      	ldp	x20, x19, [sp], #0x20
     2b0:      	ret
     2b4:      	ldr	x8, [x20]
     2b8:      	ldr	x8, [x8, #0x10]
     2bc:      	mov	x0, x20
     2c0:      	blr	x8
     2c4:      	mov	x0, x20
     2c8:      	bl	0x2c8 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0xbc>
     2cc:      	mov	x0, x19
     2d0:      	ldp	x29, x30, [sp, #0x10]
     2d4:      	ldp	x20, x19, [sp], #0x20
     2d8:      	ret

00000000000002dc <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE>:
     2dc:      	sub	sp, sp, #0x50
     2e0:      	stp	x22, x21, [sp, #0x20]
     2e4:      	stp	x20, x19, [sp, #0x30]
     2e8:      	stp	x29, x30, [sp, #0x40]
     2ec:      	add	x29, sp, #0x40
     2f0:      	mov	x20, x1
     2f4:      	mov	x19, x0
     2f8:      	mov	w0, #0x1a0              ; =416
     2fc:      	bl	0x2fc <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x20>
     300:      	mov	x21, x0
     304:      	ldp	x9, x8, [x20]
     308:      	stp	x9, x8, [sp, #0x10]
     30c:      	cbz	x8, 0x324 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x48>
     310:      	add	x8, x8, #0x8
     314:      	ldxr	x9, [x8]
     318:      	add	x9, x9, #0x1
     31c:      	stxr	w10, x9, [x8]
     320:      	cbnz	w10, 0x314 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x38>
     324:      	add	x1, sp, #0x10
     328:      	mov	x0, x21
     32c:      	bl	0x32c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x50>
     330:      	ldr	x22, [sp, #0x18]
     334:      	cbz	x22, 0x368 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x8c>
     338:      	add	x8, x22, #0x8
     33c:      	ldaxr	x9, [x8]
     340:      	sub	x10, x9, #0x1
     344:      	stlxr	w11, x10, [x8]
     348:      	cbnz	w11, 0x33c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x60>
     34c:      	cbnz	x9, 0x368 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x8c>
     350:      	ldr	x8, [x22]
     354:      	ldr	x8, [x8, #0x10]
     358:      	mov	x0, x22
     35c:      	blr	x8
     360:      	mov	x0, x22
     364:      	bl	0x364 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x88>
     368:      	ldr	x0, [x19, #0x10]
     36c:      	str	x21, [x19, #0x10]
     370:      	cbz	x0, 0x380 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xa4>
     374:      	ldr	x8, [x0]
     378:      	ldr	x8, [x8, #0x8]
     37c:      	blr	x8
     380:      	ldp	x9, x8, [x20]
     384:      	cbz	x8, 0x39c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xc0>
     388:      	add	x10, x8, #0x8
     38c:      	ldxr	x11, [x10]
     390:      	add	x11, x11, #0x1
     394:      	stxr	w12, x11, [x10]
     398:      	cbnz	w12, 0x38c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xb0>
     39c:      	ldr	x20, [x19, #0x8]
     3a0:      	stp	x9, x8, [x19]
     3a4:      	cbz	x20, 0x3d8 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xfc>
     3a8:      	add	x8, x20, #0x8
     3ac:      	ldaxr	x9, [x8]
     3b0:      	sub	x10, x9, #0x1
     3b4:      	stlxr	w11, x10, [x8]
     3b8:      	cbnz	w11, 0x3ac <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xd0>
     3bc:      	cbnz	x9, 0x3d8 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xfc>
     3c0:      	ldr	x8, [x20]
     3c4:      	ldr	x8, [x8, #0x10]
     3c8:      	mov	x0, x20
     3cc:      	blr	x8
     3d0:      	mov	x0, x20
     3d4:      	bl	0x3d4 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xf8>
     3d8:      	adrp	x8, 0x0 <ltmp0>
     3dc:      	add	x8, x8, #0x0
     3e0:      	str	x8, [sp]
     3e4:      	adrp	x1, 0x0 <ltmp0>
     3e8:      	add	x1, x1, #0x0
     3ec:      	mov	w0, #0x0                ; =0
     3f0:      	bl	0x3f0 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x114>
     3f4:      	ldr	x0, [x19]
     3f8:      	bl	0x3f8 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x11c>
     3fc:      	adrp	x0, 0x0 <ltmp0>
     400:      	ldr	x0, [x0]
     404:      	adrp	x1, 0x0 <ltmp0>
     408:      	add	x1, x1, #0x0
     40c:      	mov	w2, #0x20               ; =32
     410:      	bl	0x410 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x134>
     414:      	adrp	x1, 0x0 <ltmp0>
     418:      	add	x1, x1, #0x0
     41c:      	mov	w2, #0x5                ; =5
     420:      	bl	0x420 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x144>
     424:      	adrp	x1, 0x0 <ltmp0>
     428:      	add	x1, x1, #0x0
     42c:      	mov	w2, #0x18               ; =24
     430:      	bl	0x430 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x154>
     434:      	mov	x19, x0
     438:      	ldr	x8, [x0]
     43c:      	ldur	x9, [x8, #-0x18]
     440:      	add	x8, sp, #0x10
     444:      	add	x0, x0, x9
     448:      	bl	0x448 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x16c>
     44c:      	adrp	x1, 0x0 <ltmp0>
     450:      	ldr	x1, [x1]
     454:      	add	x0, sp, #0x10
     458:      	bl	0x458 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x17c>
     45c:      	ldr	x8, [x0]
     460:      	ldr	x8, [x8, #0x38]
     464:      	mov	w1, #0xa                ; =10
     468:      	blr	x8
     46c:      	mov	x20, x0
     470:      	add	x0, sp, #0x10
     474:      	bl	0x474 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x198>
     478:      	mov	x0, x19
     47c:      	mov	x1, x20
     480:      	bl	0x480 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1a4>
     484:      	mov	x0, x19
     488:      	bl	0x488 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1ac>
     48c:      	ldp	x29, x30, [sp, #0x40]
     490:      	ldp	x20, x19, [sp, #0x30]
     494:      	ldp	x22, x21, [sp, #0x20]
     498:      	add	sp, sp, #0x50
     49c:      	ret
     4a0:      	mov	x19, x0
     4a4:      	add	x0, sp, #0x10
     4a8:      	bl	0x4a8 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1cc>
     4ac:      	mov	x0, x21
     4b0:      	bl	0x4b0 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1d4>
     4b4:      	mov	x0, x19
     4b8:      	bl	0x4b8 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1dc>
     4bc:      	mov	x19, x0
     4c0:      	add	x0, sp, #0x10
     4c4:      	bl	0x4c4 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1e8>
     4c8:      	mov	x0, x19
     4cc:      	bl	0x4cc <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1f0>

00000000000004d0 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_>:
     4d0:      	sub	sp, sp, #0x30
     4d4:      	stp	x20, x19, [sp, #0x10]
     4d8:      	stp	x29, x30, [sp, #0x20]
     4dc:      	add	x29, sp, #0x20
     4e0:      	mov	x19, x0
     4e4:      	ldr	x8, [x0]
     4e8:      	ldur	x9, [x8, #-0x18]
     4ec:      	add	x8, sp, #0x8
     4f0:      	add	x0, x0, x9
     4f4:      	bl	0x4f4 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x24>
     4f8:      	adrp	x1, 0x0 <ltmp0>
     4fc:      	ldr	x1, [x1]
     500:      	add	x0, sp, #0x8
     504:      	bl	0x504 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x34>
     508:      	ldr	x8, [x0]
     50c:      	ldr	x8, [x8, #0x38]
     510:      	mov	w1, #0xa                ; =10
     514:      	blr	x8
     518:      	mov	x20, x0
     51c:      	add	x0, sp, #0x8
     520:      	bl	0x520 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x50>
     524:      	mov	x0, x19
     528:      	mov	x1, x20
     52c:      	bl	0x52c <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x5c>
     530:      	mov	x0, x19
     534:      	bl	0x534 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x64>
     538:      	mov	x0, x19
     53c:      	ldp	x29, x30, [sp, #0x20]
     540:      	ldp	x20, x19, [sp, #0x10]
     544:      	add	sp, sp, #0x30
     548:      	ret
     54c:      	mov	x19, x0
     550:      	add	x0, sp, #0x8
     554:      	bl	0x554 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x84>
     558:      	mov	x0, x19
     55c:      	bl	0x55c <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x8c>

0000000000000560 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv>:
     560:      	sub	sp, sp, #0x30
     564:      	stp	x20, x19, [sp, #0x10]
     568:      	stp	x29, x30, [sp, #0x20]
     56c:      	add	x29, sp, #0x20
     570:      	mov	x19, x0
     574:      	add	x0, x0, #0x18
     578:      	bl	0x578 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x18>
     57c:      	ldr	x20, [x19, #0x60]
     580:      	stp	xzr, xzr, [x19, #0x58]
     584:      	cbz	x20, 0x5b8 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x58>
     588:      	add	x8, x20, #0x8
     58c:      	ldaxr	x9, [x8]
     590:      	sub	x10, x9, #0x1
     594:      	stlxr	w11, x10, [x8]
     598:      	cbnz	w11, 0x58c <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x2c>
     59c:      	cbnz	x9, 0x5b8 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x58>
     5a0:      	ldr	x8, [x20]
     5a4:      	ldr	x8, [x8, #0x10]
     5a8:      	mov	x0, x20
     5ac:      	blr	x8
     5b0:      	mov	x0, x20
     5b4:      	bl	0x5b4 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x54>
     5b8:      	add	x0, x19, #0x18
     5bc:      	bl	0x5bc <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x5c>
     5c0:      	add	x0, x19, #0x100
     5c4:      	bl	0x5c4 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x64>
     5c8:      	strb	wzr, [x19, #0x160]
     5cc:      	add	x0, x19, #0x100
     5d0:      	bl	0x5d0 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x70>
     5d4:      	ldr	x0, [x19, #0x10]
     5d8:      	str	xzr, [x19, #0x10]
     5dc:      	cbz	x0, 0x5ec <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x8c>
     5e0:      	ldr	x8, [x0]
     5e4:      	ldr	x8, [x8, #0x8]
     5e8:      	blr	x8
     5ec:      	ldr	x20, [x19, #0x8]
     5f0:      	stp	xzr, xzr, [x19]
     5f4:      	cbz	x20, 0x628 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xc8>
     5f8:      	add	x8, x20, #0x8
     5fc:      	ldaxr	x9, [x8]
     600:      	sub	x10, x9, #0x1
     604:      	stlxr	w11, x10, [x8]
     608:      	cbnz	w11, 0x5fc <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x9c>
     60c:      	cbnz	x9, 0x628 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xc8>
     610:      	ldr	x8, [x20]
     614:      	ldr	x8, [x8, #0x10]
     618:      	mov	x0, x20
     61c:      	blr	x8
     620:      	mov	x0, x20
     624:      	bl	0x624 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xc4>
     628:      	adrp	x0, 0x0 <ltmp0>
     62c:      	ldr	x0, [x0]
     630:      	adrp	x1, 0x0 <ltmp0>
     634:      	add	x1, x1, #0x0
     638:      	mov	w2, #0x21               ; =33
     63c:      	bl	0x63c <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xdc>
     640:      	adrp	x1, 0x0 <ltmp0>
     644:      	add	x1, x1, #0x0
     648:      	mov	w2, #0x5                ; =5
     64c:      	bl	0x64c <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xec>
     650:      	adrp	x1, 0x0 <ltmp0>
     654:      	add	x1, x1, #0x0
     658:      	mov	w2, #0x18               ; =24
     65c:      	bl	0x65c <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xfc>
     660:      	mov	x19, x0
     664:      	ldr	x8, [x0]
     668:      	ldur	x9, [x8, #-0x18]
     66c:      	add	x8, sp, #0x8
     670:      	add	x0, x0, x9
     674:      	bl	0x674 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x114>
     678:      	adrp	x1, 0x0 <ltmp0>
     67c:      	ldr	x1, [x1]
     680:      	add	x0, sp, #0x8
     684:      	bl	0x684 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x124>
     688:      	ldr	x8, [x0]
     68c:      	ldr	x8, [x8, #0x38]
     690:      	mov	w1, #0xa                ; =10
     694:      	blr	x8
     698:      	mov	x20, x0
     69c:      	add	x0, sp, #0x8
     6a0:      	bl	0x6a0 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x140>
     6a4:      	mov	x0, x19
     6a8:      	mov	x1, x20
     6ac:      	bl	0x6ac <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x14c>
     6b0:      	mov	x0, x19
     6b4:      	bl	0x6b4 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x154>
     6b8:      	ldp	x29, x30, [sp, #0x20]
     6bc:      	ldp	x20, x19, [sp, #0x10]
     6c0:      	add	sp, sp, #0x30
     6c4:      	ret
     6c8:      	mov	x19, x0
     6cc:      	add	x0, sp, #0x8
     6d0:      	bl	0x6d0 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x170>
     6d4:      	mov	x0, x19
     6d8:      	bl	0x6d8 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x178>

00000000000006dc <__ZN12xrslam_0_5_013XRSLAMManager12CheckLicenseEPKcS2_>:
     6dc:      	mov	w0, #0x1                ; =1
     6e0:      	ret

00000000000006e4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage>:
     6e4:      	sub	sp, sp, #0x170
     6e8:      	stp	d13, d12, [sp, #0xf0]
     6ec:      	stp	d11, d10, [sp, #0x100]
     6f0:      	stp	d9, d8, [sp, #0x110]
     6f4:      	stp	x26, x25, [sp, #0x120]
     6f8:      	stp	x24, x23, [sp, #0x130]
     6fc:      	stp	x22, x21, [sp, #0x140]
     700:      	stp	x20, x19, [sp, #0x150]
     704:      	stp	x29, x30, [sp, #0x160]
     708:      	add	x29, sp, #0x160
     70c:      	ldr	w8, [x1, #0x14]
     710:      	cbz	w8, 0x73c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x58>
     714:      	ldp	x29, x30, [sp, #0x160]
     718:      	ldp	x20, x19, [sp, #0x150]
     71c:      	ldp	x22, x21, [sp, #0x140]
     720:      	ldp	x24, x23, [sp, #0x130]
     724:      	ldp	x26, x25, [sp, #0x120]
     728:      	ldp	d9, d8, [sp, #0x110]
     72c:      	ldp	d11, d10, [sp, #0x100]
     730:      	ldp	d13, d12, [sp, #0xf0]
     734:      	add	sp, sp, #0x170
     738:      	ret
     73c:      	mov	x20, x1
     740:      	mov	x19, x0
     744:      	sub	x8, x29, #0x98
     748:      	bl	0x748 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x64>
     74c:      	ldr	x0, [x19]
     750:      	ldr	x8, [x0]
     754:      	ldr	x9, [x8, #0x10]
     758:      	add	x8, sp, #0x60
     75c:      	blr	x9
     760:      	ldr	d8, [sp, #0x60]
     764:      	ldr	x0, [x19]
     768:      	ldr	x8, [x0]
     76c:      	ldr	x9, [x8, #0x10]
     770:      	add	x8, sp, #0x60
     774:      	blr	x9
     778:      	ldr	d9, [sp, #0x68]
     77c:      	ldr	d0, [x20, #0x8]
     780:      	ldur	x8, [x29, #-0x98]
     784:      	str	d0, [x8, #0x8]
     788:      	ldr	x9, [x20, #0x20]
     78c:      	cbz	x9, 0x808 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
     790:      	ldr	w10, [x20, #0x1c]
     794:      	cmp	w10, #0x48
     798:      	b.ne	0x808 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
     79c:      	ldr	w10, [x9, #0x40]
     7a0:      	cmp	w10, #0x1
     7a4:      	b.ne	0x808 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
     7a8:      	ldr	d10, [x9, #0x20]
     7ac:      	fcmp	d10, #0.0
     7b0:      	b.le	0x808 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
     7b4:      	ldr	d11, [x9, #0x28]
     7b8:      	fcmp	d11, #0.0
     7bc:      	b.le	0x808 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
     7c0:      	ldp	d12, d13, [x9, #0x30]
     7c4:      	stp	xzr, xzr, [x8, #0x18]
     7c8:      	str	xzr, [x8, #0x28]
     7cc:      	str	xzr, [x8, #0x38]
     7d0:      	mov	x9, #0x3ff0000000000000 ; =4607182418800017408
     7d4:      	str	x9, [x8, #0x50]
     7d8:      	str	d10, [x8, #0x10]
     7dc:      	str	d11, [x8, #0x30]
     7e0:      	stp	d12, d13, [x8, #0x40]
     7e4:      	mov	w21, #0x1               ; =1
     7e8:      	strb	w21, [x8, #0x58]
     7ec:      	add	x0, x19, #0x100
     7f0:      	bl	0x7f0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x10c>
     7f4:      	stp	d10, d11, [x19, #0x140]
     7f8:      	stp	d12, d13, [x19, #0x150]
     7fc:      	strb	w21, [x19, #0x160]
     800:      	add	x0, x19, #0x100
     804:      	bl	0x804 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x120>
     808:      	fcvtzs	w8, d8
     80c:      	fcvtzs	w9, d9
     810:      	mov	w10, #0x42ff0000        ; =1124007936
     814:      	str	w10, [sp, #0x60]
     818:      	add	x10, sp, #0x60
     81c:      	orr	x21, x10, #0x8
     820:      	movi.16b	v0, #0x0
     824:      	stur	q0, [sp, #0x64]
     828:      	stur	q0, [sp, #0x74]
     82c:      	stur	q0, [sp, #0x84]
     830:      	str	q0, [sp, #0x90]
     834:      	add	x22, x10, #0x50
     838:      	stp	x21, x22, [sp, #0xa0]
     83c:      	stp	xzr, xzr, [sp, #0xb0]
     840:      	ldr	w10, [x20, #0x18]
     844:      	cmp	w10, #0x4
     848:      	b.eq	0xa88 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3a4>
     84c:      	cmp	w10, #0x3
     850:      	b.eq	0x970 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x28c>
     854:      	cmp	w10, #0x1
     858:      	b.ne	0x11ec <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb08>
     85c:      	ldr	x10, [x20]
     860:      	ldrsw	x11, [x20, #0x10]
     864:      	mov	x24, sp
     868:      	adrp	x12, 0x0 <ltmp0>
     86c:      	ldr	d0, [x12]
     870:      	str	d0, [sp]
     874:      	orr	x23, x24, #0x8
     878:      	stp	w9, w8, [sp, #0x8]
     87c:      	stp	x10, x10, [sp, #0x10]
     880:      	movi.16b	v0, #0x0
     884:      	stp	q0, q0, [sp, #0x20]
     888:      	add	x20, x24, #0x50
     88c:      	stp	x23, x20, [sp, #0x40]
     890:      	smull	x12, w9, w8
     894:      	stp	xzr, xzr, [sp, #0x50]
     898:      	cbz	x12, 0x8a0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x1bc>
     89c:      	cbz	x10, 0x1214 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb30>
     8a0:      	sxtw	x9, w9
     8a4:      	sxtw	x8, w8
     8a8:      	cmp	w11, #0x0
     8ac:      	csel	x11, x8, x11, eq
     8b0:      	mov	w12, #0x1               ; =1
     8b4:      	stp	x11, x12, [sp, #0x50]
     8b8:      	madd	x9, x11, x9, x10
     8bc:      	sub	x10, x9, x11
     8c0:      	add	x8, x10, x8
     8c4:      	stp	x8, x9, [sp, #0x20]
     8c8:      	mov	x0, sp
     8cc:      	bl	0x8cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x1e8>
     8d0:      	ldr	x8, [sp, #0x98]
     8d4:      	cbz	x8, 0x8f8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x214>
     8d8:      	add	x8, x8, #0x14
     8dc:      	ldaxr	w9, [x8]
     8e0:      	subs	w9, w9, #0x1
     8e4:      	stlxr	w10, w9, [x8]
     8e8:      	cbnz	w10, 0x8dc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x1f8>
     8ec:      	b.ne	0x8f8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x214>
     8f0:      	add	x0, sp, #0x60
     8f4:      	bl	0x8f4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x210>
     8f8:      	ldr	w8, [sp, #0x64]
     8fc:      	cmp	w8, #0x1
     900:      	b.lt	0x920 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x23c>
     904:      	mov	x8, #0x0                ; =0
     908:      	ldr	x9, [sp, #0xa0]
     90c:      	str	wzr, [x9, x8, lsl #2]
     910:      	add	x8, x8, #0x1
     914:      	ldrsw	x10, [sp, #0x64]
     918:      	cmp	x8, x10
     91c:      	b.lt	0x90c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x228>
     920:      	ldp	q0, q1, [sp]
     924:      	stp	q0, q1, [sp, #0x60]
     928:      	ldp	q1, q2, [sp, #0x20]
     92c:      	stp	q1, q2, [sp, #0x80]
     930:      	ldr	x0, [sp, #0xa8]
     934:      	cmp	x0, x22
     938:      	b.eq	0xca4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5c0>
     93c:      	bl	0x93c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x258>
     940:      	stp	x21, x22, [sp, #0xa0]
     944:      	mov	x0, x22
     948:      	ldr	w9, [sp, #0x4]
     94c:      	orr	x8, x24, #0x4
     950:      	ldr	x10, [sp, #0x48]
     954:      	cmp	w9, #0x2
     958:      	b.gt	0xcb8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5d4>
     95c:      	ldr	x9, [x10]
     960:      	str	x9, [x0]
     964:      	ldr	x9, [x10, #0x8]
     968:      	str	x9, [x0, #0x8]
     96c:      	b	0xcc4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5e0>
     970:      	ldr	x10, [x20]
     974:      	ldrsw	x11, [x20, #0x10]
     978:      	mov	x24, sp
     97c:      	adrp	x12, 0x0 <ltmp0>
     980:      	ldr	d0, [x12]
     984:      	str	d0, [sp]
     988:      	orr	x23, x24, #0x8
     98c:      	stp	w9, w8, [sp, #0x8]
     990:      	stp	x10, x10, [sp, #0x10]
     994:      	movi.16b	v0, #0x0
     998:      	stp	q0, q0, [sp, #0x20]
     99c:      	add	x20, x24, #0x50
     9a0:      	stp	x23, x20, [sp, #0x40]
     9a4:      	smull	x12, w9, w8
     9a8:      	stp	xzr, xzr, [sp, #0x50]
     9ac:      	cbz	x12, 0x9b4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x2d0>
     9b0:      	cbz	x10, 0x1248 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb64>
     9b4:      	sxtw	x9, w9
     9b8:      	sxtw	x8, w8
     9bc:      	add	x8, x8, x8, lsl #1
     9c0:      	cmp	w11, #0x0
     9c4:      	csel	x11, x8, x11, eq
     9c8:      	mov	w12, #0x3               ; =3
     9cc:      	stp	x11, x12, [sp, #0x50]
     9d0:      	madd	x9, x11, x9, x10
     9d4:      	sub	x10, x9, x11
     9d8:      	add	x8, x10, x8
     9dc:      	stp	x8, x9, [sp, #0x20]
     9e0:      	mov	x0, sp
     9e4:      	bl	0x9e4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x300>
     9e8:      	ldr	x8, [sp, #0x98]
     9ec:      	cbz	x8, 0xa10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x32c>
     9f0:      	add	x8, x8, #0x14
     9f4:      	ldaxr	w9, [x8]
     9f8:      	subs	w9, w9, #0x1
     9fc:      	stlxr	w10, w9, [x8]
     a00:      	cbnz	w10, 0x9f4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x310>
     a04:      	b.ne	0xa10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x32c>
     a08:      	add	x0, sp, #0x60
     a0c:      	bl	0xa0c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x328>
     a10:      	ldr	w8, [sp, #0x64]
     a14:      	cmp	w8, #0x1
     a18:      	b.lt	0xa38 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x354>
     a1c:      	mov	x8, #0x0                ; =0
     a20:      	ldr	x9, [sp, #0xa0]
     a24:      	str	wzr, [x9, x8, lsl #2]
     a28:      	add	x8, x8, #0x1
     a2c:      	ldrsw	x10, [sp, #0x64]
     a30:      	cmp	x8, x10
     a34:      	b.lt	0xa24 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x340>
     a38:      	ldp	q0, q1, [sp]
     a3c:      	stp	q0, q1, [sp, #0x60]
     a40:      	ldp	q1, q2, [sp, #0x20]
     a44:      	stp	q1, q2, [sp, #0x80]
     a48:      	ldr	x0, [sp, #0xa8]
     a4c:      	cmp	x0, x22
     a50:      	b.eq	0xb9c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4b8>
     a54:      	bl	0xa54 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x370>
     a58:      	stp	x21, x22, [sp, #0xa0]
     a5c:      	mov	x0, x22
     a60:      	ldr	w9, [sp, #0x4]
     a64:      	orr	x8, x24, #0x4
     a68:      	ldr	x10, [sp, #0x48]
     a6c:      	cmp	w9, #0x2
     a70:      	b.gt	0xbb0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4cc>
     a74:      	ldr	x9, [x10]
     a78:      	str	x9, [x0]
     a7c:      	ldr	x9, [x10, #0x8]
     a80:      	str	x9, [x0, #0x8]
     a84:      	b	0xbbc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4d8>
     a88:      	ldr	x10, [x20]
     a8c:      	ldrsw	x11, [x20, #0x10]
     a90:      	mov	x24, sp
     a94:      	adrp	x12, 0x0 <ltmp0>
     a98:      	ldr	d1, [x12]
     a9c:      	str	d1, [sp]
     aa0:      	orr	x23, x24, #0x8
     aa4:      	stp	w9, w8, [sp, #0x8]
     aa8:      	stp	x10, x10, [sp, #0x10]
     aac:      	stp	q0, q0, [sp, #0x20]
     ab0:      	add	x20, x24, #0x50
     ab4:      	stp	x23, x20, [sp, #0x40]
     ab8:      	smull	x12, w9, w8
     abc:      	stp	xzr, xzr, [sp, #0x50]
     ac0:      	cbz	x12, 0xac8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3e4>
     ac4:      	cbz	x10, 0x127c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb98>
     ac8:      	sxtw	x9, w9
     acc:      	sxtw	x8, w8
     ad0:      	lsl	x8, x8, #2
     ad4:      	cmp	w11, #0x0
     ad8:      	csel	x11, x8, x11, eq
     adc:      	mov	w12, #0x4               ; =4
     ae0:      	stp	x11, x12, [sp, #0x50]
     ae4:      	madd	x9, x11, x9, x10
     ae8:      	sub	x10, x9, x11
     aec:      	add	x8, x10, x8
     af0:      	stp	x8, x9, [sp, #0x20]
     af4:      	mov	x0, sp
     af8:      	bl	0xaf8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x414>
     afc:      	ldr	x8, [sp, #0x98]
     b00:      	cbz	x8, 0xb24 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x440>
     b04:      	add	x8, x8, #0x14
     b08:      	ldaxr	w9, [x8]
     b0c:      	subs	w9, w9, #0x1
     b10:      	stlxr	w10, w9, [x8]
     b14:      	cbnz	w10, 0xb08 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x424>
     b18:      	b.ne	0xb24 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x440>
     b1c:      	add	x0, sp, #0x60
     b20:      	bl	0xb20 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x43c>
     b24:      	ldr	w8, [sp, #0x64]
     b28:      	cmp	w8, #0x1
     b2c:      	b.lt	0xb4c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x468>
     b30:      	mov	x8, #0x0                ; =0
     b34:      	ldr	x9, [sp, #0xa0]
     b38:      	str	wzr, [x9, x8, lsl #2]
     b3c:      	add	x8, x8, #0x1
     b40:      	ldrsw	x10, [sp, #0x64]
     b44:      	cmp	x8, x10
     b48:      	b.lt	0xb38 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x454>
     b4c:      	ldp	q0, q1, [sp]
     b50:      	stp	q0, q1, [sp, #0x60]
     b54:      	ldp	q1, q2, [sp, #0x20]
     b58:      	stp	q1, q2, [sp, #0x80]
     b5c:      	ldr	x0, [sp, #0xa8]
     b60:      	cmp	x0, x22
     b64:      	b.eq	0xc20 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x53c>
     b68:      	bl	0xb68 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x484>
     b6c:      	stp	x21, x22, [sp, #0xa0]
     b70:      	mov	x0, x22
     b74:      	ldr	w9, [sp, #0x4]
     b78:      	orr	x8, x24, #0x4
     b7c:      	ldr	x10, [sp, #0x48]
     b80:      	cmp	w9, #0x2
     b84:      	b.gt	0xc34 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x550>
     b88:      	ldr	x9, [x10]
     b8c:      	str	x9, [x0]
     b90:      	ldr	x9, [x10, #0x8]
     b94:      	str	x9, [x0, #0x8]
     b98:      	b	0xc40 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x55c>
     b9c:      	mov.s	w9, v0[1]
     ba0:      	orr	x8, x24, #0x4
     ba4:      	ldr	x10, [sp, #0x48]
     ba8:      	cmp	w9, #0x2
     bac:      	b.le	0xa74 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x390>
     bb0:      	ldr	x9, [sp, #0x40]
     bb4:      	stp	x9, x10, [sp, #0xa0]
     bb8:      	stp	x23, x20, [sp, #0x40]
     bbc:      	mov	w9, #0x42ff0000         ; =1124007936
     bc0:      	str	w9, [sp]
     bc4:      	movi.16b	v0, #0x0
     bc8:      	stp	q0, q0, [x8]
     bcc:      	str	q0, [x8, #0x20]
     bd0:      	stur	q0, [x8, #0x2c]
     bd4:      	ldr	x0, [sp, #0x48]
     bd8:      	cmp	x0, x20
     bdc:      	b.eq	0xbe4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x500>
     be0:      	bl	0xbe0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4fc>
     be4:      	mov	w8, #0x1010000          ; =16842752
     be8:      	str	w8, [sp]
     bec:      	add	x8, sp, #0x60
     bf0:      	stp	x8, xzr, [sp, #0x8]
     bf4:      	ldur	x8, [x29, #-0x98]
     bf8:      	add	x8, x8, #0x60
     bfc:      	mov	w9, #0x2010000          ; =33619968
     c00:      	stur	w9, [x29, #-0x88]
     c04:      	stp	x8, xzr, [x29, #-0x80]
     c08:      	mov	x0, sp
     c0c:      	sub	x1, x29, #0x88
     c10:      	mov	w2, #0x6                ; =6
     c14:      	mov	w3, #0x0                ; =0
     c18:      	bl	0xc18 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x534>
     c1c:      	b	0xe98 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b4>
     c20:      	mov.s	w9, v0[1]
     c24:      	orr	x8, x24, #0x4
     c28:      	ldr	x10, [sp, #0x48]
     c2c:      	cmp	w9, #0x2
     c30:      	b.le	0xb88 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4a4>
     c34:      	ldr	x9, [sp, #0x40]
     c38:      	stp	x9, x10, [sp, #0xa0]
     c3c:      	stp	x23, x20, [sp, #0x40]
     c40:      	mov	w9, #0x42ff0000         ; =1124007936
     c44:      	str	w9, [sp]
     c48:      	movi.16b	v0, #0x0
     c4c:      	stp	q0, q0, [x8]
     c50:      	str	q0, [x8, #0x20]
     c54:      	stur	q0, [x8, #0x2c]
     c58:      	ldr	x0, [sp, #0x48]
     c5c:      	cmp	x0, x20
     c60:      	b.eq	0xc68 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x584>
     c64:      	bl	0xc64 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x580>
     c68:      	mov	w8, #0x1010000          ; =16842752
     c6c:      	str	w8, [sp]
     c70:      	add	x8, sp, #0x60
     c74:      	stp	x8, xzr, [sp, #0x8]
     c78:      	ldur	x8, [x29, #-0x98]
     c7c:      	add	x8, x8, #0x60
     c80:      	mov	w9, #0x2010000          ; =33619968
     c84:      	stur	w9, [x29, #-0x88]
     c88:      	stp	x8, xzr, [x29, #-0x80]
     c8c:      	mov	x0, sp
     c90:      	sub	x1, x29, #0x88
     c94:      	mov	w2, #0xa                ; =10
     c98:      	mov	w3, #0x0                ; =0
     c9c:      	bl	0xc9c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5b8>
     ca0:      	b	0xe98 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b4>
     ca4:      	mov.s	w9, v0[1]
     ca8:      	orr	x8, x24, #0x4
     cac:      	ldr	x10, [sp, #0x48]
     cb0:      	cmp	w9, #0x2
     cb4:      	b.le	0x95c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x278>
     cb8:      	ldr	x9, [sp, #0x40]
     cbc:      	stp	x9, x10, [sp, #0xa0]
     cc0:      	stp	x23, x20, [sp, #0x40]
     cc4:      	mov	w21, #0x42ff0000        ; =1124007936
     cc8:      	str	w21, [sp]
     ccc:      	movi.16b	v0, #0x0
     cd0:      	stp	q0, q0, [x8]
     cd4:      	str	q0, [x8, #0x20]
     cd8:      	stur	q0, [x8, #0x2c]
     cdc:      	ldr	x0, [sp, #0x48]
     ce0:      	cmp	x0, x20
     ce4:      	b.eq	0xcec <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x608>
     ce8:      	bl	0xce8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x604>
     cec:      	str	w21, [sp]
     cf0:      	mov	x23, sp
     cf4:      	orr	x21, x23, #0x8
     cf8:      	movi.16b	v0, #0x0
     cfc:      	stur	q0, [sp, #0x4]
     d00:      	stur	q0, [sp, #0x14]
     d04:      	stur	q0, [sp, #0x24]
     d08:      	str	q0, [sp, #0x30]
     d0c:      	add	x20, x23, #0x50
     d10:      	stp	x21, x20, [sp, #0x40]
     d14:      	stp	xzr, xzr, [sp, #0x50]
     d18:      	mov	w8, #0x2010000          ; =33619968
     d1c:      	stur	w8, [x29, #-0x88]
     d20:      	stp	x23, xzr, [x29, #-0x80]
     d24:      	add	x0, sp, #0x60
     d28:      	sub	x1, x29, #0x88
     d2c:      	bl	0xd2c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x648>
     d30:      	ldur	x24, [x29, #-0x98]
     d34:      	add	x0, x24, #0x60
     d38:      	cmp	x0, x23
     d3c:      	b.eq	0xdf0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x70c>
     d40:      	ldr	x8, [x24, #0x98]
     d44:      	cbz	x8, 0xd64 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x680>
     d48:      	add	x8, x8, #0x14
     d4c:      	ldaxr	w9, [x8]
     d50:      	subs	w9, w9, #0x1
     d54:      	stlxr	w10, w9, [x8]
     d58:      	cbnz	w10, 0xd4c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x668>
     d5c:      	b.ne	0xd64 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x680>
     d60:      	bl	0xd60 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x67c>
     d64:      	str	xzr, [x24, #0x98]
     d68:      	movi.16b	v0, #0x0
     d6c:      	stp	q0, q0, [x24, #0x70]
     d70:      	ldr	w8, [x24, #0x64]
     d74:      	cmp	w8, #0x1
     d78:      	b.lt	0xd98 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6b4>
     d7c:      	mov	x8, #0x0                ; =0
     d80:      	ldr	x9, [x24, #0xa0]
     d84:      	str	wzr, [x9, x8, lsl #2]
     d88:      	add	x8, x8, #0x1
     d8c:      	ldrsw	x10, [x24, #0x64]
     d90:      	cmp	x8, x10
     d94:      	b.lt	0xd84 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6a0>
     d98:      	ldp	q0, q1, [sp]
     d9c:      	stp	q0, q1, [x24, #0x60]
     da0:      	ldp	q1, q2, [sp, #0x20]
     da4:      	stp	q1, q2, [x24, #0x80]
     da8:      	ldr	x0, [x24, #0xa8]
     dac:      	add	x25, x24, #0xb0
     db0:      	cmp	x0, x25
     db4:      	b.eq	0xe50 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x76c>
     db8:      	bl	0xdb8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6d4>
     dbc:      	add	x8, x24, #0x68
     dc0:      	stp	x8, x25, [x24, #0xa0]
     dc4:      	ldr	w9, [sp, #0x4]
     dc8:      	mov	x0, x25
     dcc:      	orr	x8, x23, #0x4
     dd0:      	ldr	x10, [sp, #0x48]
     dd4:      	cmp	w9, #0x2
     dd8:      	b.gt	0xe64 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x780>
     ddc:      	ldr	x9, [x10]
     de0:      	str	x9, [x0]
     de4:      	ldr	x9, [x10, #0x8]
     de8:      	str	x9, [x0, #0x8]
     dec:      	b	0xe70 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x78c>
     df0:      	ldr	x8, [sp, #0x38]
     df4:      	cbz	x8, 0xe18 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x734>
     df8:      	add	x8, x8, #0x14
     dfc:      	ldaxr	w9, [x8]
     e00:      	subs	w9, w9, #0x1
     e04:      	stlxr	w10, w9, [x8]
     e08:      	cbnz	w10, 0xdfc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x718>
     e0c:      	b.ne	0xe18 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x734>
     e10:      	mov	x0, sp
     e14:      	bl	0xe14 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x730>
     e18:      	ldr	w8, [sp, #0x4]
     e1c:      	str	xzr, [sp, #0x38]
     e20:      	movi.16b	v0, #0x0
     e24:      	stp	q0, q0, [sp, #0x10]
     e28:      	cmp	w8, #0x1
     e2c:      	b.lt	0xe88 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7a4>
     e30:      	mov	x8, #0x0                ; =0
     e34:      	ldr	x9, [sp, #0x40]
     e38:      	str	wzr, [x9, x8, lsl #2]
     e3c:      	add	x8, x8, #0x1
     e40:      	ldrsw	x10, [sp, #0x4]
     e44:      	cmp	x8, x10
     e48:      	b.lt	0xe38 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x754>
     e4c:      	b	0xe88 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7a4>
     e50:      	mov.s	w9, v0[1]
     e54:      	orr	x8, x23, #0x4
     e58:      	ldr	x10, [sp, #0x48]
     e5c:      	cmp	w9, #0x2
     e60:      	b.le	0xddc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6f8>
     e64:      	ldr	x9, [sp, #0x40]
     e68:      	stp	x9, x10, [x24, #0xa0]
     e6c:      	stp	x21, x20, [sp, #0x40]
     e70:      	mov	w9, #0x42ff0000         ; =1124007936
     e74:      	str	w9, [sp]
     e78:      	movi.16b	v0, #0x0
     e7c:      	stp	q0, q0, [x8]
     e80:      	str	q0, [x8, #0x20]
     e84:      	stur	q0, [x8, #0x2c]
     e88:      	ldr	x0, [sp, #0x48]
     e8c:      	cmp	x0, x20
     e90:      	b.eq	0xe98 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b4>
     e94:      	bl	0xe94 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b0>
     e98:      	mov	w8, #0x42ff0000         ; =1124007936
     e9c:      	str	w8, [sp]
     ea0:      	mov	x23, sp
     ea4:      	movi.16b	v0, #0x0
     ea8:      	stur	q0, [sp, #0x4]
     eac:      	orr	x21, x23, #0x8
     eb0:      	stur	q0, [sp, #0x14]
     eb4:      	stur	q0, [sp, #0x24]
     eb8:      	str	q0, [sp, #0x30]
     ebc:      	add	x20, x23, #0x50
     ec0:      	stp	x21, x20, [sp, #0x40]
     ec4:      	stp	xzr, xzr, [sp, #0x50]
     ec8:      	mov	w8, #0x2010000          ; =33619968
     ecc:      	stur	w8, [x29, #-0x88]
     ed0:      	stp	x23, xzr, [x29, #-0x80]
     ed4:      	add	x0, sp, #0x60
     ed8:      	sub	x1, x29, #0x88
     edc:      	bl	0xedc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7f8>
     ee0:      	ldur	x24, [x29, #-0x98]
     ee4:      	add	x0, x24, #0xc0
     ee8:      	cmp	x0, x23
     eec:      	b.eq	0xfa0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8bc>
     ef0:      	ldr	x8, [x24, #0xf8]
     ef4:      	cbz	x8, 0xf14 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x830>
     ef8:      	add	x8, x8, #0x14
     efc:      	ldaxr	w9, [x8]
     f00:      	subs	w9, w9, #0x1
     f04:      	stlxr	w10, w9, [x8]
     f08:      	cbnz	w10, 0xefc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x818>
     f0c:      	b.ne	0xf14 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x830>
     f10:      	bl	0xf10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x82c>
     f14:      	str	xzr, [x24, #0xf8]
     f18:      	movi.16b	v0, #0x0
     f1c:      	stp	q0, q0, [x24, #0xd0]
     f20:      	ldr	w8, [x24, #0xc4]
     f24:      	cmp	w8, #0x1
     f28:      	b.lt	0xf48 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x864>
     f2c:      	mov	x8, #0x0                ; =0
     f30:      	ldr	x9, [x24, #0x100]
     f34:      	str	wzr, [x9, x8, lsl #2]
     f38:      	add	x8, x8, #0x1
     f3c:      	ldrsw	x10, [x24, #0xc4]
     f40:      	cmp	x8, x10
     f44:      	b.lt	0xf34 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x850>
     f48:      	ldp	q0, q1, [sp]
     f4c:      	stp	q0, q1, [x24, #0xc0]
     f50:      	ldp	q1, q2, [sp, #0x20]
     f54:      	stp	q1, q2, [x24, #0xe0]
     f58:      	ldr	x0, [x24, #0x108]
     f5c:      	add	x25, x24, #0x110
     f60:      	cmp	x0, x25
     f64:      	b.eq	0x100c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x928>
     f68:      	bl	0xf68 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x884>
     f6c:      	add	x8, x24, #0xc8
     f70:      	stp	x8, x25, [x24, #0x100]
     f74:      	ldr	w9, [sp, #0x4]
     f78:      	mov	x0, x25
     f7c:      	orr	x8, x23, #0x4
     f80:      	ldr	x10, [sp, #0x48]
     f84:      	cmp	w9, #0x2
     f88:      	b.gt	0x1020 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x93c>
     f8c:      	ldr	x9, [x10]
     f90:      	str	x9, [x0]
     f94:      	ldr	x9, [x10, #0x8]
     f98:      	str	x9, [x0, #0x8]
     f9c:      	b	0x102c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x948>
     fa0:      	ldr	x8, [sp, #0x38]
     fa4:      	cbz	x8, 0xfc8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8e4>
     fa8:      	add	x8, x8, #0x14
     fac:      	ldaxr	w9, [x8]
     fb0:      	subs	w9, w9, #0x1
     fb4:      	stlxr	w10, w9, [x8]
     fb8:      	cbnz	w10, 0xfac <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8c8>
     fbc:      	b.ne	0xfc8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8e4>
     fc0:      	mov	x0, sp
     fc4:      	bl	0xfc4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8e0>
     fc8:      	ldr	w8, [sp, #0x4]
     fcc:      	str	xzr, [sp, #0x38]
     fd0:      	movi.16b	v0, #0x0
     fd4:      	stp	q0, q0, [sp, #0x10]
     fd8:      	cmp	w8, #0x1
     fdc:      	b.lt	0xffc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x918>
     fe0:      	mov	x8, #0x0                ; =0
     fe4:      	ldr	x9, [sp, #0x40]
     fe8:      	str	wzr, [x9, x8, lsl #2]
     fec:      	add	x8, x8, #0x1
     ff0:      	ldrsw	x10, [sp, #0x4]
     ff4:      	cmp	x8, x10
     ff8:      	b.lt	0xfe8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x904>
     ffc:      	ldr	x0, [sp, #0x48]
    1000:      	cmp	x0, x20
    1004:      	b.ne	0x1050 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x96c>
    1008:      	b	0x1054 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x970>
    100c:      	mov.s	w9, v0[1]
    1010:      	orr	x8, x23, #0x4
    1014:      	ldr	x10, [sp, #0x48]
    1018:      	cmp	w9, #0x2
    101c:      	b.le	0xf8c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a8>
    1020:      	ldr	x9, [sp, #0x40]
    1024:      	stp	x9, x10, [x24, #0x100]
    1028:      	stp	x21, x20, [sp, #0x40]
    102c:      	mov	w9, #0x42ff0000         ; =1124007936
    1030:      	str	w9, [sp]
    1034:      	movi.16b	v0, #0x0
    1038:      	stp	q0, q0, [x8]
    103c:      	str	q0, [x8, #0x20]
    1040:      	stur	q0, [x8, #0x2c]
    1044:      	ldr	x0, [sp, #0x48]
    1048:      	cmp	x0, x20
    104c:      	b.eq	0x1054 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x970>
    1050:      	bl	0x1050 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x96c>
    1054:      	ldur	x0, [x29, #-0x98]
    1058:      	cbz	x0, 0x10c8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9e4>
    105c:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1060:      	ldr	x1, [x1]
    1064:      	adrp	x2, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1068:      	ldr	x2, [x2]
    106c:      	mov	x3, #0x0                ; =0
    1070:      	bl	0x1070 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x98c>
    1074:      	cbz	x0, 0x10c8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9e4>
    1078:      	mov	x20, x0
    107c:      	ldr	x0, [x19]
    1080:      	ldr	x8, [x0]
    1084:      	ldr	x8, [x8, #0xe0]
    1088:      	blr	x8
    108c:      	fmov	d8, d0
    1090:      	ldr	x0, [x19]
    1094:      	ldr	x8, [x0]
    1098:      	ldr	x8, [x8, #0xe8]
    109c:      	blr	x8
    10a0:      	mov	x21, x0
    10a4:      	ldr	x0, [x19]
    10a8:      	ldr	x8, [x0]
    10ac:      	ldr	x8, [x8, #0xf0]
    10b0:      	blr	x8
    10b4:      	mov	x2, x0
    10b8:      	mov	x0, x20
    10bc:      	fmov	d0, d8
    10c0:      	mov	x1, x21
    10c4:      	bl	0x10c4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9e0>
    10c8:      	add	x0, x19, #0x18
    10cc:      	bl	0x10cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9e8>
    10d0:      	ldp	x9, x8, [x29, #-0x98]
    10d4:      	cbz	x8, 0x10ec <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa08>
    10d8:      	add	x10, x8, #0x8
    10dc:      	ldxr	x11, [x10]
    10e0:      	add	x11, x11, #0x1
    10e4:      	stxr	w12, x11, [x10]
    10e8:      	cbnz	w12, 0x10dc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9f8>
    10ec:      	ldr	x20, [x19, #0x60]
    10f0:      	stp	x9, x8, [x19, #0x58]
    10f4:      	cbz	x20, 0x1110 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa2c>
    10f8:      	add	x8, x20, #0x8
    10fc:      	ldaxr	x9, [x8]
    1100:      	sub	x10, x9, #0x1
    1104:      	stlxr	w11, x10, [x8]
    1108:      	cbnz	w11, 0x10fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa18>
    110c:      	cbz	x9, 0x1144 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa60>
    1110:      	add	x0, x19, #0x18
    1114:      	bl	0x1114 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa30>
    1118:      	ldr	x8, [sp, #0x98]
    111c:      	cbz	x8, 0x116c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa88>
    1120:      	add	x8, x8, #0x14
    1124:      	ldaxr	w9, [x8]
    1128:      	subs	w9, w9, #0x1
    112c:      	stlxr	w10, w9, [x8]
    1130:      	cbnz	w10, 0x1124 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa40>
    1134:      	b.ne	0x116c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa88>
    1138:      	add	x0, sp, #0x60
    113c:      	bl	0x113c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa58>
    1140:      	b	0x116c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa88>
    1144:      	ldr	x8, [x20]
    1148:      	ldr	x8, [x8, #0x10]
    114c:      	mov	x0, x20
    1150:      	blr	x8
    1154:      	mov	x0, x20
    1158:      	bl	0x1158 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa74>
    115c:      	add	x0, x19, #0x18
    1160:      	bl	0x1160 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa7c>
    1164:      	ldr	x8, [sp, #0x98]
    1168:      	cbnz	x8, 0x1120 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa3c>
    116c:      	str	xzr, [sp, #0x98]
    1170:      	movi.16b	v0, #0x0
    1174:      	stp	q0, q0, [sp, #0x70]
    1178:      	ldr	w8, [sp, #0x64]
    117c:      	cmp	w8, #0x1
    1180:      	b.lt	0x11a0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xabc>
    1184:      	mov	x8, #0x0                ; =0
    1188:      	ldr	x9, [sp, #0xa0]
    118c:      	str	wzr, [x9, x8, lsl #2]
    1190:      	add	x8, x8, #0x1
    1194:      	ldrsw	x10, [sp, #0x64]
    1198:      	cmp	x8, x10
    119c:      	b.lt	0x118c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xaa8>
    11a0:      	ldr	x0, [sp, #0xa8]
    11a4:      	cmp	x0, x22
    11a8:      	b.eq	0x11b0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xacc>
    11ac:      	bl	0x11ac <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xac8>
    11b0:      	ldur	x19, [x29, #-0x90]
    11b4:      	cbz	x19, 0x714 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x30>
    11b8:      	add	x8, x19, #0x8
    11bc:      	ldaxr	x9, [x8]
    11c0:      	sub	x10, x9, #0x1
    11c4:      	stlxr	w11, x10, [x8]
    11c8:      	cbnz	w11, 0x11bc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xad8>
    11cc:      	cbnz	x9, 0x714 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x30>
    11d0:      	ldr	x8, [x19]
    11d4:      	ldr	x8, [x8, #0x10]
    11d8:      	mov	x0, x19
    11dc:      	blr	x8
    11e0:      	mov	x0, x19
    11e4:      	bl	0x11e4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb00>
    11e8:      	b	0x714 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x30>
    11ec:      	adrp	x0, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    11f0:      	ldr	x0, [x0]
    11f4:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    11f8:      	add	x1, x1, #0x0
    11fc:      	mov	w2, #0x1f               ; =31
    1200:      	bl	0x1200 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb1c>
    1204:      	bl	0x1204 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb20>
    1208:      	mov	w0, #-0x1               ; =-1
    120c:      	bl	0x120c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb28>
    1210:      	b	0x12ac <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc8>
    1214:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1218:      	add	x1, x1, #0x0
    121c:      	sub	x0, x29, #0x88
    1220:      	bl	0x1220 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb3c>
    1224:      	adrp	x2, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1228:      	add	x2, x2, #0x0
    122c:      	adrp	x3, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1230:      	add	x3, x3, #0x0
    1234:      	sub	x1, x29, #0x88
    1238:      	mov	w0, #-0xd7              ; =-215
    123c:      	mov	w4, #0x224              ; =548
    1240:      	bl	0x1240 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb5c>
    1244:      	b	0x12ac <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc8>
    1248:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    124c:      	add	x1, x1, #0x0
    1250:      	sub	x0, x29, #0x88
    1254:      	bl	0x1254 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb70>
    1258:      	adrp	x2, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    125c:      	add	x2, x2, #0x0
    1260:      	adrp	x3, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1264:      	add	x3, x3, #0x0
    1268:      	sub	x1, x29, #0x88
    126c:      	mov	w0, #-0xd7              ; =-215
    1270:      	mov	w4, #0x224              ; =548
    1274:      	bl	0x1274 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb90>
    1278:      	b	0x12ac <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc8>
    127c:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1280:      	add	x1, x1, #0x0
    1284:      	sub	x0, x29, #0x88
    1288:      	bl	0x1288 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xba4>
    128c:      	adrp	x2, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1290:      	add	x2, x2, #0x0
    1294:      	adrp	x3, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1298:      	add	x3, x3, #0x0
    129c:      	sub	x1, x29, #0x88
    12a0:      	mov	w0, #-0xd7              ; =-215
    12a4:      	mov	w4, #0x224              ; =548
    12a8:      	bl	0x12a8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc4>
    12ac:      	brk	#0x1
    12b0:      	mov	x19, x0
    12b4:      	sub	x0, x29, #0x98
    12b8:      	bl	0x12b8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbd4>
    12bc:      	mov	x0, x19
    12c0:      	bl	0x12c0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbdc>
    12c4:      	b	0x12cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbe8>
    12c8:      	b	0x12cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbe8>
    12cc:      	mov	x19, x0
    12d0:      	ldursb	w8, [x29, #-0x71]
    12d4:      	tbz	w8, #0x1f, 0x1394 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcb0>
    12d8:      	ldur	x0, [x29, #-0x88]
    12dc:      	bl	0x12dc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbf8>
    12e0:      	add	x0, sp, #0x60
    12e4:      	bl	0x12e4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc00>
    12e8:      	sub	x0, x29, #0x98
    12ec:      	bl	0x12ec <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc08>
    12f0:      	mov	x0, x19
    12f4:      	bl	0x12f4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc10>
    12f8:      	b	0x1344 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
    12fc:      	bl	0x12fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc18>
    1300:      	bl	0x1300 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc1c>
    1304:      	bl	0x1304 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc20>
    1308:      	bl	0x1308 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc24>
    130c:      	b	0x1344 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
    1310:      	b	0x1344 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
    1314:      	b	0x1344 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
    1318:      	b	0x1344 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
    131c:      	b	0x1390 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
    1320:      	b	0x1390 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
    1324:      	b	0x1390 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
    1328:      	b	0x1390 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
    132c:      	b	0x1390 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
    1330:      	b	0x1390 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
    1334:      	b	0x1344 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
    1338:      	bl	0x1338 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc54>
    133c:      	bl	0x133c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc58>
    1340:      	b	0x1390 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
    1344:      	mov	x19, x0
    1348:      	mov	x0, sp
    134c:      	bl	0x134c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc68>
    1350:      	add	x0, sp, #0x60
    1354:      	bl	0x1354 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc70>
    1358:      	sub	x0, x29, #0x98
    135c:      	bl	0x135c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc78>
    1360:      	mov	x0, x19
    1364:      	bl	0x1364 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc80>
    1368:      	mov	x19, x0
    136c:      	sub	x0, x29, #0x98
    1370:      	bl	0x1370 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc8c>
    1374:      	mov	x0, x19
    1378:      	bl	0x1378 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc94>
    137c:      	mov	x19, x0
    1380:      	sub	x0, x29, #0x98
    1384:      	bl	0x1384 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xca0>
    1388:      	mov	x0, x19
    138c:      	bl	0x138c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xca8>
    1390:      	mov	x19, x0
    1394:      	add	x0, sp, #0x60
    1398:      	bl	0x1398 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcb4>
    139c:      	sub	x0, x29, #0x98
    13a0:      	bl	0x13a0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcbc>
    13a4:      	mov	x0, x19
    13a8:      	bl	0x13a8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcc4>

00000000000013ac <__ZN2cv3MatD1Ev>:
    13ac:      	stp	x20, x19, [sp, #-0x20]!
    13b0:      	stp	x29, x30, [sp, #0x10]
    13b4:      	add	x29, sp, #0x10
    13b8:      	mov	x19, x0
    13bc:      	ldr	x8, [x0, #0x38]
    13c0:      	cbz	x8, 0x13e4 <__ZN2cv3MatD1Ev+0x38>
    13c4:      	add	x8, x8, #0x14
    13c8:      	ldaxr	w9, [x8]
    13cc:      	subs	w9, w9, #0x1
    13d0:      	stlxr	w10, w9, [x8]
    13d4:      	cbnz	w10, 0x13c8 <__ZN2cv3MatD1Ev+0x1c>
    13d8:      	b.ne	0x13e4 <__ZN2cv3MatD1Ev+0x38>
    13dc:      	mov	x0, x19
    13e0:      	bl	0x13e0 <__ZN2cv3MatD1Ev+0x34>
    13e4:      	str	xzr, [x19, #0x38]
    13e8:      	movi.16b	v0, #0x0
    13ec:      	stp	q0, q0, [x19, #0x10]
    13f0:      	ldr	w8, [x19, #0x4]
    13f4:      	cmp	w8, #0x1
    13f8:      	b.lt	0x1418 <__ZN2cv3MatD1Ev+0x6c>
    13fc:      	mov	x8, #0x0                ; =0
    1400:      	ldr	x9, [x19, #0x40]
    1404:      	str	wzr, [x9, x8, lsl #2]
    1408:      	add	x8, x8, #0x1
    140c:      	ldrsw	x10, [x19, #0x4]
    1410:      	cmp	x8, x10
    1414:      	b.lt	0x1404 <__ZN2cv3MatD1Ev+0x58>
    1418:      	ldr	x0, [x19, #0x48]
    141c:      	add	x8, x19, #0x50
    1420:      	cmp	x0, x8
    1424:      	b.eq	0x142c <__ZN2cv3MatD1Ev+0x80>
    1428:      	bl	0x1428 <__ZN2cv3MatD1Ev+0x7c>
    142c:      	mov	x0, x19
    1430:      	ldp	x29, x30, [sp, #0x10]
    1434:      	ldp	x20, x19, [sp], #0x20
    1438:      	ret
    143c:      	bl	0x143c <__ZN2cv3MatD1Ev+0x90>

0000000000001440 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev>:
    1440:      	stp	x20, x19, [sp, #-0x20]!
    1444:      	stp	x29, x30, [sp, #0x10]
    1448:      	add	x29, sp, #0x10
    144c:      	ldr	x19, [x0, #0x8]
    1450:      	cbz	x19, 0x146c <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev+0x2c>
    1454:      	add	x8, x19, #0x8
    1458:      	ldaxr	x9, [x8]
    145c:      	sub	x10, x9, #0x1
    1460:      	stlxr	w11, x10, [x8]
    1464:      	cbnz	w11, 0x1458 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev+0x18>
    1468:      	cbz	x9, 0x1478 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev+0x38>
    146c:      	ldp	x29, x30, [sp, #0x10]
    1470:      	ldp	x20, x19, [sp], #0x20
    1474:      	ret
    1478:      	ldr	x8, [x19]
    147c:      	ldr	x8, [x8, #0x10]
    1480:      	mov	x20, x0
    1484:      	mov	x0, x19
    1488:      	blr	x8
    148c:      	mov	x0, x19
    1490:      	bl	0x1490 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev+0x50>
    1494:      	mov	x0, x20
    1498:      	ldp	x29, x30, [sp, #0x10]
    149c:      	ldp	x20, x19, [sp], #0x20
    14a0:      	ret

00000000000014a4 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration>:
    14a4:      	sub	sp, sp, #0x80
    14a8:      	stp	d9, d8, [sp, #0x50]
    14ac:      	stp	x20, x19, [sp, #0x60]
    14b0:      	stp	x29, x30, [sp, #0x70]
    14b4:      	add	x29, sp, #0x70
    14b8:      	mov	x20, x1
    14bc:      	mov	x19, x0
    14c0:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    14c4:      	ldr	x8, [x8]
    14c8:      	ldr	x8, [x8]
    14cc:      	stur	x8, [x29, #-0x28]
    14d0:      	ldr	x0, [x0, #0x10]
    14d4:      	mov	x8, sp
    14d8:      	add	x1, x1, #0x18
    14dc:      	add	x3, x20, #0x8
    14e0:      	add	x4, x20, #0x10
    14e4:      	mov	x2, x20
    14e8:      	bl	0x14e8 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x44>
    14ec:      	ldur	d8, [x20, #0x18]
    14f0:      	ldr	d0, [sp]
    14f4:      	fabs	d1, d0
    14f8:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    14fc:      	ldr	d0, [x8]
    1500:      	fcmp	d1, d0
    1504:      	b.gt	0x1538 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x94>
    1508:      	ldr	d1, [sp, #0x8]
    150c:      	fabs	d1, d1
    1510:      	fcmp	d1, d0
    1514:      	b.gt	0x1538 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x94>
    1518:      	ldr	d1, [sp, #0x10]
    151c:      	fabs	d1, d1
    1520:      	fcmp	d1, d0
    1524:      	b.gt	0x1538 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x94>
    1528:      	ldr	d1, [sp, #0x18]
    152c:      	fabs	d1, d1
    1530:      	fcmp	d1, d0
    1534:      	b.le	0x1578 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0xd4>
    1538:      	add	x0, x19, #0x68
    153c:      	bl	0x153c <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x98>
    1540:      	ldr	d0, [x19, #0xf0]
    1544:      	fcmp	d0, d8
    1548:      	b.gt	0x1570 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0xcc>
    154c:      	ldp	q0, q1, [sp]
    1550:      	stp	q0, q1, [x19, #0xb0]
    1554:      	ldr	q0, [sp, #0x20]
    1558:      	str	q0, [x19, #0xd0]
    155c:      	ldr	d0, [sp, #0x30]
    1560:      	str	d0, [x19, #0xe0]
    1564:      	str	d8, [x19, #0xf0]
    1568:      	mov	w8, #0x1                ; =1
    156c:      	strb	w8, [x19, #0xf8]
    1570:      	add	x0, x19, #0x68
    1574:      	bl	0x1574 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0xd0>
    1578:      	ldur	x8, [x29, #-0x28]
    157c:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1580:      	ldr	x9, [x9]
    1584:      	ldr	x9, [x9]
    1588:      	cmp	x9, x8
    158c:      	b.ne	0x15a4 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x100>
    1590:      	ldp	x29, x30, [sp, #0x70]
    1594:      	ldp	x20, x19, [sp, #0x60]
    1598:      	ldp	d9, d8, [sp, #0x50]
    159c:      	add	sp, sp, #0x80
    15a0:      	ret
    15a4:      	bl	0x15a4 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x100>
    15a8:      	bl	0x15a8 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x104>

00000000000015ac <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE>:
    15ac:      	stp	d9, d8, [sp, #-0x30]!
    15b0:      	stp	x20, x19, [sp, #0x10]
    15b4:      	stp	x29, x30, [sp, #0x20]
    15b8:      	add	x29, sp, #0x20
    15bc:      	mov	x20, x1
    15c0:      	fmov	d8, d0
    15c4:      	mov	x19, x0
    15c8:      	ldr	d0, [x1]
    15cc:      	fabs	d1, d0
    15d0:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    15d4:      	ldr	d0, [x8]
    15d8:      	fcmp	d1, d0
    15dc:      	b.gt	0x1610 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0x64>
    15e0:      	ldr	d1, [x20, #0x8]
    15e4:      	fabs	d1, d1
    15e8:      	fcmp	d1, d0
    15ec:      	b.gt	0x1610 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0x64>
    15f0:      	ldr	d1, [x20, #0x10]
    15f4:      	fabs	d1, d1
    15f8:      	fcmp	d1, d0
    15fc:      	b.gt	0x1610 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0x64>
    1600:      	ldr	d1, [x20, #0x18]
    1604:      	fabs	d1, d1
    1608:      	fcmp	d1, d0
    160c:      	b.le	0x1664 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0xb8>
    1610:      	add	x0, x19, #0x68
    1614:      	bl	0x1614 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0x68>
    1618:      	ldr	d0, [x19, #0xf0]
    161c:      	fcmp	d0, d8
    1620:      	b.gt	0x1650 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0xa4>
    1624:      	ldr	q0, [x20]
    1628:      	str	q0, [x19, #0xb0]
    162c:      	ldr	q0, [x20, #0x10]
    1630:      	str	q0, [x19, #0xc0]
    1634:      	ldr	q0, [x20, #0x20]
    1638:      	str	q0, [x19, #0xd0]
    163c:      	ldr	d0, [x20, #0x30]
    1640:      	str	d0, [x19, #0xe0]
    1644:      	str	d8, [x19, #0xf0]
    1648:      	mov	w8, #0x1                ; =1
    164c:      	strb	w8, [x19, #0xf8]
    1650:      	add	x0, x19, #0x68
    1654:      	ldp	x29, x30, [sp, #0x20]
    1658:      	ldp	x20, x19, [sp, #0x10]
    165c:      	ldp	d9, d8, [sp], #0x30
    1660:      	b	0x1660 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0xb4>
    1664:      	ldp	x29, x30, [sp, #0x20]
    1668:      	ldp	x20, x19, [sp, #0x10]
    166c:      	ldp	d9, d8, [sp], #0x30
    1670:      	ret

0000000000001674 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope>:
    1674:      	sub	sp, sp, #0x80
    1678:      	stp	d9, d8, [sp, #0x50]
    167c:      	stp	x20, x19, [sp, #0x60]
    1680:      	stp	x29, x30, [sp, #0x70]
    1684:      	add	x29, sp, #0x70
    1688:      	mov	x20, x1
    168c:      	mov	x19, x0
    1690:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1694:      	ldr	x8, [x8]
    1698:      	ldr	x8, [x8]
    169c:      	stur	x8, [x29, #-0x28]
    16a0:      	ldr	x0, [x0, #0x10]
    16a4:      	mov	x8, sp
    16a8:      	add	x1, x1, #0x18
    16ac:      	add	x3, x20, #0x8
    16b0:      	add	x4, x20, #0x10
    16b4:      	mov	x2, x20
    16b8:      	bl	0x16b8 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x44>
    16bc:      	ldur	d8, [x20, #0x18]
    16c0:      	ldr	d0, [sp]
    16c4:      	fabs	d1, d0
    16c8:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    16cc:      	ldr	d0, [x8]
    16d0:      	fcmp	d1, d0
    16d4:      	b.gt	0x1708 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x94>
    16d8:      	ldr	d1, [sp, #0x8]
    16dc:      	fabs	d1, d1
    16e0:      	fcmp	d1, d0
    16e4:      	b.gt	0x1708 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x94>
    16e8:      	ldr	d1, [sp, #0x10]
    16ec:      	fabs	d1, d1
    16f0:      	fcmp	d1, d0
    16f4:      	b.gt	0x1708 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x94>
    16f8:      	ldr	d1, [sp, #0x18]
    16fc:      	fabs	d1, d1
    1700:      	fcmp	d1, d0
    1704:      	b.le	0x1748 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0xd4>
    1708:      	add	x0, x19, #0x68
    170c:      	bl	0x170c <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x98>
    1710:      	ldr	d0, [x19, #0xf0]
    1714:      	fcmp	d0, d8
    1718:      	b.gt	0x1740 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0xcc>
    171c:      	ldp	q0, q1, [sp]
    1720:      	stp	q0, q1, [x19, #0xb0]
    1724:      	ldr	q0, [sp, #0x20]
    1728:      	str	q0, [x19, #0xd0]
    172c:      	ldr	d0, [sp, #0x30]
    1730:      	str	d0, [x19, #0xe0]
    1734:      	str	d8, [x19, #0xf0]
    1738:      	mov	w8, #0x1                ; =1
    173c:      	strb	w8, [x19, #0xf8]
    1740:      	add	x0, x19, #0x68
    1744:      	bl	0x1744 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0xd0>
    1748:      	ldur	x8, [x29, #-0x28]
    174c:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1750:      	ldr	x9, [x9]
    1754:      	ldr	x9, [x9]
    1758:      	cmp	x9, x8
    175c:      	b.ne	0x1774 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x100>
    1760:      	ldp	x29, x30, [sp, #0x70]
    1764:      	ldp	x20, x19, [sp, #0x60]
    1768:      	ldp	d9, d8, [sp, #0x50]
    176c:      	add	sp, sp, #0x80
    1770:      	ret
    1774:      	bl	0x1774 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x100>
    1778:      	bl	0x1778 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x104>

000000000000177c <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose>:
    177c:      	stp	x20, x19, [sp, #-0x20]!
    1780:      	stp	x29, x30, [sp, #0x10]
    1784:      	add	x29, sp, #0x10
    1788:      	mov	x20, x1
    178c:      	mov	x19, x0
    1790:      	add	x0, x0, #0x68
    1794:      	bl	0x1794 <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose+0x18>
    1798:      	ldrb	w8, [x19, #0xf8]
    179c:      	tbz	w8, #0x0, 0x17f0 <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose+0x74>
    17a0:      	ldr	d0, [x19, #0xf0]
    17a4:      	str	d0, [x20, #0x38]
    17a8:      	ldr	d0, [x19, #0xb0]
    17ac:      	str	d0, [x20]
    17b0:      	ldr	d0, [x19, #0xb8]
    17b4:      	str	d0, [x20, #0x8]
    17b8:      	ldr	d0, [x19, #0xc0]
    17bc:      	str	d0, [x20, #0x10]
    17c0:      	ldr	d0, [x19, #0xc8]
    17c4:      	str	d0, [x20, #0x18]
    17c8:      	ldr	d0, [x19, #0xd0]
    17cc:      	str	d0, [x20, #0x20]
    17d0:      	ldr	d0, [x19, #0xd8]
    17d4:      	str	d0, [x20, #0x28]
    17d8:      	ldr	d0, [x19, #0xe0]
    17dc:      	str	d0, [x20, #0x30]
    17e0:      	add	x0, x19, #0x68
    17e4:      	ldp	x29, x30, [sp, #0x10]
    17e8:      	ldp	x20, x19, [sp], #0x20
    17ec:      	b	0x17ec <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose+0x70>
    17f0:      	movi.16b	v0, #0x0
    17f4:      	stp	q0, q0, [x20, #0x20]
    17f8:      	stp	q0, q0, [x20]
    17fc:      	add	x0, x19, #0x68
    1800:      	ldp	x29, x30, [sp, #0x10]
    1804:      	ldp	x20, x19, [sp], #0x20
    1808:      	b	0x1808 <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose+0x8c>

000000000000180c <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj>:
    180c:      	stp	x22, x21, [sp, #-0x30]!
    1810:      	stp	x20, x19, [sp, #0x10]
    1814:      	stp	x29, x30, [sp, #0x20]
    1818:      	add	x29, sp, #0x20
    181c:      	mov	x19, x2
    1820:      	mov	x20, x1
    1824:      	mov	x21, x0
    1828:      	cbz	x2, 0x1830 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x24>
    182c:      	str	wzr, [x19]
    1830:      	cbz	x20, 0x1890 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x84>
    1834:      	add	x0, x21, #0x68
    1838:      	bl	0x1838 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x2c>
    183c:      	ldrb	w8, [x21, #0xf8]
    1840:      	tbz	w8, #0x0, 0x18a0 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x94>
    1844:      	ldr	d0, [x21, #0xf0]
    1848:      	str	d0, [x20, #0x38]
    184c:      	ldr	d0, [x21, #0xb0]
    1850:      	str	d0, [x20]
    1854:      	ldr	d0, [x21, #0xb8]
    1858:      	str	d0, [x20, #0x8]
    185c:      	ldr	d0, [x21, #0xc0]
    1860:      	str	d0, [x20, #0x10]
    1864:      	ldr	d0, [x21, #0xc8]
    1868:      	str	d0, [x20, #0x18]
    186c:      	ldr	d0, [x21, #0xd0]
    1870:      	str	d0, [x20, #0x20]
    1874:      	ldr	d0, [x21, #0xd8]
    1878:      	str	d0, [x20, #0x28]
    187c:      	ldr	d0, [x21, #0xe0]
    1880:      	str	d0, [x20, #0x30]
    1884:      	add	x0, x21, #0x68
    1888:      	bl	0x1888 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x7c>
    188c:      	cbnz	x19, 0x18b8 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0xac>
    1890:      	ldp	x29, x30, [sp, #0x20]
    1894:      	ldp	x20, x19, [sp, #0x10]
    1898:      	ldp	x22, x21, [sp], #0x30
    189c:      	ret
    18a0:      	movi.16b	v0, #0x0
    18a4:      	stp	q0, q0, [x20, #0x20]
    18a8:      	stp	q0, q0, [x20]
    18ac:      	add	x0, x21, #0x68
    18b0:      	bl	0x18b0 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0xa4>
    18b4:      	cbz	x19, 0x1890 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x84>
    18b8:      	ldr	d0, [x20, #0x38]
    18bc:      	fcmp	d0, #0.0
    18c0:      	b.le	0x18fc <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0xf0>
    18c4:      	ldp	q0, q1, [x20]
    18c8:      	fmul.2d	v1, v1, v1
    18cc:      	fmla.2d	v1, v0, v0
    18d0:      	faddp.2d	d0, v1
    18d4:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    18d8:      	ldr	d1, [x8]
    18dc:      	fcmp	d0, d1
    18e0:      	mov	w8, #0x2                ; =2
    18e4:      	cinc	w8, w8, gt
    18e8:      	str	w8, [x19]
    18ec:      	ldp	x29, x30, [sp, #0x20]
    18f0:      	ldp	x20, x19, [sp, #0x10]
    18f4:      	ldp	x22, x21, [sp], #0x30
    18f8:      	ret
    18fc:      	mov	w8, #0x0                ; =0
    1900:      	str	w8, [x19]
    1904:      	ldp	x29, x30, [sp, #0x20]
    1908:      	ldp	x20, x19, [sp, #0x10]
    190c:      	ldp	x22, x21, [sp], #0x30
    1910:      	ret

0000000000001914 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj>:
    1914:      	sub	sp, sp, #0x120
    1918:      	stp	d15, d14, [sp, #0xa0]
    191c:      	stp	d13, d12, [sp, #0xb0]
    1920:      	stp	d11, d10, [sp, #0xc0]
    1924:      	stp	d9, d8, [sp, #0xd0]
    1928:      	stp	x28, x27, [sp, #0xe0]
    192c:      	stp	x22, x21, [sp, #0xf0]
    1930:      	stp	x20, x19, [sp, #0x100]
    1934:      	stp	x29, x30, [sp, #0x110]
    1938:      	add	x29, sp, #0x110
    193c:      	mov	x19, x2
    1940:      	mov	x21, x1
    1944:      	mov	x20, x0
    1948:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    194c:      	ldr	x8, [x8]
    1950:      	ldr	x8, [x8]
    1954:      	stur	x8, [x29, #-0x78]
    1958:      	cbz	x2, 0x1960 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x4c>
    195c:      	str	wzr, [x19]
    1960:      	cbz	x21, 0x1ae8 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1d4>
    1964:      	cmp	x19, #0x0
    1968:      	cset	w22, eq
    196c:      	ldr	x0, [x20, #0x10]
    1970:      	add	x8, sp, #0x40
    1974:      	bl	0x1974 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x60>
    1978:      	ldr	d0, [sp, #0x40]
    197c:      	ldp	d8, d9, [sp, #0x50]
    1980:      	str	d0, [x21, #0x38]
    1984:      	ldp	d12, d1, [sp, #0x60]
    1988:      	ldr	q0, [sp, #0x70]
    198c:      	stp	q0, q1, [sp]
    1990:      	ldr	d10, [sp, #0x80]
    1994:      	ldr	x0, [x20]
    1998:      	ldr	x8, [x0]
    199c:      	ldr	x9, [x8, #0x48]
    19a0:      	add	x8, sp, #0x20
    19a4:      	blr	x9
    19a8:      	ldp	d14, d13, [sp, #0x20]
    19ac:      	ldp	d11, d15, [sp, #0x30]
    19b0:      	ldr	x0, [x20]
    19b4:      	ldr	x8, [x0]
    19b8:      	ldr	x9, [x8, #0x50]
    19bc:      	add	x8, sp, #0x20
    19c0:      	blr	x9
    19c4:      	fmul	d0, d14, d8
    19c8:      	fmadd	d0, d13, d9, d0
    19cc:      	fmadd	d0, d11, d12, d0
    19d0:      	ldr	q17, [sp, #0x10]
    19d4:      	fnmsub	d0, d15, d17, d0
    19d8:      	fmul	d1, d15, d8
    19dc:      	fmadd	d1, d14, d17, d1
    19e0:      	fmsub	d1, d13, d12, d1
    19e4:      	fmul	d2, d15, d9
    19e8:      	fmadd	d2, d14, d12, d2
    19ec:      	fmadd	d3, d13, d17, d2
    19f0:      	fmul	d2, d14, d9
    19f4:      	fnmsub	d2, d15, d12, d2
    19f8:      	fmadd	d4, d13, d8, d2
    19fc:      	ldp	d6, d5, [sp, #0x28]
    1a00:      	fmul	d2, d6, d12
    1a04:      	fnmsub	d7, d5, d9, d2
    1a08:      	ldr	d16, [sp, #0x20]
    1a0c:      	fmul	d2, d5, d8
    1a10:      	fnmsub	d2, d16, d12, d2
    1a14:      	mov.d	v7[1], v2[0]
    1a18:      	fmadd	d2, d11, d9, d1
    1a1c:      	fmsub	d1, d11, d8, d3
    1a20:      	fmul	d3, d16, d9
    1a24:      	fnmsub	d3, d6, d8, d3
    1a28:      	fadd.2d	v6, v7, v7
    1a2c:      	fadd	d3, d3, d3
    1a30:      	fmul	d7, d3, d8
    1a34:      	fnmsub	d7, d12, d6, d7
    1a38:      	fmul.d	d16, d12, v6[1]
    1a3c:      	fnmsub	d16, d3, d9, d16
    1a40:      	mov.d	v16[1], v7[0]
    1a44:      	ldr	q7, [sp, #0x20]
    1a48:      	ldr	q18, [sp]
    1a4c:      	fadd.2d	v7, v7, v18
    1a50:      	fmla.2d	v7, v6, v17[0]
    1a54:      	fadd.2d	v7, v7, v16
    1a58:      	fadd	d5, d5, d10
    1a5c:      	fmadd	d3, d3, d17, d5
    1a60:      	fmla.d	d3, d8, v6[1]
    1a64:      	fmsub	d3, d9, d6, d3
    1a68:      	str	q7, [x21, #0x20]
    1a6c:      	str	d3, [x21, #0x30]
    1a70:      	stp	d2, d1, [x21]
    1a74:      	fmadd	d3, d11, d17, d4
    1a78:      	stp	d3, d0, [x21, #0x10]
    1a7c:      	tbnz	w22, #0x0, 0x1ae8 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1d4>
    1a80:      	ldr	d4, [x21, #0x38]
    1a84:      	fcmp	d4, #0.0
    1a88:      	b.le	0x1ae0 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1cc>
    1a8c:      	fmul	d2, d2, d2
    1a90:      	fmadd	d2, d3, d3, d2
    1a94:      	fmadd	d1, d1, d1, d2
    1a98:      	fmadd	d0, d0, d0, d1
    1a9c:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1aa0:      	ldr	d1, [x8]
    1aa4:      	fcmp	d0, d1
    1aa8:      	mov	w8, #0x2                ; =2
    1aac:      	cinc	w21, w8, gt
    1ab0:      	ldr	x0, [x20, #0x10]
    1ab4:      	cbz	x0, 0x1ae4 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1d0>
    1ab8:      	fcmp	d0, d1
    1abc:      	cset	w20, gt
    1ac0:      	bl	0x1ac0 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1ac>
    1ac4:      	cmp	w20, #0x0
    1ac8:      	mov	w8, #0x22               ; =34
    1acc:      	mov	w9, #0x33               ; =51
    1ad0:      	csel	w8, w9, w8, ne
    1ad4:      	cmp	w0, #0x1
    1ad8:      	csel	w21, w8, w21, eq
    1adc:      	b	0x1ae4 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1d0>
    1ae0:      	mov	w21, #0x0               ; =0
    1ae4:      	str	w21, [x19]
    1ae8:      	ldur	x8, [x29, #-0x78]
    1aec:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1af0:      	ldr	x9, [x9]
    1af4:      	ldr	x9, [x9]
    1af8:      	cmp	x9, x8
    1afc:      	b.ne	0x1b28 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x214>
    1b00:      	ldp	x29, x30, [sp, #0x110]
    1b04:      	ldp	x20, x19, [sp, #0x100]
    1b08:      	ldp	x22, x21, [sp, #0xf0]
    1b0c:      	ldp	x28, x27, [sp, #0xe0]
    1b10:      	ldp	d9, d8, [sp, #0xd0]
    1b14:      	ldp	d11, d10, [sp, #0xc0]
    1b18:      	ldp	d13, d12, [sp, #0xb0]
    1b1c:      	ldp	d15, d14, [sp, #0xa0]
    1b20:      	add	sp, sp, #0x120
    1b24:      	ret
    1b28:      	bl	0x1b28 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x214>
    1b2c:      	bl	0x1b2c <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x218>

0000000000001b30 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose>:
    1b30:      	sub	sp, sp, #0x110
    1b34:      	stp	d15, d14, [sp, #0xa0]
    1b38:      	stp	d13, d12, [sp, #0xb0]
    1b3c:      	stp	d11, d10, [sp, #0xc0]
    1b40:      	stp	d9, d8, [sp, #0xd0]
    1b44:      	stp	x28, x27, [sp, #0xe0]
    1b48:      	stp	x20, x19, [sp, #0xf0]
    1b4c:      	stp	x29, x30, [sp, #0x100]
    1b50:      	add	x29, sp, #0x100
    1b54:      	mov	x19, x1
    1b58:      	mov	x20, x0
    1b5c:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1b60:      	ldr	x8, [x8]
    1b64:      	ldr	x8, [x8]
    1b68:      	stur	x8, [x29, #-0x68]
    1b6c:      	ldr	x0, [x0, #0x10]
    1b70:      	add	x8, sp, #0x40
    1b74:      	bl	0x1b74 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose+0x44>
    1b78:      	ldr	d0, [sp, #0x40]
    1b7c:      	ldp	d8, d9, [sp, #0x50]
    1b80:      	str	d0, [x19, #0x38]
    1b84:      	ldp	d11, d1, [sp, #0x60]
    1b88:      	ldr	q0, [sp, #0x70]
    1b8c:      	stp	q0, q1, [sp]
    1b90:      	ldr	d10, [sp, #0x80]
    1b94:      	ldr	x0, [x20]
    1b98:      	ldr	x8, [x0]
    1b9c:      	ldr	x9, [x8, #0x48]
    1ba0:      	add	x8, sp, #0x20
    1ba4:      	blr	x9
    1ba8:      	ldp	d14, d13, [sp, #0x20]
    1bac:      	ldp	d12, d15, [sp, #0x30]
    1bb0:      	ldr	x0, [x20]
    1bb4:      	ldr	x8, [x0]
    1bb8:      	ldr	x9, [x8, #0x50]
    1bbc:      	add	x8, sp, #0x20
    1bc0:      	blr	x9
    1bc4:      	fmul	d0, d14, d8
    1bc8:      	fmadd	d0, d13, d9, d0
    1bcc:      	fmadd	d0, d12, d11, d0
    1bd0:      	ldr	q17, [sp, #0x10]
    1bd4:      	fnmsub	d0, d15, d17, d0
    1bd8:      	fmul	d1, d15, d8
    1bdc:      	fmadd	d1, d14, d17, d1
    1be0:      	fmsub	d1, d13, d11, d1
    1be4:      	fmadd	d1, d12, d9, d1
    1be8:      	fmul	d2, d15, d9
    1bec:      	fmadd	d2, d14, d11, d2
    1bf0:      	fmadd	d2, d13, d17, d2
    1bf4:      	fmsub	d2, d12, d8, d2
    1bf8:      	fmul	d3, d14, d9
    1bfc:      	fnmsub	d3, d15, d11, d3
    1c00:      	fmadd	d3, d13, d8, d3
    1c04:      	ldp	d5, d4, [sp, #0x28]
    1c08:      	ldr	d6, [sp, #0x20]
    1c0c:      	fmul	d7, d4, d8
    1c10:      	fnmsub	d7, d6, d11, d7
    1c14:      	fmul	d6, d6, d9
    1c18:      	fnmsub	d6, d5, d8, d6
    1c1c:      	fmul	d5, d5, d11
    1c20:      	fnmsub	d5, d4, d9, d5
    1c24:      	mov.d	v5[1], v7[0]
    1c28:      	fadd.2d	v5, v5, v5
    1c2c:      	fadd	d6, d6, d6
    1c30:      	fmul	d7, d6, d8
    1c34:      	fnmsub	d7, d11, d5, d7
    1c38:      	fmul.d	d16, d11, v5[1]
    1c3c:      	fnmsub	d16, d6, d9, d16
    1c40:      	mov.d	v16[1], v7[0]
    1c44:      	fmadd	d3, d12, d17, d3
    1c48:      	ldr	q7, [sp, #0x20]
    1c4c:      	ldr	q18, [sp]
    1c50:      	fadd.2d	v7, v7, v18
    1c54:      	fmla.2d	v7, v5, v17[0]
    1c58:      	fadd.2d	v7, v7, v16
    1c5c:      	fadd	d4, d4, d10
    1c60:      	fmadd	d4, d6, d17, d4
    1c64:      	fmla.d	d4, d8, v5[1]
    1c68:      	fmsub	d4, d9, d5, d4
    1c6c:      	str	q7, [x19, #0x20]
    1c70:      	str	d4, [x19, #0x30]
    1c74:      	stp	d1, d2, [x19]
    1c78:      	stp	d3, d0, [x19, #0x10]
    1c7c:      	ldur	x8, [x29, #-0x68]
    1c80:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1c84:      	ldr	x9, [x9]
    1c88:      	ldr	x9, [x9]
    1c8c:      	cmp	x9, x8
    1c90:      	b.ne	0x1cb8 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose+0x188>
    1c94:      	ldp	x29, x30, [sp, #0x100]
    1c98:      	ldp	x20, x19, [sp, #0xf0]
    1c9c:      	ldp	x28, x27, [sp, #0xe0]
    1ca0:      	ldp	d9, d8, [sp, #0xd0]
    1ca4:      	ldp	d11, d10, [sp, #0xc0]
    1ca8:      	ldp	d13, d12, [sp, #0xb0]
    1cac:      	ldp	d15, d14, [sp, #0xa0]
    1cb0:      	add	sp, sp, #0x110
    1cb4:      	ret
    1cb8:      	bl	0x1cb8 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose+0x188>
    1cbc:      	bl	0x1cbc <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose+0x18c>

0000000000001cc0 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv>:
    1cc0:      	sub	sp, sp, #0x80
    1cc4:      	stp	x20, x19, [sp, #0x60]
    1cc8:      	stp	x29, x30, [sp, #0x70]
    1ccc:      	add	x29, sp, #0x70
    1cd0:      	mov	x19, x0
    1cd4:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1cd8:      	ldr	x8, [x8]
    1cdc:      	ldr	x8, [x8]
    1ce0:      	stur	x8, [x29, #-0x18]
    1ce4:      	add	x0, x0, #0x18
    1ce8:      	bl	0x1ce8 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x28>
    1cec:      	ldr	x0, [x19, #0x10]
    1cf0:      	ldp	x9, x8, [x19, #0x58]
    1cf4:      	stp	x9, x8, [sp]
    1cf8:      	cbz	x8, 0x1d10 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x50>
    1cfc:      	add	x8, x8, #0x8
    1d00:      	ldxr	x9, [x8]
    1d04:      	add	x9, x9, #0x1
    1d08:      	stxr	w10, x9, [x8]
    1d0c:      	cbnz	w10, 0x1d00 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x40>
    1d10:      	add	x8, sp, #0x10
    1d14:      	mov	x1, sp
    1d18:      	bl	0x1d18 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x58>
    1d1c:      	ldr	x20, [sp, #0x8]
    1d20:      	cbz	x20, 0x1d54 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x94>
    1d24:      	add	x8, x20, #0x8
    1d28:      	ldaxr	x9, [x8]
    1d2c:      	sub	x10, x9, #0x1
    1d30:      	stlxr	w11, x10, [x8]
    1d34:      	cbnz	w11, 0x1d28 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x68>
    1d38:      	cbnz	x9, 0x1d54 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x94>
    1d3c:      	ldr	x8, [x20]
    1d40:      	ldr	x8, [x8, #0x10]
    1d44:      	mov	x0, x20
    1d48:      	blr	x8
    1d4c:      	mov	x0, x20
    1d50:      	bl	0x1d50 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x90>
    1d54:      	add	x0, x19, #0x18
    1d58:      	bl	0x1d58 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x98>
    1d5c:      	ldur	x8, [x29, #-0x18]
    1d60:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1d64:      	ldr	x9, [x9]
    1d68:      	ldr	x9, [x9]
    1d6c:      	cmp	x9, x8
    1d70:      	b.ne	0x1d84 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xc4>
    1d74:      	ldp	x29, x30, [sp, #0x70]
    1d78:      	ldp	x20, x19, [sp, #0x60]
    1d7c:      	add	sp, sp, #0x80
    1d80:      	ret
    1d84:      	bl	0x1d84 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xc4>
    1d88:      	mov	x20, x0
    1d8c:      	mov	x0, sp
    1d90:      	bl	0x1d90 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xd0>
    1d94:      	add	x0, x19, #0x18
    1d98:      	bl	0x1d98 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xd8>
    1d9c:      	mov	x0, x20
    1da0:      	bl	0x1da0 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xe0>

0000000000001da4 <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose>:
    1da4:      	sub	sp, sp, #0x110
    1da8:      	stp	d15, d14, [sp, #0xa0]
    1dac:      	stp	d13, d12, [sp, #0xb0]
    1db0:      	stp	d11, d10, [sp, #0xc0]
    1db4:      	stp	d9, d8, [sp, #0xd0]
    1db8:      	stp	x28, x27, [sp, #0xe0]
    1dbc:      	stp	x20, x19, [sp, #0xf0]
    1dc0:      	stp	x29, x30, [sp, #0x100]
    1dc4:      	add	x29, sp, #0x100
    1dc8:      	mov	x19, x1
    1dcc:      	mov	x20, x0
    1dd0:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1dd4:      	ldr	x8, [x8]
    1dd8:      	ldr	x8, [x8]
    1ddc:      	stur	x8, [x29, #-0x68]
    1de0:      	ldr	x0, [x0, #0x10]
    1de4:      	add	x8, sp, #0x40
    1de8:      	bl	0x1de8 <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose+0x44>
    1dec:      	ldr	d0, [sp, #0x40]
    1df0:      	ldp	d8, d9, [sp, #0x50]
    1df4:      	str	d0, [x19, #0x38]
    1df8:      	ldp	d11, d1, [sp, #0x60]
    1dfc:      	ldr	q0, [sp, #0x70]
    1e00:      	stp	q0, q1, [sp]
    1e04:      	ldr	d10, [sp, #0x80]
    1e08:      	ldr	x0, [x20]
    1e0c:      	ldr	x8, [x0]
    1e10:      	ldr	x9, [x8, #0x28]
    1e14:      	add	x8, sp, #0x20
    1e18:      	blr	x9
    1e1c:      	ldp	d14, d13, [sp, #0x20]
    1e20:      	ldp	d12, d15, [sp, #0x30]
    1e24:      	ldr	x0, [x20]
    1e28:      	ldr	x8, [x0]
    1e2c:      	ldr	x9, [x8, #0x30]
    1e30:      	add	x8, sp, #0x20
    1e34:      	blr	x9
    1e38:      	fmul	d0, d14, d8
    1e3c:      	fmadd	d0, d13, d9, d0
    1e40:      	fmadd	d0, d12, d11, d0
    1e44:      	ldr	q17, [sp, #0x10]
    1e48:      	fnmsub	d0, d15, d17, d0
    1e4c:      	fmul	d1, d15, d8
    1e50:      	fmadd	d1, d14, d17, d1
    1e54:      	fmsub	d1, d13, d11, d1
    1e58:      	fmadd	d1, d12, d9, d1
    1e5c:      	fmul	d2, d15, d9
    1e60:      	fmadd	d2, d14, d11, d2
    1e64:      	fmadd	d2, d13, d17, d2
    1e68:      	fmsub	d2, d12, d8, d2
    1e6c:      	fmul	d3, d14, d9
    1e70:      	fnmsub	d3, d15, d11, d3
    1e74:      	fmadd	d3, d13, d8, d3
    1e78:      	ldp	d5, d4, [sp, #0x28]
    1e7c:      	ldr	d6, [sp, #0x20]
    1e80:      	fmul	d7, d4, d8
    1e84:      	fnmsub	d7, d6, d11, d7
    1e88:      	fmul	d6, d6, d9
    1e8c:      	fnmsub	d6, d5, d8, d6
    1e90:      	fmul	d5, d5, d11
    1e94:      	fnmsub	d5, d4, d9, d5
    1e98:      	mov.d	v5[1], v7[0]
    1e9c:      	fadd.2d	v5, v5, v5
    1ea0:      	fadd	d6, d6, d6
    1ea4:      	fmul	d7, d6, d8
    1ea8:      	fnmsub	d7, d11, d5, d7
    1eac:      	fmul.d	d16, d11, v5[1]
    1eb0:      	fnmsub	d16, d6, d9, d16
    1eb4:      	mov.d	v16[1], v7[0]
    1eb8:      	fmadd	d3, d12, d17, d3
    1ebc:      	ldr	q7, [sp, #0x20]
    1ec0:      	ldr	q18, [sp]
    1ec4:      	fadd.2d	v7, v7, v18
    1ec8:      	fmla.2d	v7, v5, v17[0]
    1ecc:      	fadd.2d	v7, v7, v16
    1ed0:      	fadd	d4, d4, d10
    1ed4:      	fmadd	d4, d6, d17, d4
    1ed8:      	fmla.d	d4, d8, v5[1]
    1edc:      	fmsub	d4, d9, d5, d4
    1ee0:      	str	q7, [x19, #0x20]
    1ee4:      	str	d4, [x19, #0x30]
    1ee8:      	stp	d1, d2, [x19]
    1eec:      	stp	d3, d0, [x19, #0x10]
    1ef0:      	ldur	x8, [x29, #-0x68]
    1ef4:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x91c>
    1ef8:      	ldr	x9, [x9]
    1efc:      	ldr	x9, [x9]
    1f00:      	cmp	x9, x8
    1f04:      	b.ne	0x1f2c <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose+0x188>
    1f08:      	ldp	x29, x30, [sp, #0x100]
    1f0c:      	ldp	x20, x19, [sp, #0xf0]
    1f10:      	ldp	x28, x27, [sp, #0xe0]
    1f14:      	ldp	d9, d8, [sp, #0xd0]
    1f18:      	ldp	d11, d10, [sp, #0xc0]
    1f1c:      	ldp	d13, d12, [sp, #0xb0]
    1f20:      	ldp	d15, d14, [sp, #0xa0]
    1f24:      	add	sp, sp, #0x110
    1f28:      	ret
    1f2c:      	bl	0x1f2c <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose+0x188>
    1f30:      	bl	0x1f30 <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose+0x18c>

0000000000001f34 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics>:
    1f34:      	sub	sp, sp, #0x70
    1f38:      	stp	x20, x19, [sp, #0x50]
    1f3c:      	stp	x29, x30, [sp, #0x60]
    1f40:      	add	x29, sp, #0x60
    1f44:      	mov	x19, x1
    1f48:      	mov	x20, x0
    1f4c:      	add	x0, x0, #0x100
    1f50:      	bl	0x1f50 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0x1c>
    1f54:      	ldrb	w8, [x20, #0x160]
    1f58:      	cmp	w8, #0x1
    1f5c:      	b.ne	0x1f7c <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0x48>
    1f60:      	ldp	q0, q1, [x20, #0x140]
    1f64:      	stp	q0, q1, [x19]
    1f68:      	add	x0, x20, #0x100
    1f6c:      	ldp	x29, x30, [sp, #0x60]
    1f70:      	ldp	x20, x19, [sp, #0x50]
    1f74:      	add	sp, sp, #0x70
    1f78:      	b	0x1f78 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0x44>
    1f7c:      	add	x0, x20, #0x100
    1f80:      	bl	0x1f80 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0x4c>
    1f84:      	ldr	x0, [x20]
    1f88:      	ldr	x8, [x0]
    1f8c:      	ldr	x9, [x8, #0x18]
    1f90:      	add	x8, sp, #0x8
    1f94:      	blr	x9
    1f98:      	ldr	d0, [sp, #0x8]
    1f9c:      	str	d0, [x19]
    1fa0:      	ldr	x0, [x20]
    1fa4:      	ldr	x8, [x0]
    1fa8:      	ldr	x9, [x8, #0x18]
    1fac:      	add	x8, sp, #0x8
    1fb0:      	blr	x9
    1fb4:      	ldr	d0, [sp, #0x28]
    1fb8:      	str	d0, [x19, #0x8]
    1fbc:      	ldr	x0, [x20]
    1fc0:      	ldr	x8, [x0]
    1fc4:      	ldr	x9, [x8, #0x18]
    1fc8:      	add	x8, sp, #0x8
    1fcc:      	blr	x9
    1fd0:      	ldr	d0, [sp, #0x38]
    1fd4:      	str	d0, [x19, #0x10]
    1fd8:      	ldr	x0, [x20]
    1fdc:      	ldr	x8, [x0]
    1fe0:      	ldr	x9, [x8, #0x18]
    1fe4:      	add	x8, sp, #0x8
    1fe8:      	blr	x9
    1fec:      	ldr	d0, [sp, #0x40]
    1ff0:      	str	d0, [x19, #0x18]
    1ff4:      	ldp	x29, x30, [sp, #0x60]
    1ff8:      	ldp	x20, x19, [sp, #0x50]
    1ffc:      	add	sp, sp, #0x70
    2000:      	ret

0000000000002004 <__ZNK12xrslam_0_5_013XRSLAMManager14GetResultStateEP11XRSLAMState>:
    2004:      	stp	x20, x19, [sp, #-0x20]!
    2008:      	stp	x29, x30, [sp, #0x10]
    200c:      	add	x29, sp, #0x10
    2010:      	mov	x19, x1
    2014:      	ldr	x0, [x0, #0x10]
    2018:      	bl	0x2018 <__ZNK12xrslam_0_5_013XRSLAMManager14GetResultStateEP11XRSLAMState+0x14>
    201c:      	cmp	w0, #0x3
    2020:      	b.hi	0x2034 <__ZNK12xrslam_0_5_013XRSLAMManager14GetResultStateEP11XRSLAMState+0x30>
    2024:      	adrp	x8, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2028:      	add	x8, x8, #0x0
    202c:      	ldr	w8, [x8, w0, uxtw #2]
    2030:      	str	w8, [x19]
    2034:      	ldp	x29, x30, [sp, #0x10]
    2038:      	ldp	x20, x19, [sp], #0x20
    203c:      	ret

0000000000002040 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks>:
    2040:      	sub	sp, sp, #0x60
    2044:      	stp	x24, x23, [sp, #0x20]
    2048:      	stp	x22, x21, [sp, #0x30]
    204c:      	stp	x20, x19, [sp, #0x40]
    2050:      	stp	x29, x30, [sp, #0x50]
    2054:      	add	x29, sp, #0x50
    2058:      	mov	x20, x1
    205c:      	add	x8, sp, #0x8
    2060:      	mov	w0, #0x8                ; =8
    2064:      	bl	0x2064 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x24>
    2068:      	ldr	x1, [sp, #0x8]
    206c:      	ldr	x8, [x1]
    2070:      	cbz	x8, 0x2208 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1c8>
    2074:      	adrp	x3, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2078:      	add	x3, x3, #0x0
    207c:      	adrp	x4, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2080:      	add	x4, x4, #0x0
    2084:      	mov	w0, #0x3                ; =3
    2088:      	mov	x2, #0x0                ; =0
    208c:      	blr	x8
    2090:      	cbz	x0, 0x2208 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1c8>
    2094:      	ldp	x22, x23, [x0]
    2098:      	subs	x0, x23, x22
    209c:      	b.eq	0x20dc <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x9c>
    20a0:      	tbnz	x0, #0x3f, 0x2210 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1d0>
    20a4:      	bl	0x20a4 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x64>
    20a8:      	mov	x19, x0
    20ac:      	mov	x21, x0
    20b0:      	ldr	q0, [x22]
    20b4:      	ldr	x8, [x22, #0x10]
    20b8:      	str	x8, [x21, #0x10]
    20bc:      	str	q0, [x21]
    20c0:      	ldrb	w8, [x22, #0x18]
    20c4:      	strb	w8, [x21, #0x18]
    20c8:      	add	x22, x22, #0x20
    20cc:      	add	x21, x21, #0x20
    20d0:      	cmp	x22, x23
    20d4:      	b.ne	0x20b0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x70>
    20d8:      	b	0x20e4 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xa4>
    20dc:      	mov	x21, #0x0               ; =0
    20e0:      	mov	x19, #0x0               ; =0
    20e4:      	sub	x8, x21, x19
    20e8:      	asr	x22, x8, #5
    20ec:      	str	w22, [x20, #0x8]
    20f0:      	add	x8, x22, x8, asr #4
    20f4:      	lsl	x8, x8, #3
    20f8:      	mov	w9, #0x18               ; =24
    20fc:      	umulh	x9, x22, x9
    2100:      	cmp	xzr, x9
    2104:      	csinv	x0, x8, xzr, eq
    2108:      	bl	0x2108 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xc8>
    210c:      	str	x0, [x20]
    2110:      	cmp	x21, x19
    2114:      	b.ne	0x2148 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x108>
    2118:      	cbnz	x19, 0x21f0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1b0>
    211c:      	ldrb	w8, [sp, #0x18]
    2120:      	cmp	w8, #0x1
    2124:      	b.ne	0x2130 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xf0>
    2128:      	ldr	x0, [sp, #0x10]
    212c:      	bl	0x212c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xec>
    2130:      	ldp	x29, x30, [sp, #0x50]
    2134:      	ldp	x20, x19, [sp, #0x40]
    2138:      	ldp	x22, x21, [sp, #0x30]
    213c:      	ldp	x24, x23, [sp, #0x20]
    2140:      	add	sp, sp, #0x60
    2144:      	ret
    2148:      	cmp	x22, #0x1
    214c:      	csinc	x8, x22, xzr, hi
    2150:      	cmp	x22, #0x4
    2154:      	b.hi	0x2160 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x120>
    2158:      	mov	x9, #0x0                ; =0
    215c:      	b	0x21bc <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x17c>
    2160:      	ands	x9, x8, #0x3
    2164:      	mov	w10, #0x4               ; =4
    2168:      	csel	x9, x10, x9, eq
    216c:      	sub	x9, x8, x9
    2170:      	add	x10, x19, #0x40
    2174:      	mov	x11, x9
    2178:      	mov	x12, x0
    217c:      	ldp	q1, q0, [x10, #-0x20]
    2180:      	ldp	q3, q2, [x10, #-0x40]
    2184:      	ldp	q5, q4, [x10, #0x20]
    2188:      	ldp	q7, q6, [x10], #0x80
    218c:      	zip1.2d	v16, v3, v1
    2190:      	zip2.2d	v17, v3, v1
    2194:      	zip1.2d	v18, v2, v0
    2198:      	add	x13, x12, #0x60
    219c:      	st3.2d	{ v16, v17, v18 }, [x12], #48
    21a0:      	zip1.2d	v0, v7, v5
    21a4:      	zip2.2d	v1, v7, v5
    21a8:      	zip1.2d	v2, v6, v4
    21ac:      	st3.2d	{ v0, v1, v2 }, [x12]
    21b0:      	mov	x12, x13
    21b4:      	subs	x11, x11, #0x4
    21b8:      	b.ne	0x217c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x13c>
    21bc:      	mov	w10, #0x18              ; =24
    21c0:      	madd	x10, x9, x10, x0
    21c4:      	add	x10, x10, #0x10
    21c8:      	add	x11, x19, x9, lsl #5
    21cc:      	add	x11, x11, #0x10
    21d0:      	sub	x8, x8, x9
    21d4:      	ldr	d0, [x11]
    21d8:      	ldur	q1, [x11, #-0x10]
    21dc:      	stur	q1, [x10, #-0x10]
    21e0:      	str	d0, [x10], #0x18
    21e4:      	add	x11, x11, #0x20
    21e8:      	subs	x8, x8, #0x1
    21ec:      	b.ne	0x21d4 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x194>
    21f0:      	mov	x0, x19
    21f4:      	bl	0x21f4 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1b4>
    21f8:      	ldrb	w8, [sp, #0x18]
    21fc:      	cmp	w8, #0x1
    2200:      	b.eq	0x2128 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xe8>
    2204:      	b	0x2130 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xf0>
    2208:      	bl	0x2208 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1c8>
    220c:      	b	0x2214 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1d4>
    2210:      	bl	0x2210 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1d0>
    2214:      	brk	#0x1
    2218:      	mov	x20, x0
    221c:      	cbnz	x19, 0x2234 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1f4>
    2220:      	ldrb	w8, [sp, #0x18]
    2224:      	cmp	w8, #0x1
    2228:      	b.eq	0x2260 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x220>
    222c:      	mov	x0, x20
    2230:      	bl	0x2230 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1f0>
    2234:      	mov	x0, x19
    2238:      	bl	0x2238 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1f8>
    223c:      	ldrb	w8, [sp, #0x18]
    2240:      	cmp	w8, #0x1
    2244:      	b.ne	0x222c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1ec>
    2248:      	b	0x2260 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x220>
    224c:      	bl	0x224c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x20c>
    2250:      	mov	x20, x0
    2254:      	ldrb	w8, [sp, #0x18]
    2258:      	cmp	w8, #0x1
    225c:      	b.ne	0x222c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1ec>
    2260:      	ldr	x0, [sp, #0x10]
    2264:      	bl	0x2264 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x224>
    2268:      	mov	x0, x20
    226c:      	bl	0x226c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x22c>

0000000000002270 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultFeaturesEP14XRSLAMFeatures>:
    2270:      	ret

0000000000002274 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias>:
    2274:      	sub	sp, sp, #0x40
    2278:      	stp	x20, x19, [sp, #0x20]
    227c:      	stp	x29, x30, [sp, #0x30]
    2280:      	add	x29, sp, #0x30
    2284:      	mov	x19, x1
    2288:      	add	x8, sp, #0x8
    228c:      	mov	w0, #0x9                ; =9
    2290:      	bl	0x2290 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x1c>
    2294:      	ldr	x1, [sp, #0x8]
    2298:      	ldr	x8, [x1]
    229c:      	cbz	x8, 0x22d0 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x5c>
    22a0:      	adrp	x3, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    22a4:      	add	x3, x3, #0x0
    22a8:      	adrp	x4, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    22ac:      	add	x4, x4, #0x0
    22b0:      	mov	w0, #0x3                ; =3
    22b4:      	mov	x2, #0x0                ; =0
    22b8:      	blr	x8
    22bc:      	cbz	x0, 0x2350 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xdc>
    22c0:      	ldr	d0, [x0, #0x10]
    22c4:      	ldr	q1, [x0]
    22c8:      	stur	q1, [x19, #0x18]
    22cc:      	str	d0, [x19, #0x28]
    22d0:      	ldrb	w8, [sp, #0x18]
    22d4:      	cmp	w8, #0x1
    22d8:      	b.ne	0x22e4 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x70>
    22dc:      	ldr	x0, [sp, #0x10]
    22e0:      	bl	0x22e0 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x6c>
    22e4:      	add	x8, sp, #0x8
    22e8:      	mov	w0, #0xa                ; =10
    22ec:      	bl	0x22ec <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x78>
    22f0:      	ldr	x1, [sp, #0x8]
    22f4:      	ldr	x8, [x1]
    22f8:      	cbz	x8, 0x232c <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xb8>
    22fc:      	adrp	x3, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2300:      	add	x3, x3, #0x0
    2304:      	adrp	x4, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2308:      	add	x4, x4, #0x0
    230c:      	mov	w0, #0x3                ; =3
    2310:      	mov	x2, #0x0                ; =0
    2314:      	blr	x8
    2318:      	cbz	x0, 0x2358 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xe4>
    231c:      	ldr	d0, [x0, #0x10]
    2320:      	ldr	q1, [x0]
    2324:      	str	q1, [x19]
    2328:      	str	d0, [x19, #0x10]
    232c:      	ldrb	w8, [sp, #0x18]
    2330:      	cmp	w8, #0x1
    2334:      	b.ne	0x2340 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xcc>
    2338:      	ldr	x0, [sp, #0x10]
    233c:      	bl	0x233c <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xc8>
    2340:      	ldp	x29, x30, [sp, #0x30]
    2344:      	ldp	x20, x19, [sp, #0x20]
    2348:      	add	sp, sp, #0x40
    234c:      	ret
    2350:      	bl	0x2350 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xdc>
    2354:      	b	0x235c <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xe8>
    2358:      	bl	0x2358 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xe4>
    235c:      	brk	#0x1
    2360:      	b	0x2368 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xf4>
    2364:      	bl	0x2364 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xf0>
    2368:      	mov	x19, x0
    236c:      	ldrb	w8, [sp, #0x18]
    2370:      	cmp	w8, #0x1
    2374:      	b.ne	0x2380 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x10c>
    2378:      	ldr	x0, [sp, #0x10]
    237c:      	bl	0x237c <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x108>
    2380:      	mov	x0, x19
    2384:      	bl	0x2384 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x110>
    2388:      	bl	0x2388 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x114>

000000000000238c <__ZNK12xrslam_0_5_013XRSLAMManager16GetResultVersionEP18XRSLAMStringOutput>:
    238c:      	stp	x20, x19, [sp, #-0x20]!
    2390:      	stp	x29, x30, [sp, #0x10]
    2394:      	add	x29, sp, #0x10
    2398:      	mov	x19, x1
    239c:      	mov	w8, #0x5                ; =5
    23a0:      	str	w8, [x1]
    23a4:      	mov	w0, #0xa                ; =10
    23a8:      	bl	0x23a8 <__ZNK12xrslam_0_5_013XRSLAMManager16GetResultVersionEP18XRSLAMStringOutput+0x1c>
    23ac:      	str	x0, [x19, #0x8]
    23b0:      	mov	w8, #0x2e30             ; =11824
    23b4:      	movk	w8, #0x2e31, lsl #16
    23b8:      	str	w8, [x0]
    23bc:      	mov	w8, #0x30               ; =48
    23c0:      	strh	w8, [x0, #0x4]
    23c4:      	ldp	x29, x30, [sp, #0x10]
    23c8:      	ldp	x20, x19, [sp], #0x20
    23cc:      	ret

00000000000023d0 <___clang_call_terminate>:
    23d0:      	stp	x29, x30, [sp, #-0x10]!
    23d4:      	mov	x29, sp
    23d8:      	bl	0x23d8 <___clang_call_terminate+0x8>
    23dc:      	bl	0x23dc <___clang_call_terminate+0xc>

00000000000023e0 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc>:
    23e0:      	stp	x24, x23, [sp, #-0x40]!
    23e4:      	stp	x22, x21, [sp, #0x10]
    23e8:      	stp	x20, x19, [sp, #0x20]
    23ec:      	stp	x29, x30, [sp, #0x30]
    23f0:      	add	x29, sp, #0x30
    23f4:      	mov	x21, x1
    23f8:      	mov	x19, x0
    23fc:      	mov	x0, x1
    2400:      	bl	0x2400 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x20>
    2404:      	mov	x8, #0x7ffffffffffffff8 ; =9223372036854775800
    2408:      	cmp	x0, x8
    240c:      	b.hs	0x2480 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0xa0>
    2410:      	mov	x20, x0
    2414:      	cmp	x0, #0x17
    2418:      	b.hs	0x242c <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x4c>
    241c:      	strb	w20, [x19, #0x17]
    2420:      	mov	x22, x19
    2424:      	cbnz	x20, 0x2454 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x74>
    2428:      	b	0x2464 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x84>
    242c:      	orr	x8, x20, #0x7
    2430:      	cmp	x8, #0x17
    2434:      	mov	w9, #0x19               ; =25
    2438:      	csinc	x23, x9, x8, eq
    243c:      	mov	x0, x23
    2440:      	bl	0x2440 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x60>
    2444:      	mov	x22, x0
    2448:      	orr	x8, x23, #0x8000000000000000
    244c:      	stp	x20, x8, [x19, #0x8]
    2450:      	str	x0, [x19]
    2454:      	mov	x0, x22
    2458:      	mov	x1, x21
    245c:      	mov	x2, x20
    2460:      	bl	0x2460 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x80>
    2464:      	strb	wzr, [x22, x20]
    2468:      	mov	x0, x19
    246c:      	ldp	x29, x30, [sp, #0x30]
    2470:      	ldp	x20, x19, [sp, #0x20]
    2474:      	ldp	x22, x21, [sp, #0x10]
    2478:      	ldp	x24, x23, [sp], #0x40
    247c:      	ret
    2480:      	bl	0x2480 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0xa0>

0000000000002484 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE20__throw_length_errorB8ne200100Ev>:
    2484:      	stp	x29, x30, [sp, #-0x10]!
    2488:      	mov	x29, sp
    248c:      	adrp	x0, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2490:      	add	x0, x0, #0x0
    2494:      	bl	0x2494 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE20__throw_length_errorB8ne200100Ev+0x10>

0000000000002498 <__ZNSt3__120__throw_length_errorB8ne200100EPKc>:
    2498:      	stp	x20, x19, [sp, #-0x20]!
    249c:      	stp	x29, x30, [sp, #0x10]
    24a0:      	add	x29, sp, #0x10
    24a4:      	mov	x20, x0
    24a8:      	mov	w0, #0x10               ; =16
    24ac:      	bl	0x24ac <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x14>
    24b0:      	mov	x19, x0
    24b4:      	mov	x1, x20
    24b8:      	bl	0x24b8 <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x20>
    24bc:      	adrp	x1, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    24c0:      	ldr	x1, [x1]
    24c4:      	adrp	x2, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    24c8:      	ldr	x2, [x2]
    24cc:      	mov	x0, x19
    24d0:      	bl	0x24d0 <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x38>
    24d4:      	mov	x20, x0
    24d8:      	mov	x0, x19
    24dc:      	bl	0x24dc <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x44>
    24e0:      	mov	x0, x20
    24e4:      	bl	0x24e4 <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x4c>

00000000000024e8 <__ZNSt12length_errorC1B8ne200100EPKc>:
    24e8:      	stp	x29, x30, [sp, #-0x10]!
    24ec:      	mov	x29, sp
    24f0:      	bl	0x24f0 <__ZNSt12length_errorC1B8ne200100EPKc+0x8>
    24f4:      	adrp	x8, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    24f8:      	ldr	x8, [x8]
    24fc:      	add	x8, x8, #0x10
    2500:      	str	x8, [x0]
    2504:      	ldp	x29, x30, [sp], #0x10
    2508:      	ret

000000000000250c <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m>:
    250c:      	sub	sp, sp, #0x70
    2510:      	stp	x26, x25, [sp, #0x20]
    2514:      	stp	x24, x23, [sp, #0x30]
    2518:      	stp	x22, x21, [sp, #0x40]
    251c:      	stp	x20, x19, [sp, #0x50]
    2520:      	stp	x29, x30, [sp, #0x60]
    2524:      	add	x29, sp, #0x60
    2528:      	mov	x21, x2
    252c:      	mov	x20, x1
    2530:      	mov	x19, x0
    2534:      	add	x0, sp, #0x8
    2538:      	mov	x1, x19
    253c:      	bl	0x253c <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x30>
    2540:      	ldrb	w8, [sp, #0x8]
    2544:      	cmp	w8, #0x1
    2548:      	b.ne	0x25f4 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xe8>
    254c:      	ldr	x8, [x19]
    2550:      	ldur	x8, [x8, #-0x18]
    2554:      	add	x4, x19, x8
    2558:      	ldr	x22, [x4, #0x28]
    255c:      	ldr	w24, [x4, #0x8]
    2560:      	ldr	w23, [x4, #0x90]
    2564:      	cmn	w23, #0x1
    2568:      	b.ne	0x25b0 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xa4>
    256c:      	add	x8, sp, #0x18
    2570:      	mov	x25, x4
    2574:      	mov	x0, x4
    2578:      	bl	0x2578 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x6c>
    257c:      	adrp	x1, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2580:      	ldr	x1, [x1]
    2584:      	add	x0, sp, #0x18
    2588:      	bl	0x2588 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x7c>
    258c:      	ldr	x8, [x0]
    2590:      	ldr	x8, [x8, #0x38]
    2594:      	mov	w1, #0x20               ; =32
    2598:      	blr	x8
    259c:      	mov	x23, x0
    25a0:      	add	x0, sp, #0x18
    25a4:      	bl	0x25a4 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x98>
    25a8:      	mov	x4, x25
    25ac:      	str	w23, [x25, #0x90]
    25b0:      	mov	w8, #0xb0               ; =176
    25b4:      	and	w8, w24, w8
    25b8:      	add	x3, x20, x21
    25bc:      	cmp	w8, #0x20
    25c0:      	csel	x2, x3, x20, eq
    25c4:      	sxtb	w5, w23
    25c8:      	mov	x0, x22
    25cc:      	mov	x1, x20
    25d0:      	bl	0x25d0 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xc4>
    25d4:      	cbnz	x0, 0x25f4 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xe8>
    25d8:      	ldr	x8, [x19]
    25dc:      	ldur	x8, [x8, #-0x18]
    25e0:      	add	x0, x19, x8
    25e4:      	ldr	w8, [x0, #0x20]
    25e8:      	mov	w9, #0x5                ; =5
    25ec:      	orr	w1, w8, w9
    25f0:      	bl	0x25f0 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xe4>
    25f4:      	add	x0, sp, #0x8
    25f8:      	bl	0x25f8 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xec>
    25fc:      	mov	x0, x19
    2600:      	ldp	x29, x30, [sp, #0x60]
    2604:      	ldp	x20, x19, [sp, #0x50]
    2608:      	ldp	x22, x21, [sp, #0x40]
    260c:      	ldp	x24, x23, [sp, #0x30]
    2610:      	ldp	x26, x25, [sp, #0x20]
    2614:      	add	sp, sp, #0x70
    2618:      	ret
    261c:      	b	0x2630 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x124>
    2620:      	mov	x20, x0
    2624:      	add	x0, sp, #0x18
    2628:      	bl	0x2628 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x11c>
    262c:      	b	0x2634 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x128>
    2630:      	mov	x20, x0
    2634:      	add	x0, sp, #0x8
    2638:      	bl	0x2638 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x12c>
    263c:      	b	0x2644 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x138>
    2640:      	mov	x20, x0
    2644:      	mov	x0, x20
    2648:      	bl	0x2648 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x13c>
    264c:      	ldr	x8, [x19]
    2650:      	ldur	x8, [x8, #-0x18]
    2654:      	add	x0, x19, x8
    2658:      	bl	0x2658 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x14c>
    265c:      	bl	0x265c <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x150>
    2660:      	b	0x25fc <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xf0>
    2664:      	mov	x19, x0
    2668:      	bl	0x2668 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x15c>
    266c:      	mov	x0, x19
    2670:      	bl	0x2670 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x164>
    2674:      	bl	0x2674 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x168>

0000000000002678 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_>:
    2678:      	sub	sp, sp, #0x70
    267c:      	stp	x26, x25, [sp, #0x20]
    2680:      	stp	x24, x23, [sp, #0x30]
    2684:      	stp	x22, x21, [sp, #0x40]
    2688:      	stp	x20, x19, [sp, #0x50]
    268c:      	stp	x29, x30, [sp, #0x60]
    2690:      	add	x29, sp, #0x60
    2694:      	mov	x19, x0
    2698:      	cbz	x0, 0x27d4 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x15c>
    269c:      	mov	x24, x5
    26a0:      	mov	x20, x4
    26a4:      	mov	x22, x3
    26a8:      	mov	x21, x2
    26ac:      	sub	x8, x3, x1
    26b0:      	ldr	x9, [x4, #0x18]
    26b4:      	subs	x8, x9, x8
    26b8:      	csel	x23, x8, xzr, gt
    26bc:      	sub	x25, x2, x1
    26c0:      	cmp	x25, #0x1
    26c4:      	b.lt	0x26e4 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x6c>
    26c8:      	ldr	x8, [x19]
    26cc:      	ldr	x8, [x8, #0x60]
    26d0:      	mov	x0, x19
    26d4:      	mov	x2, x25
    26d8:      	blr	x8
    26dc:      	cmp	x0, x25
    26e0:      	b.ne	0x27d0 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x158>
    26e4:      	cmp	x23, #0x1
    26e8:      	b.lt	0x279c <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x124>
    26ec:      	mov	x8, #0x7ffffffffffffff8 ; =9223372036854775800
    26f0:      	cmp	x23, x8
    26f4:      	b.hs	0x27f4 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x17c>
    26f8:      	cmp	x23, #0x17
    26fc:      	b.hs	0x270c <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x94>
    2700:      	strb	w23, [sp, #0x1f]
    2704:      	add	x25, sp, #0x8
    2708:      	b	0x2734 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0xbc>
    270c:      	orr	x8, x23, #0x7
    2710:      	cmp	x8, #0x17
    2714:      	mov	w9, #0x19               ; =25
    2718:      	csinc	x26, x9, x8, eq
    271c:      	mov	x0, x26
    2720:      	bl	0x2720 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0xa8>
    2724:      	mov	x25, x0
    2728:      	orr	x8, x26, #0x8000000000000000
    272c:      	stp	x23, x8, [sp, #0x10]
    2730:      	str	x0, [sp, #0x8]
    2734:      	mov	x0, x25
    2738:      	mov	x1, x24
    273c:      	mov	x2, x23
    2740:      	bl	0x2740 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0xc8>
    2744:      	strb	wzr, [x25, x23]
    2748:      	ldrsb	w8, [sp, #0x1f]
    274c:      	ldr	x9, [sp, #0x8]
    2750:      	cmp	w8, #0x0
    2754:      	add	x8, sp, #0x8
    2758:      	csel	x1, x9, x8, lt
    275c:      	ldr	x8, [x19]
    2760:      	ldr	x8, [x8, #0x60]
    2764:      	mov	x0, x19
    2768:      	mov	x2, x23
    276c:      	blr	x8
    2770:      	ldrsb	w8, [sp, #0x1f]
    2774:      	tbnz	w8, #0x1f, 0x2784 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x10c>
    2778:      	cmp	x0, x23
    277c:      	b.ne	0x27d0 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x158>
    2780:      	b	0x279c <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x124>
    2784:      	ldr	x8, [sp, #0x8]
    2788:      	mov	x24, x0
    278c:      	mov	x0, x8
    2790:      	bl	0x2790 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x118>
    2794:      	cmp	x24, x23
    2798:      	b.ne	0x27d0 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x158>
    279c:      	sub	x22, x22, x21
    27a0:      	cmp	x22, #0x1
    27a4:      	b.lt	0x27c8 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x150>
    27a8:      	ldr	x8, [x19]
    27ac:      	ldr	x8, [x8, #0x60]
    27b0:      	mov	x0, x19
    27b4:      	mov	x1, x21
    27b8:      	mov	x2, x22
    27bc:      	blr	x8
    27c0:      	cmp	x0, x22
    27c4:      	b.ne	0x27d0 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x158>
    27c8:      	str	xzr, [x20, #0x18]
    27cc:      	b	0x27d4 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x15c>
    27d0:      	mov	x19, #0x0               ; =0
    27d4:      	mov	x0, x19
    27d8:      	ldp	x29, x30, [sp, #0x60]
    27dc:      	ldp	x20, x19, [sp, #0x50]
    27e0:      	ldp	x22, x21, [sp, #0x40]
    27e4:      	ldp	x24, x23, [sp, #0x30]
    27e8:      	ldp	x26, x25, [sp, #0x20]
    27ec:      	add	sp, sp, #0x70
    27f0:      	ret
    27f4:      	bl	0x27f4 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x17c>
    27f8:      	mov	x19, x0
    27fc:      	ldrsb	w8, [sp, #0x1f]
    2800:      	tbz	w8, #0x1f, 0x280c <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x194>
    2804:      	ldr	x0, [sp, #0x8]
    2808:      	bl	0x2808 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x190>
    280c:      	mov	x0, x19
    2810:      	bl	0x2810 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x198>

0000000000002814 <__ZNSt3__120__throw_bad_any_castB8ne200100Ev>:
    2814:      	stp	x29, x30, [sp, #-0x10]!
    2818:      	mov	x29, sp
    281c:      	mov	w0, #0x8                ; =8
    2820:      	bl	0x2820 <__ZNSt3__120__throw_bad_any_castB8ne200100Ev+0xc>
    2824:      	str	xzr, [x0]
    2828:      	bl	0x2828 <__ZNSt3__120__throw_bad_any_castB8ne200100Ev+0x14>
    282c:      	adrp	x1, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2830:      	ldr	x1, [x1]
    2834:      	adrp	x2, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2838:      	add	x2, x2, #0x0
    283c:      	bl	0x283c <__ZNSt3__120__throw_bad_any_castB8ne200100Ev+0x28>

0000000000002840 <__ZNSt12bad_any_castC1Ev>:
    2840:      	stp	x29, x30, [sp, #-0x10]!
    2844:      	mov	x29, sp
    2848:      	bl	0x2848 <__ZNSt12bad_any_castC1Ev+0x8>
    284c:      	adrp	x8, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2850:      	ldr	x8, [x8]
    2854:      	add	x8, x8, #0x10
    2858:      	str	x8, [x0]
    285c:      	ldp	x29, x30, [sp], #0x10
    2860:      	ret

0000000000002864 <__ZNSt12bad_any_castD1Ev>:
    2864:      	b	0x2864 <__ZNSt12bad_any_castD1Ev>

0000000000002868 <__ZNSt3__16vectorIN12xrslam_0_5_08LandmarkENS_9allocatorIS2_EEE20__throw_length_errorB8ne200100Ev>:
    2868:      	stp	x29, x30, [sp, #-0x10]!
    286c:      	mov	x29, sp
    2870:      	adrp	x0, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2874:      	add	x0, x0, #0x0
    2878:      	bl	0x2878 <__ZNSt3__16vectorIN12xrslam_0_5_08LandmarkENS_9allocatorIS2_EEE20__throw_length_errorB8ne200100Ev+0x10>

000000000000287c <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1>:
    287c:      	stp	x20, x19, [sp, #-0x20]!
    2880:      	stp	x29, x30, [sp, #0x10]
    2884:      	add	x29, sp, #0x10
    2888:      	adrp	x19, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    288c:      	add	x19, x19, #0x0
    2890:      	mov	x0, x19
    2894:      	bl	0x2894 <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1+0x18>
    2898:      	cbz	w0, 0x2928 <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1+0xac>
    289c:      	stp	xzr, xzr, [x19, #0x18]
    28a0:      	mov	x1, x19
    28a4:      	str	xzr, [x1, #0x10]!
    28a8:      	mov	w8, #0xaba7             ; =43943
    28ac:      	movk	w8, #0x32aa, lsl #16
    28b0:      	str	x8, [x19, #0x28]
    28b4:      	movi.16b	v0, #0x0
    28b8:      	stp	q0, q0, [x19, #0x30]
    28bc:      	stp	q0, q0, [x19, #0x50]
    28c0:      	stp	xzr, x8, [x19, #0x70]
    28c4:      	stp	q0, q0, [x19, #0x80]
    28c8:      	str	q0, [x19, #0xa0]
    28cc:      	str	xzr, [x19, #0xb0]
    28d0:      	stp	xzr, xzr, [x19, #0xc0]
    28d4:      	mov	x9, #0x3ff0000000000000 ; =4607182418800017408
    28d8:      	stp	xzr, x9, [x19, #0xd0]
    28dc:      	stp	xzr, xzr, [x19, #0xe8]
    28e0:      	str	xzr, [x19, #0xe0]
    28e4:      	str	xzr, [x19, #0x100]
    28e8:      	strb	wzr, [x19, #0x108]
    28ec:      	str	x8, [x19, #0x110]
    28f0:      	add	x8, x19, #0x118
    28f4:      	stp	q0, q0, [x8]
    28f8:      	stp	q0, q0, [x8, #0x20]
    28fc:      	str	q0, [x8, #0x40]
    2900:      	stur	q0, [x8, #0x49]
    2904:      	adrp	x0, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2908:      	add	x0, x0, #0x0
    290c:      	adrp	x2, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics+0xcc>
    2910:      	add	x2, x2, #0x0
    2914:      	bl	0x2914 <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1+0x98>
    2918:      	mov	x0, x19
    291c:      	ldp	x29, x30, [sp, #0x10]
    2920:      	ldp	x20, x19, [sp], #0x20
    2924:      	b	0x2924 <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1+0xa8>
    2928:      	ldp	x29, x30, [sp, #0x10]
    292c:      	ldp	x20, x19, [sp], #0x20
    2930:      	ret

Disassembly of section __TEXT,__StaticInit:

0000000000002bd0 <ltmp3>:
    2bd0:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2bd4:      	ldrb	w9, [x8]
    2bd8:      	tbnz	w9, #0x0, 0x2be4 <ltmp3+0x14>
    2bdc:      	mov	w9, #0x1                ; =1
    2be0:      	strb	w9, [x8]
    2be4:      	ret

0000000000002be8 <___cxx_global_var_init.6>:
    2be8:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2bec:      	ldrb	w9, [x8]
    2bf0:      	tbnz	w9, #0x0, 0x2bfc <___cxx_global_var_init.6+0x14>
    2bf4:      	mov	w9, #0x1                ; =1
    2bf8:      	strb	w9, [x8]
    2bfc:      	ret

0000000000002c00 <___cxx_global_var_init.7>:
    2c00:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c04:      	ldrb	w9, [x8]
    2c08:      	tbnz	w9, #0x0, 0x2c14 <___cxx_global_var_init.7+0x14>
    2c0c:      	mov	w9, #0x1                ; =1
    2c10:      	strb	w9, [x8]
    2c14:      	ret

0000000000002c18 <___cxx_global_var_init.8>:
    2c18:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c1c:      	ldrb	w9, [x8]
    2c20:      	tbnz	w9, #0x0, 0x2c2c <___cxx_global_var_init.8+0x14>
    2c24:      	mov	w9, #0x1                ; =1
    2c28:      	strb	w9, [x8]
    2c2c:      	ret

0000000000002c30 <___cxx_global_var_init.9>:
    2c30:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c34:      	ldrb	w9, [x8]
    2c38:      	tbnz	w9, #0x0, 0x2c44 <___cxx_global_var_init.9+0x14>
    2c3c:      	mov	w9, #0x1                ; =1
    2c40:      	strb	w9, [x8]
    2c44:      	ret

0000000000002c48 <___cxx_global_var_init.10>:
    2c48:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c4c:      	ldrb	w9, [x8]
    2c50:      	tbnz	w9, #0x0, 0x2c5c <___cxx_global_var_init.10+0x14>
    2c54:      	mov	w9, #0x1                ; =1
    2c58:      	strb	w9, [x8]
    2c5c:      	ret

0000000000002c60 <___cxx_global_var_init.11>:
    2c60:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c64:      	ldrb	w9, [x8]
    2c68:      	tbnz	w9, #0x0, 0x2c74 <___cxx_global_var_init.11+0x14>
    2c6c:      	mov	w9, #0x1                ; =1
    2c70:      	strb	w9, [x8]
    2c74:      	ret

0000000000002c78 <___cxx_global_var_init.12>:
    2c78:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c7c:      	ldrb	w9, [x8]
    2c80:      	tbnz	w9, #0x0, 0x2c8c <___cxx_global_var_init.12+0x14>
    2c84:      	mov	w9, #0x1                ; =1
    2c88:      	strb	w9, [x8]
    2c8c:      	ret

0000000000002c90 <___cxx_global_var_init.13>:
    2c90:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c94:      	ldrb	w9, [x8]
    2c98:      	tbnz	w9, #0x0, 0x2ca4 <___cxx_global_var_init.13+0x14>
    2c9c:      	mov	w9, #0x1                ; =1
    2ca0:      	strb	w9, [x8]
    2ca4:      	ret
