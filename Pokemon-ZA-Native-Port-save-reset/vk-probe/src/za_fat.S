/*
 * ZA Native Probe r5 - the fat variant's padding: a .text section of
 * ZA_FAT_TEXT_BYTES of int3 with one real function after the padding, and a
 * .rodata section of ZA_FAT_RODATA_BYTES, so the title's image is the size the
 * recomp's game library would make it. The probe calls the far function and
 * samples rodata. Text is execute-only on native PS5, so it is never read as
 * data. No game content.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef ZA_FAT_TEXT_BYTES
#define ZA_FAT_TEXT_BYTES 0x15e00000
#endif
#ifndef ZA_FAT_RODATA_BYTES
#define ZA_FAT_RODATA_BYTES 0x02800000
#endif

	.section .text.zafat,"ax",@progbits
	.p2align 14
	.globl za_fat_text_start
	.hidden za_fat_text_start
za_fat_text_start:
	.fill ZA_FAT_TEXT_BYTES, 1, 0xcc

	.globl za_fat_function
	.hidden za_fat_function
	.type za_fat_function,@function
za_fat_function:
	/* The function's own distance from the padding's start, so the value
	 * proves the code ran where the linker placed it. */
	leaq za_fat_text_start(%rip), %rax
	leaq za_fat_function(%rip), %rcx
	subq %rax, %rcx
	movq %rcx, %rax
	ret
	.size za_fat_function, .-za_fat_function

	.globl za_fat_text_end
	.hidden za_fat_text_end
za_fat_text_end:

	.section .rodata.zafat,"a",@progbits
	.p2align 14
	.globl za_fat_rodata_start
	.hidden za_fat_rodata_start
za_fat_rodata_start:
	.fill ZA_FAT_RODATA_BYTES, 1, 0x5a
	.globl za_fat_rodata_end
	.hidden za_fat_rodata_end
za_fat_rodata_end:

	.section .note.GNU-stack,"",@progbits
