// PS5 host layer (runtime/platform.h): a homebrew title on firmware 13.60, built with the PS5 payload SDK fork and
// linked with RADV (ENVIRONMENT.md: the pins; Makefile: PLATFORM=ps5). x86-64 only (Zen 2).
//
// Every function says what is proven on the console and what is not:
//   [proven r2]   measured by the native probe (Pokemon-ZA-Native-Port/native-probe/src/probe.cpp) on 13.60
//   [proven r4]   measured by the Vulkan probe (Pokemon-ZA-Native-Port/vk-probe/src/za_vk_probe.c) on 13.60
//   [TODO verify] written from the toolchain / platform documentation (analysis/ps5-toolchain-capabilities.md,
//                 PS5_PayloadSDK/platform/docs/PROBE.md), not yet run on the console
//
// Memory model. The guest window (GUEST_LO..GUEST_HI: 32 GiB of address space, runtime/rt.h) is reserved exactly there
// with sceKernelReserveVirtualRange [proven r2]; a reservation backs nothing. Backing is direct memory (the 12 GiB pool:
// a title's flexible budget is ~400 MiB and can't hold the game), allocated and mapped at fixed addresses inside the
// reservation in 64 KiB units [proven r2 for one unit]: eagerly by plat_commit (the kernel's region_add, the NSO loader,
// the HLE heap and the Vulkan host import all call it before the guest or the OS writes there), and as a safety net on
// the first touch of an unbacked page by the SIGSEGV handler, as Windows' lazy commit (runtime/platform/windows.c) -
// counted and logged, so paths that bypass plat_commit show up [TODO verify: SIGSEGV with si_addr for a reserved,
// unmapped page; sceKernelMapDirectMemory from a signal handler]. Host stacks for guest threads and fibers come from a
// second reserved range (the stack arena, right above the guest window) backed the same lazy way: libkernel takes
// pthread stacks from the flexible budget (64 KiB by default; the SDK's --wrap=pthread_create gives 2 MiB of direct
// memory to threads that ask for nothing), and 48 guest threads of 256 MiB (runtime/kernel.c on the PC) could never
// come from there. See plat_stack_alloc for the sizes and why.
#include <cpuid.h>
#include <dirent.h>
#include <errno.h>
#include <execinfo.h>  // backtrace: the link recipe binds it to the platform's ps5_backtrace (PS5_Vulkan/tools/radv-link.sh)
#include <fcntl.h>
#include <math.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>

#include "../platform.h"
#include "ps5_fiber.h"

// The SDK fork's declarations of the console's libkernel (ps5platform/kernel.h), its stderr-to-klog helper
// (ps5platform/klog.h) and its libc fill-ins (ps5platform/libc.h: the directory streams below); context.h asserts the
// console's ucontext layout (uc_mcontext 48 bytes later than FreeBSD's: mc_rip below is the faulting instruction only
// with the fork's sys/_ucontext.h).
#include <ps5platform/context.h>
#include <ps5platform/kernel.h>
#include <ps5platform/klog.h>
#include <ps5platform/libc.h>

// Not in ps5platform/kernel.h: the direct-memory allocation the native probe used [proven r2] (libkernel exports it).
int32_t sceKernelAllocateMainDirectMemory(size_t length, size_t alignment, int memory_type, int64_t *physical_start);

// Static destructors of the C++ units (runtime/ui/*.mm, ImGui, VMA) register through __cxa_atexit(fn, obj, &__dso_handle);
// the SDK's crt objects define no __dso_handle and no system module exports one (tools/ps5/compile-runtime.sh found it
// MISSING), so the title defines its own - hidden, as a title exports nothing.
__attribute__((visibility("hidden"))) void *__dso_handle = &__dso_handle;

#define CHUNK 0x10000ull           // direct memory's allocation unit: the commit granularity here (PS5_KERNEL_DIRECT_ALIGNMENT)
#define RESERVE_NO_OVERWRITE 0x80  // sceKernelReserveVirtualRange: refuse rather than replace a mapping [proven r2]
#define RW (PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE)
#define ARENA_BASE 0x7800000000ull  // the stack arena: right above the guest window (GUEST_HI), reserved with it
#define ARENA_SIZE (32ull << 30)    //   48 guest threads x 32 MiB + 1024 fibers x 8 MiB (runtime/hle/fiber.c) fit with room
#define THREAD_STACK_DEFAULT (32ull << 20)
#define DATA_ROOT "/download0/zarecomp"  // the title's writable storage (param.json downloadDataSize > 0) [proven r4: /download0]

#define LOGP(...) fprintf(stderr, "[ps5] " __VA_ARGS__)

