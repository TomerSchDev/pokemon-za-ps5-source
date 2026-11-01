"""Apply r26's one runtime edit to an r25 work copy (r24-prof's, r24-clock's and r25's edits are already in it).

  source/runtime/nvn/vulkan/exec.c   the dynamic timing's window keys (za_dt_report, port/perf-r26/za_dyn_glue_r26.c)
                                     on the [za-r24-perf] line, after r25's keys and before the thread list (which the
                                     klog may truncate)

The game-code hooks are not here: they are patched copies of five generated units (prepare-dynamic-hooks.py) whose
objects replace the archive's (build-perf-r26.sh). Exact-text edit; the anchor must occur exactly once, and a tree that
already has the edit is left unchanged (idempotent). Usage: python3 apply-runtime-r26.py <work copy>
"""
import sys
from pathlib import Path

EDITS = {
    'source/runtime/nvn/vulkan/exec.c': [
        ('    if (n < sizeof line) n += za_r25_report(line + n, sizeof line - n, lns, pns);'
         '  // r25: submitter and render-thread keys\n',
         '    if (n < sizeof line) n += za_r25_report(line + n, sizeof line - n, lns, pns);'
         '  // r25: submitter and render-thread keys\n'
         '    {   // r26: dynamic frame timing, the window since the previous line (port/perf-r26/za_dyn_glue_r26.c)\n'
         '        extern size_t za_dt_report(char *out, size_t cap);\n'
         '        if (n < sizeof line) n += za_dt_report(line + n, sizeof line - n);\n'
         '    }\n'),
    ],
}


def main(work):
    for rel, edits in EDITS.items():
        path = Path(work) / rel
        text = path.read_text()
        changed = False
        for before, after in edits:
            if text.count(after) == 1:
                continue  # (already applied)
            n = text.count(before)
            assert n == 1, '%s: anchor occurs %d times: %r' % (rel, n, before[:80])
            text = text.replace(before, after)
            changed = True
        if changed:
            path.write_text(text)
        print('%s: %s' % (rel, 'edited' if changed else 'already r26'))


if __name__ == '__main__':
    main(sys.argv[1])
