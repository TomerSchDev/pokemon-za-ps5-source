"""Apply r24-clock's edits to an r24-prof work copy (r24-prof's own edits are already in it).

  source/runtime/nvn/vulkan/exec.c   log the renderer CPU profile's effective state at init; append za_clock_report
                                     (za_clock.c: clock_gettime per thread class) to the [za-r24-perf] line
  source/runtime/platform/ps5.c      log which clock plat_now_ns uses (LARECOMP_PS5_TSC)
  port/sdl3-shim/src/sdl3_ps5_core.c SDL3_PS5_TICKS=tsc: SDL_GetTicksNS & co. from the TSC, chosen at run time, with a
                                     one-time check against clock_gettime (the default stays clock_gettime)

Exact-text edits; each anchor must occur exactly once, and a tree that already has the edits is left unchanged
(idempotent). Usage: python3 apply-runtime-r24clock.py <work copy, e.g. /home/tomer/ps5-za-native/perf-r24clock-20261029>
"""
import sys
from pathlib import Path

EDITS = {
    'source/runtime/nvn/vulkan/exec.c': [
        ('    prof = ENV("LARECOMP_VK_PROF") != NULL;\n',
         '    prof = ENV("LARECOMP_VK_PROF") != NULL;\n'
         '    LOG("[za-r24clock] renderer CPU profile (LARECOMP_VK_PROF): %s\\n", prof ? "on" : "off");  // r24-clock\n'),
        ('    if (n < sizeof line) n += za_r24_window(line + n, sizeof line - n);\n',
         '    if (n < sizeof line) n += za_r24_window(line + n, sizeof line - n);\n'
         '    {   // r24-clock: clock_gettime calls / time per thread class (port/perf-r24clock/za_clock.c)\n'
         '        extern size_t za_clock_report(char *out, size_t cap);\n'
         '        if (n < sizeof line) n += za_clock_report(line + n, sizeof line - n);\n'
         '    }\n'),
    ],
    'source/runtime/platform/ps5.c': [
        ("    if (tsc && *tsc == '1') g_tsc_hz = sceKernelGetTscFrequency();\n",
         "    if (tsc && *tsc == '1') g_tsc_hz = sceKernelGetTscFrequency();\n"
         "    LOGP(\"clock: plat_now_ns from %s (LARECOMP_PS5_TSC=%s, TSC %llu Hz)\\n\", g_tsc_hz ? \"the TSC\" : \"clock_gettime\",  // r24-clock\n"
         "         tsc ? tsc : \"-\", (unsigned long long)g_tsc_hz);\n"),
    ],
}