// ---- lazily backed reservations (the guest window and the stack arena)
typedef struct {
    const char *name;
    uint64_t base, size;
    uint8_t *backed;  // one bit per chunk: direct memory mapped there
    uint8_t *guard;   // one bit per chunk: a stack guard, never backed (a touch is a stack overflow)
    int64_t *phys;    // per chunk: its direct-memory start (plat_reset_guest releases it)
    uint64_t committed, faults;
} Lazy;

static Lazy g_guest = {.name = "guest window"}, g_arena = {.name = "stack arena"};
static atomic_flag g_lock = ATOMIC_FLAG_INIT;  // (a spinlock: also taken inside the signal handler)

static void lock(void) { while (atomic_flag_test_and_set_explicit(&g_lock, memory_order_acquire)) __builtin_ia32_pause(); }
static void unlock(void) { atomic_flag_clear_explicit(&g_lock, memory_order_release); }
static inline bool bit(const uint8_t *b, uint64_t i) { return (b[i >> 3] >> (i & 7)) & 1; }
static inline void bit_set(uint8_t *b, uint64_t i) { b[i >> 3] |= (uint8_t)(1 << (i & 7)); }
static inline void bit_clear(uint8_t *b, uint64_t i) { b[i >> 3] &= (uint8_t)~(1 << (i & 7)); }
static inline bool in_range(const Lazy *l, uint64_t a) { return l->backed && a >= l->base && a < l->base + l->size; }

static bool reserve_range(uint64_t lo, uint64_t size) {
    void *at = (void *)(uintptr_t)lo;
    int32_t rc = sceKernelReserveVirtualRange(&at, size, PS5_KERNEL_MAP_FIXED | RESERVE_NO_OVERWRITE, PS5_KERNEL_PAGE_SIZE);
    if (rc != 0) {
        LOGP("reserve %llx+%llx: 0x%08x\n", (unsigned long long)lo, (unsigned long long)size, (unsigned)rc);
        return false;
    }
    if (at != (void *)(uintptr_t)lo) {  // (not expected with MAP_FIXED: the range went elsewhere)
        LOGP("reserve %llx landed at %p\n", (unsigned long long)lo, at);
        sceKernelMunmap(at, size);
        return false;
    }
    return true;
}

static bool lazy_init(Lazy *l, uint64_t base, uint64_t size) {
    uint64_t n = size / CHUNK;
    l->base = base;
    l->size = size;
    l->backed = calloc(n / 8 + 1, 1);  // (the title heap: direct memory through the SDK's --wrap=malloc)
    l->guard = calloc(n / 8 + 1, 1);
    l->phys = calloc(n, sizeof *l->phys);
    return l->backed && l->guard && l->phys;
}

// [addr, addr+size) of l backed: direct memory for every unbacked chunk, contiguous runs in one allocation each.
// Lock held. false = the pool is exhausted or the range holds a guard (the caller reports).
static bool commit_locked(Lazy *l, uint64_t addr, uint64_t size) {
    uint64_t first = (addr - l->base) / CHUNK, last = (addr + size - 1 - l->base) / CHUNK;
    for (uint64_t i = first; i <= last;) {
        if (bit(l->backed, i)) { i++; continue; }
        if (bit(l->guard, i)) return false;
        uint64_t j = i;
        while (j <= last && !bit(l->backed, j) && !bit(l->guard, j)) j++;
        uint64_t bytes = (j - i) * CHUNK;
        int64_t phys = 0;
        int32_t rc = sceKernelAllocateMainDirectMemory(bytes, CHUNK, PS5_KERNEL_DIRECT_TYPE_CPU, &phys);  // [proven r2: 64 KiB]
        if (rc != 0) {  // [TODO verify: multi-GB allocations in one call (PROBE.md: up to 11.87 GiB)]
            LOGP("%s: no direct memory for %llu KiB at %llx (0x%08x; %llu MiB committed)\n", l->name,
                 (unsigned long long)(bytes >> 10), (unsigned long long)(l->base + i * CHUNK), (unsigned)rc,
                 (unsigned long long)(l->committed >> 20));
            return false;
        }
        void *want = (void *)(uintptr_t)(l->base + i * CHUNK), *at = want;
        rc = sceKernelMapDirectMemory(&at, bytes, RW, PS5_KERNEL_MAP_FIXED, phys, CHUNK);  // [proven r2: inside a reservation]
        if (rc != 0 || at != want) {
            LOGP("%s: map %llu KiB at %p: 0x%08x (got %p)\n", l->name, (unsigned long long)(bytes >> 10), want, (unsigned)rc, at);
            sceKernelReleaseDirectMemory(phys, bytes);
            return false;
        }
        for (uint64_t k = i; k < j; k++) { bit_set(l->backed, k); l->phys[k] = phys + (int64_t)((k - i) * CHUNK); }
        l->committed += bytes;
        i = j;
    }
    return true;
}

