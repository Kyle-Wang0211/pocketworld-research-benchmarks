
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
      68:      	mov	x8, #0x3ff0000000000000 ; =4607182418800017408
      6c:      	stp	xzr, x8, [x0, #0xc0]
      70:      	stp	xzr, xzr, [x0, #0xd8]
      74:      	str	xzr, [x0, #0xd0]
      78:      	str	xzr, [x0, #0xf0]
      7c:      	strb	wzr, [x0, #0xf8]
      80:      	ret

0000000000000084 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev>:
      84:      	stp	x20, x19, [sp, #-0x20]!
      88:      	stp	x29, x30, [sp, #0x10]
      8c:      	add	x29, sp, #0x10
      90:      	mov	x19, x0
      94:      	add	x0, x0, #0x68
      98:      	bl	0x98 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x14>
      9c:      	ldr	x20, [x19, #0x60]
      a0:      	cbz	x20, 0xd4 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x50>
      a4:      	add	x8, x20, #0x8
      a8:      	ldaxr	x9, [x8]
      ac:      	sub	x10, x9, #0x1
      b0:      	stlxr	w11, x10, [x8]
      b4:      	cbnz	w11, 0xa8 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x24>
      b8:      	cbnz	x9, 0xd4 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x50>
      bc:      	ldr	x8, [x20]
      c0:      	ldr	x8, [x8, #0x10]
      c4:      	mov	x0, x20
      c8:      	blr	x8
      cc:      	mov	x0, x20
      d0:      	bl	0xd0 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x4c>
      d4:      	add	x0, x19, #0x18
      d8:      	bl	0xd8 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x54>
      dc:      	ldr	x0, [x19, #0x10]
      e0:      	str	xzr, [x19, #0x10]
      e4:      	cbz	x0, 0xf4 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x70>
      e8:      	ldr	x8, [x0]
      ec:      	ldr	x8, [x8, #0x8]
      f0:      	blr	x8
      f4:      	ldr	x20, [x19, #0x8]
      f8:      	cbz	x20, 0x114 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x90>
      fc:      	add	x8, x20, #0x8
     100:      	ldaxr	x9, [x8]
     104:      	sub	x10, x9, #0x1
     108:      	stlxr	w11, x10, [x8]
     10c:      	cbnz	w11, 0x100 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0x7c>
     110:      	cbz	x9, 0x124 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0xa0>
     114:      	mov	x0, x19
     118:      	ldp	x29, x30, [sp, #0x10]
     11c:      	ldp	x20, x19, [sp], #0x20
     120:      	ret
     124:      	ldr	x8, [x20]
     128:      	ldr	x8, [x8, #0x10]
     12c:      	mov	x0, x20
     130:      	blr	x8
     134:      	mov	x0, x20
     138:      	bl	0x138 <__ZN12xrslam_0_5_013XRSLAMManagerD1Ev+0xb4>
     13c:      	mov	x0, x19
     140:      	ldp	x29, x30, [sp, #0x10]
     144:      	ldp	x20, x19, [sp], #0x20
     148:      	ret

000000000000014c <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv>:
     14c:      	ldr	x8, [x0, #0x10]
     150:      	cbz	x8, 0x16c <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv+0x20>
     154:      	ldr	x9, [x8, #0x8]
     158:      	cbz	x9, 0x174 <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv+0x28>
     15c:      	ldr	x0, [x9, #0xa0]
     160:      	ldr	x8, [x8, #0x10]
     164:      	cbnz	x8, 0x180 <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv+0x34>
     168:      	ret
     16c:      	mov	w0, #0x0                ; =0
     170:      	ret
     174:      	mov	x0, #0x0                ; =0
     178:      	ldr	x8, [x8, #0x10]
     17c:      	cbz	x8, 0x168 <__ZNK12xrslam_0_5_013XRSLAMManager19PendingWorkerFramesEv+0x1c>
     180:      	ldr	x8, [x8, #0x88]
     184:      	add	x0, x8, x0
     188:      	ret

000000000000018c <__ZN12xrslam_0_5_013XRSLAMManagerC2Ev>:
     18c:      	stp	xzr, xzr, [x0]
     190:      	mov	w8, #0xaba7             ; =43943
     194:      	movk	w8, #0x32aa, lsl #16
     198:      	stp	xzr, x8, [x0, #0x10]
     19c:      	movi.16b	v0, #0x0
     1a0:      	stp	q0, q0, [x0, #0x20]
     1a4:      	stp	q0, q0, [x0, #0x40]
     1a8:      	stp	xzr, x8, [x0, #0x60]
     1ac:      	stp	q0, q0, [x0, #0x70]
     1b0:      	str	q0, [x0, #0x90]
     1b4:      	str	xzr, [x0, #0xa0]
     1b8:      	stp	xzr, xzr, [x0, #0xb0]
     1bc:      	mov	x8, #0x3ff0000000000000 ; =4607182418800017408
     1c0:      	stp	xzr, x8, [x0, #0xc0]
     1c4:      	stp	xzr, xzr, [x0, #0xd8]
     1c8:      	str	xzr, [x0, #0xd0]
     1cc:      	str	xzr, [x0, #0xf0]
     1d0:      	strb	wzr, [x0, #0xf8]
     1d4:      	ret

00000000000001d8 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev>:
     1d8:      	stp	x20, x19, [sp, #-0x20]!
     1dc:      	stp	x29, x30, [sp, #0x10]
     1e0:      	add	x29, sp, #0x10
     1e4:      	ldr	x19, [x0, #0x8]
     1e8:      	cbz	x19, 0x204 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev+0x2c>
     1ec:      	add	x8, x19, #0x8
     1f0:      	ldaxr	x9, [x8]
     1f4:      	sub	x10, x9, #0x1
     1f8:      	stlxr	w11, x10, [x8]
     1fc:      	cbnz	w11, 0x1f0 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev+0x18>
     200:      	cbz	x9, 0x210 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev+0x38>
     204:      	ldp	x29, x30, [sp, #0x10]
     208:      	ldp	x20, x19, [sp], #0x20
     20c:      	ret
     210:      	ldr	x8, [x19]
     214:      	ldr	x8, [x8, #0x10]
     218:      	mov	x20, x0
     21c:      	mov	x0, x19
     220:      	blr	x8
     224:      	mov	x0, x19
     228:      	bl	0x228 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05ImageEED1B8ne200100Ev+0x50>
     22c:      	mov	x0, x20
     230:      	ldp	x29, x30, [sp, #0x10]
     234:      	ldp	x20, x19, [sp], #0x20
     238:      	ret

000000000000023c <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev>:
     23c:      	stp	x20, x19, [sp, #-0x20]!
     240:      	stp	x29, x30, [sp, #0x10]
     244:      	add	x29, sp, #0x10
     248:      	ldr	x19, [x0, #0x8]
     24c:      	cbz	x19, 0x268 <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev+0x2c>
     250:      	add	x8, x19, #0x8
     254:      	ldaxr	x9, [x8]
     258:      	sub	x10, x9, #0x1
     25c:      	stlxr	w11, x10, [x8]
     260:      	cbnz	w11, 0x254 <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev+0x18>
     264:      	cbz	x9, 0x274 <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev+0x38>
     268:      	ldp	x29, x30, [sp, #0x10]
     26c:      	ldp	x20, x19, [sp], #0x20
     270:      	ret
     274:      	ldr	x8, [x19]
     278:      	ldr	x8, [x8, #0x10]
     27c:      	mov	x20, x0
     280:      	mov	x0, x19
     284:      	blr	x8
     288:      	mov	x0, x19
     28c:      	bl	0x28c <__ZNSt3__110shared_ptrIN12xrslam_0_5_06ConfigEED1B8ne200100Ev+0x50>
     290:      	mov	x0, x20
     294:      	ldp	x29, x30, [sp, #0x10]
     298:      	ldp	x20, x19, [sp], #0x20
     29c:      	ret

00000000000002a0 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev>:
     2a0:      	stp	x20, x19, [sp, #-0x20]!
     2a4:      	stp	x29, x30, [sp, #0x10]
     2a8:      	add	x29, sp, #0x10
     2ac:      	mov	x19, x0
     2b0:      	add	x0, x0, #0x68
     2b4:      	bl	0x2b4 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x14>
     2b8:      	ldr	x20, [x19, #0x60]
     2bc:      	cbz	x20, 0x2f0 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x50>
     2c0:      	add	x8, x20, #0x8
     2c4:      	ldaxr	x9, [x8]
     2c8:      	sub	x10, x9, #0x1
     2cc:      	stlxr	w11, x10, [x8]
     2d0:      	cbnz	w11, 0x2c4 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x24>
     2d4:      	cbnz	x9, 0x2f0 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x50>
     2d8:      	ldr	x8, [x20]
     2dc:      	ldr	x8, [x8, #0x10]
     2e0:      	mov	x0, x20
     2e4:      	blr	x8
     2e8:      	mov	x0, x20
     2ec:      	bl	0x2ec <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x4c>
     2f0:      	add	x0, x19, #0x18
     2f4:      	bl	0x2f4 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x54>
     2f8:      	ldr	x0, [x19, #0x10]
     2fc:      	str	xzr, [x19, #0x10]
     300:      	cbz	x0, 0x310 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x70>
     304:      	ldr	x8, [x0]
     308:      	ldr	x8, [x8, #0x8]
     30c:      	blr	x8
     310:      	ldr	x20, [x19, #0x8]
     314:      	cbz	x20, 0x330 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x90>
     318:      	add	x8, x20, #0x8
     31c:      	ldaxr	x9, [x8]
     320:      	sub	x10, x9, #0x1
     324:      	stlxr	w11, x10, [x8]
     328:      	cbnz	w11, 0x31c <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0x7c>
     32c:      	cbz	x9, 0x340 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0xa0>
     330:      	mov	x0, x19
     334:      	ldp	x29, x30, [sp, #0x10]
     338:      	ldp	x20, x19, [sp], #0x20
     33c:      	ret
     340:      	ldr	x8, [x20]
     344:      	ldr	x8, [x8, #0x10]
     348:      	mov	x0, x20
     34c:      	blr	x8
     350:      	mov	x0, x20
     354:      	bl	0x354 <__ZN12xrslam_0_5_013XRSLAMManagerD2Ev+0xb4>
     358:      	mov	x0, x19
     35c:      	ldp	x29, x30, [sp, #0x10]
     360:      	ldp	x20, x19, [sp], #0x20
     364:      	ret

0000000000000368 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE>:
     368:      	sub	sp, sp, #0x50
     36c:      	stp	x22, x21, [sp, #0x20]
     370:      	stp	x20, x19, [sp, #0x30]
     374:      	stp	x29, x30, [sp, #0x40]
     378:      	add	x29, sp, #0x40
     37c:      	mov	x20, x1
     380:      	mov	x19, x0
     384:      	mov	w0, #0x1a0              ; =416
     388:      	bl	0x388 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x20>
     38c:      	mov	x21, x0
     390:      	ldp	x9, x8, [x20]
     394:      	stp	x9, x8, [sp, #0x10]
     398:      	cbz	x8, 0x3b0 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x48>
     39c:      	add	x8, x8, #0x8
     3a0:      	ldxr	x9, [x8]
     3a4:      	add	x9, x9, #0x1
     3a8:      	stxr	w10, x9, [x8]
     3ac:      	cbnz	w10, 0x3a0 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x38>
     3b0:      	add	x1, sp, #0x10
     3b4:      	mov	x0, x21
     3b8:      	bl	0x3b8 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x50>
     3bc:      	ldr	x22, [sp, #0x18]
     3c0:      	cbz	x22, 0x3f4 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x8c>
     3c4:      	add	x8, x22, #0x8
     3c8:      	ldaxr	x9, [x8]
     3cc:      	sub	x10, x9, #0x1
     3d0:      	stlxr	w11, x10, [x8]
     3d4:      	cbnz	w11, 0x3c8 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x60>
     3d8:      	cbnz	x9, 0x3f4 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x8c>
     3dc:      	ldr	x8, [x22]
     3e0:      	ldr	x8, [x8, #0x10]
     3e4:      	mov	x0, x22
     3e8:      	blr	x8
     3ec:      	mov	x0, x22
     3f0:      	bl	0x3f0 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x88>
     3f4:      	ldr	x0, [x19, #0x10]
     3f8:      	str	x21, [x19, #0x10]
     3fc:      	cbz	x0, 0x40c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xa4>
     400:      	ldr	x8, [x0]
     404:      	ldr	x8, [x8, #0x8]
     408:      	blr	x8
     40c:      	ldp	x9, x8, [x20]
     410:      	cbz	x8, 0x428 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xc0>
     414:      	add	x10, x8, #0x8
     418:      	ldxr	x11, [x10]
     41c:      	add	x11, x11, #0x1
     420:      	stxr	w12, x11, [x10]
     424:      	cbnz	w12, 0x418 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xb0>
     428:      	ldr	x20, [x19, #0x8]
     42c:      	stp	x9, x8, [x19]
     430:      	cbz	x20, 0x464 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xfc>
     434:      	add	x8, x20, #0x8
     438:      	ldaxr	x9, [x8]
     43c:      	sub	x10, x9, #0x1
     440:      	stlxr	w11, x10, [x8]
     444:      	cbnz	w11, 0x438 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xd0>
     448:      	cbnz	x9, 0x464 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xfc>
     44c:      	ldr	x8, [x20]
     450:      	ldr	x8, [x8, #0x10]
     454:      	mov	x0, x20
     458:      	blr	x8
     45c:      	mov	x0, x20
     460:      	bl	0x460 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0xf8>
     464:      	adrp	x8, 0x0 <ltmp0>
     468:      	add	x8, x8, #0x0
     46c:      	str	x8, [sp]
     470:      	adrp	x1, 0x0 <ltmp0>
     474:      	add	x1, x1, #0x0
     478:      	mov	w0, #0x0                ; =0
     47c:      	bl	0x47c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x114>
     480:      	ldr	x0, [x19]
     484:      	bl	0x484 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x11c>
     488:      	adrp	x0, 0x0 <ltmp0>
     48c:      	ldr	x0, [x0]
     490:      	adrp	x1, 0x0 <ltmp0>
     494:      	add	x1, x1, #0x0
     498:      	mov	w2, #0x20               ; =32
     49c:      	bl	0x49c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x134>
     4a0:      	adrp	x1, 0x0 <ltmp0>
     4a4:      	add	x1, x1, #0x0
     4a8:      	mov	w2, #0x5                ; =5
     4ac:      	bl	0x4ac <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x144>
     4b0:      	adrp	x1, 0x0 <ltmp0>
     4b4:      	add	x1, x1, #0x0
     4b8:      	mov	w2, #0x18               ; =24
     4bc:      	bl	0x4bc <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x154>
     4c0:      	mov	x19, x0
     4c4:      	ldr	x8, [x0]
     4c8:      	ldur	x9, [x8, #-0x18]
     4cc:      	add	x8, sp, #0x10
     4d0:      	add	x0, x0, x9
     4d4:      	bl	0x4d4 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x16c>
     4d8:      	adrp	x1, 0x0 <ltmp0>
     4dc:      	ldr	x1, [x1]
     4e0:      	add	x0, sp, #0x10
     4e4:      	bl	0x4e4 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x17c>
     4e8:      	ldr	x8, [x0]
     4ec:      	ldr	x8, [x8, #0x38]
     4f0:      	mov	w1, #0xa                ; =10
     4f4:      	blr	x8
     4f8:      	mov	x20, x0
     4fc:      	add	x0, sp, #0x10
     500:      	bl	0x500 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x198>
     504:      	mov	x0, x19
     508:      	mov	x1, x20
     50c:      	bl	0x50c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1a4>
     510:      	mov	x0, x19
     514:      	bl	0x514 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1ac>
     518:      	ldp	x29, x30, [sp, #0x40]
     51c:      	ldp	x20, x19, [sp, #0x30]
     520:      	ldp	x22, x21, [sp, #0x20]
     524:      	add	sp, sp, #0x50
     528:      	ret
     52c:      	mov	x19, x0
     530:      	add	x0, sp, #0x10
     534:      	bl	0x534 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1cc>
     538:      	mov	x0, x21
     53c:      	bl	0x53c <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1d4>
     540:      	mov	x0, x19
     544:      	bl	0x544 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1dc>
     548:      	mov	x19, x0
     54c:      	add	x0, sp, #0x10
     550:      	bl	0x550 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1e8>
     554:      	mov	x0, x19
     558:      	bl	0x558 <__ZN12xrslam_0_5_013XRSLAMManager4InitENSt3__110shared_ptrINS_6ConfigEEE+0x1f0>

000000000000055c <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_>:
     55c:      	sub	sp, sp, #0x30
     560:      	stp	x20, x19, [sp, #0x10]
     564:      	stp	x29, x30, [sp, #0x20]
     568:      	add	x29, sp, #0x20
     56c:      	mov	x19, x0
     570:      	ldr	x8, [x0]
     574:      	ldur	x9, [x8, #-0x18]
     578:      	add	x8, sp, #0x8
     57c:      	add	x0, x0, x9
     580:      	bl	0x580 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x24>
     584:      	adrp	x1, 0x0 <ltmp0>
     588:      	ldr	x1, [x1]
     58c:      	add	x0, sp, #0x8
     590:      	bl	0x590 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x34>
     594:      	ldr	x8, [x0]
     598:      	ldr	x8, [x8, #0x38]
     59c:      	mov	w1, #0xa                ; =10
     5a0:      	blr	x8
     5a4:      	mov	x20, x0
     5a8:      	add	x0, sp, #0x8
     5ac:      	bl	0x5ac <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x50>
     5b0:      	mov	x0, x19
     5b4:      	mov	x1, x20
     5b8:      	bl	0x5b8 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x5c>
     5bc:      	mov	x0, x19
     5c0:      	bl	0x5c0 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x64>
     5c4:      	mov	x0, x19
     5c8:      	ldp	x29, x30, [sp, #0x20]
     5cc:      	ldp	x20, x19, [sp, #0x10]
     5d0:      	add	sp, sp, #0x30
     5d4:      	ret
     5d8:      	mov	x19, x0
     5dc:      	add	x0, sp, #0x8
     5e0:      	bl	0x5e0 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x84>
     5e4:      	mov	x0, x19
     5e8:      	bl	0x5e8 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_+0x8c>

00000000000005ec <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv>:
     5ec:      	sub	sp, sp, #0x30
     5f0:      	stp	x20, x19, [sp, #0x10]
     5f4:      	stp	x29, x30, [sp, #0x20]
     5f8:      	add	x29, sp, #0x20
     5fc:      	mov	x19, x0
     600:      	add	x0, x0, #0x18
     604:      	bl	0x604 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x18>
     608:      	ldr	x20, [x19, #0x60]
     60c:      	stp	xzr, xzr, [x19, #0x58]
     610:      	cbz	x20, 0x644 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x58>
     614:      	add	x8, x20, #0x8
     618:      	ldaxr	x9, [x8]
     61c:      	sub	x10, x9, #0x1
     620:      	stlxr	w11, x10, [x8]
     624:      	cbnz	w11, 0x618 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x2c>
     628:      	cbnz	x9, 0x644 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x58>
     62c:      	ldr	x8, [x20]
     630:      	ldr	x8, [x8, #0x10]
     634:      	mov	x0, x20
     638:      	blr	x8
     63c:      	mov	x0, x20
     640:      	bl	0x640 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x54>
     644:      	add	x0, x19, #0x18
     648:      	bl	0x648 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x5c>
     64c:      	ldr	x0, [x19, #0x10]
     650:      	str	xzr, [x19, #0x10]
     654:      	cbz	x0, 0x664 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x78>
     658:      	ldr	x8, [x0]
     65c:      	ldr	x8, [x8, #0x8]
     660:      	blr	x8
     664:      	ldr	x20, [x19, #0x8]
     668:      	stp	xzr, xzr, [x19]
     66c:      	cbz	x20, 0x6a0 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xb4>
     670:      	add	x8, x20, #0x8
     674:      	ldaxr	x9, [x8]
     678:      	sub	x10, x9, #0x1
     67c:      	stlxr	w11, x10, [x8]
     680:      	cbnz	w11, 0x674 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x88>
     684:      	cbnz	x9, 0x6a0 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xb4>
     688:      	ldr	x8, [x20]
     68c:      	ldr	x8, [x8, #0x10]
     690:      	mov	x0, x20
     694:      	blr	x8
     698:      	mov	x0, x20
     69c:      	bl	0x69c <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xb0>
     6a0:      	adrp	x0, 0x0 <ltmp0>
     6a4:      	ldr	x0, [x0]
     6a8:      	adrp	x1, 0x0 <ltmp0>
     6ac:      	add	x1, x1, #0x0
     6b0:      	mov	w2, #0x21               ; =33
     6b4:      	bl	0x6b4 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xc8>
     6b8:      	adrp	x1, 0x0 <ltmp0>
     6bc:      	add	x1, x1, #0x0
     6c0:      	mov	w2, #0x5                ; =5
     6c4:      	bl	0x6c4 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xd8>
     6c8:      	adrp	x1, 0x0 <ltmp0>
     6cc:      	add	x1, x1, #0x0
     6d0:      	mov	w2, #0x18               ; =24
     6d4:      	bl	0x6d4 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0xe8>
     6d8:      	mov	x19, x0
     6dc:      	ldr	x8, [x0]
     6e0:      	ldur	x9, [x8, #-0x18]
     6e4:      	add	x8, sp, #0x8
     6e8:      	add	x0, x0, x9
     6ec:      	bl	0x6ec <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x100>
     6f0:      	adrp	x1, 0x0 <ltmp0>
     6f4:      	ldr	x1, [x1]
     6f8:      	add	x0, sp, #0x8
     6fc:      	bl	0x6fc <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x110>
     700:      	ldr	x8, [x0]
     704:      	ldr	x8, [x8, #0x38]
     708:      	mov	w1, #0xa                ; =10
     70c:      	blr	x8
     710:      	mov	x20, x0
     714:      	add	x0, sp, #0x8
     718:      	bl	0x718 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x12c>
     71c:      	mov	x0, x19
     720:      	mov	x1, x20
     724:      	bl	0x724 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x138>
     728:      	mov	x0, x19
     72c:      	bl	0x72c <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x140>
     730:      	ldp	x29, x30, [sp, #0x20]
     734:      	ldp	x20, x19, [sp, #0x10]
     738:      	add	sp, sp, #0x30
     73c:      	ret
     740:      	mov	x19, x0
     744:      	add	x0, sp, #0x8
     748:      	bl	0x748 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x15c>
     74c:      	mov	x0, x19
     750:      	bl	0x750 <__ZN12xrslam_0_5_013XRSLAMManager7DestroyEv+0x164>

0000000000000754 <__ZN12xrslam_0_5_013XRSLAMManager12CheckLicenseEPKcS2_>:
     754:      	mov	w0, #0x1                ; =1
     758:      	ret

000000000000075c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage>:
     75c:      	sub	sp, sp, #0x150
     760:      	stp	d9, d8, [sp, #0xf0]
     764:      	stp	x26, x25, [sp, #0x100]
     768:      	stp	x24, x23, [sp, #0x110]
     76c:      	stp	x22, x21, [sp, #0x120]
     770:      	stp	x20, x19, [sp, #0x130]
     774:      	stp	x29, x30, [sp, #0x140]
     778:      	add	x29, sp, #0x140
     77c:      	ldr	w8, [x1, #0x14]
     780:      	cbz	w8, 0x7a4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x48>
     784:      	ldp	x29, x30, [sp, #0x140]
     788:      	ldp	x20, x19, [sp, #0x130]
     78c:      	ldp	x22, x21, [sp, #0x120]
     790:      	ldp	x24, x23, [sp, #0x110]
     794:      	ldp	x26, x25, [sp, #0x100]
     798:      	ldp	d9, d8, [sp, #0xf0]
     79c:      	add	sp, sp, #0x150
     7a0:      	ret
     7a4:      	mov	x19, x0
     7a8:      	mov	x20, x1
     7ac:      	sub	x8, x29, #0x78
     7b0:      	bl	0x7b0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x54>
     7b4:      	ldr	x0, [x19]
     7b8:      	ldr	x8, [x0]
     7bc:      	ldr	x9, [x8, #0x10]
     7c0:      	add	x8, sp, #0x60
     7c4:      	blr	x9
     7c8:      	ldr	d8, [sp, #0x60]
     7cc:      	ldr	x0, [x19]
     7d0:      	ldr	x8, [x0]
     7d4:      	ldr	x9, [x8, #0x10]
     7d8:      	add	x21, sp, #0x60
     7dc:      	add	x8, sp, #0x60
     7e0:      	blr	x9
     7e4:      	fcvtzs	w8, d8
     7e8:      	ldr	d0, [sp, #0x68]
     7ec:      	fcvtzs	w9, d0
     7f0:      	mov	x11, x20
     7f4:      	ldr	d0, [x20, #0x8]
     7f8:      	ldur	x10, [x29, #-0x78]
     7fc:      	str	d0, [x10, #0x8]
     800:      	mov	w10, #0x42ff0000        ; =1124007936
     804:      	str	w10, [sp, #0x60]
     808:      	orr	x20, x21, #0x8
     80c:      	movi.16b	v0, #0x0
     810:      	stur	q0, [sp, #0x64]
     814:      	stur	q0, [sp, #0x74]
     818:      	stur	q0, [sp, #0x84]
     81c:      	str	q0, [sp, #0x90]
     820:      	add	x22, x21, #0x50
     824:      	stp	x20, x22, [sp, #0xa0]
     828:      	stp	xzr, xzr, [sp, #0xb0]
     82c:      	ldr	w10, [x11, #0x18]
     830:      	cmp	w10, #0x4
     834:      	b.eq	0xa74 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x318>
     838:      	cmp	w10, #0x3
     83c:      	b.eq	0x95c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x200>
     840:      	cmp	w10, #0x1
     844:      	b.ne	0x11e8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa8c>
     848:      	ldr	x10, [x11]
     84c:      	ldrsw	x11, [x11, #0x10]
     850:      	mov	x24, sp
     854:      	adrp	x12, 0x0 <ltmp0>
     858:      	ldr	d0, [x12]
     85c:      	str	d0, [sp]
     860:      	orr	x23, x24, #0x8
     864:      	stp	w9, w8, [sp, #0x8]
     868:      	stp	x10, x10, [sp, #0x10]
     86c:      	movi.16b	v0, #0x0
     870:      	stp	q0, q0, [sp, #0x20]
     874:      	add	x21, x24, #0x50
     878:      	stp	x23, x21, [sp, #0x40]
     87c:      	smull	x12, w9, w8
     880:      	stp	xzr, xzr, [sp, #0x50]
     884:      	cbz	x12, 0x88c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x130>
     888:      	cbz	x10, 0x1210 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xab4>
     88c:      	sxtw	x9, w9
     890:      	sxtw	x8, w8
     894:      	cmp	w11, #0x0
     898:      	csel	x11, x8, x11, eq
     89c:      	mov	w12, #0x1               ; =1
     8a0:      	stp	x11, x12, [sp, #0x50]
     8a4:      	madd	x9, x11, x9, x10
     8a8:      	sub	x10, x9, x11
     8ac:      	add	x8, x10, x8
     8b0:      	stp	x8, x9, [sp, #0x20]
     8b4:      	mov	x0, sp
     8b8:      	bl	0x8b8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x15c>
     8bc:      	ldr	x8, [sp, #0x98]
     8c0:      	cbz	x8, 0x8e4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x188>
     8c4:      	add	x8, x8, #0x14
     8c8:      	ldaxr	w9, [x8]
     8cc:      	subs	w9, w9, #0x1
     8d0:      	stlxr	w10, w9, [x8]
     8d4:      	cbnz	w10, 0x8c8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x16c>
     8d8:      	b.ne	0x8e4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x188>
     8dc:      	add	x0, sp, #0x60
     8e0:      	bl	0x8e0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x184>
     8e4:      	ldr	w8, [sp, #0x64]
     8e8:      	cmp	w8, #0x1
     8ec:      	b.lt	0x90c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x1b0>
     8f0:      	mov	x8, #0x0                ; =0
     8f4:      	ldr	x9, [sp, #0xa0]
     8f8:      	str	wzr, [x9, x8, lsl #2]
     8fc:      	add	x8, x8, #0x1
     900:      	ldrsw	x10, [sp, #0x64]
     904:      	cmp	x8, x10
     908:      	b.lt	0x8f8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x19c>
     90c:      	ldp	q0, q1, [sp]
     910:      	stp	q0, q1, [sp, #0x60]
     914:      	ldp	q1, q2, [sp, #0x20]
     918:      	stp	q1, q2, [sp, #0x80]
     91c:      	ldr	x0, [sp, #0xa8]
     920:      	cmp	x0, x22
     924:      	b.eq	0xc90 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x534>
     928:      	bl	0x928 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x1cc>
     92c:      	stp	x20, x22, [sp, #0xa0]
     930:      	mov	x0, x22
     934:      	ldr	w9, [sp, #0x4]
     938:      	orr	x8, x24, #0x4
     93c:      	ldr	x10, [sp, #0x48]
     940:      	cmp	w9, #0x2
     944:      	b.gt	0xca4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x548>
     948:      	ldr	x9, [x10]
     94c:      	str	x9, [x0]
     950:      	ldr	x9, [x10, #0x8]
     954:      	str	x9, [x0, #0x8]
     958:      	b	0xcb0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x554>
     95c:      	ldr	x10, [x11]
     960:      	ldrsw	x11, [x11, #0x10]
     964:      	mov	x24, sp
     968:      	adrp	x12, 0x0 <ltmp0>
     96c:      	ldr	d0, [x12]
     970:      	str	d0, [sp]
     974:      	orr	x23, x24, #0x8
     978:      	stp	w9, w8, [sp, #0x8]
     97c:      	stp	x10, x10, [sp, #0x10]
     980:      	movi.16b	v0, #0x0
     984:      	stp	q0, q0, [sp, #0x20]
     988:      	add	x21, x24, #0x50
     98c:      	stp	x23, x21, [sp, #0x40]
     990:      	smull	x12, w9, w8
     994:      	stp	xzr, xzr, [sp, #0x50]
     998:      	cbz	x12, 0x9a0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x244>
     99c:      	cbz	x10, 0x1244 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xae8>
     9a0:      	sxtw	x9, w9
     9a4:      	sxtw	x8, w8
     9a8:      	add	x8, x8, x8, lsl #1
     9ac:      	cmp	w11, #0x0
     9b0:      	csel	x11, x8, x11, eq
     9b4:      	mov	w12, #0x3               ; =3
     9b8:      	stp	x11, x12, [sp, #0x50]
     9bc:      	madd	x9, x11, x9, x10
     9c0:      	sub	x10, x9, x11
     9c4:      	add	x8, x10, x8
     9c8:      	stp	x8, x9, [sp, #0x20]
     9cc:      	mov	x0, sp
     9d0:      	bl	0x9d0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x274>
     9d4:      	ldr	x8, [sp, #0x98]
     9d8:      	cbz	x8, 0x9fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x2a0>
     9dc:      	add	x8, x8, #0x14
     9e0:      	ldaxr	w9, [x8]
     9e4:      	subs	w9, w9, #0x1
     9e8:      	stlxr	w10, w9, [x8]
     9ec:      	cbnz	w10, 0x9e0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x284>
     9f0:      	b.ne	0x9fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x2a0>
     9f4:      	add	x0, sp, #0x60
     9f8:      	bl	0x9f8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x29c>
     9fc:      	ldr	w8, [sp, #0x64]
     a00:      	cmp	w8, #0x1
     a04:      	b.lt	0xa24 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x2c8>
     a08:      	mov	x8, #0x0                ; =0
     a0c:      	ldr	x9, [sp, #0xa0]
     a10:      	str	wzr, [x9, x8, lsl #2]
     a14:      	add	x8, x8, #0x1
     a18:      	ldrsw	x10, [sp, #0x64]
     a1c:      	cmp	x8, x10
     a20:      	b.lt	0xa10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x2b4>
     a24:      	ldp	q0, q1, [sp]
     a28:      	stp	q0, q1, [sp, #0x60]
     a2c:      	ldp	q1, q2, [sp, #0x20]
     a30:      	stp	q1, q2, [sp, #0x80]
     a34:      	ldr	x0, [sp, #0xa8]
     a38:      	cmp	x0, x22
     a3c:      	b.eq	0xb88 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x42c>
     a40:      	bl	0xa40 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x2e4>
     a44:      	stp	x20, x22, [sp, #0xa0]
     a48:      	mov	x0, x22
     a4c:      	ldr	w9, [sp, #0x4]
     a50:      	orr	x8, x24, #0x4
     a54:      	ldr	x10, [sp, #0x48]
     a58:      	cmp	w9, #0x2
     a5c:      	b.gt	0xb9c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x440>
     a60:      	ldr	x9, [x10]
     a64:      	str	x9, [x0]
     a68:      	ldr	x9, [x10, #0x8]
     a6c:      	str	x9, [x0, #0x8]
     a70:      	b	0xba8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x44c>
     a74:      	ldr	x10, [x11]
     a78:      	ldrsw	x11, [x11, #0x10]
     a7c:      	mov	x24, sp
     a80:      	adrp	x12, 0x0 <ltmp0>
     a84:      	ldr	d1, [x12]
     a88:      	str	d1, [sp]
     a8c:      	orr	x23, x24, #0x8
     a90:      	stp	w9, w8, [sp, #0x8]
     a94:      	stp	x10, x10, [sp, #0x10]
     a98:      	stp	q0, q0, [sp, #0x20]
     a9c:      	add	x21, x24, #0x50
     aa0:      	stp	x23, x21, [sp, #0x40]
     aa4:      	smull	x12, w9, w8
     aa8:      	stp	xzr, xzr, [sp, #0x50]
     aac:      	cbz	x12, 0xab4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x358>
     ab0:      	cbz	x10, 0x1278 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb1c>
     ab4:      	sxtw	x9, w9
     ab8:      	sxtw	x8, w8
     abc:      	lsl	x8, x8, #2
     ac0:      	cmp	w11, #0x0
     ac4:      	csel	x11, x8, x11, eq
     ac8:      	mov	w12, #0x4               ; =4
     acc:      	stp	x11, x12, [sp, #0x50]
     ad0:      	madd	x9, x11, x9, x10
     ad4:      	sub	x10, x9, x11
     ad8:      	add	x8, x10, x8
     adc:      	stp	x8, x9, [sp, #0x20]
     ae0:      	mov	x0, sp
     ae4:      	bl	0xae4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x388>
     ae8:      	ldr	x8, [sp, #0x98]
     aec:      	cbz	x8, 0xb10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3b4>
     af0:      	add	x8, x8, #0x14
     af4:      	ldaxr	w9, [x8]
     af8:      	subs	w9, w9, #0x1
     afc:      	stlxr	w10, w9, [x8]
     b00:      	cbnz	w10, 0xaf4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x398>
     b04:      	b.ne	0xb10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3b4>
     b08:      	add	x0, sp, #0x60
     b0c:      	bl	0xb0c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3b0>
     b10:      	ldr	w8, [sp, #0x64]
     b14:      	cmp	w8, #0x1
     b18:      	b.lt	0xb38 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3dc>
     b1c:      	mov	x8, #0x0                ; =0
     b20:      	ldr	x9, [sp, #0xa0]
     b24:      	str	wzr, [x9, x8, lsl #2]
     b28:      	add	x8, x8, #0x1
     b2c:      	ldrsw	x10, [sp, #0x64]
     b30:      	cmp	x8, x10
     b34:      	b.lt	0xb24 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3c8>
     b38:      	ldp	q0, q1, [sp]
     b3c:      	stp	q0, q1, [sp, #0x60]
     b40:      	ldp	q1, q2, [sp, #0x20]
     b44:      	stp	q1, q2, [sp, #0x80]
     b48:      	ldr	x0, [sp, #0xa8]
     b4c:      	cmp	x0, x22
     b50:      	b.eq	0xc0c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4b0>
     b54:      	bl	0xb54 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3f8>
     b58:      	stp	x20, x22, [sp, #0xa0]
     b5c:      	mov	x0, x22
     b60:      	ldr	w9, [sp, #0x4]
     b64:      	orr	x8, x24, #0x4
     b68:      	ldr	x10, [sp, #0x48]
     b6c:      	cmp	w9, #0x2
     b70:      	b.gt	0xc20 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4c4>
     b74:      	ldr	x9, [x10]
     b78:      	str	x9, [x0]
     b7c:      	ldr	x9, [x10, #0x8]
     b80:      	str	x9, [x0, #0x8]
     b84:      	b	0xc2c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4d0>
     b88:      	mov.s	w9, v0[1]
     b8c:      	orr	x8, x24, #0x4
     b90:      	ldr	x10, [sp, #0x48]
     b94:      	cmp	w9, #0x2
     b98:      	b.le	0xa60 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x304>
     b9c:      	ldr	x9, [sp, #0x40]
     ba0:      	stp	x9, x10, [sp, #0xa0]
     ba4:      	stp	x23, x21, [sp, #0x40]
     ba8:      	mov	w9, #0x42ff0000         ; =1124007936
     bac:      	str	w9, [sp]
     bb0:      	movi.16b	v0, #0x0
     bb4:      	stp	q0, q0, [x8]
     bb8:      	str	q0, [x8, #0x20]
     bbc:      	stur	q0, [x8, #0x2c]
     bc0:      	ldr	x0, [sp, #0x48]
     bc4:      	cmp	x0, x21
     bc8:      	b.eq	0xbd0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x474>
     bcc:      	bl	0xbcc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x470>
     bd0:      	mov	w8, #0x1010000          ; =16842752
     bd4:      	str	w8, [sp]
     bd8:      	add	x8, sp, #0x60
     bdc:      	stp	x8, xzr, [sp, #0x8]
     be0:      	ldur	x8, [x29, #-0x78]
     be4:      	add	x8, x8, #0x10
     be8:      	mov	w9, #0x2010000          ; =33619968
     bec:      	stur	w9, [x29, #-0x68]
     bf0:      	stp	x8, xzr, [x29, #-0x60]
     bf4:      	mov	x0, sp
     bf8:      	sub	x1, x29, #0x68
     bfc:      	mov	w2, #0x6                ; =6
     c00:      	mov	w3, #0x0                ; =0
     c04:      	bl	0xc04 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4a8>
     c08:      	b	0xe94 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x738>
     c0c:      	mov.s	w9, v0[1]
     c10:      	orr	x8, x24, #0x4
     c14:      	ldr	x10, [sp, #0x48]
     c18:      	cmp	w9, #0x2
     c1c:      	b.le	0xb74 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x418>
     c20:      	ldr	x9, [sp, #0x40]
     c24:      	stp	x9, x10, [sp, #0xa0]
     c28:      	stp	x23, x21, [sp, #0x40]
     c2c:      	mov	w9, #0x42ff0000         ; =1124007936
     c30:      	str	w9, [sp]
     c34:      	movi.16b	v0, #0x0
     c38:      	stp	q0, q0, [x8]
     c3c:      	str	q0, [x8, #0x20]
     c40:      	stur	q0, [x8, #0x2c]
     c44:      	ldr	x0, [sp, #0x48]
     c48:      	cmp	x0, x21
     c4c:      	b.eq	0xc54 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4f8>
     c50:      	bl	0xc50 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4f4>
     c54:      	mov	w8, #0x1010000          ; =16842752
     c58:      	str	w8, [sp]
     c5c:      	add	x8, sp, #0x60
     c60:      	stp	x8, xzr, [sp, #0x8]
     c64:      	ldur	x8, [x29, #-0x78]
     c68:      	add	x8, x8, #0x10
     c6c:      	mov	w9, #0x2010000          ; =33619968
     c70:      	stur	w9, [x29, #-0x68]
     c74:      	stp	x8, xzr, [x29, #-0x60]
     c78:      	mov	x0, sp
     c7c:      	sub	x1, x29, #0x68
     c80:      	mov	w2, #0xa                ; =10
     c84:      	mov	w3, #0x0                ; =0
     c88:      	bl	0xc88 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x52c>
     c8c:      	b	0xe94 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x738>
     c90:      	mov.s	w9, v0[1]
     c94:      	orr	x8, x24, #0x4
     c98:      	ldr	x10, [sp, #0x48]
     c9c:      	cmp	w9, #0x2
     ca0:      	b.le	0x948 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x1ec>
     ca4:      	ldr	x9, [sp, #0x40]
     ca8:      	stp	x9, x10, [sp, #0xa0]
     cac:      	stp	x23, x21, [sp, #0x40]
     cb0:      	mov	w20, #0x42ff0000        ; =1124007936
     cb4:      	str	w20, [sp]
     cb8:      	movi.16b	v0, #0x0
     cbc:      	stp	q0, q0, [x8]
     cc0:      	str	q0, [x8, #0x20]
     cc4:      	stur	q0, [x8, #0x2c]
     cc8:      	ldr	x0, [sp, #0x48]
     ccc:      	cmp	x0, x21
     cd0:      	b.eq	0xcd8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x57c>
     cd4:      	bl	0xcd4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x578>
     cd8:      	str	w20, [sp]
     cdc:      	mov	x23, sp
     ce0:      	orr	x21, x23, #0x8
     ce4:      	movi.16b	v0, #0x0
     ce8:      	stur	q0, [sp, #0x4]
     cec:      	stur	q0, [sp, #0x14]
     cf0:      	stur	q0, [sp, #0x24]
     cf4:      	str	q0, [sp, #0x30]
     cf8:      	add	x20, x23, #0x50
     cfc:      	stp	x21, x20, [sp, #0x40]
     d00:      	stp	xzr, xzr, [sp, #0x50]
     d04:      	mov	w8, #0x2010000          ; =33619968
     d08:      	stur	w8, [x29, #-0x68]
     d0c:      	stp	x23, xzr, [x29, #-0x60]
     d10:      	add	x0, sp, #0x60
     d14:      	sub	x1, x29, #0x68
     d18:      	bl	0xd18 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5bc>
     d1c:      	ldur	x24, [x29, #-0x78]
     d20:      	add	x0, x24, #0x10
     d24:      	cmp	x0, x23
     d28:      	b.eq	0xdec <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x690>
     d2c:      	ldr	x8, [x24, #0x48]
     d30:      	cbz	x8, 0xd50 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5f4>
     d34:      	add	x8, x8, #0x14
     d38:      	ldaxr	w9, [x8]
     d3c:      	subs	w9, w9, #0x1
     d40:      	stlxr	w10, w9, [x8]
     d44:      	cbnz	w10, 0xd38 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5dc>
     d48:      	b.ne	0xd50 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5f4>
     d4c:      	bl	0xd4c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5f0>
     d50:      	str	xzr, [x24, #0x48]
     d54:      	movi.16b	v0, #0x0
     d58:      	stp	q0, q0, [x24, #0x20]
     d5c:      	ldr	w8, [x24, #0x14]
     d60:      	cmp	w8, #0x1
     d64:      	b.lt	0xd84 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x628>
     d68:      	mov	x8, #0x0                ; =0
     d6c:      	ldr	x9, [x24, #0x50]
     d70:      	str	wzr, [x9, x8, lsl #2]
     d74:      	add	x8, x8, #0x1
     d78:      	ldrsw	x10, [x24, #0x14]
     d7c:      	cmp	x8, x10
     d80:      	b.lt	0xd70 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x614>
     d84:      	ldr	q0, [sp]
     d88:      	str	q0, [x24, #0x10]
     d8c:      	ldr	q1, [sp, #0x10]
     d90:      	str	q1, [x24, #0x20]
     d94:      	ldr	q1, [sp, #0x20]
     d98:      	str	q1, [x24, #0x30]
     d9c:      	ldr	q1, [sp, #0x30]
     da0:      	str	q1, [x24, #0x40]
     da4:      	ldr	x0, [x24, #0x58]
     da8:      	add	x25, x24, #0x60
     dac:      	cmp	x0, x25
     db0:      	b.eq	0xe4c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6f0>
     db4:      	bl	0xdb4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x658>
     db8:      	add	x8, x24, #0x18
     dbc:      	stp	x8, x25, [x24, #0x50]
     dc0:      	ldr	w9, [sp, #0x4]
     dc4:      	mov	x0, x25
     dc8:      	orr	x8, x23, #0x4
     dcc:      	ldr	x10, [sp, #0x48]
     dd0:      	cmp	w9, #0x2
     dd4:      	b.gt	0xe60 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x704>
     dd8:      	ldr	x9, [x10]
     ddc:      	str	x9, [x0]
     de0:      	ldr	x9, [x10, #0x8]
     de4:      	str	x9, [x0, #0x8]
     de8:      	b	0xe6c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x710>
     dec:      	ldr	x8, [sp, #0x38]
     df0:      	cbz	x8, 0xe14 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6b8>
     df4:      	add	x8, x8, #0x14
     df8:      	ldaxr	w9, [x8]
     dfc:      	subs	w9, w9, #0x1
     e00:      	stlxr	w10, w9, [x8]
     e04:      	cbnz	w10, 0xdf8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x69c>
     e08:      	b.ne	0xe14 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6b8>
     e0c:      	mov	x0, sp
     e10:      	bl	0xe10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6b4>
     e14:      	ldr	w8, [sp, #0x4]
     e18:      	str	xzr, [sp, #0x38]
     e1c:      	movi.16b	v0, #0x0
     e20:      	stp	q0, q0, [sp, #0x10]
     e24:      	cmp	w8, #0x1
     e28:      	b.lt	0xe84 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x728>
     e2c:      	mov	x8, #0x0                ; =0
     e30:      	ldr	x9, [sp, #0x40]
     e34:      	str	wzr, [x9, x8, lsl #2]
     e38:      	add	x8, x8, #0x1
     e3c:      	ldrsw	x10, [sp, #0x4]
     e40:      	cmp	x8, x10
     e44:      	b.lt	0xe34 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6d8>
     e48:      	b	0xe84 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x728>
     e4c:      	mov.s	w9, v0[1]
     e50:      	orr	x8, x23, #0x4
     e54:      	ldr	x10, [sp, #0x48]
     e58:      	cmp	w9, #0x2
     e5c:      	b.le	0xdd8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x67c>
     e60:      	ldr	x9, [sp, #0x40]
     e64:      	stp	x9, x10, [x24, #0x50]
     e68:      	stp	x21, x20, [sp, #0x40]
     e6c:      	mov	w9, #0x42ff0000         ; =1124007936
     e70:      	str	w9, [sp]
     e74:      	movi.16b	v0, #0x0
     e78:      	stp	q0, q0, [x8]
     e7c:      	str	q0, [x8, #0x20]
     e80:      	stur	q0, [x8, #0x2c]
     e84:      	ldr	x0, [sp, #0x48]
     e88:      	cmp	x0, x20
     e8c:      	b.eq	0xe94 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x738>
     e90:      	bl	0xe90 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x734>
     e94:      	mov	w8, #0x42ff0000         ; =1124007936
     e98:      	str	w8, [sp]
     e9c:      	mov	x23, sp
     ea0:      	movi.16b	v0, #0x0
     ea4:      	stur	q0, [sp, #0x4]
     ea8:      	orr	x21, x23, #0x8
     eac:      	stur	q0, [sp, #0x14]
     eb0:      	stur	q0, [sp, #0x24]
     eb4:      	str	q0, [sp, #0x30]
     eb8:      	add	x20, x23, #0x50
     ebc:      	stp	x21, x20, [sp, #0x40]
     ec0:      	stp	xzr, xzr, [sp, #0x50]
     ec4:      	mov	w8, #0x2010000          ; =33619968
     ec8:      	stur	w8, [x29, #-0x68]
     ecc:      	stp	x23, xzr, [x29, #-0x60]
     ed0:      	add	x0, sp, #0x60
     ed4:      	sub	x1, x29, #0x68
     ed8:      	bl	0xed8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x77c>
     edc:      	ldur	x24, [x29, #-0x78]
     ee0:      	add	x0, x24, #0x70
     ee4:      	cmp	x0, x23
     ee8:      	b.eq	0xf9c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x840>
     eec:      	ldr	x8, [x24, #0xa8]
     ef0:      	cbz	x8, 0xf10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b4>
     ef4:      	add	x8, x8, #0x14
     ef8:      	ldaxr	w9, [x8]
     efc:      	subs	w9, w9, #0x1
     f00:      	stlxr	w10, w9, [x8]
     f04:      	cbnz	w10, 0xef8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x79c>
     f08:      	b.ne	0xf10 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b4>
     f0c:      	bl	0xf0c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b0>
     f10:      	str	xzr, [x24, #0xa8]
     f14:      	movi.16b	v0, #0x0
     f18:      	stp	q0, q0, [x24, #0x80]
     f1c:      	ldr	w8, [x24, #0x74]
     f20:      	cmp	w8, #0x1
     f24:      	b.lt	0xf44 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7e8>
     f28:      	mov	x8, #0x0                ; =0
     f2c:      	ldr	x9, [x24, #0xb0]
     f30:      	str	wzr, [x9, x8, lsl #2]
     f34:      	add	x8, x8, #0x1
     f38:      	ldrsw	x10, [x24, #0x74]
     f3c:      	cmp	x8, x10
     f40:      	b.lt	0xf30 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7d4>
     f44:      	ldp	q0, q1, [sp]
     f48:      	stp	q0, q1, [x24, #0x70]
     f4c:      	ldp	q1, q2, [sp, #0x20]
     f50:      	stp	q1, q2, [x24, #0x90]
     f54:      	ldr	x0, [x24, #0xb8]
     f58:      	add	x25, x24, #0xc0
     f5c:      	cmp	x0, x25
     f60:      	b.eq	0x1008 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8ac>
     f64:      	bl	0xf64 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x808>
     f68:      	add	x8, x24, #0x78
     f6c:      	stp	x8, x25, [x24, #0xb0]
     f70:      	ldr	w9, [sp, #0x4]
     f74:      	mov	x0, x25
     f78:      	orr	x8, x23, #0x4
     f7c:      	ldr	x10, [sp, #0x48]
     f80:      	cmp	w9, #0x2
     f84:      	b.gt	0x101c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8c0>
     f88:      	ldr	x9, [x10]
     f8c:      	str	x9, [x0]
     f90:      	ldr	x9, [x10, #0x8]
     f94:      	str	x9, [x0, #0x8]
     f98:      	b	0x1028 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8cc>
     f9c:      	ldr	x8, [sp, #0x38]
     fa0:      	cbz	x8, 0xfc4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x868>
     fa4:      	add	x8, x8, #0x14
     fa8:      	ldaxr	w9, [x8]
     fac:      	subs	w9, w9, #0x1
     fb0:      	stlxr	w10, w9, [x8]
     fb4:      	cbnz	w10, 0xfa8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x84c>
     fb8:      	b.ne	0xfc4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x868>
     fbc:      	mov	x0, sp
     fc0:      	bl	0xfc0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x864>
     fc4:      	ldr	w8, [sp, #0x4]
     fc8:      	str	xzr, [sp, #0x38]
     fcc:      	movi.16b	v0, #0x0
     fd0:      	stp	q0, q0, [sp, #0x10]
     fd4:      	cmp	w8, #0x1
     fd8:      	b.lt	0xff8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x89c>
     fdc:      	mov	x8, #0x0                ; =0
     fe0:      	ldr	x9, [sp, #0x40]
     fe4:      	str	wzr, [x9, x8, lsl #2]
     fe8:      	add	x8, x8, #0x1
     fec:      	ldrsw	x10, [sp, #0x4]
     ff0:      	cmp	x8, x10
     ff4:      	b.lt	0xfe4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x888>
     ff8:      	ldr	x0, [sp, #0x48]
     ffc:      	cmp	x0, x20
    1000:      	b.ne	0x104c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8f0>
    1004:      	b	0x1050 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8f4>
    1008:      	mov.s	w9, v0[1]
    100c:      	orr	x8, x23, #0x4
    1010:      	ldr	x10, [sp, #0x48]
    1014:      	cmp	w9, #0x2
    1018:      	b.le	0xf88 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x82c>
    101c:      	ldr	x9, [sp, #0x40]
    1020:      	stp	x9, x10, [x24, #0xb0]
    1024:      	stp	x21, x20, [sp, #0x40]
    1028:      	mov	w9, #0x42ff0000         ; =1124007936
    102c:      	str	w9, [sp]
    1030:      	movi.16b	v0, #0x0
    1034:      	stp	q0, q0, [x8]
    1038:      	str	q0, [x8, #0x20]
    103c:      	stur	q0, [x8, #0x2c]
    1040:      	ldr	x0, [sp, #0x48]
    1044:      	cmp	x0, x20
    1048:      	b.eq	0x1050 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8f4>
    104c:      	bl	0x104c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8f0>
    1050:      	ldur	x0, [x29, #-0x78]
    1054:      	cbz	x0, 0x10c4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x968>
    1058:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    105c:      	ldr	x1, [x1]
    1060:      	adrp	x2, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1064:      	ldr	x2, [x2]
    1068:      	mov	x3, #0x0                ; =0
    106c:      	bl	0x106c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x910>
    1070:      	cbz	x0, 0x10c4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x968>
    1074:      	mov	x20, x0
    1078:      	ldr	x0, [x19]
    107c:      	ldr	x8, [x0]
    1080:      	ldr	x8, [x8, #0xe0]
    1084:      	blr	x8
    1088:      	fmov	d8, d0
    108c:      	ldr	x0, [x19]
    1090:      	ldr	x8, [x0]
    1094:      	ldr	x8, [x8, #0xe8]
    1098:      	blr	x8
    109c:      	mov	x21, x0
    10a0:      	ldr	x0, [x19]
    10a4:      	ldr	x8, [x0]
    10a8:      	ldr	x8, [x8, #0xf0]
    10ac:      	blr	x8
    10b0:      	mov	x2, x0
    10b4:      	mov	x0, x20
    10b8:      	fmov	d0, d8
    10bc:      	mov	x1, x21
    10c0:      	bl	0x10c0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x964>
    10c4:      	add	x0, x19, #0x18
    10c8:      	bl	0x10c8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x96c>
    10cc:      	ldp	x9, x8, [x29, #-0x78]
    10d0:      	cbz	x8, 0x10e8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x98c>
    10d4:      	add	x10, x8, #0x8
    10d8:      	ldxr	x11, [x10]
    10dc:      	add	x11, x11, #0x1
    10e0:      	stxr	w12, x11, [x10]
    10e4:      	cbnz	w12, 0x10d8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x97c>
    10e8:      	ldr	x20, [x19, #0x60]
    10ec:      	stp	x9, x8, [x19, #0x58]
    10f0:      	cbz	x20, 0x110c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9b0>
    10f4:      	add	x8, x20, #0x8
    10f8:      	ldaxr	x9, [x8]
    10fc:      	sub	x10, x9, #0x1
    1100:      	stlxr	w11, x10, [x8]
    1104:      	cbnz	w11, 0x10f8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x99c>
    1108:      	cbz	x9, 0x1140 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9e4>
    110c:      	add	x0, x19, #0x18
    1110:      	bl	0x1110 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9b4>
    1114:      	ldr	x8, [sp, #0x98]
    1118:      	cbz	x8, 0x1168 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa0c>
    111c:      	add	x8, x8, #0x14
    1120:      	ldaxr	w9, [x8]
    1124:      	subs	w9, w9, #0x1
    1128:      	stlxr	w10, w9, [x8]
    112c:      	cbnz	w10, 0x1120 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9c4>
    1130:      	b.ne	0x1168 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa0c>
    1134:      	add	x0, sp, #0x60
    1138:      	bl	0x1138 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9dc>
    113c:      	b	0x1168 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa0c>
    1140:      	ldr	x8, [x20]
    1144:      	ldr	x8, [x8, #0x10]
    1148:      	mov	x0, x20
    114c:      	blr	x8
    1150:      	mov	x0, x20
    1154:      	bl	0x1154 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9f8>
    1158:      	add	x0, x19, #0x18
    115c:      	bl	0x115c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa00>
    1160:      	ldr	x8, [sp, #0x98]
    1164:      	cbnz	x8, 0x111c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9c0>
    1168:      	str	xzr, [sp, #0x98]
    116c:      	movi.16b	v0, #0x0
    1170:      	stp	q0, q0, [sp, #0x70]
    1174:      	ldr	w8, [sp, #0x64]
    1178:      	cmp	w8, #0x1
    117c:      	b.lt	0x119c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa40>
    1180:      	mov	x8, #0x0                ; =0
    1184:      	ldr	x9, [sp, #0xa0]
    1188:      	str	wzr, [x9, x8, lsl #2]
    118c:      	add	x8, x8, #0x1
    1190:      	ldrsw	x10, [sp, #0x64]
    1194:      	cmp	x8, x10
    1198:      	b.lt	0x1188 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa2c>
    119c:      	ldr	x0, [sp, #0xa8]
    11a0:      	cmp	x0, x22
    11a4:      	b.eq	0x11ac <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa50>
    11a8:      	bl	0x11a8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa4c>
    11ac:      	ldur	x19, [x29, #-0x70]
    11b0:      	cbz	x19, 0x784 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x28>
    11b4:      	add	x8, x19, #0x8
    11b8:      	ldaxr	x9, [x8]
    11bc:      	sub	x10, x9, #0x1
    11c0:      	stlxr	w11, x10, [x8]
    11c4:      	cbnz	w11, 0x11b8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa5c>
    11c8:      	cbnz	x9, 0x784 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x28>
    11cc:      	ldr	x8, [x19]
    11d0:      	ldr	x8, [x8, #0x10]
    11d4:      	mov	x0, x19
    11d8:      	blr	x8
    11dc:      	mov	x0, x19
    11e0:      	bl	0x11e0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa84>
    11e4:      	b	0x784 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x28>
    11e8:      	adrp	x0, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    11ec:      	ldr	x0, [x0]
    11f0:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    11f4:      	add	x1, x1, #0x0
    11f8:      	mov	w2, #0x1f               ; =31
    11fc:      	bl	0x11fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xaa0>
    1200:      	bl	0x1200 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xaa4>
    1204:      	mov	w0, #-0x1               ; =-1
    1208:      	bl	0x1208 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xaac>
    120c:      	b	0x12a8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb4c>
    1210:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1214:      	add	x1, x1, #0x0
    1218:      	sub	x0, x29, #0x68
    121c:      	bl	0x121c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xac0>
    1220:      	adrp	x2, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1224:      	add	x2, x2, #0x0
    1228:      	adrp	x3, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    122c:      	add	x3, x3, #0x0
    1230:      	sub	x1, x29, #0x68
    1234:      	mov	w0, #-0xd7              ; =-215
    1238:      	mov	w4, #0x224              ; =548
    123c:      	bl	0x123c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xae0>
    1240:      	b	0x12a8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb4c>
    1244:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1248:      	add	x1, x1, #0x0
    124c:      	sub	x0, x29, #0x68
    1250:      	bl	0x1250 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xaf4>
    1254:      	adrp	x2, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1258:      	add	x2, x2, #0x0
    125c:      	adrp	x3, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1260:      	add	x3, x3, #0x0
    1264:      	sub	x1, x29, #0x68
    1268:      	mov	w0, #-0xd7              ; =-215
    126c:      	mov	w4, #0x224              ; =548
    1270:      	bl	0x1270 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb14>
    1274:      	b	0x12a8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb4c>
    1278:      	adrp	x1, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    127c:      	add	x1, x1, #0x0
    1280:      	sub	x0, x29, #0x68
    1284:      	bl	0x1284 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb28>
    1288:      	adrp	x2, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    128c:      	add	x2, x2, #0x0
    1290:      	adrp	x3, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1294:      	add	x3, x3, #0x0
    1298:      	sub	x1, x29, #0x68
    129c:      	mov	w0, #-0xd7              ; =-215
    12a0:      	mov	w4, #0x224              ; =548
    12a4:      	bl	0x12a4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb48>
    12a8:      	brk	#0x1
    12ac:      	b	0x12b4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb58>
    12b0:      	b	0x12b4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb58>
    12b4:      	mov	x19, x0
    12b8:      	ldursb	w8, [x29, #-0x51]
    12bc:      	tbz	w8, #0x1f, 0x137c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc20>
    12c0:      	ldur	x0, [x29, #-0x68]
    12c4:      	bl	0x12c4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb68>
    12c8:      	add	x0, sp, #0x60
    12cc:      	bl	0x12cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb70>
    12d0:      	sub	x0, x29, #0x78
    12d4:      	bl	0x12d4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb78>
    12d8:      	mov	x0, x19
    12dc:      	bl	0x12dc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb80>
    12e0:      	b	0x132c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbd0>
    12e4:      	bl	0x12e4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb88>
    12e8:      	bl	0x12e8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb8c>
    12ec:      	bl	0x12ec <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb90>
    12f0:      	bl	0x12f0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb94>
    12f4:      	b	0x132c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbd0>
    12f8:      	b	0x132c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbd0>
    12fc:      	b	0x132c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbd0>
    1300:      	b	0x132c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbd0>
    1304:      	b	0x1378 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc1c>
    1308:      	b	0x1378 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc1c>
    130c:      	b	0x1378 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc1c>
    1310:      	b	0x1378 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc1c>
    1314:      	b	0x1378 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc1c>
    1318:      	b	0x1378 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc1c>
    131c:      	b	0x132c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbd0>
    1320:      	bl	0x1320 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc4>
    1324:      	bl	0x1324 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc8>
    1328:      	b	0x1378 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc1c>
    132c:      	mov	x19, x0
    1330:      	mov	x0, sp
    1334:      	bl	0x1334 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbd8>
    1338:      	add	x0, sp, #0x60
    133c:      	bl	0x133c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbe0>
    1340:      	sub	x0, x29, #0x78
    1344:      	bl	0x1344 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbe8>
    1348:      	mov	x0, x19
    134c:      	bl	0x134c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbf0>
    1350:      	mov	x19, x0
    1354:      	sub	x0, x29, #0x78
    1358:      	bl	0x1358 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbfc>
    135c:      	mov	x0, x19
    1360:      	bl	0x1360 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc04>
    1364:      	mov	x19, x0
    1368:      	sub	x0, x29, #0x78
    136c:      	bl	0x136c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc10>
    1370:      	mov	x0, x19
    1374:      	bl	0x1374 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc18>
    1378:      	mov	x19, x0
    137c:      	add	x0, sp, #0x60
    1380:      	bl	0x1380 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc24>
    1384:      	sub	x0, x29, #0x78
    1388:      	bl	0x1388 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc2c>
    138c:      	mov	x0, x19
    1390:      	bl	0x1390 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc34>

0000000000001394 <__ZN2cv3MatD1Ev>:
    1394:      	stp	x20, x19, [sp, #-0x20]!
    1398:      	stp	x29, x30, [sp, #0x10]
    139c:      	add	x29, sp, #0x10
    13a0:      	mov	x19, x0
    13a4:      	ldr	x8, [x0, #0x38]
    13a8:      	cbz	x8, 0x13cc <__ZN2cv3MatD1Ev+0x38>
    13ac:      	add	x8, x8, #0x14
    13b0:      	ldaxr	w9, [x8]
    13b4:      	subs	w9, w9, #0x1
    13b8:      	stlxr	w10, w9, [x8]
    13bc:      	cbnz	w10, 0x13b0 <__ZN2cv3MatD1Ev+0x1c>
    13c0:      	b.ne	0x13cc <__ZN2cv3MatD1Ev+0x38>
    13c4:      	mov	x0, x19
    13c8:      	bl	0x13c8 <__ZN2cv3MatD1Ev+0x34>
    13cc:      	str	xzr, [x19, #0x38]
    13d0:      	movi.16b	v0, #0x0
    13d4:      	stp	q0, q0, [x19, #0x10]
    13d8:      	ldr	w8, [x19, #0x4]
    13dc:      	cmp	w8, #0x1
    13e0:      	b.lt	0x1400 <__ZN2cv3MatD1Ev+0x6c>
    13e4:      	mov	x8, #0x0                ; =0
    13e8:      	ldr	x9, [x19, #0x40]
    13ec:      	str	wzr, [x9, x8, lsl #2]
    13f0:      	add	x8, x8, #0x1
    13f4:      	ldrsw	x10, [x19, #0x4]
    13f8:      	cmp	x8, x10
    13fc:      	b.lt	0x13ec <__ZN2cv3MatD1Ev+0x58>
    1400:      	ldr	x0, [x19, #0x48]
    1404:      	add	x8, x19, #0x50
    1408:      	cmp	x0, x8
    140c:      	b.eq	0x1414 <__ZN2cv3MatD1Ev+0x80>
    1410:      	bl	0x1410 <__ZN2cv3MatD1Ev+0x7c>
    1414:      	mov	x0, x19
    1418:      	ldp	x29, x30, [sp, #0x10]
    141c:      	ldp	x20, x19, [sp], #0x20
    1420:      	ret
    1424:      	bl	0x1424 <__ZN2cv3MatD1Ev+0x90>

0000000000001428 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev>:
    1428:      	stp	x20, x19, [sp, #-0x20]!
    142c:      	stp	x29, x30, [sp, #0x10]
    1430:      	add	x29, sp, #0x10
    1434:      	ldr	x19, [x0, #0x8]
    1438:      	cbz	x19, 0x1454 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev+0x2c>
    143c:      	add	x8, x19, #0x8
    1440:      	ldaxr	x9, [x8]
    1444:      	sub	x10, x9, #0x1
    1448:      	stlxr	w11, x10, [x8]
    144c:      	cbnz	w11, 0x1440 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev+0x18>
    1450:      	cbz	x9, 0x1460 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev+0x38>
    1454:      	ldp	x29, x30, [sp, #0x10]
    1458:      	ldp	x20, x19, [sp], #0x20
    145c:      	ret
    1460:      	ldr	x8, [x19]
    1464:      	ldr	x8, [x8, #0x10]
    1468:      	mov	x20, x0
    146c:      	mov	x0, x19
    1470:      	blr	x8
    1474:      	mov	x0, x19
    1478:      	bl	0x1478 <__ZNSt3__110shared_ptrIN12xrslam_0_5_05extra11OpenCvImageEED1B8ne200100Ev+0x50>
    147c:      	mov	x0, x20
    1480:      	ldp	x29, x30, [sp, #0x10]
    1484:      	ldp	x20, x19, [sp], #0x20
    1488:      	ret

000000000000148c <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration>:
    148c:      	sub	sp, sp, #0x80
    1490:      	stp	d9, d8, [sp, #0x50]
    1494:      	stp	x20, x19, [sp, #0x60]
    1498:      	stp	x29, x30, [sp, #0x70]
    149c:      	add	x29, sp, #0x70
    14a0:      	mov	x20, x1
    14a4:      	mov	x19, x0
    14a8:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    14ac:      	ldr	x8, [x8]
    14b0:      	ldr	x8, [x8]
    14b4:      	stur	x8, [x29, #-0x28]
    14b8:      	ldr	x0, [x0, #0x10]
    14bc:      	mov	x8, sp
    14c0:      	add	x1, x1, #0x18
    14c4:      	add	x3, x20, #0x8
    14c8:      	add	x4, x20, #0x10
    14cc:      	mov	x2, x20
    14d0:      	bl	0x14d0 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x44>
    14d4:      	ldur	d8, [x20, #0x18]
    14d8:      	ldr	d0, [sp]
    14dc:      	fabs	d1, d0
    14e0:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    14e4:      	ldr	d0, [x8]
    14e8:      	fcmp	d1, d0
    14ec:      	b.gt	0x1520 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x94>
    14f0:      	ldr	d1, [sp, #0x8]
    14f4:      	fabs	d1, d1
    14f8:      	fcmp	d1, d0
    14fc:      	b.gt	0x1520 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x94>
    1500:      	ldr	d1, [sp, #0x10]
    1504:      	fabs	d1, d1
    1508:      	fcmp	d1, d0
    150c:      	b.gt	0x1520 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x94>
    1510:      	ldr	d1, [sp, #0x18]
    1514:      	fabs	d1, d1
    1518:      	fcmp	d1, d0
    151c:      	b.le	0x1560 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0xd4>
    1520:      	add	x0, x19, #0x68
    1524:      	bl	0x1524 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x98>
    1528:      	ldr	d0, [x19, #0xf0]
    152c:      	fcmp	d0, d8
    1530:      	b.gt	0x1558 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0xcc>
    1534:      	ldp	q0, q1, [sp]
    1538:      	stp	q0, q1, [x19, #0xb0]
    153c:      	ldr	q0, [sp, #0x20]
    1540:      	str	q0, [x19, #0xd0]
    1544:      	ldr	d0, [sp, #0x30]
    1548:      	str	d0, [x19, #0xe0]
    154c:      	str	d8, [x19, #0xf0]
    1550:      	mov	w8, #0x1                ; =1
    1554:      	strb	w8, [x19, #0xf8]
    1558:      	add	x0, x19, #0x68
    155c:      	bl	0x155c <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0xd0>
    1560:      	ldur	x8, [x29, #-0x28]
    1564:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1568:      	ldr	x9, [x9]
    156c:      	ldr	x9, [x9]
    1570:      	cmp	x9, x8
    1574:      	b.ne	0x158c <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x100>
    1578:      	ldp	x29, x30, [sp, #0x70]
    157c:      	ldp	x20, x19, [sp, #0x60]
    1580:      	ldp	d9, d8, [sp, #0x50]
    1584:      	add	sp, sp, #0x80
    1588:      	ret
    158c:      	bl	0x158c <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x100>
    1590:      	bl	0x1590 <__ZN12xrslam_0_5_013XRSLAMManager16PushAccelerationEP18XRSLAMAcceleration+0x104>

0000000000001594 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE>:
    1594:      	stp	d9, d8, [sp, #-0x30]!
    1598:      	stp	x20, x19, [sp, #0x10]
    159c:      	stp	x29, x30, [sp, #0x20]
    15a0:      	add	x29, sp, #0x20
    15a4:      	mov	x20, x1
    15a8:      	fmov	d8, d0
    15ac:      	mov	x19, x0
    15b0:      	ldr	d0, [x1]
    15b4:      	fabs	d1, d0
    15b8:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    15bc:      	ldr	d0, [x8]
    15c0:      	fcmp	d1, d0
    15c4:      	b.gt	0x15f8 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0x64>
    15c8:      	ldr	d1, [x20, #0x8]
    15cc:      	fabs	d1, d1
    15d0:      	fcmp	d1, d0
    15d4:      	b.gt	0x15f8 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0x64>
    15d8:      	ldr	d1, [x20, #0x10]
    15dc:      	fabs	d1, d1
    15e0:      	fcmp	d1, d0
    15e4:      	b.gt	0x15f8 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0x64>
    15e8:      	ldr	d1, [x20, #0x18]
    15ec:      	fabs	d1, d1
    15f0:      	fcmp	d1, d0
    15f4:      	b.le	0x164c <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0xb8>
    15f8:      	add	x0, x19, #0x68
    15fc:      	bl	0x15fc <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0x68>
    1600:      	ldr	d0, [x19, #0xf0]
    1604:      	fcmp	d0, d8
    1608:      	b.gt	0x1638 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0xa4>
    160c:      	ldr	q0, [x20]
    1610:      	str	q0, [x19, #0xb0]
    1614:      	ldr	q0, [x20, #0x10]
    1618:      	str	q0, [x19, #0xc0]
    161c:      	ldr	q0, [x20, #0x20]
    1620:      	str	q0, [x19, #0xd0]
    1624:      	ldr	d0, [x20, #0x30]
    1628:      	str	d0, [x19, #0xe0]
    162c:      	str	d8, [x19, #0xf0]
    1630:      	mov	w8, #0x1                ; =1
    1634:      	strb	w8, [x19, #0xf8]
    1638:      	add	x0, x19, #0x68
    163c:      	ldp	x29, x30, [sp, #0x20]
    1640:      	ldp	x20, x19, [sp, #0x10]
    1644:      	ldp	d9, d8, [sp], #0x30
    1648:      	b	0x1648 <__ZN12xrslam_0_5_013XRSLAMManager18KeepPropagatedPoseEdRKNS_4PoseE+0xb4>
    164c:      	ldp	x29, x30, [sp, #0x20]
    1650:      	ldp	x20, x19, [sp, #0x10]
    1654:      	ldp	d9, d8, [sp], #0x30
    1658:      	ret

000000000000165c <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope>:
    165c:      	sub	sp, sp, #0x80
    1660:      	stp	d9, d8, [sp, #0x50]
    1664:      	stp	x20, x19, [sp, #0x60]
    1668:      	stp	x29, x30, [sp, #0x70]
    166c:      	add	x29, sp, #0x70
    1670:      	mov	x20, x1
    1674:      	mov	x19, x0
    1678:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    167c:      	ldr	x8, [x8]
    1680:      	ldr	x8, [x8]
    1684:      	stur	x8, [x29, #-0x28]
    1688:      	ldr	x0, [x0, #0x10]
    168c:      	mov	x8, sp
    1690:      	add	x1, x1, #0x18
    1694:      	add	x3, x20, #0x8
    1698:      	add	x4, x20, #0x10
    169c:      	mov	x2, x20
    16a0:      	bl	0x16a0 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x44>
    16a4:      	ldur	d8, [x20, #0x18]
    16a8:      	ldr	d0, [sp]
    16ac:      	fabs	d1, d0
    16b0:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    16b4:      	ldr	d0, [x8]
    16b8:      	fcmp	d1, d0
    16bc:      	b.gt	0x16f0 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x94>
    16c0:      	ldr	d1, [sp, #0x8]
    16c4:      	fabs	d1, d1
    16c8:      	fcmp	d1, d0
    16cc:      	b.gt	0x16f0 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x94>
    16d0:      	ldr	d1, [sp, #0x10]
    16d4:      	fabs	d1, d1
    16d8:      	fcmp	d1, d0
    16dc:      	b.gt	0x16f0 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x94>
    16e0:      	ldr	d1, [sp, #0x18]
    16e4:      	fabs	d1, d1
    16e8:      	fcmp	d1, d0
    16ec:      	b.le	0x1730 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0xd4>
    16f0:      	add	x0, x19, #0x68
    16f4:      	bl	0x16f4 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x98>
    16f8:      	ldr	d0, [x19, #0xf0]
    16fc:      	fcmp	d0, d8
    1700:      	b.gt	0x1728 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0xcc>
    1704:      	ldp	q0, q1, [sp]
    1708:      	stp	q0, q1, [x19, #0xb0]
    170c:      	ldr	q0, [sp, #0x20]
    1710:      	str	q0, [x19, #0xd0]
    1714:      	ldr	d0, [sp, #0x30]
    1718:      	str	d0, [x19, #0xe0]
    171c:      	str	d8, [x19, #0xf0]
    1720:      	mov	w8, #0x1                ; =1
    1724:      	strb	w8, [x19, #0xf8]
    1728:      	add	x0, x19, #0x68
    172c:      	bl	0x172c <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0xd0>
    1730:      	ldur	x8, [x29, #-0x28]
    1734:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1738:      	ldr	x9, [x9]
    173c:      	ldr	x9, [x9]
    1740:      	cmp	x9, x8
    1744:      	b.ne	0x175c <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x100>
    1748:      	ldp	x29, x30, [sp, #0x70]
    174c:      	ldp	x20, x19, [sp, #0x60]
    1750:      	ldp	d9, d8, [sp, #0x50]
    1754:      	add	sp, sp, #0x80
    1758:      	ret
    175c:      	bl	0x175c <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x100>
    1760:      	bl	0x1760 <__ZN12xrslam_0_5_013XRSLAMManager13PushGyroscopeEP15XRSLAMGyroscope+0x104>

0000000000001764 <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose>:
    1764:      	stp	x20, x19, [sp, #-0x20]!
    1768:      	stp	x29, x30, [sp, #0x10]
    176c:      	add	x29, sp, #0x10
    1770:      	mov	x20, x1
    1774:      	mov	x19, x0
    1778:      	add	x0, x0, #0x68
    177c:      	bl	0x177c <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose+0x18>
    1780:      	ldrb	w8, [x19, #0xf8]
    1784:      	tbz	w8, #0x0, 0x17d8 <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose+0x74>
    1788:      	ldr	d0, [x19, #0xf0]
    178c:      	str	d0, [x20, #0x38]
    1790:      	ldr	d0, [x19, #0xb0]
    1794:      	str	d0, [x20]
    1798:      	ldr	d0, [x19, #0xb8]
    179c:      	str	d0, [x20, #0x8]
    17a0:      	ldr	d0, [x19, #0xc0]
    17a4:      	str	d0, [x20, #0x10]
    17a8:      	ldr	d0, [x19, #0xc8]
    17ac:      	str	d0, [x20, #0x18]
    17b0:      	ldr	d0, [x19, #0xd0]
    17b4:      	str	d0, [x20, #0x20]
    17b8:      	ldr	d0, [x19, #0xd8]
    17bc:      	str	d0, [x20, #0x28]
    17c0:      	ldr	d0, [x19, #0xe0]
    17c4:      	str	d0, [x20, #0x30]
    17c8:      	add	x0, x19, #0x68
    17cc:      	ldp	x29, x30, [sp, #0x10]
    17d0:      	ldp	x20, x19, [sp], #0x20
    17d4:      	b	0x17d4 <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose+0x70>
    17d8:      	movi.16b	v0, #0x0
    17dc:      	stp	q0, q0, [x20, #0x20]
    17e0:      	stp	q0, q0, [x20]
    17e4:      	add	x0, x19, #0x68
    17e8:      	ldp	x29, x30, [sp, #0x10]
    17ec:      	ldp	x20, x19, [sp], #0x20
    17f0:      	b	0x17f0 <__ZNK12xrslam_0_5_013XRSLAMManager23GetResultPropagatedPoseEP10XRSLAMPose+0x8c>

00000000000017f4 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj>:
    17f4:      	stp	x22, x21, [sp, #-0x30]!
    17f8:      	stp	x20, x19, [sp, #0x10]
    17fc:      	stp	x29, x30, [sp, #0x20]
    1800:      	add	x29, sp, #0x20
    1804:      	mov	x19, x2
    1808:      	mov	x20, x1
    180c:      	mov	x21, x0
    1810:      	cbz	x2, 0x1818 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x24>
    1814:      	str	wzr, [x19]
    1818:      	cbz	x20, 0x1878 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x84>
    181c:      	add	x0, x21, #0x68
    1820:      	bl	0x1820 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x2c>
    1824:      	ldrb	w8, [x21, #0xf8]
    1828:      	tbz	w8, #0x0, 0x1888 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x94>
    182c:      	ldr	d0, [x21, #0xf0]
    1830:      	str	d0, [x20, #0x38]
    1834:      	ldr	d0, [x21, #0xb0]
    1838:      	str	d0, [x20]
    183c:      	ldr	d0, [x21, #0xb8]
    1840:      	str	d0, [x20, #0x8]
    1844:      	ldr	d0, [x21, #0xc0]
    1848:      	str	d0, [x20, #0x10]
    184c:      	ldr	d0, [x21, #0xc8]
    1850:      	str	d0, [x20, #0x18]
    1854:      	ldr	d0, [x21, #0xd0]
    1858:      	str	d0, [x20, #0x20]
    185c:      	ldr	d0, [x21, #0xd8]
    1860:      	str	d0, [x20, #0x28]
    1864:      	ldr	d0, [x21, #0xe0]
    1868:      	str	d0, [x20, #0x30]
    186c:      	add	x0, x21, #0x68
    1870:      	bl	0x1870 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x7c>
    1874:      	cbnz	x19, 0x18a0 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0xac>
    1878:      	ldp	x29, x30, [sp, #0x20]
    187c:      	ldp	x20, x19, [sp, #0x10]
    1880:      	ldp	x22, x21, [sp], #0x30
    1884:      	ret
    1888:      	movi.16b	v0, #0x0
    188c:      	stp	q0, q0, [x20, #0x20]
    1890:      	stp	q0, q0, [x20]
    1894:      	add	x0, x21, #0x68
    1898:      	bl	0x1898 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0xa4>
    189c:      	cbz	x19, 0x1878 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0x84>
    18a0:      	ldr	d0, [x20, #0x38]
    18a4:      	fcmp	d0, #0.0
    18a8:      	b.le	0x18e4 <__ZNK12xrslam_0_5_013XRSLAMManager25GetPropagatedPoseRelationEP10XRSLAMPosePj+0xf0>
    18ac:      	ldp	q0, q1, [x20]
    18b0:      	fmul.2d	v1, v1, v1
    18b4:      	fmla.2d	v1, v0, v0
    18b8:      	faddp.2d	d0, v1
    18bc:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    18c0:      	ldr	d1, [x8]
    18c4:      	fcmp	d0, d1
    18c8:      	mov	w8, #0x2                ; =2
    18cc:      	cinc	w8, w8, gt
    18d0:      	str	w8, [x19]
    18d4:      	ldp	x29, x30, [sp, #0x20]
    18d8:      	ldp	x20, x19, [sp, #0x10]
    18dc:      	ldp	x22, x21, [sp], #0x30
    18e0:      	ret
    18e4:      	mov	w8, #0x0                ; =0
    18e8:      	str	w8, [x19]
    18ec:      	ldp	x29, x30, [sp, #0x20]
    18f0:      	ldp	x20, x19, [sp, #0x10]
    18f4:      	ldp	x22, x21, [sp], #0x30
    18f8:      	ret

00000000000018fc <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj>:
    18fc:      	sub	sp, sp, #0x120
    1900:      	stp	d15, d14, [sp, #0xa0]
    1904:      	stp	d13, d12, [sp, #0xb0]
    1908:      	stp	d11, d10, [sp, #0xc0]
    190c:      	stp	d9, d8, [sp, #0xd0]
    1910:      	stp	x28, x27, [sp, #0xe0]
    1914:      	stp	x22, x21, [sp, #0xf0]
    1918:      	stp	x20, x19, [sp, #0x100]
    191c:      	stp	x29, x30, [sp, #0x110]
    1920:      	add	x29, sp, #0x110
    1924:      	mov	x19, x2
    1928:      	mov	x21, x1
    192c:      	mov	x20, x0
    1930:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1934:      	ldr	x8, [x8]
    1938:      	ldr	x8, [x8]
    193c:      	stur	x8, [x29, #-0x78]
    1940:      	cbz	x2, 0x1948 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x4c>
    1944:      	str	wzr, [x19]
    1948:      	cbz	x21, 0x1ad0 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1d4>
    194c:      	cmp	x19, #0x0
    1950:      	cset	w22, eq
    1954:      	ldr	x0, [x20, #0x10]
    1958:      	add	x8, sp, #0x40
    195c:      	bl	0x195c <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x60>
    1960:      	ldr	d0, [sp, #0x40]
    1964:      	ldp	d8, d9, [sp, #0x50]
    1968:      	str	d0, [x21, #0x38]
    196c:      	ldp	d12, d1, [sp, #0x60]
    1970:      	ldr	q0, [sp, #0x70]
    1974:      	stp	q0, q1, [sp]
    1978:      	ldr	d10, [sp, #0x80]
    197c:      	ldr	x0, [x20]
    1980:      	ldr	x8, [x0]
    1984:      	ldr	x9, [x8, #0x48]
    1988:      	add	x8, sp, #0x20
    198c:      	blr	x9
    1990:      	ldp	d14, d13, [sp, #0x20]
    1994:      	ldp	d11, d15, [sp, #0x30]
    1998:      	ldr	x0, [x20]
    199c:      	ldr	x8, [x0]
    19a0:      	ldr	x9, [x8, #0x50]
    19a4:      	add	x8, sp, #0x20
    19a8:      	blr	x9
    19ac:      	fmul	d0, d14, d8
    19b0:      	fmadd	d0, d13, d9, d0
    19b4:      	fmadd	d0, d11, d12, d0
    19b8:      	ldr	q17, [sp, #0x10]
    19bc:      	fnmsub	d0, d15, d17, d0
    19c0:      	fmul	d1, d15, d8
    19c4:      	fmadd	d1, d14, d17, d1
    19c8:      	fmsub	d1, d13, d12, d1
    19cc:      	fmul	d2, d15, d9
    19d0:      	fmadd	d2, d14, d12, d2
    19d4:      	fmadd	d3, d13, d17, d2
    19d8:      	fmul	d2, d14, d9
    19dc:      	fnmsub	d2, d15, d12, d2
    19e0:      	fmadd	d4, d13, d8, d2
    19e4:      	ldp	d6, d5, [sp, #0x28]
    19e8:      	fmul	d2, d6, d12
    19ec:      	fnmsub	d7, d5, d9, d2
    19f0:      	ldr	d16, [sp, #0x20]
    19f4:      	fmul	d2, d5, d8
    19f8:      	fnmsub	d2, d16, d12, d2
    19fc:      	mov.d	v7[1], v2[0]
    1a00:      	fmadd	d2, d11, d9, d1
    1a04:      	fmsub	d1, d11, d8, d3
    1a08:      	fmul	d3, d16, d9
    1a0c:      	fnmsub	d3, d6, d8, d3
    1a10:      	fadd.2d	v6, v7, v7
    1a14:      	fadd	d3, d3, d3
    1a18:      	fmul	d7, d3, d8
    1a1c:      	fnmsub	d7, d12, d6, d7
    1a20:      	fmul.d	d16, d12, v6[1]
    1a24:      	fnmsub	d16, d3, d9, d16
    1a28:      	mov.d	v16[1], v7[0]
    1a2c:      	ldr	q7, [sp, #0x20]
    1a30:      	ldr	q18, [sp]
    1a34:      	fadd.2d	v7, v7, v18
    1a38:      	fmla.2d	v7, v6, v17[0]
    1a3c:      	fadd.2d	v7, v7, v16
    1a40:      	fadd	d5, d5, d10
    1a44:      	fmadd	d3, d3, d17, d5
    1a48:      	fmla.d	d3, d8, v6[1]
    1a4c:      	fmsub	d3, d9, d6, d3
    1a50:      	str	q7, [x21, #0x20]
    1a54:      	str	d3, [x21, #0x30]
    1a58:      	stp	d2, d1, [x21]
    1a5c:      	fmadd	d3, d11, d17, d4
    1a60:      	stp	d3, d0, [x21, #0x10]
    1a64:      	tbnz	w22, #0x0, 0x1ad0 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1d4>
    1a68:      	ldr	d4, [x21, #0x38]
    1a6c:      	fcmp	d4, #0.0
    1a70:      	b.le	0x1ac8 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1cc>
    1a74:      	fmul	d2, d2, d2
    1a78:      	fmadd	d2, d3, d3, d2
    1a7c:      	fmadd	d1, d1, d1, d2
    1a80:      	fmadd	d0, d0, d0, d1
    1a84:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1a88:      	ldr	d1, [x8]
    1a8c:      	fcmp	d0, d1
    1a90:      	mov	w8, #0x2                ; =2
    1a94:      	cinc	w21, w8, gt
    1a98:      	ldr	x0, [x20, #0x10]
    1a9c:      	cbz	x0, 0x1acc <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1d0>
    1aa0:      	fcmp	d0, d1
    1aa4:      	cset	w20, gt
    1aa8:      	bl	0x1aa8 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1ac>
    1aac:      	cmp	w20, #0x0
    1ab0:      	mov	w8, #0x22               ; =34
    1ab4:      	mov	w9, #0x33               ; =51
    1ab8:      	csel	w8, w9, w8, ne
    1abc:      	cmp	w0, #0x1
    1ac0:      	csel	w21, w8, w21, eq
    1ac4:      	b	0x1acc <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x1d0>
    1ac8:      	mov	w21, #0x0               ; =0
    1acc:      	str	w21, [x19]
    1ad0:      	ldur	x8, [x29, #-0x78]
    1ad4:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1ad8:      	ldr	x9, [x9]
    1adc:      	ldr	x9, [x9]
    1ae0:      	cmp	x9, x8
    1ae4:      	b.ne	0x1b10 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x214>
    1ae8:      	ldp	x29, x30, [sp, #0x110]
    1aec:      	ldp	x20, x19, [sp, #0x100]
    1af0:      	ldp	x22, x21, [sp, #0xf0]
    1af4:      	ldp	x28, x27, [sp, #0xe0]
    1af8:      	ldp	d9, d8, [sp, #0xd0]
    1afc:      	ldp	d11, d10, [sp, #0xc0]
    1b00:      	ldp	d13, d12, [sp, #0xb0]
    1b04:      	ldp	d15, d14, [sp, #0xa0]
    1b08:      	add	sp, sp, #0x120
    1b0c:      	ret
    1b10:      	bl	0x1b10 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x214>
    1b14:      	bl	0x1b14 <__ZNK12xrslam_0_5_013XRSLAMManager19GetBodyPoseRelationEP10XRSLAMPosePj+0x218>

0000000000001b18 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose>:
    1b18:      	sub	sp, sp, #0x110
    1b1c:      	stp	d15, d14, [sp, #0xa0]
    1b20:      	stp	d13, d12, [sp, #0xb0]
    1b24:      	stp	d11, d10, [sp, #0xc0]
    1b28:      	stp	d9, d8, [sp, #0xd0]
    1b2c:      	stp	x28, x27, [sp, #0xe0]
    1b30:      	stp	x20, x19, [sp, #0xf0]
    1b34:      	stp	x29, x30, [sp, #0x100]
    1b38:      	add	x29, sp, #0x100
    1b3c:      	mov	x19, x1
    1b40:      	mov	x20, x0
    1b44:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1b48:      	ldr	x8, [x8]
    1b4c:      	ldr	x8, [x8]
    1b50:      	stur	x8, [x29, #-0x68]
    1b54:      	ldr	x0, [x0, #0x10]
    1b58:      	add	x8, sp, #0x40
    1b5c:      	bl	0x1b5c <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose+0x44>
    1b60:      	ldr	d0, [sp, #0x40]
    1b64:      	ldp	d8, d9, [sp, #0x50]
    1b68:      	str	d0, [x19, #0x38]
    1b6c:      	ldp	d11, d1, [sp, #0x60]
    1b70:      	ldr	q0, [sp, #0x70]
    1b74:      	stp	q0, q1, [sp]
    1b78:      	ldr	d10, [sp, #0x80]
    1b7c:      	ldr	x0, [x20]
    1b80:      	ldr	x8, [x0]
    1b84:      	ldr	x9, [x8, #0x48]
    1b88:      	add	x8, sp, #0x20
    1b8c:      	blr	x9
    1b90:      	ldp	d14, d13, [sp, #0x20]
    1b94:      	ldp	d12, d15, [sp, #0x30]
    1b98:      	ldr	x0, [x20]
    1b9c:      	ldr	x8, [x0]
    1ba0:      	ldr	x9, [x8, #0x50]
    1ba4:      	add	x8, sp, #0x20
    1ba8:      	blr	x9
    1bac:      	fmul	d0, d14, d8
    1bb0:      	fmadd	d0, d13, d9, d0
    1bb4:      	fmadd	d0, d12, d11, d0
    1bb8:      	ldr	q17, [sp, #0x10]
    1bbc:      	fnmsub	d0, d15, d17, d0
    1bc0:      	fmul	d1, d15, d8
    1bc4:      	fmadd	d1, d14, d17, d1
    1bc8:      	fmsub	d1, d13, d11, d1
    1bcc:      	fmadd	d1, d12, d9, d1
    1bd0:      	fmul	d2, d15, d9
    1bd4:      	fmadd	d2, d14, d11, d2
    1bd8:      	fmadd	d2, d13, d17, d2
    1bdc:      	fmsub	d2, d12, d8, d2
    1be0:      	fmul	d3, d14, d9
    1be4:      	fnmsub	d3, d15, d11, d3
    1be8:      	fmadd	d3, d13, d8, d3
    1bec:      	ldp	d5, d4, [sp, #0x28]
    1bf0:      	ldr	d6, [sp, #0x20]
    1bf4:      	fmul	d7, d4, d8
    1bf8:      	fnmsub	d7, d6, d11, d7
    1bfc:      	fmul	d6, d6, d9
    1c00:      	fnmsub	d6, d5, d8, d6
    1c04:      	fmul	d5, d5, d11
    1c08:      	fnmsub	d5, d4, d9, d5
    1c0c:      	mov.d	v5[1], v7[0]
    1c10:      	fadd.2d	v5, v5, v5
    1c14:      	fadd	d6, d6, d6
    1c18:      	fmul	d7, d6, d8
    1c1c:      	fnmsub	d7, d11, d5, d7
    1c20:      	fmul.d	d16, d11, v5[1]
    1c24:      	fnmsub	d16, d6, d9, d16
    1c28:      	mov.d	v16[1], v7[0]
    1c2c:      	fmadd	d3, d12, d17, d3
    1c30:      	ldr	q7, [sp, #0x20]
    1c34:      	ldr	q18, [sp]
    1c38:      	fadd.2d	v7, v7, v18
    1c3c:      	fmla.2d	v7, v5, v17[0]
    1c40:      	fadd.2d	v7, v7, v16
    1c44:      	fadd	d4, d4, d10
    1c48:      	fmadd	d4, d6, d17, d4
    1c4c:      	fmla.d	d4, d8, v5[1]
    1c50:      	fmsub	d4, d9, d5, d4
    1c54:      	str	q7, [x19, #0x20]
    1c58:      	str	d4, [x19, #0x30]
    1c5c:      	stp	d1, d2, [x19]
    1c60:      	stp	d3, d0, [x19, #0x10]
    1c64:      	ldur	x8, [x29, #-0x68]
    1c68:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1c6c:      	ldr	x9, [x9]
    1c70:      	ldr	x9, [x9]
    1c74:      	cmp	x9, x8
    1c78:      	b.ne	0x1ca0 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose+0x188>
    1c7c:      	ldp	x29, x30, [sp, #0x100]
    1c80:      	ldp	x20, x19, [sp, #0xf0]
    1c84:      	ldp	x28, x27, [sp, #0xe0]
    1c88:      	ldp	d9, d8, [sp, #0xd0]
    1c8c:      	ldp	d11, d10, [sp, #0xc0]
    1c90:      	ldp	d13, d12, [sp, #0xb0]
    1c94:      	ldp	d15, d14, [sp, #0xa0]
    1c98:      	add	sp, sp, #0x110
    1c9c:      	ret
    1ca0:      	bl	0x1ca0 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose+0x188>
    1ca4:      	bl	0x1ca4 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultBodyPoseEP10XRSLAMPose+0x18c>

0000000000001ca8 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv>:
    1ca8:      	sub	sp, sp, #0x80
    1cac:      	stp	x20, x19, [sp, #0x60]
    1cb0:      	stp	x29, x30, [sp, #0x70]
    1cb4:      	add	x29, sp, #0x70
    1cb8:      	mov	x19, x0
    1cbc:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1cc0:      	ldr	x8, [x8]
    1cc4:      	ldr	x8, [x8]
    1cc8:      	stur	x8, [x29, #-0x18]
    1ccc:      	add	x0, x0, #0x18
    1cd0:      	bl	0x1cd0 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x28>
    1cd4:      	ldr	x0, [x19, #0x10]
    1cd8:      	ldp	x9, x8, [x19, #0x58]
    1cdc:      	stp	x9, x8, [sp]
    1ce0:      	cbz	x8, 0x1cf8 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x50>
    1ce4:      	add	x8, x8, #0x8
    1ce8:      	ldxr	x9, [x8]
    1cec:      	add	x9, x9, #0x1
    1cf0:      	stxr	w10, x9, [x8]
    1cf4:      	cbnz	w10, 0x1ce8 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x40>
    1cf8:      	add	x8, sp, #0x10
    1cfc:      	mov	x1, sp
    1d00:      	bl	0x1d00 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x58>
    1d04:      	ldr	x20, [sp, #0x8]
    1d08:      	cbz	x20, 0x1d3c <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x94>
    1d0c:      	add	x8, x20, #0x8
    1d10:      	ldaxr	x9, [x8]
    1d14:      	sub	x10, x9, #0x1
    1d18:      	stlxr	w11, x10, [x8]
    1d1c:      	cbnz	w11, 0x1d10 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x68>
    1d20:      	cbnz	x9, 0x1d3c <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x94>
    1d24:      	ldr	x8, [x20]
    1d28:      	ldr	x8, [x8, #0x10]
    1d2c:      	mov	x0, x20
    1d30:      	blr	x8
    1d34:      	mov	x0, x20
    1d38:      	bl	0x1d38 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x90>
    1d3c:      	add	x0, x19, #0x18
    1d40:      	bl	0x1d40 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0x98>
    1d44:      	ldur	x8, [x29, #-0x18]
    1d48:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1d4c:      	ldr	x9, [x9]
    1d50:      	ldr	x9, [x9]
    1d54:      	cmp	x9, x8
    1d58:      	b.ne	0x1d6c <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xc4>
    1d5c:      	ldp	x29, x30, [sp, #0x70]
    1d60:      	ldp	x20, x19, [sp, #0x60]
    1d64:      	add	sp, sp, #0x80
    1d68:      	ret
    1d6c:      	bl	0x1d6c <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xc4>
    1d70:      	mov	x20, x0
    1d74:      	mov	x0, sp
    1d78:      	bl	0x1d78 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xd0>
    1d7c:      	add	x0, x19, #0x18
    1d80:      	bl	0x1d80 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xd8>
    1d84:      	mov	x0, x20
    1d88:      	bl	0x1d88 <__ZN12xrslam_0_5_013XRSLAMManager11RunOneFrameEv+0xe0>

0000000000001d8c <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose>:
    1d8c:      	sub	sp, sp, #0x110
    1d90:      	stp	d15, d14, [sp, #0xa0]
    1d94:      	stp	d13, d12, [sp, #0xb0]
    1d98:      	stp	d11, d10, [sp, #0xc0]
    1d9c:      	stp	d9, d8, [sp, #0xd0]
    1da0:      	stp	x28, x27, [sp, #0xe0]
    1da4:      	stp	x20, x19, [sp, #0xf0]
    1da8:      	stp	x29, x30, [sp, #0x100]
    1dac:      	add	x29, sp, #0x100
    1db0:      	mov	x19, x1
    1db4:      	mov	x20, x0
    1db8:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1dbc:      	ldr	x8, [x8]
    1dc0:      	ldr	x8, [x8]
    1dc4:      	stur	x8, [x29, #-0x68]
    1dc8:      	ldr	x0, [x0, #0x10]
    1dcc:      	add	x8, sp, #0x40
    1dd0:      	bl	0x1dd0 <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose+0x44>
    1dd4:      	ldr	d0, [sp, #0x40]
    1dd8:      	ldp	d8, d9, [sp, #0x50]
    1ddc:      	str	d0, [x19, #0x38]
    1de0:      	ldp	d11, d1, [sp, #0x60]
    1de4:      	ldr	q0, [sp, #0x70]
    1de8:      	stp	q0, q1, [sp]
    1dec:      	ldr	d10, [sp, #0x80]
    1df0:      	ldr	x0, [x20]
    1df4:      	ldr	x8, [x0]
    1df8:      	ldr	x9, [x8, #0x28]
    1dfc:      	add	x8, sp, #0x20
    1e00:      	blr	x9
    1e04:      	ldp	d14, d13, [sp, #0x20]
    1e08:      	ldp	d12, d15, [sp, #0x30]
    1e0c:      	ldr	x0, [x20]
    1e10:      	ldr	x8, [x0]
    1e14:      	ldr	x9, [x8, #0x30]
    1e18:      	add	x8, sp, #0x20
    1e1c:      	blr	x9
    1e20:      	fmul	d0, d14, d8
    1e24:      	fmadd	d0, d13, d9, d0
    1e28:      	fmadd	d0, d12, d11, d0
    1e2c:      	ldr	q17, [sp, #0x10]
    1e30:      	fnmsub	d0, d15, d17, d0
    1e34:      	fmul	d1, d15, d8
    1e38:      	fmadd	d1, d14, d17, d1
    1e3c:      	fmsub	d1, d13, d11, d1
    1e40:      	fmadd	d1, d12, d9, d1
    1e44:      	fmul	d2, d15, d9
    1e48:      	fmadd	d2, d14, d11, d2
    1e4c:      	fmadd	d2, d13, d17, d2
    1e50:      	fmsub	d2, d12, d8, d2
    1e54:      	fmul	d3, d14, d9
    1e58:      	fnmsub	d3, d15, d11, d3
    1e5c:      	fmadd	d3, d13, d8, d3
    1e60:      	ldp	d5, d4, [sp, #0x28]
    1e64:      	ldr	d6, [sp, #0x20]
    1e68:      	fmul	d7, d4, d8
    1e6c:      	fnmsub	d7, d6, d11, d7
    1e70:      	fmul	d6, d6, d9
    1e74:      	fnmsub	d6, d5, d8, d6
    1e78:      	fmul	d5, d5, d11
    1e7c:      	fnmsub	d5, d4, d9, d5
    1e80:      	mov.d	v5[1], v7[0]
    1e84:      	fadd.2d	v5, v5, v5
    1e88:      	fadd	d6, d6, d6
    1e8c:      	fmul	d7, d6, d8
    1e90:      	fnmsub	d7, d11, d5, d7
    1e94:      	fmul.d	d16, d11, v5[1]
    1e98:      	fnmsub	d16, d6, d9, d16
    1e9c:      	mov.d	v16[1], v7[0]
    1ea0:      	fmadd	d3, d12, d17, d3
    1ea4:      	ldr	q7, [sp, #0x20]
    1ea8:      	ldr	q18, [sp]
    1eac:      	fadd.2d	v7, v7, v18
    1eb0:      	fmla.2d	v7, v5, v17[0]
    1eb4:      	fadd.2d	v7, v7, v16
    1eb8:      	fadd	d4, d4, d10
    1ebc:      	fmadd	d4, d6, d17, d4
    1ec0:      	fmla.d	d4, d8, v5[1]
    1ec4:      	fmsub	d4, d9, d5, d4
    1ec8:      	str	q7, [x19, #0x20]
    1ecc:      	str	d4, [x19, #0x30]
    1ed0:      	stp	d1, d2, [x19]
    1ed4:      	stp	d3, d0, [x19, #0x10]
    1ed8:      	ldur	x8, [x29, #-0x68]
    1edc:      	adrp	x9, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1ee0:      	ldr	x9, [x9]
    1ee4:      	ldr	x9, [x9]
    1ee8:      	cmp	x9, x8
    1eec:      	b.ne	0x1f14 <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose+0x188>
    1ef0:      	ldp	x29, x30, [sp, #0x100]
    1ef4:      	ldp	x20, x19, [sp, #0xf0]
    1ef8:      	ldp	x28, x27, [sp, #0xe0]
    1efc:      	ldp	d9, d8, [sp, #0xd0]
    1f00:      	ldp	d11, d10, [sp, #0xc0]
    1f04:      	ldp	d13, d12, [sp, #0xb0]
    1f08:      	ldp	d15, d14, [sp, #0xa0]
    1f0c:      	add	sp, sp, #0x110
    1f10:      	ret
    1f14:      	bl	0x1f14 <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose+0x188>
    1f18:      	bl	0x1f18 <__ZNK12xrslam_0_5_013XRSLAMManager19GetResultCameraPoseEP10XRSLAMPose+0x18c>

0000000000001f1c <__ZNK12xrslam_0_5_013XRSLAMManager17GetInfoIntrinsicsEP16XRSLAMIntrinsics>:
    1f1c:      	sub	sp, sp, #0x70
    1f20:      	stp	x20, x19, [sp, #0x50]
    1f24:      	stp	x29, x30, [sp, #0x60]
    1f28:      	add	x29, sp, #0x60
    1f2c:      	mov	x19, x1
    1f30:      	mov	x20, x0
    1f34:      	ldr	x0, [x0]
    1f38:      	ldr	x8, [x0]
    1f3c:      	ldr	x9, [x8, #0x18]
    1f40:      	add	x8, sp, #0x8
    1f44:      	blr	x9
    1f48:      	ldr	d0, [sp, #0x8]
    1f4c:      	str	d0, [x19]
    1f50:      	ldr	x0, [x20]
    1f54:      	ldr	x8, [x0]
    1f58:      	ldr	x9, [x8, #0x18]
    1f5c:      	add	x8, sp, #0x8
    1f60:      	blr	x9
    1f64:      	ldr	d0, [sp, #0x28]
    1f68:      	str	d0, [x19, #0x8]
    1f6c:      	ldr	x0, [x20]
    1f70:      	ldr	x8, [x0]
    1f74:      	ldr	x9, [x8, #0x18]
    1f78:      	add	x8, sp, #0x8
    1f7c:      	blr	x9
    1f80:      	ldr	d0, [sp, #0x38]
    1f84:      	str	d0, [x19, #0x10]
    1f88:      	ldr	x0, [x20]
    1f8c:      	ldr	x8, [x0]
    1f90:      	ldr	x9, [x8, #0x18]
    1f94:      	add	x8, sp, #0x8
    1f98:      	blr	x9
    1f9c:      	ldr	d0, [sp, #0x40]
    1fa0:      	str	d0, [x19, #0x18]
    1fa4:      	ldp	x29, x30, [sp, #0x60]
    1fa8:      	ldp	x20, x19, [sp, #0x50]
    1fac:      	add	sp, sp, #0x70
    1fb0:      	ret

0000000000001fb4 <__ZNK12xrslam_0_5_013XRSLAMManager14GetResultStateEP11XRSLAMState>:
    1fb4:      	stp	x20, x19, [sp, #-0x20]!
    1fb8:      	stp	x29, x30, [sp, #0x10]
    1fbc:      	add	x29, sp, #0x10
    1fc0:      	mov	x19, x1
    1fc4:      	ldr	x0, [x0, #0x10]
    1fc8:      	bl	0x1fc8 <__ZNK12xrslam_0_5_013XRSLAMManager14GetResultStateEP11XRSLAMState+0x14>
    1fcc:      	cmp	w0, #0x3
    1fd0:      	b.hi	0x1fe4 <__ZNK12xrslam_0_5_013XRSLAMManager14GetResultStateEP11XRSLAMState+0x30>
    1fd4:      	adrp	x8, 0x1000 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a4>
    1fd8:      	add	x8, x8, #0x0
    1fdc:      	ldr	w8, [x8, w0, uxtw #2]
    1fe0:      	str	w8, [x19]
    1fe4:      	ldp	x29, x30, [sp, #0x10]
    1fe8:      	ldp	x20, x19, [sp], #0x20
    1fec:      	ret

0000000000001ff0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks>:
    1ff0:      	sub	sp, sp, #0x60
    1ff4:      	stp	x24, x23, [sp, #0x20]
    1ff8:      	stp	x22, x21, [sp, #0x30]
    1ffc:      	stp	x20, x19, [sp, #0x40]
    2000:      	stp	x29, x30, [sp, #0x50]
    2004:      	add	x29, sp, #0x50
    2008:      	mov	x20, x1
    200c:      	add	x8, sp, #0x8
    2010:      	mov	w0, #0x8                ; =8
    2014:      	bl	0x2014 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x24>
    2018:      	ldr	x1, [sp, #0x8]
    201c:      	ldr	x8, [x1]
    2020:      	cbz	x8, 0x21b8 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1c8>
    2024:      	adrp	x3, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2028:      	add	x3, x3, #0x0
    202c:      	adrp	x4, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2030:      	add	x4, x4, #0x0
    2034:      	mov	w0, #0x3                ; =3
    2038:      	mov	x2, #0x0                ; =0
    203c:      	blr	x8
    2040:      	cbz	x0, 0x21b8 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1c8>
    2044:      	ldp	x22, x23, [x0]
    2048:      	subs	x0, x23, x22
    204c:      	b.eq	0x208c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x9c>
    2050:      	tbnz	x0, #0x3f, 0x21c0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1d0>
    2054:      	bl	0x2054 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x64>
    2058:      	mov	x19, x0
    205c:      	mov	x21, x0
    2060:      	ldr	q0, [x22]
    2064:      	ldr	x8, [x22, #0x10]
    2068:      	str	x8, [x21, #0x10]
    206c:      	str	q0, [x21]
    2070:      	ldrb	w8, [x22, #0x18]
    2074:      	strb	w8, [x21, #0x18]
    2078:      	add	x22, x22, #0x20
    207c:      	add	x21, x21, #0x20
    2080:      	cmp	x22, x23
    2084:      	b.ne	0x2060 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x70>
    2088:      	b	0x2094 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xa4>
    208c:      	mov	x21, #0x0               ; =0
    2090:      	mov	x19, #0x0               ; =0
    2094:      	sub	x8, x21, x19
    2098:      	asr	x22, x8, #5
    209c:      	str	w22, [x20, #0x8]
    20a0:      	add	x8, x22, x8, asr #4
    20a4:      	lsl	x8, x8, #3
    20a8:      	mov	w9, #0x18               ; =24
    20ac:      	umulh	x9, x22, x9
    20b0:      	cmp	xzr, x9
    20b4:      	csinv	x0, x8, xzr, eq
    20b8:      	bl	0x20b8 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xc8>
    20bc:      	str	x0, [x20]
    20c0:      	cmp	x21, x19
    20c4:      	b.ne	0x20f8 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x108>
    20c8:      	cbnz	x19, 0x21a0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1b0>
    20cc:      	ldrb	w8, [sp, #0x18]
    20d0:      	cmp	w8, #0x1
    20d4:      	b.ne	0x20e0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xf0>
    20d8:      	ldr	x0, [sp, #0x10]
    20dc:      	bl	0x20dc <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xec>
    20e0:      	ldp	x29, x30, [sp, #0x50]
    20e4:      	ldp	x20, x19, [sp, #0x40]
    20e8:      	ldp	x22, x21, [sp, #0x30]
    20ec:      	ldp	x24, x23, [sp, #0x20]
    20f0:      	add	sp, sp, #0x60
    20f4:      	ret
    20f8:      	cmp	x22, #0x1
    20fc:      	csinc	x8, x22, xzr, hi
    2100:      	cmp	x22, #0x4
    2104:      	b.hi	0x2110 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x120>
    2108:      	mov	x9, #0x0                ; =0
    210c:      	b	0x216c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x17c>
    2110:      	ands	x9, x8, #0x3
    2114:      	mov	w10, #0x4               ; =4
    2118:      	csel	x9, x10, x9, eq
    211c:      	sub	x9, x8, x9
    2120:      	add	x10, x19, #0x40
    2124:      	mov	x11, x9
    2128:      	mov	x12, x0
    212c:      	ldp	q1, q0, [x10, #-0x20]
    2130:      	ldp	q3, q2, [x10, #-0x40]
    2134:      	ldp	q5, q4, [x10, #0x20]
    2138:      	ldp	q7, q6, [x10], #0x80
    213c:      	zip1.2d	v16, v3, v1
    2140:      	zip2.2d	v17, v3, v1
    2144:      	zip1.2d	v18, v2, v0
    2148:      	add	x13, x12, #0x60
    214c:      	st3.2d	{ v16, v17, v18 }, [x12], #48
    2150:      	zip1.2d	v0, v7, v5
    2154:      	zip2.2d	v1, v7, v5
    2158:      	zip1.2d	v2, v6, v4
    215c:      	st3.2d	{ v0, v1, v2 }, [x12]
    2160:      	mov	x12, x13
    2164:      	subs	x11, x11, #0x4
    2168:      	b.ne	0x212c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x13c>
    216c:      	mov	w10, #0x18              ; =24
    2170:      	madd	x10, x9, x10, x0
    2174:      	add	x10, x10, #0x10
    2178:      	add	x11, x19, x9, lsl #5
    217c:      	add	x11, x11, #0x10
    2180:      	sub	x8, x8, x9
    2184:      	ldr	d0, [x11]
    2188:      	ldur	q1, [x11, #-0x10]
    218c:      	stur	q1, [x10, #-0x10]
    2190:      	str	d0, [x10], #0x18
    2194:      	add	x11, x11, #0x20
    2198:      	subs	x8, x8, #0x1
    219c:      	b.ne	0x2184 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x194>
    21a0:      	mov	x0, x19
    21a4:      	bl	0x21a4 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1b4>
    21a8:      	ldrb	w8, [sp, #0x18]
    21ac:      	cmp	w8, #0x1
    21b0:      	b.eq	0x20d8 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xe8>
    21b4:      	b	0x20e0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0xf0>
    21b8:      	bl	0x21b8 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1c8>
    21bc:      	b	0x21c4 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1d4>
    21c0:      	bl	0x21c0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1d0>
    21c4:      	brk	#0x1
    21c8:      	mov	x20, x0
    21cc:      	cbnz	x19, 0x21e4 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1f4>
    21d0:      	ldrb	w8, [sp, #0x18]
    21d4:      	cmp	w8, #0x1
    21d8:      	b.eq	0x2210 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x220>
    21dc:      	mov	x0, x20
    21e0:      	bl	0x21e0 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1f0>
    21e4:      	mov	x0, x19
    21e8:      	bl	0x21e8 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1f8>
    21ec:      	ldrb	w8, [sp, #0x18]
    21f0:      	cmp	w8, #0x1
    21f4:      	b.ne	0x21dc <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1ec>
    21f8:      	b	0x2210 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x220>
    21fc:      	bl	0x21fc <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x20c>
    2200:      	mov	x20, x0
    2204:      	ldrb	w8, [sp, #0x18]
    2208:      	cmp	w8, #0x1
    220c:      	b.ne	0x21dc <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x1ec>
    2210:      	ldr	x0, [sp, #0x10]
    2214:      	bl	0x2214 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x224>
    2218:      	mov	x0, x20
    221c:      	bl	0x221c <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x22c>

0000000000002220 <__ZNK12xrslam_0_5_013XRSLAMManager17GetResultFeaturesEP14XRSLAMFeatures>:
    2220:      	ret

0000000000002224 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias>:
    2224:      	sub	sp, sp, #0x40
    2228:      	stp	x20, x19, [sp, #0x20]
    222c:      	stp	x29, x30, [sp, #0x30]
    2230:      	add	x29, sp, #0x30
    2234:      	mov	x19, x1
    2238:      	add	x8, sp, #0x8
    223c:      	mov	w0, #0x9                ; =9
    2240:      	bl	0x2240 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x1c>
    2244:      	ldr	x1, [sp, #0x8]
    2248:      	ldr	x8, [x1]
    224c:      	cbz	x8, 0x2280 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x5c>
    2250:      	adrp	x3, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2254:      	add	x3, x3, #0x0
    2258:      	adrp	x4, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    225c:      	add	x4, x4, #0x0
    2260:      	mov	w0, #0x3                ; =3
    2264:      	mov	x2, #0x0                ; =0
    2268:      	blr	x8
    226c:      	cbz	x0, 0x2300 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xdc>
    2270:      	ldr	d0, [x0, #0x10]
    2274:      	ldr	q1, [x0]
    2278:      	stur	q1, [x19, #0x18]
    227c:      	str	d0, [x19, #0x28]
    2280:      	ldrb	w8, [sp, #0x18]
    2284:      	cmp	w8, #0x1
    2288:      	b.ne	0x2294 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x70>
    228c:      	ldr	x0, [sp, #0x10]
    2290:      	bl	0x2290 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x6c>
    2294:      	add	x8, sp, #0x8
    2298:      	mov	w0, #0xa                ; =10
    229c:      	bl	0x229c <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x78>
    22a0:      	ldr	x1, [sp, #0x8]
    22a4:      	ldr	x8, [x1]
    22a8:      	cbz	x8, 0x22dc <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xb8>
    22ac:      	adrp	x3, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    22b0:      	add	x3, x3, #0x0
    22b4:      	adrp	x4, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    22b8:      	add	x4, x4, #0x0
    22bc:      	mov	w0, #0x3                ; =3
    22c0:      	mov	x2, #0x0                ; =0
    22c4:      	blr	x8
    22c8:      	cbz	x0, 0x2308 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xe4>
    22cc:      	ldr	d0, [x0, #0x10]
    22d0:      	ldr	q1, [x0]
    22d4:      	str	q1, [x19]
    22d8:      	str	d0, [x19, #0x10]
    22dc:      	ldrb	w8, [sp, #0x18]
    22e0:      	cmp	w8, #0x1
    22e4:      	b.ne	0x22f0 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xcc>
    22e8:      	ldr	x0, [sp, #0x10]
    22ec:      	bl	0x22ec <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xc8>
    22f0:      	ldp	x29, x30, [sp, #0x30]
    22f4:      	ldp	x20, x19, [sp, #0x20]
    22f8:      	add	sp, sp, #0x40
    22fc:      	ret
    2300:      	bl	0x2300 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xdc>
    2304:      	b	0x230c <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xe8>
    2308:      	bl	0x2308 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xe4>
    230c:      	brk	#0x1
    2310:      	b	0x2318 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xf4>
    2314:      	bl	0x2314 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0xf0>
    2318:      	mov	x19, x0
    231c:      	ldrb	w8, [sp, #0x18]
    2320:      	cmp	w8, #0x1
    2324:      	b.ne	0x2330 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x10c>
    2328:      	ldr	x0, [sp, #0x10]
    232c:      	bl	0x232c <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x108>
    2330:      	mov	x0, x19
    2334:      	bl	0x2334 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x110>
    2338:      	bl	0x2338 <__ZNK12xrslam_0_5_013XRSLAMManager13GetResultBiasEP13XRSLAMIMUBias+0x114>

000000000000233c <__ZNK12xrslam_0_5_013XRSLAMManager16GetResultVersionEP18XRSLAMStringOutput>:
    233c:      	stp	x20, x19, [sp, #-0x20]!
    2340:      	stp	x29, x30, [sp, #0x10]
    2344:      	add	x29, sp, #0x10
    2348:      	mov	x19, x1
    234c:      	mov	w8, #0x5                ; =5
    2350:      	str	w8, [x1]
    2354:      	mov	w0, #0xa                ; =10
    2358:      	bl	0x2358 <__ZNK12xrslam_0_5_013XRSLAMManager16GetResultVersionEP18XRSLAMStringOutput+0x1c>
    235c:      	str	x0, [x19, #0x8]
    2360:      	mov	w8, #0x2e30             ; =11824
    2364:      	movk	w8, #0x2e31, lsl #16
    2368:      	str	w8, [x0]
    236c:      	mov	w8, #0x30               ; =48
    2370:      	strh	w8, [x0, #0x4]
    2374:      	ldp	x29, x30, [sp, #0x10]
    2378:      	ldp	x20, x19, [sp], #0x20
    237c:      	ret

0000000000002380 <___clang_call_terminate>:
    2380:      	stp	x29, x30, [sp, #-0x10]!
    2384:      	mov	x29, sp
    2388:      	bl	0x2388 <___clang_call_terminate+0x8>
    238c:      	bl	0x238c <___clang_call_terminate+0xc>

0000000000002390 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc>:
    2390:      	stp	x24, x23, [sp, #-0x40]!
    2394:      	stp	x22, x21, [sp, #0x10]
    2398:      	stp	x20, x19, [sp, #0x20]
    239c:      	stp	x29, x30, [sp, #0x30]
    23a0:      	add	x29, sp, #0x30
    23a4:      	mov	x21, x1
    23a8:      	mov	x19, x0
    23ac:      	mov	x0, x1
    23b0:      	bl	0x23b0 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x20>
    23b4:      	mov	x8, #0x7ffffffffffffff8 ; =9223372036854775800
    23b8:      	cmp	x0, x8
    23bc:      	b.hs	0x2430 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0xa0>
    23c0:      	mov	x20, x0
    23c4:      	cmp	x0, #0x17
    23c8:      	b.hs	0x23dc <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x4c>
    23cc:      	strb	w20, [x19, #0x17]
    23d0:      	mov	x22, x19
    23d4:      	cbnz	x20, 0x2404 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x74>
    23d8:      	b	0x2414 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x84>
    23dc:      	orr	x8, x20, #0x7
    23e0:      	cmp	x8, #0x17
    23e4:      	mov	w9, #0x19               ; =25
    23e8:      	csinc	x23, x9, x8, eq
    23ec:      	mov	x0, x23
    23f0:      	bl	0x23f0 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x60>
    23f4:      	mov	x22, x0
    23f8:      	orr	x8, x23, #0x8000000000000000
    23fc:      	stp	x20, x8, [x19, #0x8]
    2400:      	str	x0, [x19]
    2404:      	mov	x0, x22
    2408:      	mov	x1, x21
    240c:      	mov	x2, x20
    2410:      	bl	0x2410 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0x80>
    2414:      	strb	wzr, [x22, x20]
    2418:      	mov	x0, x19
    241c:      	ldp	x29, x30, [sp, #0x30]
    2420:      	ldp	x20, x19, [sp, #0x20]
    2424:      	ldp	x22, x21, [sp, #0x10]
    2428:      	ldp	x24, x23, [sp], #0x40
    242c:      	ret
    2430:      	bl	0x2430 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc+0xa0>

0000000000002434 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE20__throw_length_errorB8ne200100Ev>:
    2434:      	stp	x29, x30, [sp, #-0x10]!
    2438:      	mov	x29, sp
    243c:      	adrp	x0, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2440:      	add	x0, x0, #0x0
    2444:      	bl	0x2444 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE20__throw_length_errorB8ne200100Ev+0x10>

0000000000002448 <__ZNSt3__120__throw_length_errorB8ne200100EPKc>:
    2448:      	stp	x20, x19, [sp, #-0x20]!
    244c:      	stp	x29, x30, [sp, #0x10]
    2450:      	add	x29, sp, #0x10
    2454:      	mov	x20, x0
    2458:      	mov	w0, #0x10               ; =16
    245c:      	bl	0x245c <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x14>
    2460:      	mov	x19, x0
    2464:      	mov	x1, x20
    2468:      	bl	0x2468 <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x20>
    246c:      	adrp	x1, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2470:      	ldr	x1, [x1]
    2474:      	adrp	x2, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2478:      	ldr	x2, [x2]
    247c:      	mov	x0, x19
    2480:      	bl	0x2480 <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x38>
    2484:      	mov	x20, x0
    2488:      	mov	x0, x19
    248c:      	bl	0x248c <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x44>
    2490:      	mov	x0, x20
    2494:      	bl	0x2494 <__ZNSt3__120__throw_length_errorB8ne200100EPKc+0x4c>

0000000000002498 <__ZNSt12length_errorC1B8ne200100EPKc>:
    2498:      	stp	x29, x30, [sp, #-0x10]!
    249c:      	mov	x29, sp
    24a0:      	bl	0x24a0 <__ZNSt12length_errorC1B8ne200100EPKc+0x8>
    24a4:      	adrp	x8, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    24a8:      	ldr	x8, [x8]
    24ac:      	add	x8, x8, #0x10
    24b0:      	str	x8, [x0]
    24b4:      	ldp	x29, x30, [sp], #0x10
    24b8:      	ret

00000000000024bc <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m>:
    24bc:      	sub	sp, sp, #0x70
    24c0:      	stp	x26, x25, [sp, #0x20]
    24c4:      	stp	x24, x23, [sp, #0x30]
    24c8:      	stp	x22, x21, [sp, #0x40]
    24cc:      	stp	x20, x19, [sp, #0x50]
    24d0:      	stp	x29, x30, [sp, #0x60]
    24d4:      	add	x29, sp, #0x60
    24d8:      	mov	x21, x2
    24dc:      	mov	x20, x1
    24e0:      	mov	x19, x0
    24e4:      	add	x0, sp, #0x8
    24e8:      	mov	x1, x19
    24ec:      	bl	0x24ec <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x30>
    24f0:      	ldrb	w8, [sp, #0x8]
    24f4:      	cmp	w8, #0x1
    24f8:      	b.ne	0x25a4 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xe8>
    24fc:      	ldr	x8, [x19]
    2500:      	ldur	x8, [x8, #-0x18]
    2504:      	add	x4, x19, x8
    2508:      	ldr	x22, [x4, #0x28]
    250c:      	ldr	w24, [x4, #0x8]
    2510:      	ldr	w23, [x4, #0x90]
    2514:      	cmn	w23, #0x1
    2518:      	b.ne	0x2560 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xa4>
    251c:      	add	x8, sp, #0x18
    2520:      	mov	x25, x4
    2524:      	mov	x0, x4
    2528:      	bl	0x2528 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x6c>
    252c:      	adrp	x1, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2530:      	ldr	x1, [x1]
    2534:      	add	x0, sp, #0x18
    2538:      	bl	0x2538 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x7c>
    253c:      	ldr	x8, [x0]
    2540:      	ldr	x8, [x8, #0x38]
    2544:      	mov	w1, #0x20               ; =32
    2548:      	blr	x8
    254c:      	mov	x23, x0
    2550:      	add	x0, sp, #0x18
    2554:      	bl	0x2554 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x98>
    2558:      	mov	x4, x25
    255c:      	str	w23, [x25, #0x90]
    2560:      	mov	w8, #0xb0               ; =176
    2564:      	and	w8, w24, w8
    2568:      	add	x3, x20, x21
    256c:      	cmp	w8, #0x20
    2570:      	csel	x2, x3, x20, eq
    2574:      	sxtb	w5, w23
    2578:      	mov	x0, x22
    257c:      	mov	x1, x20
    2580:      	bl	0x2580 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xc4>
    2584:      	cbnz	x0, 0x25a4 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xe8>
    2588:      	ldr	x8, [x19]
    258c:      	ldur	x8, [x8, #-0x18]
    2590:      	add	x0, x19, x8
    2594:      	ldr	w8, [x0, #0x20]
    2598:      	mov	w9, #0x5                ; =5
    259c:      	orr	w1, w8, w9
    25a0:      	bl	0x25a0 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xe4>
    25a4:      	add	x0, sp, #0x8
    25a8:      	bl	0x25a8 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xec>
    25ac:      	mov	x0, x19
    25b0:      	ldp	x29, x30, [sp, #0x60]
    25b4:      	ldp	x20, x19, [sp, #0x50]
    25b8:      	ldp	x22, x21, [sp, #0x40]
    25bc:      	ldp	x24, x23, [sp, #0x30]
    25c0:      	ldp	x26, x25, [sp, #0x20]
    25c4:      	add	sp, sp, #0x70
    25c8:      	ret
    25cc:      	b	0x25e0 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x124>
    25d0:      	mov	x20, x0
    25d4:      	add	x0, sp, #0x18
    25d8:      	bl	0x25d8 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x11c>
    25dc:      	b	0x25e4 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x128>
    25e0:      	mov	x20, x0
    25e4:      	add	x0, sp, #0x8
    25e8:      	bl	0x25e8 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x12c>
    25ec:      	b	0x25f4 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x138>
    25f0:      	mov	x20, x0
    25f4:      	mov	x0, x20
    25f8:      	bl	0x25f8 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x13c>
    25fc:      	ldr	x8, [x19]
    2600:      	ldur	x8, [x8, #-0x18]
    2604:      	add	x0, x19, x8
    2608:      	bl	0x2608 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x14c>
    260c:      	bl	0x260c <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x150>
    2610:      	b	0x25ac <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0xf0>
    2614:      	mov	x19, x0
    2618:      	bl	0x2618 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x15c>
    261c:      	mov	x0, x19
    2620:      	bl	0x2620 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x164>
    2624:      	bl	0x2624 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m+0x168>

0000000000002628 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_>:
    2628:      	sub	sp, sp, #0x70
    262c:      	stp	x26, x25, [sp, #0x20]
    2630:      	stp	x24, x23, [sp, #0x30]
    2634:      	stp	x22, x21, [sp, #0x40]
    2638:      	stp	x20, x19, [sp, #0x50]
    263c:      	stp	x29, x30, [sp, #0x60]
    2640:      	add	x29, sp, #0x60
    2644:      	mov	x19, x0
    2648:      	cbz	x0, 0x2784 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x15c>
    264c:      	mov	x24, x5
    2650:      	mov	x20, x4
    2654:      	mov	x22, x3
    2658:      	mov	x21, x2
    265c:      	sub	x8, x3, x1
    2660:      	ldr	x9, [x4, #0x18]
    2664:      	subs	x8, x9, x8
    2668:      	csel	x23, x8, xzr, gt
    266c:      	sub	x25, x2, x1
    2670:      	cmp	x25, #0x1
    2674:      	b.lt	0x2694 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x6c>
    2678:      	ldr	x8, [x19]
    267c:      	ldr	x8, [x8, #0x60]
    2680:      	mov	x0, x19
    2684:      	mov	x2, x25
    2688:      	blr	x8
    268c:      	cmp	x0, x25
    2690:      	b.ne	0x2780 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x158>
    2694:      	cmp	x23, #0x1
    2698:      	b.lt	0x274c <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x124>
    269c:      	mov	x8, #0x7ffffffffffffff8 ; =9223372036854775800
    26a0:      	cmp	x23, x8
    26a4:      	b.hs	0x27a4 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x17c>
    26a8:      	cmp	x23, #0x17
    26ac:      	b.hs	0x26bc <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x94>
    26b0:      	strb	w23, [sp, #0x1f]
    26b4:      	add	x25, sp, #0x8
    26b8:      	b	0x26e4 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0xbc>
    26bc:      	orr	x8, x23, #0x7
    26c0:      	cmp	x8, #0x17
    26c4:      	mov	w9, #0x19               ; =25
    26c8:      	csinc	x26, x9, x8, eq
    26cc:      	mov	x0, x26
    26d0:      	bl	0x26d0 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0xa8>
    26d4:      	mov	x25, x0
    26d8:      	orr	x8, x26, #0x8000000000000000
    26dc:      	stp	x23, x8, [sp, #0x10]
    26e0:      	str	x0, [sp, #0x8]
    26e4:      	mov	x0, x25
    26e8:      	mov	x1, x24
    26ec:      	mov	x2, x23
    26f0:      	bl	0x26f0 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0xc8>
    26f4:      	strb	wzr, [x25, x23]
    26f8:      	ldrsb	w8, [sp, #0x1f]
    26fc:      	ldr	x9, [sp, #0x8]
    2700:      	cmp	w8, #0x0
    2704:      	add	x8, sp, #0x8
    2708:      	csel	x1, x9, x8, lt
    270c:      	ldr	x8, [x19]
    2710:      	ldr	x8, [x8, #0x60]
    2714:      	mov	x0, x19
    2718:      	mov	x2, x23
    271c:      	blr	x8
    2720:      	ldrsb	w8, [sp, #0x1f]
    2724:      	tbnz	w8, #0x1f, 0x2734 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x10c>
    2728:      	cmp	x0, x23
    272c:      	b.ne	0x2780 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x158>
    2730:      	b	0x274c <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x124>
    2734:      	ldr	x8, [sp, #0x8]
    2738:      	mov	x24, x0
    273c:      	mov	x0, x8
    2740:      	bl	0x2740 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x118>
    2744:      	cmp	x24, x23
    2748:      	b.ne	0x2780 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x158>
    274c:      	sub	x22, x22, x21
    2750:      	cmp	x22, #0x1
    2754:      	b.lt	0x2778 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x150>
    2758:      	ldr	x8, [x19]
    275c:      	ldr	x8, [x8, #0x60]
    2760:      	mov	x0, x19
    2764:      	mov	x1, x21
    2768:      	mov	x2, x22
    276c:      	blr	x8
    2770:      	cmp	x0, x22
    2774:      	b.ne	0x2780 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x158>
    2778:      	str	xzr, [x20, #0x18]
    277c:      	b	0x2784 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x15c>
    2780:      	mov	x19, #0x0               ; =0
    2784:      	mov	x0, x19
    2788:      	ldp	x29, x30, [sp, #0x60]
    278c:      	ldp	x20, x19, [sp, #0x50]
    2790:      	ldp	x22, x21, [sp, #0x40]
    2794:      	ldp	x24, x23, [sp, #0x30]
    2798:      	ldp	x26, x25, [sp, #0x20]
    279c:      	add	sp, sp, #0x70
    27a0:      	ret
    27a4:      	bl	0x27a4 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x17c>
    27a8:      	mov	x19, x0
    27ac:      	ldrsb	w8, [sp, #0x1f]
    27b0:      	tbz	w8, #0x1f, 0x27bc <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x194>
    27b4:      	ldr	x0, [sp, #0x8]
    27b8:      	bl	0x27b8 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x190>
    27bc:      	mov	x0, x19
    27c0:      	bl	0x27c0 <__ZNSt3__116__pad_and_outputB8ne200100IcNS_11char_traitsIcEEEENS_19ostreambuf_iteratorIT_T0_EES6_PKS4_S8_S8_RNS_8ios_baseES4_+0x198>

00000000000027c4 <__ZNSt3__120__throw_bad_any_castB8ne200100Ev>:
    27c4:      	stp	x29, x30, [sp, #-0x10]!
    27c8:      	mov	x29, sp
    27cc:      	mov	w0, #0x8                ; =8
    27d0:      	bl	0x27d0 <__ZNSt3__120__throw_bad_any_castB8ne200100Ev+0xc>
    27d4:      	str	xzr, [x0]
    27d8:      	bl	0x27d8 <__ZNSt3__120__throw_bad_any_castB8ne200100Ev+0x14>
    27dc:      	adrp	x1, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    27e0:      	ldr	x1, [x1]
    27e4:      	adrp	x2, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    27e8:      	add	x2, x2, #0x0
    27ec:      	bl	0x27ec <__ZNSt3__120__throw_bad_any_castB8ne200100Ev+0x28>

00000000000027f0 <__ZNSt12bad_any_castC1Ev>:
    27f0:      	stp	x29, x30, [sp, #-0x10]!
    27f4:      	mov	x29, sp
    27f8:      	bl	0x27f8 <__ZNSt12bad_any_castC1Ev+0x8>
    27fc:      	adrp	x8, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2800:      	ldr	x8, [x8]
    2804:      	add	x8, x8, #0x10
    2808:      	str	x8, [x0]
    280c:      	ldp	x29, x30, [sp], #0x10
    2810:      	ret

0000000000002814 <__ZNSt12bad_any_castD1Ev>:
    2814:      	b	0x2814 <__ZNSt12bad_any_castD1Ev>

0000000000002818 <__ZNSt3__16vectorIN12xrslam_0_5_08LandmarkENS_9allocatorIS2_EEE20__throw_length_errorB8ne200100Ev>:
    2818:      	stp	x29, x30, [sp, #-0x10]!
    281c:      	mov	x29, sp
    2820:      	adrp	x0, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    2824:      	add	x0, x0, #0x0
    2828:      	bl	0x2828 <__ZNSt3__16vectorIN12xrslam_0_5_08LandmarkENS_9allocatorIS2_EEE20__throw_length_errorB8ne200100Ev+0x10>

000000000000282c <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1>:
    282c:      	stp	x20, x19, [sp, #-0x20]!
    2830:      	stp	x29, x30, [sp, #0x10]
    2834:      	add	x29, sp, #0x10
    2838:      	adrp	x19, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    283c:      	add	x19, x19, #0x0
    2840:      	mov	x0, x19
    2844:      	bl	0x2844 <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1+0x18>
    2848:      	cbz	w0, 0x28c0 <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1+0x94>
    284c:      	mov	x1, x19
    2850:      	str	xzr, [x1, #0x10]!
    2854:      	stp	xzr, xzr, [x19, #0x18]
    2858:      	mov	w8, #0xaba7             ; =43943
    285c:      	movk	w8, #0x32aa, lsl #16
    2860:      	str	x8, [x19, #0x28]
    2864:      	movi.16b	v0, #0x0
    2868:      	stp	q0, q0, [x19, #0x30]
    286c:      	stp	q0, q0, [x19, #0x50]
    2870:      	stp	xzr, x8, [x19, #0x70]
    2874:      	stp	q0, q0, [x19, #0x80]
    2878:      	str	q0, [x19, #0xa0]
    287c:      	str	xzr, [x19, #0xb0]
    2880:      	stp	xzr, xzr, [x19, #0xc0]
    2884:      	mov	x8, #0x3ff0000000000000 ; =4607182418800017408
    2888:      	stp	xzr, x8, [x19, #0xd0]
    288c:      	stp	xzr, xzr, [x19, #0xe8]
    2890:      	str	xzr, [x19, #0xe0]
    2894:      	str	xzr, [x19, #0x100]
    2898:      	strb	wzr, [x19, #0x108]
    289c:      	adrp	x0, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    28a0:      	add	x0, x0, #0x0
    28a4:      	adrp	x2, 0x2000 <__ZNK12xrslam_0_5_013XRSLAMManager18GetResultLandmarksEP15XRSLAMLandmarks+0x10>
    28a8:      	add	x2, x2, #0x0
    28ac:      	bl	0x28ac <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1+0x80>
    28b0:      	mov	x0, x19
    28b4:      	ldp	x29, x30, [sp, #0x10]
    28b8:      	ldp	x20, x19, [sp], #0x20
    28bc:      	b	0x28bc <__ZN12xrslam_0_5_013XRSLAMManager8InstanceEv.cold.1+0x90>
    28c0:      	ldp	x29, x30, [sp, #0x10]
    28c4:      	ldp	x20, x19, [sp], #0x20
    28c8:      	ret

Disassembly of section __TEXT,__StaticInit:

0000000000002b68 <ltmp3>:
    2b68:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2b6c:      	ldrb	w9, [x8]
    2b70:      	tbnz	w9, #0x0, 0x2b7c <ltmp3+0x14>
    2b74:      	mov	w9, #0x1                ; =1
    2b78:      	strb	w9, [x8]
    2b7c:      	ret

0000000000002b80 <___cxx_global_var_init.6>:
    2b80:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2b84:      	ldrb	w9, [x8]
    2b88:      	tbnz	w9, #0x0, 0x2b94 <___cxx_global_var_init.6+0x14>
    2b8c:      	mov	w9, #0x1                ; =1
    2b90:      	strb	w9, [x8]
    2b94:      	ret

0000000000002b98 <___cxx_global_var_init.7>:
    2b98:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2b9c:      	ldrb	w9, [x8]
    2ba0:      	tbnz	w9, #0x0, 0x2bac <___cxx_global_var_init.7+0x14>
    2ba4:      	mov	w9, #0x1                ; =1
    2ba8:      	strb	w9, [x8]
    2bac:      	ret

0000000000002bb0 <___cxx_global_var_init.8>:
    2bb0:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2bb4:      	ldrb	w9, [x8]
    2bb8:      	tbnz	w9, #0x0, 0x2bc4 <___cxx_global_var_init.8+0x14>
    2bbc:      	mov	w9, #0x1                ; =1
    2bc0:      	strb	w9, [x8]
    2bc4:      	ret

0000000000002bc8 <___cxx_global_var_init.9>:
    2bc8:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2bcc:      	ldrb	w9, [x8]
    2bd0:      	tbnz	w9, #0x0, 0x2bdc <___cxx_global_var_init.9+0x14>
    2bd4:      	mov	w9, #0x1                ; =1
    2bd8:      	strb	w9, [x8]
    2bdc:      	ret

0000000000002be0 <___cxx_global_var_init.10>:
    2be0:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2be4:      	ldrb	w9, [x8]
    2be8:      	tbnz	w9, #0x0, 0x2bf4 <___cxx_global_var_init.10+0x14>
    2bec:      	mov	w9, #0x1                ; =1
    2bf0:      	strb	w9, [x8]
    2bf4:      	ret

0000000000002bf8 <___cxx_global_var_init.11>:
    2bf8:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2bfc:      	ldrb	w9, [x8]
    2c00:      	tbnz	w9, #0x0, 0x2c0c <___cxx_global_var_init.11+0x14>
    2c04:      	mov	w9, #0x1                ; =1
    2c08:      	strb	w9, [x8]
    2c0c:      	ret

0000000000002c10 <___cxx_global_var_init.12>:
    2c10:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c14:      	ldrb	w9, [x8]
    2c18:      	tbnz	w9, #0x0, 0x2c24 <___cxx_global_var_init.12+0x14>
    2c1c:      	mov	w9, #0x1                ; =1
    2c20:      	strb	w9, [x8]
    2c24:      	ret

0000000000002c28 <___cxx_global_var_init.13>:
    2c28:      	adrp	x8, 0x2000 <_strlen+0x2000>
    2c2c:      	ldrb	w9, [x8]
    2c30:      	tbnz	w9, #0x0, 0x2c3c <___cxx_global_var_init.13+0x14>
    2c34:      	mov	w9, #0x1                ; =1
    2c38:      	strb	w9, [x8]
    2c3c:      	ret
