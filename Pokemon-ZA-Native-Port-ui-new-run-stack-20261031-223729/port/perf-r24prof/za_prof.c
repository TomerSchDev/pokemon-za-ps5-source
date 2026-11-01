/* r24-prof: sampling CPU profiler, force60 and the RADV kick thread's registration, for the native title.
 * Off unless /app0/perf-r24-options.txt sets sample=1 / force60=1 (the title entry turns those into ZA_PROF_* /
 * ZA_PERF_FORCE60 before the runtime starts); off, every hook below is one relaxed atomic load.
 *
 * Sampling: a sampler thread sends SIGPROF with pthread_kill to the render thread every period, and - unless
 * sample_threads=render - to the next guest thread too (round robin), so about two samples per period. The handler
 * records the interrupted RIP and one caller ([RBP+8] when RBP lies inside the thread's own stack above RSP,
 * za_prof_core.h) into a preallocated ring; every window the sampler thread writes the ring to a bounded file
 * under /download0/zarecomp/r24prof and prints one klog line. The handler takes no lock, allocates nothing, does
 * no stdio and touches no thread-local storage (the title's TLS is emulated).
 * Threads: guest threads register in kernel.c's thread_main, the render thread is marked at its first
 * nvnQueueSubmitCommands (objects.c), and RADV's kick thread at its first sceAgcSuspendPoint (link --wrap). */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <pthread_np.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>

#include "za_prof_core.h"

int sceKernelDebugOutText(int channel, const char *text);
uint64_t sceKernelReadTsc(void);
uint64_t sceKernelGetTscFrequency(void);
int sceKernelVirtualQuery(const void *addr, int flags, void *info, size_t info_size);

#define ZP_DIR "/download0/zarecomp/r24prof"
#define ZP_RING_CAP (1u << 16)  /* 65,536 records (1.5 MiB): one window at the default rate is about 40,000 */
#define ZP_SIG SIGPROF

static _Atomic int g_enabled;          /* sampling on (set once by za_prof_start, before any guest thread) */
static ZpRegistry g_reg;
static ZpRing g_ring;
static uint64_t g_text_lo, g_text_hi;  /* the eboot's text mapping (sceKernelVirtualQuery); 0/0 = unknown */
static _Atomic int g_render_slot = -1;
static _Atomic uintptr_t g_render_tid;
static _Atomic int g_kick_registered;
static _Atomic uint32_t g_unknown;     /* signals that found no registered thread */
static unsigned g_period_us = 1000, g_window_s = 20, g_keep = 30;
static bool g_render_only;
static uint64_t g_boot;

static void zp_log(const char *line) { sceKernelDebugOutText(0, line); }

/* (a fixed function whose runtime address, with its address in the PIE, gives the image base offline) */
__attribute__((noinline, used)) void za_prof_anchor(void) { __asm__ volatile(""); }

/* ------------------------------------------------------------------ signal handler */
static uint64_t zp_read_u64(uint64_t addr) { return *(const volatile uint64_t *)(uintptr_t)addr; }

static void zp_handler(int sig, siginfo_t *si, void *ctx) {
    (void)sig, (void)si;
    const ucontext_t *uc = ctx;
    zp_on_sample(&g_reg, &g_ring, (uintptr_t)pthread_self(), (uint64_t)uc->uc_mcontext.mc_rip,
                 (uint64_t)uc->uc_mcontext.mc_rsp, (uint64_t)uc->uc_mcontext.mc_rbp, g_text_lo, g_text_hi,
                 zp_read_u64, &g_unknown);
}

/* ------------------------------------------------------------------ registration (normal context) */
static void zp_stack_of_self(uintptr_t *lo, uintptr_t *hi) {
    pthread_attr_t a;
    void *addr = NULL;
    size_t size = 0;
    *lo = *hi = 0;
    if (pthread_attr_init(&a) != 0) return;
    if (pthread_attr_get_np(pthread_self(), &a) == 0 && pthread_attr_getstack(&a, &addr, &size) == 0 && addr && size)
        *lo = (uintptr_t)addr, *hi = (uintptr_t)addr + size;
    pthread_attr_destroy(&a);
}