// Everything backed inside [lo, hi) unmapped and released (lock held). Runs contiguous in both addresses go in one call.
static void release_locked(Lazy *l, uint64_t lo, uint64_t hi) {
    uint64_t first = (lo - l->base) / CHUNK, last = (hi - 1 - l->base) / CHUNK;
    for (uint64_t i = first; i <= last;) {
        if (!bit(l->backed, i)) { i++; continue; }
        uint64_t j = i + 1;
        while (j <= last && bit(l->backed, j) && l->phys[j] == l->phys[i] + (int64_t)((j - i) * CHUNK)) j++;
        uint64_t bytes = (j - i) * CHUNK;
        sceKernelMunmap((void *)(uintptr_t)(l->base + i * CHUNK), bytes);
        sceKernelReleaseDirectMemory(l->phys[i], bytes);  // [proven r2: one unit]
        for (uint64_t k = i; k < j; k++) { bit_clear(l->backed, k); l->phys[k] = 0; }
        l->committed -= bytes;
        i = j;
    }
}

// ---- guest address space
bool plat_reserve_guest(uint64_t lo, uint64_t hi) {  // (runtime/main.c: a constructor, before main)
    if (!reserve_range(lo, hi - lo)) return false;  // [proven r2: 0x7000000000 + 32 GiB, exactly there]
    if (!lazy_init(&g_guest, lo, hi - lo)) { LOGP("no memory for the guest window's tables\n"); return false; }
    // the stack arena, claimed now so the Vulkan driver's own reservations (hint-less: the kernel places them) go elsewhere
    if (reserve_range(ARENA_BASE, ARENA_SIZE) && lazy_init(&g_arena, ARENA_BASE, ARENA_SIZE)) return true;
    LOGP("no stack arena: host stacks will come from the flexible budget (mmap), which runs out fast\n");  // [TODO verify]
    return true;
}

void plat_commit(uint64_t addr, uint64_t size) {
    if (!size || !in_range(&g_guest, addr)) return;
    uint64_t lo = addr & ~(CHUNK - 1), hi = (addr + size + CHUNK - 1) & ~(CHUNK - 1);
    lock();
    bool ok = commit_locked(&g_guest, lo, hi - lo);
    unlock();
    if (!ok) {
        fprintf(stderr, "FATAL: cannot back guest memory %llx+%llx with direct memory\n", (unsigned long long)addr,
                (unsigned long long)size);
        abort();
    }
}

// In-place reboot: the window's direct memory released, the window reserved again (fresh zero pages come with the next
// commit). The whole reservation is unmapped in one call [proven r2: munmap of the 32 GiB range with a chunk inside] and
// claimed again; between the two, another thread's mapping could land there [TODO verify: never seen; guest threads are
// stopped by then, the GPU driver's threads are not].
bool plat_reset_guest(uint64_t lo, uint64_t hi) {
    if (!in_range(&g_guest, lo)) return false;
    lock();
    release_locked(&g_guest, lo, hi);
    bool ok = true;
    if (lo == g_guest.base && hi == g_guest.base + g_guest.size) {
        sceKernelMunmap((void *)(uintptr_t)lo, hi - lo);
        ok = reserve_range(lo, hi - lo);
    } else {  // (a part: its pages were released above; the reservation of the rest is untouched) [TODO verify]
        for (uint64_t a = lo; a < hi; a += CHUNK) {
            sceKernelMunmap((void *)(uintptr_t)a, CHUNK);
            ok &= reserve_range(a, CHUNK);
        }
    }
    unlock();
    return ok;
}

int plat_written_pages(uint64_t addr, uint64_t size, uint64_t *pages, int max, uint64_t *page) {  // (no write tracking)
    (void)addr; (void)size; (void)pages; (void)max; (void)page;
    return -1;
}

int plat_protect(uint64_t addr, uint64_t size, int prot) {
    // PLAT_PROT_NONE / READ / RW are 0 / 1 / 3: the console's CPU_READ (1) | CPU_WRITE (2) bits [proven r2: read-only and back]
    return sceKernelMprotect((const void *)(uintptr_t)addr, size, prot) == 0 ? 0 : -1;
}

