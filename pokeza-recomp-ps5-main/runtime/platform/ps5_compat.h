// What the PS5 title's libc (FreeBSD 11 userland headers; libSceLibcInternal + libkernel at run time) differs in from
// Linux / mingw (included via runtime/platform.h with -DZA_PS5 only). Functions that exist in the headers but not for a
// title at run time are the link-time matter of tools/ps5/compile-runtime.sh's symbol audit and
// Pokemon-ZA-Native-Port/analysis/ps5-runtime-compile-gaps.md: access() (EPERM for every path), opendir / readdir
// (the platform layer's), clock_nanosleep, gmtime_r / localtime_r, dladdr, backtrace, readlink, localeconv (an empty
// decimal point), strcasestr / mkstemp (null imports).
#pragma once
#include <dirent.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#ifndef MAP_NORESERVE
#define MAP_NORESERVE 0  // (no overcommit flag on the console: anonymous mappings count against the flexible budget)
#endif

#ifdef __cplusplus
extern "C" {
#endif
// Host stacks for guest threads and fibers (runtime/platform/ps5.c): a range in the reserved stack arena, backed by
// direct memory on first touch, with an unbacked guard below it. plat_thread_stack_size: the per-thread size
// (LARECOMP_PS5_STACK_MB, default 32 MiB). NULL = the arena is used up.
void *plat_stack_alloc(size_t size);
void plat_stack_free(void *base, size_t size);
int plat_stack_prepare_thread(void *base, size_t size);
size_t plat_thread_stack_size(void);

// Directory streams: the platform layer's (through getdents; libc's opendir is refused to a title), reached by name
// here rather than through the link recipe's --defsym, with telldir / seekdir kept by the title itself (ps5.c): the
// SDK has none for its DIR, and libSceLibcInternal's would take it for libc's.
DIR *za_opendir(const char *path);
DIR *za_fdopendir(int fd);
struct dirent *za_readdir(DIR *d);
void za_rewinddir(DIR *d);
int za_closedir(DIR *d);
long za_telldir(DIR *d);
void za_seekdir(DIR *d, long pos);
#define opendir za_opendir
#define fdopendir za_fdopendir
#define readdir za_readdir
#define rewinddir za_rewinddir
#define closedir za_closedir
#define telldir za_telldir
#define seekdir za_seekdir

// Numbers in the C locale (ps5.c): the console's own strtod sees an empty decimal point and reads "0.62" as 0
// (settings.c's volume, mouse_sens, diff_damage; the LARECOMP_* fractions).
double plat_strtod(const char *s, char **end);
#define strtod plat_strtod
#define strtof(s, end) ((float)plat_strtod((s), (end)))
#define atof(s) plat_strtod((s), NULL)
#ifdef __cplusplus
}
#endif