static int zp_register_self(int kind, const char *name, uint64_t gid, uint64_t entry, int32_t prio) {
    uintptr_t self = (uintptr_t)pthread_self();
    int i = zp_lookup(&g_reg, self);
    if (i >= 0) return i;
    i = zp_claim(&g_reg);
    if (i < 0) {
        static _Atomic int warned;
        if (!atomic_exchange(&warned, 1)) zp_log("[za-r24prof] registry full: further threads are not sampled\n");
        return -1;
    }
    uintptr_t lo, hi;
    zp_stack_of_self(&lo, &hi);
    zp_publish(&g_reg, i, self, kind, gid, entry, prio, lo, hi, name);
    return i;
}

/* kernel.c thread_main: a guest thread starts / ends (its own host thread). */
void za_prof_thread_begin(uint64_t gid, uint64_t entry, int prio) {
    if (!atomic_load_explicit(&g_enabled, memory_order_relaxed)) return;
    char name[ZP_NAME];
    snprintf(name, sizeof name, "g%llx", (unsigned long long)gid);
    zp_register_self(ZP_KIND_GUEST, name, gid, entry, prio);
}

void za_prof_thread_end(void) {
    if (!atomic_load_explicit(&g_enabled, memory_order_relaxed)) return;
    int i = zp_lookup(&g_reg, (uintptr_t)pthread_self());
    if (i < 0) return;
    if (atomic_load(&g_render_slot) == i) atomic_store(&g_render_slot, -1), atomic_store(&g_render_tid, 0);
    zp_end(&g_reg, i);
}

/* objects.c nvnQueueSubmitCommands: the thread that executes command lists. */
void za_prof_note_render(void) {
    if (!atomic_load_explicit(&g_enabled, memory_order_relaxed)) return;
    uintptr_t self = (uintptr_t)pthread_self();
    if (atomic_load_explicit(&g_render_tid, memory_order_relaxed) == self) return;
    int i = zp_lookup(&g_reg, self);
    if (i < 0) i = zp_register_self(ZP_KIND_RENDER, "render-host", 0, 0, 0);
    if (i < 0) return;
    int old = atomic_exchange(&g_render_slot, i);
    if (old >= 0 && old != i) atomic_store(&g_reg.t[old].kind, ZP_KIND_GUEST);
    atomic_store(&g_reg.t[i].kind, ZP_KIND_RENDER);
    atomic_store(&g_render_tid, self);
    char line[160];
    snprintf(line, sizeof line, "[za-r24prof] render thread: slot %d (%s, guest entry %llx)\n", i, g_reg.t[i].name,
             (unsigned long long)g_reg.t[i].entry);
    zp_log(line);
}

/* RADV's kick thread (radv_ps5_platform.c radv_ps5_kick_body) is the only caller of sceAgcSuspendPoint. */
int32_t __real_sceAgcSuspendPoint(void);
int32_t __wrap_sceAgcSuspendPoint(void) {
    if (atomic_load_explicit(&g_enabled, memory_order_relaxed) && !atomic_load_explicit(&g_kick_registered, memory_order_relaxed) &&
        !atomic_exchange(&g_kick_registered, 1)) {
        int i = zp_register_self(ZP_KIND_KICK, "radv-kick", 0, 0, 0);
        char line[96];
        snprintf(line, sizeof line, "[za-r24prof] RADV kick thread: slot %d\n", i);
        zp_log(line);
    }
    return __real_sceAgcSuspendPoint();
}

/* ------------------------------------------------------------------ force60 (link --wrap of r16's hook) */
static int zp_force60(void) {
    static _Atomic int cached = -1;
    int v = atomic_load_explicit(&cached, memory_order_relaxed);
    if (v < 0) {
        const char *e = getenv("ZA_PERF_FORCE60");
        v = e && !strcmp(e, "1");
        atomic_store(&cached, v);
    }
    return v;
}
static _Atomic int g_force60_in_effect;

int32_t __real_za_title_frame_cfg(int32_t original);
int32_t __wrap_za_title_frame_cfg(int32_t original) {
    int32_t policy = __real_za_title_frame_cfg(original);  /* (r16 keeps its own state and logs) */
    if (!zp_force60()) return policy;
    static _Atomic int64_t last = INT64_MIN;
    int64_t key = ((int64_t)original << 32) | (uint32_t)policy;
    if (atomic_exchange(&last, key) != key) {
        char line[160];
        snprintf(line, sizeof line, "[za-r24prof] force60: game frame cfg %d (r16 policy %d) -> 0 (60 fps mode)\n",
                 (int)original, (int)policy);
        zp_log(line);
    }
    atomic_store_explicit(&g_force60_in_effect, 1, memory_order_relaxed);
    return 0;
}