// ---- host stacks (guest threads: runtime/kernel.c; fibers: runtime/hle/fiber.c)
// Each stack is a range in the arena with an unbacked 64 KiB guard chunk below it, backed on first touch like the guest
// window: a stack costs what the thread actually uses, so the reserved size can be generous without 48 x 256 MiB of
// direct memory. 32 MiB per guest thread (LARECOMP_PS5_STACK_MB): the PC runs 256 MiB reserved and never commits more
// than a few MiB of it (the recompiled game code shows no deep recursion in the PC logs; Windows reports ~9 GB less
// committed with reserve-only stacks), and 48 x 32 MiB = 1.5 GiB of the arena. A touch of the guard is reported as a
// stack overflow by the crash handler. Freed stacks are reused for the same size; their backed pages stay (TODO:
// release them).
typedef struct { uint64_t base, size; } FreeStack;
static FreeStack g_free[256];
static int g_nfree;
static uint64_t g_arena_next;

size_t plat_thread_stack_size(void) {
    const char *e = getenv("LARECOMP_PS5_STACK_MB");
    uint64_t mb = e ? strtoull(e, NULL, 10) : 0;
    return mb ? (size_t)(mb << 20) : (size_t)THREAD_STACK_DEFAULT;
}

void *plat_stack_alloc(size_t size) {
    size = (size + CHUNK - 1) & ~(CHUNK - 1);
    if (!g_arena.backed) {  // no arena: the flexible budget [TODO verify: expect ENOMEM after a few hundred MiB]
        void *p = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
        return p == MAP_FAILED ? NULL : p;
    }
    lock();
    for (int i = 0; i < g_nfree; i++)
        if (g_free[i].size == size) {
            uint64_t b = g_free[i].base;
            g_free[i] = g_free[--g_nfree];
            unlock();
            return (void *)(uintptr_t)b;
        }
    if (!g_arena_next) g_arena_next = g_arena.base;
    if (g_arena_next + CHUNK + size > g_arena.base + g_arena.size) { unlock(); return NULL; }
    bit_set(g_arena.guard, (g_arena_next - g_arena.base) / CHUNK);
    uint64_t b = g_arena_next + CHUNK;
    g_arena_next = b + size;
    unlock();
    return (void *)(uintptr_t)b;
}

void plat_stack_free(void *base, size_t size) {
    size = (size + CHUNK - 1) & ~(CHUNK - 1);
    if (!in_range(&g_arena, (uint64_t)(uintptr_t)base)) { munmap(base, size); return; }
    lock();
    if (g_nfree < (int)(sizeof g_free / sizeof *g_free)) g_free[g_nfree++] = (FreeStack){(uint64_t)(uintptr_t)base, size};
    unlock();
}

// ---- time
// clock_gettime(CLOCK_MONOTONIC) [proven r4] costs ~20 us a call on the console (a syscall); LARECOMP_PS5_TSC=1 reads the
// TSC instead (sceKernelReadTsc, 12 ns; 1,596,300,232 Hz) [TODO verify: its monotonicity across cores on 13.60].
static uint64_t g_tsc_hz;

