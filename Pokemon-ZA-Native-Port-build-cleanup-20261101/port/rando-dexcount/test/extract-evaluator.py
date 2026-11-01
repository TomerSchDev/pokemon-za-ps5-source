"""Host-test helper: cut the two hooked translated functions out of the ORIGINAL units and out of the copies patched
by prepare-dexcount-hooks.py, renamed orig_/patched_ so all four link into one harness. The exact generated text is
used, nothing re-typed. Reads only; writes OUT_DIR/{evaluator,panel}_{orig,patched}.inc.

usage: extract-evaluator.py AOT_MAIN_DIR PATCHED_DIR OUT_DIR
"""
from pathlib import Path
import importlib.util, sys

own = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prep', own / 'prepare-dexcount-hooks.py')
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
NAMES = {'main_310.c': 'evaluator', 'main_261.c': 'panel'}


def cut(path, fn, prefix):
    text = Path(path).read_bytes().decode('utf-8').replace('\r\n', '\n')
    start, end = prep.function_span(text, fn)
    body = text[start:end].replace('void %s(Cpu *c) {' % fn, 'void %s_%s(Cpu *c) {' % (prefix, fn), 1)
    return body.replace('FN_ENTER(0x', 'FN_ENTER(0x', 1)


aot, patched, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
for unit in prep.UNITS:
    tag = NAMES[unit['name']]
    (out / ('%s_orig.inc' % tag)).write_text(cut(aot / unit['name'], unit['function'], 'orig'))
    (out / ('%s_patched.inc' % tag)).write_text(cut(patched / unit['name'], unit['function'], 'patched'))
    print('extracted', unit['function'], 'from', unit['name'])