/* The observer's CSV mode column: 1 (60 in effect) once force60 has replaced a frame-mode read. */
int __real_za_performance_status(void);
int __wrap_za_performance_status(void) {
    if (zp_force60() && atomic_load_explicit(&g_force60_in_effect, memory_order_relaxed)) return 1;
    return __real_za_performance_status();
}

/* ------------------------------------------------------------------ files */
static uint64_t zp_mono_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static bool zp_write_all(int fd, const void *p, size_t n) {
    const uint8_t *b = p;
    while (n) {
        ssize_t w = write(fd, b, n);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) return false;
        b += w, n -= (size_t)w;
    }
    return true;
}

static uint64_t zp_boot_counter(void) {
    char text[32] = {0};
    uint64_t boot = 0;
    int fd = open(ZP_DIR "/boot.txt", O_RDONLY);
    if (fd >= 0) {
        ssize_t n = read(fd, text, sizeof text - 1);
        if (n > 0) boot = strtoull(text, NULL, 10);
        close(fd);
    }
    boot++;
    int len = snprintf(text, sizeof text, "%llu\n", (unsigned long long)boot);
    fd = open(ZP_DIR "/boot.txt.part", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) {
        bool ok = zp_write_all(fd, text, (size_t)len);
        close(fd);
        if (ok) rename(ZP_DIR "/boot.txt.part", ZP_DIR "/boot.txt");
    }
    return boot;
}

typedef struct { uint8_t *buf; uint32_t n, cap; } ZpOut;
static void zp_collect(void *ctx, const ZpRec *r) {
    ZpOut *o = ctx;
    if (o->n < o->cap) zp_write_record(o->buf + (size_t)o->n++ * ZP_RECORD_BYTES, r);
}

static uint8_t *g_file_buf;  /* header + table + ZP_RING_CAP records */
static bool g_files_off;

static void zp_window(uint64_t window, uint64_t t0, uint64_t t1, uint32_t sent, uint32_t kill_err) {
    /* Let any handler still writing its record finish, then take what has been written. */
    struct timespec pause = {0, 2000000};
    nanosleep(&pause, NULL);
    uint64_t upto = atomic_load_explicit(&g_ring.w, memory_order_acquire);
    uint32_t skipped = 0, dropped = atomic_exchange(&g_ring.dropped, 0);
    size_t table = (size_t)ZP_MAX_THREADS * ZP_THREAD_BYTES;
    ZpOut o = {g_file_buf + ZP_HEADER_BYTES + table, 0, ZP_RING_CAP};
    zp_ring_drain(&g_ring, upto, zp_collect, &o, &skipped);
    uint32_t threads = 0;
    for (int i = 0; i < ZP_MAX_THREADS; i++) {
        ZpThread *t = &g_reg.t[i];
        t->file_samples = atomic_exchange(&t->win_samples, 0);
        t->file_ext = atomic_exchange(&t->win_ext, 0);
        t->file_nofp = atomic_exchange(&t->win_nofp, 0);
        if (atomic_load(&t->state) != ZP_FREE) threads = (uint32_t)i + 1;
    }
    atomic_store(&g_reg.window, (uint32_t)window + 1);
    int render = atomic_load(&g_render_slot);
    ZpFileHeader h = {g_boot, window, t0, t1, (uint64_t)(uintptr_t)&za_prof_anchor, g_text_lo, g_text_hi,
                      g_period_us, threads, o.n, dropped, skipped, kill_err, g_render_only ? 1u : 0u, sent,
                      render < 0 ? 0xffffffffu : (uint32_t)render};
    zp_write_header(g_file_buf, &h);
    for (uint32_t i = 0; i < threads; i++) zp_write_thread(g_file_buf + ZP_HEADER_BYTES + i * ZP_THREAD_BYTES, i, &g_reg.t[i]);
    char path[160] = "-", part[176];
    if (!g_files_off && o.n) {  /* (no file for a window without samples: menus, loading before the render thread) */
        /* (the table is written for all ZP_MAX_THREADS slots' room; only `threads` entries are used - move the
         * records down so the file is header | threads x 96 | records) */
        size_t used_table = (size_t)threads * ZP_THREAD_BYTES;
        uint8_t *recs = g_file_buf + ZP_HEADER_BYTES + table;
        if (used_table < table) memmove(g_file_buf + ZP_HEADER_BYTES + used_table, recs, (size_t)o.n * ZP_RECORD_BYTES);
        size_t bytes = ZP_HEADER_BYTES + used_table + (size_t)o.n * ZP_RECORD_BYTES;
        zp_file_name(path, sizeof path, ZP_DIR, g_boot, zp_slot(window, g_keep));
        snprintf(part, sizeof part, "%s.part", path);
        int fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        bool ok = fd >= 0 && zp_write_all(fd, g_file_buf, bytes);
        if (fd >= 0) close(fd);
        if (ok) ok = rename(part, path) == 0;
        if (!ok) {
            char line[200];
            snprintf(line, sizeof line, "[za-r24prof] writing %s failed (errno %d): no more sample files this boot\n", part, errno);
            zp_log(line);
            unlink(part);
            g_files_off = true;
            snprintf(path, sizeof path, "-");
        }
    }
    char summary[640];
    int n = snprintf(summary, sizeof summary,
                     "[za-r24prof] win=%llu span_ms=%llu sent=%u kill_err=%u recs=%u drop=%u skip=%u unk=%u text=%d file=%s th:",
                     (unsigned long long)window, (unsigned long long)((t1 - t0) / 1000000), sent, kill_err, o.n, dropped,
                     skipped, atomic_exchange(&g_unknown, 0), g_text_hi ? 1 : 0, strrchr(path, '/') ? strrchr(path, '/') + 1 : path);
    if (n > 0 && (size_t)n < sizeof summary)
        zp_summary(summary + n, sizeof summary - (size_t)n, &g_reg, 6, g_text_hi != 0);
    size_t len = strlen(summary);
    if (len + 2 < sizeof summary) summary[len] = '\n', summary[len + 1] = 0;
    zp_log(summary);
}