uint64_t plat_now_ns(void) {
    if (g_tsc_hz) return (uint64_t)((unsigned __int128)sceKernelReadTsc() * 1000000000ull / g_tsc_hz);
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

// nanosleep is relative here (clock_nanosleep with TIMER_ABSTIME is the platform layer's, not libkernel's): sleep all but
// the last 0.3 ms, spin the rest [TODO verify: nanosleep's granularity on the console; the vsync thread needs 16.7 ms].
void plat_sleep_until_ns(uint64_t t) {
    for (;;) {
        uint64_t now = plat_now_ns();
        if (now >= t) return;
        uint64_t left = t - now;
        if (left > 300000) {
            left -= 200000;
            struct timespec ts = {.tv_sec = (time_t)(left / 1000000000ull), .tv_nsec = (long)(left % 1000000000ull)};
            nanosleep(&ts, NULL);
        } else {
            for (int i = 0; i < 32; i++) __builtin_ia32_pause();
        }
    }
}

// The vsync thread above the guest threads: SCHED_FIFO through the POSIX call libkernel exports; refused quietly
// [TODO verify: whether a title may raise a priority; scePthreadSetprio(256 = highest) is the other route].
void plat_thread_realtime(uint64_t period_ns) {
    (void)period_ns;
    struct sched_param sp = {.sched_priority = 1};
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
}

// ---- process
static char g_log_path[1024];

static void mkdirs(const char *path) {
    char p[1024];
    snprintf(p, sizeof p, "%s", path);
    for (char *c = p + 1; *c; c++)
        if (*c == '/') { *c = 0; mkdir(p, 0755); *c = '/'; }
    mkdir(p, 0755);
}

// The recompiled game code is built for x86-64-v3 (Makefile GENARCH): checked with cpuid itself, no libgcc / compiler-rt
// __cpu_model needed (the PS5's Zen 2 has AVX2, FMA and BMI2 [documented]).
static void require_cpu(void) {
    unsigned a = 0, b = 0, c = 0, d = 0;
    bool fma = __get_cpuid(1, &a, &b, &c, &d) && (c & bit_FMA);
    bool avx2 = __get_cpuid_count(7, 0, &a, &b, &c, &d) && (b & bit_AVX2) && (b & bit_BMI2);
    if (fma && avx2) return;
    fprintf(stderr, "FATAL: this CPU lacks AVX2 / FMA / BMI2, which the game code is built for\n");
    exit(1);
}

// The fibers' context switch (runtime/hle/fiber.c on ps5_fiber.h's asm), tried before anything runs on a fiber: on a
// heap stack (the switch alone), then on an arena stack (its first touch backed through the crash handler, as the
// fibers' own stacks will be). A failure is logged, not fatal: the probe title reads the result [TODO verify on
// 13.60]. LARECOMP_PS5_FIBER_SELFTEST=0 skips it.
static void fiber_selftest(void) {
#if ZA_PS5_ASM_FIBERS
    const char *e = getenv("LARECOMP_PS5_FIBER_SELFTEST");
    if (e && *e == '0') return;
    const size_t size = 256 << 10;
    char why[200];
    void *heap = malloc(size);
    bool ok = heap && plat_fiber_selftest(heap, size, why, sizeof why);
    LOGP("fiber self-test on a heap stack: %s\n", ok ? "ok" : heap ? why : "no memory");
    free(heap);
    if (!g_arena.backed) return;
    uint64_t faults = g_arena.faults;
    void *arena = plat_stack_alloc(size);
    ok = arena && plat_fiber_selftest(arena, size, why, sizeof why);
    LOGP("fiber self-test on an arena stack: %s (%llu chunks backed on touch)\n", ok ? "ok" : arena ? why : "no stack",
         (unsigned long long)(g_arena.faults - faults));
    if (arena) plat_stack_free(arena, size);
#endif
}

// First thing in main(): the writable data root (LARECOMP_DATA_ROOT, default /download0/zarecomp; runtime/paths.c
// makes it the working directory), stderr into its lasrecomp.log as the Linux build does without a terminal [TODO
// verify: freopen on a /download0 file; fopen there is proven r4] - or into klog with LARECOMP_PS5_STDERR=klog
// (ps5_klog_capture_stderr [proven r4]) - the GPU driver's shader cache under the data root (set before RADV reads it;
// RADV's own default is the read-only /app0 [proven r4]), the CPU check, and the crash / lazy-commit handler for the
// main thread.
void plat_init(void) {
    const char *root = getenv("LARECOMP_DATA_ROOT");
    if (!root || !*root) { setenv("LARECOMP_DATA_ROOT", DATA_ROOT, 1); root = DATA_ROOT; }
    mkdirs(root);
    const char *mode = getenv("LARECOMP_PS5_STDERR");
    if (mode && !strcmp(mode, "klog")) {
        ps5_klog_capture_stderr("[zarecomp] ");
    } else {
        snprintf(g_log_path, sizeof g_log_path, "%s/lasrecomp.log", root);
        if (!freopen(g_log_path, getenv("LASRECOMP_LOG_APPEND") ? "a" : "w", stderr)) g_log_path[0] = 0;
    }
    char cache[1100];
    snprintf(cache, sizeof cache, "%s/cache/radv", root);
    mkdirs(cache);
    setenv("MESA_SHADER_CACHE_DIR", cache, 1);  // [proven r4: RADV then writes its cache under /download0]
    const char *tsc = getenv("LARECOMP_PS5_TSC");
    if (tsc && *tsc == '1') g_tsc_hz = sceKernelGetTscFrequency();
    require_cpu();
    plat_crash_handler_install();
    fiber_selftest();
    LOGP("data root %s, stderr -> %s, stacks: %s %llx+%llx, guest window %llx+%llx\n", root,
         g_log_path[0] ? g_log_path : "klog", g_arena.backed ? "arena" : "mmap", (unsigned long long)g_arena.base,
         (unsigned long long)g_arena.size, (unsigned long long)g_guest.base, (unsigned long long)g_guest.size);
}

bool plat_exe_path(char *buf, size_t size) {  // the title's image: /app0 is the app's read-only mount [proven r2/r4]
    return (size_t)snprintf(buf, size, "/app0/eboot.bin") < size;
}

void plat_os_name(char *buf, size_t size) {
    struct ps5_kernel_sw_version v = {.size = sizeof v};
    if (sceKernelGetSystemSwVersion(&v) == 0 && v.text[0]) snprintf(buf, size, "PlayStation 5 (%.28s)", v.text);  // [TODO verify]
    else snprintf(buf, size, "PlayStation 5");
}

// No exec in a title (and no fork): the caller (runtime/main.c: the guest window wasn't free) ends with its own error.
void plat_exec(char *const argv[]) {
    (void)argv;
    LOGP("plat_exec: a title cannot replace its process\n");
}

// Without the libc teardown: exit() ends in SIGSYS inside libkernel on this firmware [documented]; _exit is libkernel's.
void plat_terminate(void) { _exit(0); }

// ---- child processes: none on the console (no fork / posix_spawn for a title). The start screen's helpers (the game
// code generator, the seed generator, the button-icon maker) run on the PC beforehand; here they report failure.
PlatProc plat_spawn(const char *const argv[], const char *log_path, bool append_log) {
    (void)log_path; (void)append_log;
    LOGP("plat_spawn: no child processes in a title (%s)\n", argv && argv[0] ? argv[0] : "?");
    return 0;
}
int plat_proc_wait(PlatProc p, bool block) { (void)p; (void)block; return 255; }
void plat_proc_kill(PlatProc p) { (void)p; }

// rm -rf without nftw: opendir / readdir are the platform layer's (the link recipe binds them: libc's fail in a title)
// [TODO verify].
static bool remove_tree(const char *dir, int depth) {
    if (depth > 32) return false;
    DIR *d = opendir(dir);
    if (!d) return false;
    bool ok = true;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char p[2048];
        snprintf(p, sizeof p, "%s/%s", dir, e->d_name);
        struct stat st;
        if (lstat(p, &st) != 0) { ok = false; continue; }
        if (S_ISDIR(st.st_mode)) ok &= remove_tree(p, depth + 1);
        else ok &= unlink(p) == 0;
    }
    closedir(d);
    return ok && rmdir(dir) == 0;
}
bool plat_remove_tree(const char *dir) { return remove_tree(dir, 0); }

