
build/xcdd/Build/Products/Profile-iphoneos/Runner.app/Runner:	file format mach-o arm64

Disassembly of section __TEXT,__text:

00000001013d789c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage>:
1013d789c:     	sub	sp, sp, #0x170
1013d78a0:     	stp	d13, d12, [sp, #0xf0]
1013d78a4:     	stp	d11, d10, [sp, #0x100]
1013d78a8:     	stp	d9, d8, [sp, #0x110]
1013d78ac:     	stp	x26, x25, [sp, #0x120]
1013d78b0:     	stp	x24, x23, [sp, #0x130]
1013d78b4:     	stp	x22, x21, [sp, #0x140]
1013d78b8:     	stp	x20, x19, [sp, #0x150]
1013d78bc:     	stp	x29, x30, [sp, #0x160]
1013d78c0:     	add	x29, sp, #0x160
1013d78c4:     	ldr	w8, [x1, #0x14]
1013d78c8:     	cbz	w8, 0x1013d78f4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x58>
1013d78cc:     	ldp	x29, x30, [sp, #0x160]
1013d78d0:     	ldp	x20, x19, [sp, #0x150]
1013d78d4:     	ldp	x22, x21, [sp, #0x140]
1013d78d8:     	ldp	x24, x23, [sp, #0x130]
1013d78dc:     	ldp	x26, x25, [sp, #0x120]
1013d78e0:     	ldp	d9, d8, [sp, #0x110]
1013d78e4:     	ldp	d11, d10, [sp, #0x100]
1013d78e8:     	ldp	d13, d12, [sp, #0xf0]
1013d78ec:     	add	sp, sp, #0x170
1013d78f0:     	ret
1013d78f4:     	mov	x20, x1
1013d78f8:     	mov	x19, x0
1013d78fc:     	sub	x8, x29, #0x98
1013d7900:     	bl	0x1013b2c8c <__ZN12xrslam_0_5_05extra8GpuImage12create_imageEv>
1013d7904:     	ldr	x0, [x19]
1013d7908:     	ldr	x8, [x0]
1013d790c:     	ldr	x9, [x8, #0x10]
1013d7910:     	add	x8, sp, #0x60
1013d7914:     	blr	x9
1013d7918:     	ldr	d8, [sp, #0x60]
1013d791c:     	ldr	x0, [x19]
1013d7920:     	ldr	x8, [x0]
1013d7924:     	ldr	x9, [x8, #0x10]
1013d7928:     	add	x8, sp, #0x60
1013d792c:     	blr	x9
1013d7930:     	ldr	d9, [sp, #0x68]
1013d7934:     	ldr	d0, [x20, #0x8]
1013d7938:     	ldur	x8, [x29, #-0x98]
1013d793c:     	str	d0, [x8, #0x8]
1013d7940:     	ldr	x9, [x20, #0x20]
1013d7944:     	cbz	x9, 0x1013d79c0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
1013d7948:     	ldr	w10, [x20, #0x1c]
1013d794c:     	cmp	w10, #0x48
1013d7950:     	b.ne	0x1013d79c0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
1013d7954:     	ldr	w10, [x9, #0x40]
1013d7958:     	cmp	w10, #0x1
1013d795c:     	b.ne	0x1013d79c0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
1013d7960:     	ldr	d10, [x9, #0x20]
1013d7964:     	fcmp	d10, #0.0
1013d7968:     	b.le	0x1013d79c0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
1013d796c:     	ldr	d11, [x9, #0x28]
1013d7970:     	fcmp	d11, #0.0
1013d7974:     	b.le	0x1013d79c0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x124>
1013d7978:     	ldp	d12, d13, [x9, #0x30]
1013d797c:     	stp	xzr, xzr, [x8, #0x18]
1013d7980:     	str	xzr, [x8, #0x28]
1013d7984:     	str	xzr, [x8, #0x38]
1013d7988:     	mov	x9, #0x3ff0000000000000 ; =4607182418800017408
1013d798c:     	str	x9, [x8, #0x50]
1013d7990:     	str	d10, [x8, #0x10]
1013d7994:     	str	d11, [x8, #0x30]
1013d7998:     	stp	d12, d13, [x8, #0x40]
1013d799c:     	mov	w21, #0x1               ; =1
1013d79a0:     	strb	w21, [x8, #0x58]
1013d79a4:     	add	x0, x19, #0x100
1013d79a8:     	bl	0x101fa371c <Instruction+0x9255562b>
1013d79ac:     	stp	d10, d11, [x19, #0x140]
1013d79b0:     	stp	d12, d13, [x19, #0x150]
1013d79b4:     	strb	w21, [x19, #0x160]
1013d79b8:     	add	x0, x19, #0x100
1013d79bc:     	bl	0x101fa3728 <Instruction+0x92555637>
1013d79c0:     	fcvtzs	w8, d8
1013d79c4:     	fcvtzs	w9, d9
1013d79c8:     	mov	w10, #0x42ff0000        ; =1124007936
1013d79cc:     	str	w10, [sp, #0x60]
1013d79d0:     	add	x10, sp, #0x60
1013d79d4:     	orr	x21, x10, #0x8
1013d79d8:     	movi.16b	v0, #0x0
1013d79dc:     	stur	q0, [sp, #0x64]
1013d79e0:     	stur	q0, [sp, #0x74]
1013d79e4:     	stur	q0, [sp, #0x84]
1013d79e8:     	str	q0, [sp, #0x90]
1013d79ec:     	add	x22, x10, #0x50
1013d79f0:     	stp	x21, x22, [sp, #0xa0]
1013d79f4:     	stp	xzr, xzr, [sp, #0xb0]
1013d79f8:     	ldr	w10, [x20, #0x18]
1013d79fc:     	cmp	w10, #0x4
1013d7a00:     	b.eq	0x1013d7c40 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3a4>
1013d7a04:     	cmp	w10, #0x3
1013d7a08:     	b.eq	0x1013d7b28 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x28c>
1013d7a0c:     	cmp	w10, #0x1
1013d7a10:     	b.ne	0x1013d83a4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb08>
1013d7a14:     	ldr	x10, [x20]
1013d7a18:     	ldrsw	x11, [x20, #0x10]
1013d7a1c:     	mov	x24, sp
1013d7a20:     	adrp	x12, 0x1022b8000 <__ZN3fmt2v58internal10basic_dataIvE23ZERO_OR_POWERS_OF_10_32E+0x8>
1013d7a24:     	ldr	d0, [x12, #0x7f0]
1013d7a28:     	str	d0, [sp]
1013d7a2c:     	orr	x23, x24, #0x8
1013d7a30:     	stp	w9, w8, [sp, #0x8]
1013d7a34:     	stp	x10, x10, [sp, #0x10]
1013d7a38:     	movi.16b	v0, #0x0
1013d7a3c:     	stp	q0, q0, [sp, #0x20]
1013d7a40:     	add	x20, x24, #0x50
1013d7a44:     	stp	x23, x20, [sp, #0x40]
1013d7a48:     	smull	x12, w9, w8
1013d7a4c:     	stp	xzr, xzr, [sp, #0x50]
1013d7a50:     	cbz	x12, 0x1013d7a58 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x1bc>
1013d7a54:     	cbz	x10, 0x1013d83cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb30>
1013d7a58:     	sxtw	x9, w9
1013d7a5c:     	sxtw	x8, w8
1013d7a60:     	cmp	w11, #0x0
1013d7a64:     	csel	x11, x8, x11, eq
1013d7a68:     	mov	w12, #0x1               ; =1
1013d7a6c:     	stp	x11, x12, [sp, #0x50]
1013d7a70:     	madd	x9, x11, x9, x10
1013d7a74:     	sub	x10, x9, x11
1013d7a78:     	add	x8, x10, x8
1013d7a7c:     	stp	x8, x9, [sp, #0x20]
1013d7a80:     	mov	x0, sp
1013d7a84:     	bl	0x101a5c430 <__ZN2cv3Mat20updateContinuityFlagEv>
1013d7a88:     	ldr	x8, [sp, #0x98]
1013d7a8c:     	cbz	x8, 0x1013d7ab0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x214>
1013d7a90:     	add	x8, x8, #0x14
1013d7a94:     	ldaxr	w9, [x8]
1013d7a98:     	subs	w9, w9, #0x1
1013d7a9c:     	stlxr	w10, w9, [x8]
1013d7aa0:     	cbnz	w10, 0x1013d7a94 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x1f8>
1013d7aa4:     	b.ne	0x1013d7ab0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x214>
1013d7aa8:     	add	x0, sp, #0x60
1013d7aac:     	bl	0x101a5ccd4 <__ZN2cv3Mat10deallocateEv>
1013d7ab0:     	ldr	w8, [sp, #0x64]
1013d7ab4:     	cmp	w8, #0x1
1013d7ab8:     	b.lt	0x1013d7ad8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x23c>
1013d7abc:     	mov	x8, #0x0                ; =0
1013d7ac0:     	ldr	x9, [sp, #0xa0]
1013d7ac4:     	str	wzr, [x9, x8, lsl #2]
1013d7ac8:     	add	x8, x8, #0x1
1013d7acc:     	ldrsw	x10, [sp, #0x64]
1013d7ad0:     	cmp	x8, x10
1013d7ad4:     	b.lt	0x1013d7ac4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x228>
1013d7ad8:     	ldp	q0, q1, [sp]
1013d7adc:     	stp	q0, q1, [sp, #0x60]
1013d7ae0:     	ldp	q1, q2, [sp, #0x20]
1013d7ae4:     	stp	q1, q2, [sp, #0x80]
1013d7ae8:     	ldr	x0, [sp, #0xa8]
1013d7aec:     	cmp	x0, x22
1013d7af0:     	b.eq	0x1013d7e5c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5c0>
1013d7af4:     	bl	0x1008d5428 <_pw_vt_free>
1013d7af8:     	stp	x21, x22, [sp, #0xa0]
1013d7afc:     	mov	x0, x22
1013d7b00:     	ldr	w9, [sp, #0x4]
1013d7b04:     	orr	x8, x24, #0x4
1013d7b08:     	ldr	x10, [sp, #0x48]
1013d7b0c:     	cmp	w9, #0x2
1013d7b10:     	b.gt	0x1013d7e70 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5d4>
1013d7b14:     	ldr	x9, [x10]
1013d7b18:     	str	x9, [x0]
1013d7b1c:     	ldr	x9, [x10, #0x8]
1013d7b20:     	str	x9, [x0, #0x8]
1013d7b24:     	b	0x1013d7e7c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x5e0>
1013d7b28:     	ldr	x10, [x20]
1013d7b2c:     	ldrsw	x11, [x20, #0x10]
1013d7b30:     	mov	x24, sp
1013d7b34:     	adrp	x12, 0x1022ba000 <__ZTSN4YAML23RepresentationExceptionE+0xc>
1013d7b38:     	ldr	d0, [x12, #0x738]
1013d7b3c:     	str	d0, [sp]
1013d7b40:     	orr	x23, x24, #0x8
1013d7b44:     	stp	w9, w8, [sp, #0x8]
1013d7b48:     	stp	x10, x10, [sp, #0x10]
1013d7b4c:     	movi.16b	v0, #0x0
1013d7b50:     	stp	q0, q0, [sp, #0x20]
1013d7b54:     	add	x20, x24, #0x50
1013d7b58:     	stp	x23, x20, [sp, #0x40]
1013d7b5c:     	smull	x12, w9, w8
1013d7b60:     	stp	xzr, xzr, [sp, #0x50]
1013d7b64:     	cbz	x12, 0x1013d7b6c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x2d0>
1013d7b68:     	cbz	x10, 0x1013d8400 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb64>
1013d7b6c:     	sxtw	x9, w9
1013d7b70:     	sxtw	x8, w8
1013d7b74:     	add	x8, x8, x8, lsl #1
1013d7b78:     	cmp	w11, #0x0
1013d7b7c:     	csel	x11, x8, x11, eq
1013d7b80:     	mov	w12, #0x3               ; =3
1013d7b84:     	stp	x11, x12, [sp, #0x50]
1013d7b88:     	madd	x9, x11, x9, x10
1013d7b8c:     	sub	x10, x9, x11
1013d7b90:     	add	x8, x10, x8
1013d7b94:     	stp	x8, x9, [sp, #0x20]
1013d7b98:     	mov	x0, sp
1013d7b9c:     	bl	0x101a5c430 <__ZN2cv3Mat20updateContinuityFlagEv>
1013d7ba0:     	ldr	x8, [sp, #0x98]
1013d7ba4:     	cbz	x8, 0x1013d7bc8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x32c>
1013d7ba8:     	add	x8, x8, #0x14
1013d7bac:     	ldaxr	w9, [x8]
1013d7bb0:     	subs	w9, w9, #0x1
1013d7bb4:     	stlxr	w10, w9, [x8]
1013d7bb8:     	cbnz	w10, 0x1013d7bac <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x310>
1013d7bbc:     	b.ne	0x1013d7bc8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x32c>
1013d7bc0:     	add	x0, sp, #0x60
1013d7bc4:     	bl	0x101a5ccd4 <__ZN2cv3Mat10deallocateEv>
1013d7bc8:     	ldr	w8, [sp, #0x64]
1013d7bcc:     	cmp	w8, #0x1
1013d7bd0:     	b.lt	0x1013d7bf0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x354>
1013d7bd4:     	mov	x8, #0x0                ; =0
1013d7bd8:     	ldr	x9, [sp, #0xa0]
1013d7bdc:     	str	wzr, [x9, x8, lsl #2]
1013d7be0:     	add	x8, x8, #0x1
1013d7be4:     	ldrsw	x10, [sp, #0x64]
1013d7be8:     	cmp	x8, x10
1013d7bec:     	b.lt	0x1013d7bdc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x340>
1013d7bf0:     	ldp	q0, q1, [sp]
1013d7bf4:     	stp	q0, q1, [sp, #0x60]
1013d7bf8:     	ldp	q1, q2, [sp, #0x20]
1013d7bfc:     	stp	q1, q2, [sp, #0x80]
1013d7c00:     	ldr	x0, [sp, #0xa8]
1013d7c04:     	cmp	x0, x22
1013d7c08:     	b.eq	0x1013d7d54 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4b8>
1013d7c0c:     	bl	0x1008d5428 <_pw_vt_free>
1013d7c10:     	stp	x21, x22, [sp, #0xa0]
1013d7c14:     	mov	x0, x22
1013d7c18:     	ldr	w9, [sp, #0x4]
1013d7c1c:     	orr	x8, x24, #0x4
1013d7c20:     	ldr	x10, [sp, #0x48]
1013d7c24:     	cmp	w9, #0x2
1013d7c28:     	b.gt	0x1013d7d68 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4cc>
1013d7c2c:     	ldr	x9, [x10]
1013d7c30:     	str	x9, [x0]
1013d7c34:     	ldr	x9, [x10, #0x8]
1013d7c38:     	str	x9, [x0, #0x8]
1013d7c3c:     	b	0x1013d7d74 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4d8>
1013d7c40:     	ldr	x10, [x20]
1013d7c44:     	ldrsw	x11, [x20, #0x10]
1013d7c48:     	mov	x24, sp
1013d7c4c:     	adrp	x12, 0x1022ba000 <__ZTSN4YAML23RepresentationExceptionE+0xc>
1013d7c50:     	ldr	d1, [x12, #0x730]
1013d7c54:     	str	d1, [sp]
1013d7c58:     	orr	x23, x24, #0x8
1013d7c5c:     	stp	w9, w8, [sp, #0x8]
1013d7c60:     	stp	x10, x10, [sp, #0x10]
1013d7c64:     	stp	q0, q0, [sp, #0x20]
1013d7c68:     	add	x20, x24, #0x50
1013d7c6c:     	stp	x23, x20, [sp, #0x40]
1013d7c70:     	smull	x12, w9, w8
1013d7c74:     	stp	xzr, xzr, [sp, #0x50]
1013d7c78:     	cbz	x12, 0x1013d7c80 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x3e4>
1013d7c7c:     	cbz	x10, 0x1013d8434 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xb98>
1013d7c80:     	sxtw	x9, w9
1013d7c84:     	sxtw	x8, w8
1013d7c88:     	lsl	x8, x8, #2
1013d7c8c:     	cmp	w11, #0x0
1013d7c90:     	csel	x11, x8, x11, eq
1013d7c94:     	mov	w12, #0x4               ; =4
1013d7c98:     	stp	x11, x12, [sp, #0x50]
1013d7c9c:     	madd	x9, x11, x9, x10
1013d7ca0:     	sub	x10, x9, x11
1013d7ca4:     	add	x8, x10, x8
1013d7ca8:     	stp	x8, x9, [sp, #0x20]
1013d7cac:     	mov	x0, sp
1013d7cb0:     	bl	0x101a5c430 <__ZN2cv3Mat20updateContinuityFlagEv>
1013d7cb4:     	ldr	x8, [sp, #0x98]
1013d7cb8:     	cbz	x8, 0x1013d7cdc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x440>
1013d7cbc:     	add	x8, x8, #0x14
1013d7cc0:     	ldaxr	w9, [x8]
1013d7cc4:     	subs	w9, w9, #0x1
1013d7cc8:     	stlxr	w10, w9, [x8]
1013d7ccc:     	cbnz	w10, 0x1013d7cc0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x424>
1013d7cd0:     	b.ne	0x1013d7cdc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x440>
1013d7cd4:     	add	x0, sp, #0x60
1013d7cd8:     	bl	0x101a5ccd4 <__ZN2cv3Mat10deallocateEv>
1013d7cdc:     	ldr	w8, [sp, #0x64]
1013d7ce0:     	cmp	w8, #0x1
1013d7ce4:     	b.lt	0x1013d7d04 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x468>
1013d7ce8:     	mov	x8, #0x0                ; =0
1013d7cec:     	ldr	x9, [sp, #0xa0]
1013d7cf0:     	str	wzr, [x9, x8, lsl #2]
1013d7cf4:     	add	x8, x8, #0x1
1013d7cf8:     	ldrsw	x10, [sp, #0x64]
1013d7cfc:     	cmp	x8, x10
1013d7d00:     	b.lt	0x1013d7cf0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x454>
1013d7d04:     	ldp	q0, q1, [sp]
1013d7d08:     	stp	q0, q1, [sp, #0x60]
1013d7d0c:     	ldp	q1, q2, [sp, #0x20]
1013d7d10:     	stp	q1, q2, [sp, #0x80]
1013d7d14:     	ldr	x0, [sp, #0xa8]
1013d7d18:     	cmp	x0, x22
1013d7d1c:     	b.eq	0x1013d7dd8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x53c>
1013d7d20:     	bl	0x1008d5428 <_pw_vt_free>
1013d7d24:     	stp	x21, x22, [sp, #0xa0]
1013d7d28:     	mov	x0, x22
1013d7d2c:     	ldr	w9, [sp, #0x4]
1013d7d30:     	orr	x8, x24, #0x4
1013d7d34:     	ldr	x10, [sp, #0x48]
1013d7d38:     	cmp	w9, #0x2
1013d7d3c:     	b.gt	0x1013d7dec <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x550>
1013d7d40:     	ldr	x9, [x10]
1013d7d44:     	str	x9, [x0]
1013d7d48:     	ldr	x9, [x10, #0x8]
1013d7d4c:     	str	x9, [x0, #0x8]
1013d7d50:     	b	0x1013d7df8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x55c>
1013d7d54:     	mov.s	w9, v0[1]
1013d7d58:     	orr	x8, x24, #0x4
1013d7d5c:     	ldr	x10, [sp, #0x48]
1013d7d60:     	cmp	w9, #0x2
1013d7d64:     	b.le	0x1013d7c2c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x390>
1013d7d68:     	ldr	x9, [sp, #0x40]
1013d7d6c:     	stp	x9, x10, [sp, #0xa0]
1013d7d70:     	stp	x23, x20, [sp, #0x40]
1013d7d74:     	mov	w9, #0x42ff0000         ; =1124007936
1013d7d78:     	str	w9, [sp]
1013d7d7c:     	movi.16b	v0, #0x0
1013d7d80:     	stp	q0, q0, [x8]
1013d7d84:     	str	q0, [x8, #0x20]
1013d7d88:     	stur	q0, [x8, #0x2c]
1013d7d8c:     	ldr	x0, [sp, #0x48]
1013d7d90:     	cmp	x0, x20
1013d7d94:     	b.eq	0x1013d7d9c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x500>
1013d7d98:     	bl	0x1008d5428 <_pw_vt_free>
1013d7d9c:     	mov	w8, #0x1010000          ; =16842752
1013d7da0:     	str	w8, [sp]
1013d7da4:     	add	x8, sp, #0x60
1013d7da8:     	stp	x8, xzr, [sp, #0x8]
1013d7dac:     	ldur	x8, [x29, #-0x98]
1013d7db0:     	add	x8, x8, #0x60
1013d7db4:     	mov	w9, #0x2010000          ; =33619968
1013d7db8:     	stur	w9, [x29, #-0x88]
1013d7dbc:     	stp	x8, xzr, [x29, #-0x80]
1013d7dc0:     	mov	x0, sp
1013d7dc4:     	sub	x1, x29, #0x88
1013d7dc8:     	mov	w2, #0x6                ; =6
1013d7dcc:     	mov	w3, #0x0                ; =0
1013d7dd0:     	bl	0x101ac39bc <__ZN2cv8cvtColorERKNS_11_InputArrayERKNS_12_OutputArrayEii>
1013d7dd4:     	b	0x1013d8050 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b4>
1013d7dd8:     	mov.s	w9, v0[1]
1013d7ddc:     	orr	x8, x24, #0x4
1013d7de0:     	ldr	x10, [sp, #0x48]
1013d7de4:     	cmp	w9, #0x2
1013d7de8:     	b.le	0x1013d7d40 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x4a4>
1013d7dec:     	ldr	x9, [sp, #0x40]
1013d7df0:     	stp	x9, x10, [sp, #0xa0]
1013d7df4:     	stp	x23, x20, [sp, #0x40]
1013d7df8:     	mov	w9, #0x42ff0000         ; =1124007936
1013d7dfc:     	str	w9, [sp]
1013d7e00:     	movi.16b	v0, #0x0
1013d7e04:     	stp	q0, q0, [x8]
1013d7e08:     	str	q0, [x8, #0x20]
1013d7e0c:     	stur	q0, [x8, #0x2c]
1013d7e10:     	ldr	x0, [sp, #0x48]
1013d7e14:     	cmp	x0, x20
1013d7e18:     	b.eq	0x1013d7e20 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x584>
1013d7e1c:     	bl	0x1008d5428 <_pw_vt_free>
1013d7e20:     	mov	w8, #0x1010000          ; =16842752
1013d7e24:     	str	w8, [sp]
1013d7e28:     	add	x8, sp, #0x60
1013d7e2c:     	stp	x8, xzr, [sp, #0x8]
1013d7e30:     	ldur	x8, [x29, #-0x98]
1013d7e34:     	add	x8, x8, #0x60
1013d7e38:     	mov	w9, #0x2010000          ; =33619968
1013d7e3c:     	stur	w9, [x29, #-0x88]
1013d7e40:     	stp	x8, xzr, [x29, #-0x80]
1013d7e44:     	mov	x0, sp
1013d7e48:     	sub	x1, x29, #0x88
1013d7e4c:     	mov	w2, #0xa                ; =10
1013d7e50:     	mov	w3, #0x0                ; =0
1013d7e54:     	bl	0x101ac39bc <__ZN2cv8cvtColorERKNS_11_InputArrayERKNS_12_OutputArrayEii>
1013d7e58:     	b	0x1013d8050 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b4>
1013d7e5c:     	mov.s	w9, v0[1]
1013d7e60:     	orr	x8, x24, #0x4
1013d7e64:     	ldr	x10, [sp, #0x48]
1013d7e68:     	cmp	w9, #0x2
1013d7e6c:     	b.le	0x1013d7b14 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x278>
1013d7e70:     	ldr	x9, [sp, #0x40]
1013d7e74:     	stp	x9, x10, [sp, #0xa0]
1013d7e78:     	stp	x23, x20, [sp, #0x40]
1013d7e7c:     	mov	w21, #0x42ff0000        ; =1124007936
1013d7e80:     	str	w21, [sp]
1013d7e84:     	movi.16b	v0, #0x0
1013d7e88:     	stp	q0, q0, [x8]
1013d7e8c:     	str	q0, [x8, #0x20]
1013d7e90:     	stur	q0, [x8, #0x2c]
1013d7e94:     	ldr	x0, [sp, #0x48]
1013d7e98:     	cmp	x0, x20
1013d7e9c:     	b.eq	0x1013d7ea4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x608>
1013d7ea0:     	bl	0x1008d5428 <_pw_vt_free>
1013d7ea4:     	str	w21, [sp]
1013d7ea8:     	mov	x23, sp
1013d7eac:     	orr	x21, x23, #0x8
1013d7eb0:     	movi.16b	v0, #0x0
1013d7eb4:     	stur	q0, [sp, #0x4]
1013d7eb8:     	stur	q0, [sp, #0x14]
1013d7ebc:     	stur	q0, [sp, #0x24]
1013d7ec0:     	str	q0, [sp, #0x30]
1013d7ec4:     	add	x20, x23, #0x50
1013d7ec8:     	stp	x21, x20, [sp, #0x40]
1013d7ecc:     	stp	xzr, xzr, [sp, #0x50]
1013d7ed0:     	mov	w8, #0x2010000          ; =33619968
1013d7ed4:     	stur	w8, [x29, #-0x88]
1013d7ed8:     	stp	x23, xzr, [x29, #-0x80]
1013d7edc:     	add	x0, sp, #0x60
1013d7ee0:     	sub	x1, x29, #0x88
1013d7ee4:     	bl	0x101a24220 <__ZNK2cv3Mat6copyToERKNS_12_OutputArrayE>
1013d7ee8:     	ldur	x24, [x29, #-0x98]
1013d7eec:     	add	x0, x24, #0x60
1013d7ef0:     	cmp	x0, x23
1013d7ef4:     	b.eq	0x1013d7fa8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x70c>
1013d7ef8:     	ldr	x8, [x24, #0x98]
1013d7efc:     	cbz	x8, 0x1013d7f1c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x680>
1013d7f00:     	add	x8, x8, #0x14
1013d7f04:     	ldaxr	w9, [x8]
1013d7f08:     	subs	w9, w9, #0x1
1013d7f0c:     	stlxr	w10, w9, [x8]
1013d7f10:     	cbnz	w10, 0x1013d7f04 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x668>
1013d7f14:     	b.ne	0x1013d7f1c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x680>
1013d7f18:     	bl	0x101a5ccd4 <__ZN2cv3Mat10deallocateEv>
1013d7f1c:     	str	xzr, [x24, #0x98]
1013d7f20:     	movi.16b	v0, #0x0
1013d7f24:     	stp	q0, q0, [x24, #0x70]
1013d7f28:     	ldr	w8, [x24, #0x64]
1013d7f2c:     	cmp	w8, #0x1
1013d7f30:     	b.lt	0x1013d7f50 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6b4>
1013d7f34:     	mov	x8, #0x0                ; =0
1013d7f38:     	ldr	x9, [x24, #0xa0]
1013d7f3c:     	str	wzr, [x9, x8, lsl #2]
1013d7f40:     	add	x8, x8, #0x1
1013d7f44:     	ldrsw	x10, [x24, #0x64]
1013d7f48:     	cmp	x8, x10
1013d7f4c:     	b.lt	0x1013d7f3c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6a0>
1013d7f50:     	ldp	q0, q1, [sp]
1013d7f54:     	stp	q0, q1, [x24, #0x60]
1013d7f58:     	ldp	q1, q2, [sp, #0x20]
1013d7f5c:     	stp	q1, q2, [x24, #0x80]
1013d7f60:     	ldr	x0, [x24, #0xa8]
1013d7f64:     	add	x25, x24, #0xb0
1013d7f68:     	cmp	x0, x25
1013d7f6c:     	b.eq	0x1013d8008 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x76c>
1013d7f70:     	bl	0x1008d5428 <_pw_vt_free>
1013d7f74:     	add	x8, x24, #0x68
1013d7f78:     	stp	x8, x25, [x24, #0xa0]
1013d7f7c:     	ldr	w9, [sp, #0x4]
1013d7f80:     	mov	x0, x25
1013d7f84:     	orr	x8, x23, #0x4
1013d7f88:     	ldr	x10, [sp, #0x48]
1013d7f8c:     	cmp	w9, #0x2
1013d7f90:     	b.gt	0x1013d801c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x780>
1013d7f94:     	ldr	x9, [x10]
1013d7f98:     	str	x9, [x0]
1013d7f9c:     	ldr	x9, [x10, #0x8]
1013d7fa0:     	str	x9, [x0, #0x8]
1013d7fa4:     	b	0x1013d8028 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x78c>
1013d7fa8:     	ldr	x8, [sp, #0x38]
1013d7fac:     	cbz	x8, 0x1013d7fd0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x734>
1013d7fb0:     	add	x8, x8, #0x14
1013d7fb4:     	ldaxr	w9, [x8]
1013d7fb8:     	subs	w9, w9, #0x1
1013d7fbc:     	stlxr	w10, w9, [x8]
1013d7fc0:     	cbnz	w10, 0x1013d7fb4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x718>
1013d7fc4:     	b.ne	0x1013d7fd0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x734>
1013d7fc8:     	mov	x0, sp
1013d7fcc:     	bl	0x101a5ccd4 <__ZN2cv3Mat10deallocateEv>
1013d7fd0:     	ldr	w8, [sp, #0x4]
1013d7fd4:     	str	xzr, [sp, #0x38]
1013d7fd8:     	movi.16b	v0, #0x0
1013d7fdc:     	stp	q0, q0, [sp, #0x10]
1013d7fe0:     	cmp	w8, #0x1
1013d7fe4:     	b.lt	0x1013d8040 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7a4>
1013d7fe8:     	mov	x8, #0x0                ; =0
1013d7fec:     	ldr	x9, [sp, #0x40]
1013d7ff0:     	str	wzr, [x9, x8, lsl #2]
1013d7ff4:     	add	x8, x8, #0x1
1013d7ff8:     	ldrsw	x10, [sp, #0x4]
1013d7ffc:     	cmp	x8, x10
1013d8000:     	b.lt	0x1013d7ff0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x754>
1013d8004:     	b	0x1013d8040 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7a4>
1013d8008:     	mov.s	w9, v0[1]
1013d800c:     	orr	x8, x23, #0x4
1013d8010:     	ldr	x10, [sp, #0x48]
1013d8014:     	cmp	w9, #0x2
1013d8018:     	b.le	0x1013d7f94 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x6f8>
1013d801c:     	ldr	x9, [sp, #0x40]
1013d8020:     	stp	x9, x10, [x24, #0xa0]
1013d8024:     	stp	x21, x20, [sp, #0x40]
1013d8028:     	mov	w9, #0x42ff0000         ; =1124007936
1013d802c:     	str	w9, [sp]
1013d8030:     	movi.16b	v0, #0x0
1013d8034:     	stp	q0, q0, [x8]
1013d8038:     	str	q0, [x8, #0x20]
1013d803c:     	stur	q0, [x8, #0x2c]
1013d8040:     	ldr	x0, [sp, #0x48]
1013d8044:     	cmp	x0, x20
1013d8048:     	b.eq	0x1013d8050 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x7b4>
1013d804c:     	bl	0x1008d5428 <_pw_vt_free>
1013d8050:     	mov	w8, #0x42ff0000         ; =1124007936
1013d8054:     	str	w8, [sp]
1013d8058:     	mov	x23, sp
1013d805c:     	movi.16b	v0, #0x0
1013d8060:     	stur	q0, [sp, #0x4]
1013d8064:     	orr	x21, x23, #0x8
1013d8068:     	stur	q0, [sp, #0x14]
1013d806c:     	stur	q0, [sp, #0x24]
1013d8070:     	str	q0, [sp, #0x30]
1013d8074:     	add	x20, x23, #0x50
1013d8078:     	stp	x21, x20, [sp, #0x40]
1013d807c:     	stp	xzr, xzr, [sp, #0x50]
1013d8080:     	mov	w8, #0x2010000          ; =33619968
1013d8084:     	stur	w8, [x29, #-0x88]
1013d8088:     	stp	x23, xzr, [x29, #-0x80]
1013d808c:     	add	x0, sp, #0x60
1013d8090:     	sub	x1, x29, #0x88
1013d8094:     	bl	0x101a24220 <__ZNK2cv3Mat6copyToERKNS_12_OutputArrayE>
1013d8098:     	ldur	x24, [x29, #-0x98]
1013d809c:     	add	x0, x24, #0xc0
1013d80a0:     	cmp	x0, x23
1013d80a4:     	b.eq	0x1013d8158 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8bc>
1013d80a8:     	ldr	x8, [x24, #0xf8]
1013d80ac:     	cbz	x8, 0x1013d80cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x830>
1013d80b0:     	add	x8, x8, #0x14
1013d80b4:     	ldaxr	w9, [x8]
1013d80b8:     	subs	w9, w9, #0x1
1013d80bc:     	stlxr	w10, w9, [x8]
1013d80c0:     	cbnz	w10, 0x1013d80b4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x818>
1013d80c4:     	b.ne	0x1013d80cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x830>
1013d80c8:     	bl	0x101a5ccd4 <__ZN2cv3Mat10deallocateEv>
1013d80cc:     	str	xzr, [x24, #0xf8]
1013d80d0:     	movi.16b	v0, #0x0
1013d80d4:     	stp	q0, q0, [x24, #0xd0]
1013d80d8:     	ldr	w8, [x24, #0xc4]
1013d80dc:     	cmp	w8, #0x1
1013d80e0:     	b.lt	0x1013d8100 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x864>
1013d80e4:     	mov	x8, #0x0                ; =0
1013d80e8:     	ldr	x9, [x24, #0x100]
1013d80ec:     	str	wzr, [x9, x8, lsl #2]
1013d80f0:     	add	x8, x8, #0x1
1013d80f4:     	ldrsw	x10, [x24, #0xc4]
1013d80f8:     	cmp	x8, x10
1013d80fc:     	b.lt	0x1013d80ec <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x850>
1013d8100:     	ldp	q0, q1, [sp]
1013d8104:     	stp	q0, q1, [x24, #0xc0]
1013d8108:     	ldp	q1, q2, [sp, #0x20]
1013d810c:     	stp	q1, q2, [x24, #0xe0]
1013d8110:     	ldr	x0, [x24, #0x108]
1013d8114:     	add	x25, x24, #0x110
1013d8118:     	cmp	x0, x25
1013d811c:     	b.eq	0x1013d81c4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x928>
1013d8120:     	bl	0x1008d5428 <_pw_vt_free>
1013d8124:     	add	x8, x24, #0xc8
1013d8128:     	stp	x8, x25, [x24, #0x100]
1013d812c:     	ldr	w9, [sp, #0x4]
1013d8130:     	mov	x0, x25
1013d8134:     	orr	x8, x23, #0x4
1013d8138:     	ldr	x10, [sp, #0x48]
1013d813c:     	cmp	w9, #0x2
1013d8140:     	b.gt	0x1013d81d8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x93c>
1013d8144:     	ldr	x9, [x10]
1013d8148:     	str	x9, [x0]
1013d814c:     	ldr	x9, [x10, #0x8]
1013d8150:     	str	x9, [x0, #0x8]
1013d8154:     	b	0x1013d81e4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x948>
1013d8158:     	ldr	x8, [sp, #0x38]
1013d815c:     	cbz	x8, 0x1013d8180 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8e4>
1013d8160:     	add	x8, x8, #0x14
1013d8164:     	ldaxr	w9, [x8]
1013d8168:     	subs	w9, w9, #0x1
1013d816c:     	stlxr	w10, w9, [x8]
1013d8170:     	cbnz	w10, 0x1013d8164 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8c8>
1013d8174:     	b.ne	0x1013d8180 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8e4>
1013d8178:     	mov	x0, sp
1013d817c:     	bl	0x101a5ccd4 <__ZN2cv3Mat10deallocateEv>
1013d8180:     	ldr	w8, [sp, #0x4]
1013d8184:     	str	xzr, [sp, #0x38]
1013d8188:     	movi.16b	v0, #0x0
1013d818c:     	stp	q0, q0, [sp, #0x10]
1013d8190:     	cmp	w8, #0x1
1013d8194:     	b.lt	0x1013d81b4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x918>
1013d8198:     	mov	x8, #0x0                ; =0
1013d819c:     	ldr	x9, [sp, #0x40]
1013d81a0:     	str	wzr, [x9, x8, lsl #2]
1013d81a4:     	add	x8, x8, #0x1
1013d81a8:     	ldrsw	x10, [sp, #0x4]
1013d81ac:     	cmp	x8, x10
1013d81b0:     	b.lt	0x1013d81a0 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x904>
1013d81b4:     	ldr	x0, [sp, #0x48]
1013d81b8:     	cmp	x0, x20
1013d81bc:     	b.ne	0x1013d8208 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x96c>
1013d81c0:     	b	0x1013d820c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x970>
1013d81c4:     	mov.s	w9, v0[1]
1013d81c8:     	orr	x8, x23, #0x4
1013d81cc:     	ldr	x10, [sp, #0x48]
1013d81d0:     	cmp	w9, #0x2
1013d81d4:     	b.le	0x1013d8144 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x8a8>
1013d81d8:     	ldr	x9, [sp, #0x40]
1013d81dc:     	stp	x9, x10, [x24, #0x100]
1013d81e0:     	stp	x21, x20, [sp, #0x40]
1013d81e4:     	mov	w9, #0x42ff0000         ; =1124007936
1013d81e8:     	str	w9, [sp]
1013d81ec:     	movi.16b	v0, #0x0
1013d81f0:     	stp	q0, q0, [x8]
1013d81f4:     	str	q0, [x8, #0x20]
1013d81f8:     	stur	q0, [x8, #0x2c]
1013d81fc:     	ldr	x0, [sp, #0x48]
1013d8200:     	cmp	x0, x20
1013d8204:     	b.eq	0x1013d820c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x970>
1013d8208:     	bl	0x1008d5428 <_pw_vt_free>
1013d820c:     	ldur	x0, [x29, #-0x98]
1013d8210:     	cbz	x0, 0x1013d8280 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9e4>
1013d8214:     	adrp	x1, 0x102562000 <__ZTVNSt3__123__match_any_but_newlineIcEE+0x28>
1013d8218:     	add	x1, x1, #0x8a8
1013d821c:     	adrp	x2, 0x102562000 <__ZTVNSt3__123__match_any_but_newlineIcEE+0x28>
1013d8220:     	add	x2, x2, #0x930
1013d8224:     	mov	x3, #0x0                ; =0
1013d8228:     	bl	0x101fa3b18 <Instruction+0x92555a27>
1013d822c:     	cbz	x0, 0x1013d8280 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9e4>
1013d8230:     	mov	x20, x0
1013d8234:     	ldr	x0, [x19]
1013d8238:     	ldr	x8, [x0]
1013d823c:     	ldr	x8, [x8, #0xe0]
1013d8240:     	blr	x8
1013d8244:     	fmov	d8, d0
1013d8248:     	ldr	x0, [x19]
1013d824c:     	ldr	x8, [x0]
1013d8250:     	ldr	x8, [x8, #0xe8]
1013d8254:     	blr	x8
1013d8258:     	mov	x21, x0
1013d825c:     	ldr	x0, [x19]
1013d8260:     	ldr	x8, [x0]
1013d8264:     	ldr	x8, [x8, #0xf0]
1013d8268:     	blr	x8
1013d826c:     	mov	x2, x0
1013d8270:     	mov	x0, x20
1013d8274:     	fmov	d0, d8
1013d8278:     	mov	x1, x21
1013d827c:     	bl	0x1013b2e9c <__ZN12xrslam_0_5_05extra8GpuImage8prefetchEdii>
1013d8280:     	add	x0, x19, #0x18
1013d8284:     	bl	0x101fa371c <Instruction+0x9255562b>
1013d8288:     	ldp	x9, x8, [x29, #-0x98]
1013d828c:     	cbz	x8, 0x1013d82a4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa08>
1013d8290:     	add	x10, x8, #0x8
1013d8294:     	ldxr	x11, [x10]
1013d8298:     	add	x11, x11, #0x1
1013d829c:     	stxr	w12, x11, [x10]
1013d82a0:     	cbnz	w12, 0x1013d8294 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x9f8>
1013d82a4:     	ldr	x20, [x19, #0x60]
1013d82a8:     	stp	x9, x8, [x19, #0x58]
1013d82ac:     	cbz	x20, 0x1013d82c8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa2c>
1013d82b0:     	add	x8, x20, #0x8
1013d82b4:     	ldaxr	x9, [x8]
1013d82b8:     	sub	x10, x9, #0x1
1013d82bc:     	stlxr	w11, x10, [x8]
1013d82c0:     	cbnz	w11, 0x1013d82b4 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa18>
1013d82c4:     	cbz	x9, 0x1013d82fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa60>
1013d82c8:     	add	x0, x19, #0x18
1013d82cc:     	bl	0x101fa3728 <Instruction+0x92555637>
1013d82d0:     	ldr	x8, [sp, #0x98]
1013d82d4:     	cbz	x8, 0x1013d8324 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa88>
1013d82d8:     	add	x8, x8, #0x14
1013d82dc:     	ldaxr	w9, [x8]
1013d82e0:     	subs	w9, w9, #0x1
1013d82e4:     	stlxr	w10, w9, [x8]
1013d82e8:     	cbnz	w10, 0x1013d82dc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa40>
1013d82ec:     	b.ne	0x1013d8324 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa88>
1013d82f0:     	add	x0, sp, #0x60
1013d82f4:     	bl	0x101a5ccd4 <__ZN2cv3Mat10deallocateEv>
1013d82f8:     	b	0x1013d8324 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa88>
1013d82fc:     	ldr	x8, [x20]
1013d8300:     	ldr	x8, [x8, #0x10]
1013d8304:     	mov	x0, x20
1013d8308:     	blr	x8
1013d830c:     	mov	x0, x20
1013d8310:     	bl	0x101fa3638 <Instruction+0x92555547>
1013d8314:     	add	x0, x19, #0x18
1013d8318:     	bl	0x101fa3728 <Instruction+0x92555637>
1013d831c:     	ldr	x8, [sp, #0x98]
1013d8320:     	cbnz	x8, 0x1013d82d8 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xa3c>
1013d8324:     	str	xzr, [sp, #0x98]
1013d8328:     	movi.16b	v0, #0x0
1013d832c:     	stp	q0, q0, [sp, #0x70]
1013d8330:     	ldr	w8, [sp, #0x64]
1013d8334:     	cmp	w8, #0x1
1013d8338:     	b.lt	0x1013d8358 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xabc>
1013d833c:     	mov	x8, #0x0                ; =0
1013d8340:     	ldr	x9, [sp, #0xa0]
1013d8344:     	str	wzr, [x9, x8, lsl #2]
1013d8348:     	add	x8, x8, #0x1
1013d834c:     	ldrsw	x10, [sp, #0x64]
1013d8350:     	cmp	x8, x10
1013d8354:     	b.lt	0x1013d8344 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xaa8>
1013d8358:     	ldr	x0, [sp, #0xa8]
1013d835c:     	cmp	x0, x22
1013d8360:     	b.eq	0x1013d8368 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xacc>
1013d8364:     	bl	0x1008d5428 <_pw_vt_free>
1013d8368:     	ldur	x19, [x29, #-0x90]
1013d836c:     	cbz	x19, 0x1013d78cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x30>
1013d8370:     	add	x8, x19, #0x8
1013d8374:     	ldaxr	x9, [x8]
1013d8378:     	sub	x10, x9, #0x1
1013d837c:     	stlxr	w11, x10, [x8]
1013d8380:     	cbnz	w11, 0x1013d8374 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xad8>
1013d8384:     	cbnz	x9, 0x1013d78cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x30>
1013d8388:     	ldr	x8, [x19]
1013d838c:     	ldr	x8, [x8, #0x10]
1013d8390:     	mov	x0, x19
1013d8394:     	blr	x8
1013d8398:     	mov	x0, x19
1013d839c:     	bl	0x101fa3638 <Instruction+0x92555547>
1013d83a0:     	b	0x1013d78cc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0x30>
1013d83a4:     	adrp	x0, 0x1024f4000 <Instruction+0x92aa5f0f>
1013d83a8:     	ldr	x0, [x0, #0x7e0]
1013d83ac:     	adrp	x1, 0x102178000 <Instruction+0x92729f0f>
1013d83b0:     	add	x1, x1, #0xb1d
1013d83b4:     	mov	w2, #0x1f               ; =31
1013d83b8:     	bl	0x10071c9a8 <__ZNSt3__124__put_character_sequenceB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_PKS4_m>
1013d83bc:     	bl	0x1013d7690 <__ZNSt3__14endlB8ne200100IcNS_11char_traitsIcEEEERNS_13basic_ostreamIT_T0_EES7_>
1013d83c0:     	mov	w0, #-0x1               ; =-1
1013d83c4:     	bl	0x101fa3f8c <Instruction+0x92555e9b>
1013d83c8:     	b	0x1013d8464 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc8>
1013d83cc:     	adrp	x1, 0x102176000 <Instruction+0x92727f0f>
1013d83d0:     	add	x1, x1, #0xfcc
1013d83d4:     	sub	x0, x29, #0x88
1013d83d8:     	bl	0x10083bb04 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc>
1013d83dc:     	adrp	x2, 0x102176000 <Instruction+0x92727f0f>
1013d83e0:     	add	x2, x2, #0xfe9
1013d83e4:     	adrp	x3, 0x102176000 <Instruction+0x92727f0f>
1013d83e8:     	add	x3, x3, #0xfed
1013d83ec:     	sub	x1, x29, #0x88
1013d83f0:     	mov	w0, #-0xd7              ; =-215
1013d83f4:     	mov	w4, #0x224              ; =548
1013d83f8:     	bl	0x101aa8988 <__ZN2cv5errorEiRKNSt3__112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEPKcSA_i>
1013d83fc:     	b	0x1013d8464 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc8>
1013d8400:     	adrp	x1, 0x102176000 <Instruction+0x92727f0f>
1013d8404:     	add	x1, x1, #0xfcc
1013d8408:     	sub	x0, x29, #0x88
1013d840c:     	bl	0x10083bb04 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc>
1013d8410:     	adrp	x2, 0x102176000 <Instruction+0x92727f0f>
1013d8414:     	add	x2, x2, #0xfe9
1013d8418:     	adrp	x3, 0x102176000 <Instruction+0x92727f0f>
1013d841c:     	add	x3, x3, #0xfed
1013d8420:     	sub	x1, x29, #0x88
1013d8424:     	mov	w0, #-0xd7              ; =-215
1013d8428:     	mov	w4, #0x224              ; =548
1013d842c:     	bl	0x101aa8988 <__ZN2cv5errorEiRKNSt3__112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEPKcSA_i>
1013d8430:     	b	0x1013d8464 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbc8>
1013d8434:     	adrp	x1, 0x102176000 <Instruction+0x92727f0f>
1013d8438:     	add	x1, x1, #0xfcc
1013d843c:     	sub	x0, x29, #0x88
1013d8440:     	bl	0x10083bb04 <__ZNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC1B8ne200100ILi0EEEPKc>
1013d8444:     	adrp	x2, 0x102176000 <Instruction+0x92727f0f>
1013d8448:     	add	x2, x2, #0xfe9
1013d844c:     	adrp	x3, 0x102176000 <Instruction+0x92727f0f>
1013d8450:     	add	x3, x3, #0xfed
1013d8454:     	sub	x1, x29, #0x88
1013d8458:     	mov	w0, #-0xd7              ; =-215
1013d845c:     	mov	w4, #0x224              ; =548
1013d8460:     	bl	0x101aa8988 <__ZN2cv5errorEiRKNSt3__112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEPKcSA_i>
1013d8464:     	brk	#0x1
1013d8468:     	mov	x19, x0
1013d846c:     	sub	x0, x29, #0x98
1013d8470:     	bl	0x1012c1908 <__ZZN20pw_xrslam_ceres_1_148internal11ParallelForEPNS0_11ContextImplEiiiRKNSt3__18functionIFviiEEEEN3$_1D1Ev>
1013d8474:     	mov	x0, x19
1013d8478:     	bl	0x101fa2ffc <Instruction+0x92554f0b>
1013d847c:     	b	0x1013d8484 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbe8>
1013d8480:     	b	0x1013d8484 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xbe8>
1013d8484:     	mov	x19, x0
1013d8488:     	ldursb	w8, [x29, #-0x71]
1013d848c:     	tbz	w8, #0x1f, 0x1013d854c <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcb0>
1013d8490:     	ldur	x0, [x29, #-0x88]
1013d8494:     	bl	0x101fa39ec <Instruction+0x925558fb>
1013d8498:     	add	x0, sp, #0x60
1013d849c:     	bl	0x1012dbe84 <__ZN2cv3MatD1Ev>
1013d84a0:     	sub	x0, x29, #0x98
1013d84a4:     	bl	0x1012c1908 <__ZZN20pw_xrslam_ceres_1_148internal11ParallelForEPNS0_11ContextImplEiiiRKNSt3__18functionIFviiEEEEN3$_1D1Ev>
1013d84a8:     	mov	x0, x19
1013d84ac:     	bl	0x101fa2ffc <Instruction+0x92554f0b>
1013d84b0:     	b	0x1013d84fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
1013d84b4:     	bl	0x100004230 <___clang_call_terminate>
1013d84b8:     	bl	0x100004230 <___clang_call_terminate>
1013d84bc:     	bl	0x100004230 <___clang_call_terminate>
1013d84c0:     	bl	0x100004230 <___clang_call_terminate>
1013d84c4:     	b	0x1013d84fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
1013d84c8:     	b	0x1013d84fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
1013d84cc:     	b	0x1013d84fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
1013d84d0:     	b	0x1013d84fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
1013d84d4:     	b	0x1013d8548 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
1013d84d8:     	b	0x1013d8548 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
1013d84dc:     	b	0x1013d8548 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
1013d84e0:     	b	0x1013d8548 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
1013d84e4:     	b	0x1013d8548 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
1013d84e8:     	b	0x1013d8548 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
1013d84ec:     	b	0x1013d84fc <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xc60>
1013d84f0:     	bl	0x100004230 <___clang_call_terminate>
1013d84f4:     	bl	0x100004230 <___clang_call_terminate>
1013d84f8:     	b	0x1013d8548 <__ZN12xrslam_0_5_013XRSLAMManager9PushImageEP11XRSLAMImage+0xcac>
1013d84fc:     	mov	x19, x0
1013d8500:     	mov	x0, sp
1013d8504:     	bl	0x1012dbe84 <__ZN2cv3MatD1Ev>
1013d8508:     	add	x0, sp, #0x60
1013d850c:     	bl	0x1012dbe84 <__ZN2cv3MatD1Ev>
1013d8510:     	sub	x0, x29, #0x98
1013d8514:     	bl	0x1012c1908 <__ZZN20pw_xrslam_ceres_1_148internal11ParallelForEPNS0_11ContextImplEiiiRKNSt3__18functionIFviiEEEEN3$_1D1Ev>
1013d8518:     	mov	x0, x19
1013d851c:     	bl	0x101fa2ffc <Instruction+0x92554f0b>
1013d8520:     	mov	x19, x0
1013d8524:     	sub	x0, x29, #0x98
1013d8528:     	bl	0x1012c1908 <__ZZN20pw_xrslam_ceres_1_148internal11ParallelForEPNS0_11ContextImplEiiiRKNSt3__18functionIFviiEEEEN3$_1D1Ev>
1013d852c:     	mov	x0, x19
1013d8530:     	bl	0x101fa2ffc <Instruction+0x92554f0b>
1013d8534:     	mov	x19, x0
1013d8538:     	sub	x0, x29, #0x98
1013d853c:     	bl	0x1012c1908 <__ZZN20pw_xrslam_ceres_1_148internal11ParallelForEPNS0_11ContextImplEiiiRKNSt3__18functionIFviiEEEEN3$_1D1Ev>
1013d8540:     	mov	x0, x19
1013d8544:     	bl	0x101fa2ffc <Instruction+0x92554f0b>
1013d8548:     	mov	x19, x0
1013d854c:     	add	x0, sp, #0x60
1013d8550:     	bl	0x1012dbe84 <__ZN2cv3MatD1Ev>
1013d8554:     	sub	x0, x29, #0x98
1013d8558:     	bl	0x1012c1908 <__ZZN20pw_xrslam_ceres_1_148internal11ParallelForEPNS0_11ContextImplEiiiRKNSt3__18functionIFviiEEEEN3$_1D1Ev>
1013d855c:     	mov	x0, x19
1013d8560:     	bl	0x101fa2ffc <Instruction+0x92554f0b>
