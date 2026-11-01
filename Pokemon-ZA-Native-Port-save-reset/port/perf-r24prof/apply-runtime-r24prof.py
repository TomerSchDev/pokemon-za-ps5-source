"""Apply r24-prof's runtime hooks to an r24-perf source tree (kernel.c, nvn/objects.c, nvn/vulkan/device.c).

Exact-text edits; each anchor must occur exactly once, and a tree that already has the edits is left unchanged
(idempotent). Usage: python3 apply-runtime-r24prof.py <source/runtime>
"""
import sys
from pathlib import Path

MARK = 'r24-prof'

EDITS = {
    'kernel.c': [
        ('static void *thread_main(void *arg) {\n',
         '// r24-prof (port/perf-r24prof/za_prof.c): sampling profiler registration of guest threads (one relaxed\n'
         '// atomic load when sampling is off)\n'
         'void za_prof_thread_begin(uint64_t gid, uint64_t entry, int prio);\n'
         'void za_prof_thread_end(void);\n'
         'static void *thread_main(void *arg) {\n'),
        ('    crash_handler_install();\n    rt_set_fpcr(0);\n    if (!setjmp(t->unwind)) guest_call(&t->cpu, t->entry);\n',
         '    crash_handler_install();\n    rt_set_fpcr(0);\n    za_prof_thread_begin(t->id, t->entry, t->prio);  // r24-prof\n'
         '    if (!setjmp(t->unwind)) guest_call(&t->cpu, t->entry);\n'),
        ('    pthread_mutex_unlock(&g_klock);\n    t_cur = NULL;\n    return NULL;\n}\n',
         '    pthread_mutex_unlock(&g_klock);\n    za_prof_thread_end();  // r24-prof\n    t_cur = NULL;\n    return NULL;\n}\n'),
    ],
    'nvn/objects.c': [
        ('NVN(nvnQueueSubmitCommands) {\n    int n = (int)A(1);\n',
         'void za_prof_note_render(void);  // r24-prof: the render thread for the sampling profiler (za_prof.c)\n'
         'NVN(nvnQueueSubmitCommands) {\n    za_prof_note_render();\n    int n = (int)A(1);\n'),
    ],
    'nvn/vulkan/device.c': [
        ('        double sx = os.sx, sy = os.sy, vx = os.vx, vy = os.vy, vw = os.vw, vh = os.vh, shape = os.shape;\n',
         '        double sx = os.sx, sy = os.sy, vx = os.vx, vy = os.vy, vw = os.vw, vh = os.vh, shape = os.shape;\n'
         '        {   // r24-prof: the effective render scale and what the present path does with it, once per change\n'
         '            static double logged_sx = -1, logged_sy = -1;\n'
         '            if (sx != logged_sx || sy != logged_sy) {\n'
         '                logged_sx = sx, logged_sy = sy;\n'
         '                const char *forced = getenv("LARECOMP_SCALE");\n'
         '                LOG("[za-r24prof] render scale %.3f x %.3f (the game\'s 1920x1080 targets times that) for output "\n'
         '                    "%.0fx%.0f; LARECOMP_SCALE=%s res_mode=%d; present: antialias=%s upscaler=%s\\n", sx, sy, dw, dh,\n'
         '                    forced ? forced : "-", g_settings.res_mode, g_settings.antialias == AA_SMAA ? "smaa" : "off",\n'
         '                    g_settings.upscaler == UPSCALE_FSR1 ? "fsr1 (EASU+RCAS when the output is larger than the image)"\n'
         '                    : g_settings.upscaler == UPSCALE_BILINEAR ? "bilinear" : "other");\n'
         '            }\n'
         '        }\n'),
    ],
}


def main():
    root = Path(sys.argv[1])
    for rel, edits in EDITS.items():
        path = root / rel
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
            path.write_text(text, encoding='utf-8')
        print(f'{rel}: {"patched" if changed else "already patched"}')


if __name__ == '__main__':
    main()