/* ------------------------------------------------------------------ sampler thread */
static void *zp_sampler(void *arg) {
    (void)arg;
    sigset_t block;
    sigemptyset(&block);
    sigaddset(&block, ZP_SIG);
    pthread_sigmask(SIG_BLOCK, &block, NULL);
    uint64_t freq = sceKernelGetTscFrequency();
    uint64_t period = freq ? freq / 1000000 * g_period_us : 0;
    uint64_t window_ticks = freq * g_window_s;
    if (!freq || !period) {
        zp_log("[za-r24prof] no TSC frequency: sampler not started\n");
        return NULL;
    }
    uint64_t next = sceKernelReadTsc() + period, window_end = sceKernelReadTsc() + window_ticks, t0 = zp_mono_ns();
    uint64_t window = 0;
    uint32_t sent = 0, kill_err = 0;
    int rr = -1;
    for (;;) {
        uint64_t now = sceKernelReadTsc();
        if (now < next) {
            uint64_t ns = (next - now) * 1000000000ull / freq;
            struct timespec ts = {(time_t)(ns / 1000000000ull), (long)(ns % 1000000000ull)};
            nanosleep(&ts, NULL);
        }
        next += period;
        now = sceKernelReadTsc();
        if (now > next + 50 * period) next = now + period;  /* (after a stall: no burst) */
        int rs = atomic_load(&g_render_slot);
        if (rs >= 0 && atomic_load(&g_reg.t[rs].state) == ZP_ACTIVE) {
            if (pthread_kill((pthread_t)atomic_load(&g_reg.t[rs].tid), ZP_SIG) == 0) sent++;
            else kill_err++;
        }
        if (!g_render_only) {
            int i = zp_next_target(&g_reg, rr, rs);
            if (i >= 0) {
                rr = i;
                if (pthread_kill((pthread_t)atomic_load(&g_reg.t[i].tid), ZP_SIG) == 0) sent++;
                else kill_err++;
            }
        }
        if (sceKernelReadTsc() >= window_end) {
            uint64_t t1 = zp_mono_ns();
            zp_window(window++, t0, t1, sent, kill_err);
            sent = kill_err = 0;
            t0 = zp_mono_ns();
            window_end = sceKernelReadTsc() + window_ticks;
        }
    }
    return NULL;
}

/* ------------------------------------------------------------------ start (title entry, before the runtime) */
static unsigned zp_env_uint(const char *name, unsigned def, unsigned lo, unsigned hi) {
    const char *e = getenv(name);
    if (!e || !*e) return def;
    unsigned long v = strtoul(e, NULL, 10);
    return v < lo ? lo : v > hi ? hi : (unsigned)v;
}