// ---- directory streams (ps5_compat.h sends the runtime's opendir .. seekdir here): the platform layer's streams
// (ps5_opendir and family, through getdents), plus telldir / seekdir of the title's own - the SDK has none for its
// DIR, an opaque stream, and libSceLibcInternal's would walk libc's. A position is the count of entries readdir
// returned since the stream was opened or last rewound; seekdir rewinds and reads that many again: bounded by the
// directory's size, and the one caller (runtime/services/fs.c, GetEntryCount) does a telldir / seekdir pair per call
// on directories of a few entries. 64 streams are tracked; beyond them a position reads as 0 and a seekdir rewinds,
// said once [TODO verify on 13.60: the records ps5_readdir returns are the directory's own, "." and ".." included].
#define DIRS 64
typedef struct { DIR *d; long pos; } DirPos;
static DirPos g_dirs[DIRS];
static pthread_mutex_t g_dirs_lock = PTHREAD_MUTEX_INITIALIZER;

static DirPos *dir_slot(DIR *d) {  // (lock held)
    for (int i = 0; i < DIRS; i++) if (g_dirs[i].d == d) return &g_dirs[i];
    return NULL;
}

static DIR *dir_track(DIR *d) {
    if (!d) return NULL;
    pthread_mutex_lock(&g_dirs_lock);
    DirPos *s = dir_slot(NULL);
    if (s) { s->d = d; s->pos = 0; }
    pthread_mutex_unlock(&g_dirs_lock);
    if (!s) {
        static bool said;
        if (!said) { said = true; LOGP("more than %d directory streams open: telldir / seekdir on the rest see the start\n", DIRS); }
    }
    return d;
}

DIR *za_opendir(const char *path) { return dir_track(ps5_opendir(path)); }
DIR *za_fdopendir(int fd) { return dir_track(ps5_fdopendir(fd)); }

struct dirent *za_readdir(DIR *d) {
    struct dirent *e = ps5_readdir(d);
    if (e) {
        pthread_mutex_lock(&g_dirs_lock);
        DirPos *s = dir_slot(d);
        if (s) s->pos++;
        pthread_mutex_unlock(&g_dirs_lock);
    }
    return e;
}

void za_rewinddir(DIR *d) {
    ps5_rewinddir(d);
    pthread_mutex_lock(&g_dirs_lock);
    DirPos *s = dir_slot(d);
    if (s) s->pos = 0;
    pthread_mutex_unlock(&g_dirs_lock);
}