SHIM = 'port/sdl3-shim/src/sdl3_ps5_core.c'
SHIM_START = '#ifndef SDL3_PS5_TSC_TICKS\n'
SHIM_END = 'Uint64 SDL_GetPerformanceFrequency(void)\n{\n    return 1000000000ull;\n}\n'
SHIM_NEW = r'''/* r24-clock: SDL3_PS5_TICKS=tsc (the title's perf-r24-options.txt ticks=tsc) reads the TSC (sceKernelReadTsc, ~12 ns)
 * instead of clock_gettime(CLOCK_MONOTONIC) (a syscall, ~20 us a call on 13.60 per PS5_Vulkan HARDWARE_FINDINGS),
 * chosen once at the first read; the default stays clock_gettime. The compile-time SDL3_PS5_TSC_TICKS=1 still forces
 * the TSC. When the TSC is chosen, a one-time check compares 1,000 TSC-derived readings with clock_gettime on this
 * thread and logs the largest deviation, TSC readings that went backwards, and what a clock_gettime call cost. */
#ifndef SDL3_PS5_TSC_TICKS
#define SDL3_PS5_TSC_TICKS 0
#endif

static pthread_once_t ticks_once = PTHREAD_ONCE_INIT;
static int ticks_ready;     /* (release-stored at the end of ticks_init) */
static uint64_t ticks_start;
static uint64_t tsc_hz;     /* nonzero: the TSC is the clock */

static uint64_t ticks_clock_ns(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
}

static uint64_t ticks_tsc_ns(uint64_t tsc, uint64_t hz)
{
    return (uint64_t)(((unsigned __int128)tsc * 1000000000ull) / hz);
}

static void ticks_check(uint64_t hz)
{
    enum { N = 1000 };
    uint64_t a0 = sceKernelReadTsc(), c0 = ticks_clock_ns(), b0 = sceKernelReadTsc();
    uint64_t mid0 = a0 + (b0 - a0) / 2, prev = b0, max_dev = 0, backwards = 0, call_ticks = b0 - a0, last = b0;
    for (int i = 1; i < N; i++) {
        uint64_t a = sceKernelReadTsc(), c = ticks_clock_ns(), b = sceKernelReadTsc();
        if (a < prev || b < a) backwards++;
        prev = b, last = b;
        call_ticks += b - a;
        uint64_t mid = a + (b - a) / 2, dt = ticks_tsc_ns(mid - mid0, hz), dc = c - c0;
        uint64_t dev = dt > dc ? dt - dc : dc - dt;
        if (dev > max_dev) max_dev = dev;
    }
    char line[320];
    snprintf(line, sizeof line,
             "[sdl3-ps5] ticks: TSC at %llu Hz; check over %llu us: largest deviation from clock_gettime %llu ns, "
             "TSC backwards %llu of %d, clock_gettime %.2f us a call (TSC-timed)\n", (unsigned long long)hz,
             (unsigned long long)(ticks_tsc_ns(last - a0, hz) / 1000), (unsigned long long)max_dev,
             (unsigned long long)backwards, N, (double)ticks_tsc_ns(call_ticks, hz) / 1000.0 / N);
    sceKernelDebugOutText(0, line);  /* (klog directly: the first read may come before stderr is captured) */
}

static void ticks_init(void)
{
    const char *e = getenv("SDL3_PS5_TICKS");
    if (SDL3_PS5_TSC_TICKS || (e && !strcmp(e, "tsc"))) {
        uint64_t hz = sceKernelGetTscFrequency();
        if (hz) {
            ticks_check(hz);
            tsc_hz = hz;
        } else {
            sceKernelDebugOutText(0, "[sdl3-ps5] ticks: the TSC was asked for but its frequency reads 0; clock_gettime\n");
        }
    } else {
        sceKernelDebugOutText(0, "[sdl3-ps5] ticks: clock_gettime(CLOCK_MONOTONIC)\n");
    }
    ticks_start = tsc_hz ? ticks_tsc_ns(sceKernelReadTsc(), tsc_hz) : ticks_clock_ns();
    __atomic_store_n(&ticks_ready, 1, __ATOMIC_RELEASE);
}

uint64_t sdl3_ps5_now_ns(void)
{
    if (__builtin_expect(!__atomic_load_n(&ticks_ready, __ATOMIC_ACQUIRE), 0))
        pthread_once(&ticks_once, ticks_init);
    return tsc_hz ? ticks_tsc_ns(sceKernelReadTsc(), tsc_hz) : ticks_clock_ns();
}

Uint64 SDL_GetTicksNS(void)
{
    const uint64_t now = sdl3_ps5_now_ns();  /* (first: it initialises ticks_start) */
    return now - ticks_start;
}

Uint64 SDL_GetTicks(void)
{
    return SDL_GetTicksNS() / 1000000ull;
}

Uint64 SDL_GetPerformanceCounter(void)
{
    return sdl3_ps5_now_ns();
}

Uint64 SDL_GetPerformanceFrequency(void)
{
    return 1000000000ull;
}
'''


def main():
    work = Path(sys.argv[1])
    for rel, edits in EDITS.items():
        path = work / rel
        text = path.read_text(encoding='utf-8')
        changed = False
        for old, new in edits:
            if new in text:
                continue
            count = text.count(old)
            if count != 1:
                raise SystemExit(f'{rel}: anchor found {count} times: {old[:60]!r}')
            text = text.replace(old, new)
            changed = True
        if changed:
            path.write_text(text, encoding='utf-8', newline='\n')
        print(f'{rel}: {"patched" if changed else "already patched"}')
    path = work / SHIM
    text = path.read_text(encoding='utf-8')
    if 'r24-clock: SDL3_PS5_TICKS=tsc' in text:
        print(f'{SHIM}: already patched')
        return
    if text.count(SHIM_START) != 1 or text.count(SHIM_END) != 1:
        raise SystemExit(f'{SHIM}: timer block anchors found {text.count(SHIM_START)} / {text.count(SHIM_END)} times')
    a = text.index(SHIM_START)
    b = text.index(SHIM_END) + len(SHIM_END)
    path.write_text(text[:a] + SHIM_NEW + text[b:], encoding='utf-8', newline='\n')
    print(f'{SHIM}: patched')


if __name__ == '__main__':
    main()