void za_prof_start(void) {
    char line[320];
    if (zp_force60())
        zp_log("[za-r24prof] force60=1: every read of the game's frame mode returns 0 (60 fps): no trial, no fallback, "
               "measurement only; the observer reports mode 1 once it is in effect\n");
    const char *s = getenv("LARECOMP_SCALE");
    if (s) {
        snprintf(line, sizeof line, "[za-r24prof] scale=%s: render height 1080 x %s whatever the display mode "
                 "(output_scale.c); the present path logs the effective scale and upscaler\n", s, s);
        zp_log(line);
    }
    const char *e = getenv("ZA_PROF_SAMPLE");
    if (!e || strcmp(e, "1")) return;
    g_period_us = zp_env_uint("ZA_PROF_US", 1000, 200, 100000);
    g_window_s = zp_env_uint("ZA_PROF_SECONDS", 20, 5, 120);
    g_keep = zp_env_uint("ZA_PROF_KEEP", 30, 1, ZP_MAX_KEEP);
    const char *th = getenv("ZA_PROF_THREADS");
    g_render_only = th && !strcmp(th, "render");
    /* the eboot's text mapping: [start, end) of the mapping that holds za_prof_anchor (PS4 SDK layout: start, end
     * first). Used only to tell samples in our code from samples in system modules; checked, else unknown. */
    uint64_t info[16] = {0};
    int vq = sceKernelVirtualQuery((const void *)(uintptr_t)&za_prof_anchor, 0, info, 72);
    uint64_t a = (uint64_t)(uintptr_t)&za_prof_anchor;
    if (vq == 0 && info[0] <= a && a < info[1] && info[1] - info[0] >= (16ull << 20) && info[1] - info[0] <= (2ull << 30))
        g_text_lo = info[0], g_text_hi = info[1];
    g_ring.cap = ZP_RING_CAP;
    g_ring.rec = calloc(ZP_RING_CAP, sizeof(ZpRec));
    g_file_buf = malloc(ZP_HEADER_BYTES + (size_t)ZP_MAX_THREADS * ZP_THREAD_BYTES + (size_t)ZP_RING_CAP * ZP_RECORD_BYTES);
    if (!g_ring.rec || !g_file_buf) {
        zp_log("[za-r24prof] no memory for the sample ring: sampling off\n");
        return;
    }
    mkdir("/download0/zarecomp", 0755);
    mkdir(ZP_DIR, 0755);
    g_boot = zp_boot_counter();
    if (g_boot > ZP_KEEP_BOOTS) {
        char path[160];
        for (unsigned slot = 0; slot < ZP_MAX_KEEP; slot++) {
            zp_file_name(path, sizeof path, ZP_DIR, g_boot - ZP_KEEP_BOOTS, slot);
            unlink(path);
        }
    }
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = zp_handler;
    sa.sa_flags = SA_SIGINFO | SA_RESTART | SA_ONSTACK;
    sigemptyset(&sa.sa_mask);
    if (sigaction(ZP_SIG, &sa, NULL) != 0) {
        snprintf(line, sizeof line, "[za-r24prof] sigaction(SIGPROF) failed (errno %d): sampling off\n", errno);
        zp_log(line);
        return;
    }
    atomic_store(&g_enabled, 1);
    pthread_t t;
    if (pthread_create(&t, NULL, zp_sampler, NULL) != 0) {
        atomic_store(&g_enabled, 0);
        zp_log("[za-r24prof] sampler thread not created: sampling off\n");
        return;
    }
    pthread_detach(t);
    snprintf(line, sizeof line,
             "[za-r24prof] sampling on: period_us=%u threads=%s window_s=%u keep=%u boot=%llu dir=%s signal=SIGPROF "
             "anchor=%llx text=%llx-%llx (vq rc=%d) disk_bound_mib=%llu\n",
             g_period_us, g_render_only ? "render" : "all", g_window_s, g_keep, (unsigned long long)g_boot, ZP_DIR,
             (unsigned long long)a, (unsigned long long)g_text_lo, (unsigned long long)g_text_hi, vq,
             (unsigned long long)(zp_disk_bound(g_keep, ZP_RING_CAP) >> 20));
    zp_log(line);
}