int za_closedir(DIR *d) {
    pthread_mutex_lock(&g_dirs_lock);
    DirPos *s = dir_slot(d);
    if (s) s->d = NULL;
    pthread_mutex_unlock(&g_dirs_lock);
    return ps5_closedir(d);
}

long za_telldir(DIR *d) {
    pthread_mutex_lock(&g_dirs_lock);
    DirPos *s = dir_slot(d);
    long pos = s ? s->pos : 0;
    pthread_mutex_unlock(&g_dirs_lock);
    return pos;
}

void za_seekdir(DIR *d, long pos) {
    za_rewinddir(d);
    for (long i = 0; i < pos; i++)
        if (!za_readdir(d)) break;
}

// ---- numbers (ps5_compat.h sends the runtime's strtod / strtof / atof here): the console's own parse no fraction,
// libSceLibcInternal's locale having an empty decimal point (ps5platform/libc.h; PS5_Vulkan's nlohmann::json read
// 0.62 as 0 through it [documented]). The C locale's syntax: blanks, a sign, digits with one '.', an exponent,
// inf / infinity / nan (no hex, no nan(chars)). The digits go into an integer scaled by a power of ten: one correctly
// rounded multiplication or division for up to 19 digits and exponents within +-22 - all the settings file and the
// LARECOMP_* variables hold - pow() beyond. [TODO verify on the console: whether printf's %f shares the empty point;
// settings.c writes its fractions by hand in case it does.]
double plat_strtod(const char *s, char **end) {
    static const double p10[] = {1e0,  1e1,  1e2,  1e3,  1e4,  1e5,  1e6,  1e7,  1e8,  1e9,  1e10, 1e11,
                                 1e12, 1e13, 1e14, 1e15, 1e16, 1e17, 1e18, 1e19, 1e20, 1e21, 1e22};
    const char *p = s;
    while (*p == ' ' || (*p >= '\t' && *p <= '\r')) p++;
    bool neg = *p == '-';
    if (*p == '-' || *p == '+') p++;
    double v;
    if (!strncasecmp(p, "inf", 3)) {
        p += !strncasecmp(p, "infinity", 8) ? 8 : 3;
        v = INFINITY;
    } else if (!strncasecmp(p, "nan", 3)) {
        p += 3;
        v = NAN;
    } else {
        uint64_t m = 0;
        int exp10 = 0;
        bool any = false, dot = false;
        for (;; p++) {
            if (*p >= '0' && *p <= '9') {
                any = true;
                if (m <= (UINT64_MAX - 9) / 10) { m = m * 10 + (uint64_t)(*p - '0'); if (dot) exp10--; }
                else if (!dot) exp10++;  // (past 19 digits: integer digits scale, fraction digits are dropped)
            } else if (*p == '.' && !dot) {
                dot = true;
            } else {
                break;
            }
        }
        if (!any) {
            if (end) *end = (char *)s;
            return 0;
        }
        if ((*p == 'e' || *p == 'E') &&
            ((p[1] >= '0' && p[1] <= '9') || ((p[1] == '-' || p[1] == '+') && p[2] >= '0' && p[2] <= '9'))) {
            p++;
            bool eneg = *p == '-';
            if (*p == '-' || *p == '+') p++;
            int e = 0;
            for (; *p >= '0' && *p <= '9'; p++) if (e < 100000) e = e * 10 + (*p - '0');
            exp10 += eneg ? -e : e;
        }
        v = (double)m;
        if (exp10 < 0 && exp10 >= -22) v /= p10[-exp10];
        else if (exp10 >= 0 && exp10 <= 22) v *= p10[exp10];
        else if (m) v *= pow(10.0, exp10);
    }
    if (end) *end = (char *)p;
    return neg ? -v : v;
}

int plat_open_file(const char *path, int flags) { return open(path, flags, 0644); }  // [proven r4: open under /download0]

// access() is refused with EPERM for every path in a title [documented]: existence through stat.
int plat_rename(const char *from, const char *to) {
    struct stat st;
    if (stat(to, &st) == 0) { errno = EEXIST; return -1; }
    return rename(from, to);
}

// ---- diagnostics
// No symbol names for host functions (nothing like dladdr with symbols in a title); runtime/dispatch.c names the guest
// ones (f_<addr>) itself from the generated tables.
const char *plat_symbol(uint64_t pc, uint64_t *offset) { (void)pc; (void)offset; return NULL; }

const char *rt_host_fn_name(uint64_t pc, uint64_t *offset);  // runtime/dispatch.c

void plat_print_backtrace(void) {
    void *bt[64];
    int n = backtrace(bt, 64);  // (ps5_backtrace: frame pointers) [TODO verify: -O2 omits them; -fno-omit-frame-pointer]
    for (int i = 0; i < n; i++) {
        uint64_t pc = (uint64_t)(uintptr_t)bt[i], off = 0;
        const char *s = rt_host_fn_name(pc, &off);
        if (s) fprintf(stderr, "  #%-2d %016llx %s+%llx\n", i, (unsigned long long)pc, s, (unsigned long long)off);
        else fprintf(stderr, "  #%-2d %016llx\n", i, (unsigned long long)pc);
    }
}

void plat_fatal_notice(void) {  // nothing reads stderr on the console: the one line that matters also goes to klog
    fflush(stderr);
    char text[1200];
    snprintf(text, sizeof text, "[zarecomp] ZA Recomp stopped because of an error. Details: %s\n",
             g_log_path[0] ? g_log_path : "klog");
    sceKernelDebugOutText(0, text);  // [proven r4]
}

// A fault inside a lazily backed range on an unbacked chunk: back it and resume (the first touch of a page plat_commit
// didn't cover). A fault on a backed chunk is a real one (a watchpoint page, runtime/dispatch.c; or a bug), and a touch
// of a guard chunk is a stack overflow. Two threads on one chunk: the second finds it backed and resumes too.
static bool lazy_fault(uint64_t fa) {
    Lazy *l = in_range(&g_guest, fa) ? &g_guest : in_range(&g_arena, fa) ? &g_arena : NULL;
    if (!l) return false;
    uint64_t i = (fa - l->base) / CHUNK;
    if (bit(l->guard, i)) return false;
    lock();
    bool was = bit(l->backed, i);
    bool ok = was || commit_locked(l, fa & ~(CHUNK - 1), CHUNK);
    if (ok && !was) l->faults++;
    unlock();
    if (was) {  // backed already: a race with another thread's commit (resume), or a protected page (report)
        void *start, *end;
        uint32_t prot = 0;
        if (sceKernelQueryMemoryProtection((void *)(uintptr_t)fa, &start, &end, &prot) != 0) return false;  // [TODO verify]
        return (prot & RW) == RW;
    }
    if (ok && l->faults <= 16) {  // (the first few: which paths bypass plat_commit)
        char line[160];
        snprintf(line, sizeof line, "[ps5] %s: page %llx backed on first touch (%llu so far)\n", l->name,
                 (unsigned long long)(fa & ~(CHUNK - 1)), (unsigned long long)l->faults);
        sceKernelDebugOutText(0, line);
    }
    return ok;
}

static void crash_handler(int sig, siginfo_t *si, void *ctx) {
    ucontext_t *uc = ctx;
    static volatile int depth;
    if (sig == SIGABRT && depth++ > 0) { signal(SIGABRT, SIG_DFL); abort(); }  // (nested: just die)
    uint64_t fa = (uint64_t)(uintptr_t)si->si_addr;
    uint64_t pc = (uint64_t)uc->uc_mcontext.mc_rip, sp = (uint64_t)uc->uc_mcontext.mc_rsp, lr = 0;
    if ((sig == SIGSEGV || sig == SIGBUS) && lazy_fault(fa)) return;
    // x86-64 has no link register: the return address on top of the stack (valid at function entry)
    if (sig != SIGSEGV || (fa & ~0xFFFull) != (sp & ~0xFFFull)) lr = *(uint64_t *)(uintptr_t)sp;
    if (rt_fault_watch(fa, pc)) return;
    char what[48];
    if (in_range(&g_arena, fa) && bit(g_arena.guard, (fa - g_arena.base) / CHUNK)) snprintf(what, sizeof what, "stack overflow");
    else snprintf(what, sizeof what, "signal %d", sig);
    rt_fault_report(what, fa, pc, lr);
}

// Per thread (the alternate stack is per thread; the handlers are process-wide and set once) [TODO verify: SIGSEGV
// delivery with si_addr and the console's ucontext layout - ps5platform/context.h - on 13.60].
void plat_crash_handler_install(void) {
    static __thread bool installed;
    if (installed) return;
    installed = true;
    stack_t ss = {.ss_sp = malloc(1 << 20), .ss_size = 1 << 20};
    sigaltstack(&ss, NULL);
    static bool handlers;
    if (handlers) return;
    handlers = true;
    struct sigaction sa = {0};
    sa.sa_sigaction = crash_handler;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
    sigaction(SIGILL, &sa, NULL);
    sigaction(SIGFPE, &sa, NULL);
    sigaction(SIGABRT, &sa, NULL);
}
