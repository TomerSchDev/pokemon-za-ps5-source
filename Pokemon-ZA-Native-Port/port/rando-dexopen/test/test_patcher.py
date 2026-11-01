"""Guard tests for prepare-dexopen-hooks.py: approved inputs only, exact single anchor inside each audited function,
all-or-nothing, idempotent output, never writes its inputs. usage: test_patcher.py AOT_MAIN_DIR GAME_NSO"""
from pathlib import Path
import difflib, hashlib, importlib.util, sys, tempfile

own = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prep', own / 'prepare-dexopen-hooks.py')
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
src, nso = Path(sys.argv[1]), Path(sys.argv[2])
before = {u['name']: hashlib.sha256((src / u['name']).read_bytes()).hexdigest() for u in prep.UNITS}
nso_before = hashlib.sha256(nso.read_bytes()).hexdigest()
passed = 0


def ok(msg):
    global passed
    print('ok ', msg)
    passed += 1


def expect_error(fn, what):
    try:
        fn()
    except ValueError as e:
        ok('refused: %s -> %s' % (what, e))
        return
    raise AssertionError('accepted: ' + what)


def norm(path):
    return path.read_bytes().decode('utf-8').replace('\r\n', '\n')


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    r1 = prep.prepare(src, nso, t / 'a')
    r2 = prep.prepare(src, nso, t / 'a')  # idempotent: identical bytes already there
    assert r1 == r2
    # main_287: exactly one original line replaced (the final `w0 = w8 & w19`), everything else kept in order
    out, orig = (t / 'a' / 'main_287.c').read_text(), norm(src / 'main_287.c')
    assert out.count('za_dexopen_hyperspace_dex_enabled(') == 2  # the extern and the call
    ops = difflib.SequenceMatcher(None, orig.splitlines(), out.splitlines(), autojunk=False).get_opcodes()
    changed = [x for x in ops if x[0] != 'equal']
    assert len(changed) == 1 and changed[0][0] == 'replace', changed
    tag, i1, i2, j1, j2 = changed[0]
    assert i2 - i1 == 1 and orig.splitlines()[i1] == '    c->x[0] = (uint32_t)((uint32_t)c->x[8] & (uint32_t)c->x[19]);'
    assert j2 - j1 == 3
    assert out.count('f_70000393b8(c);') == orig.count('f_70000393b8(c);') and out.count('f_7000095a40(c);') == orig.count('f_7000095a40(c);')
    ok('main_287.c: one line replaced (the AND), the getter and the release untouched, idempotent')
    # main_115: insertions only, after the getter result is captured
    out, orig = (t / 'a' / 'main_115.c').read_text(), norm(src / 'main_115.c')
    assert out.count('za_dexopen_mega_dex_flag(') == 2
    ops = difflib.SequenceMatcher(None, orig.splitlines(), out.splitlines(), autojunk=False).get_opcodes()
    assert all(tag in ('equal', 'insert') for tag, *_ in ops), [x for x in ops if x[0] != 'equal']
    assert sum(j2 - j1 for tag, i1, i2, j1, j2 in ops if tag == 'insert') == 3
    lines = out.splitlines()
    at = next(i for i, l in enumerate(lines) if 'za_dexopen_mega_dex_flag((uint32_t)c->x[22])' in l)
    assert lines[at - 3].strip() == 'c->x[22] = (uint32_t)(0u | (uint32_t)c->x[0]);' and 'f_70000393b8(c);' in lines[at - 4]
    ok('main_115.c: three lines inserted right after w22 is captured, nothing removed, idempotent')
    fake = t / 'nso'
    raw = bytearray(nso.read_bytes()[:0x100]); raw[0x40] ^= 1; fake.write_bytes(bytes(raw))
    expect_error(lambda: prep.prepare(src, fake, t / 'b'), 'other build ID')
    for k, u in enumerate(prep.UNITS):
        bad = t / ('src%d' % k); bad.mkdir()
        for v in prep.UNITS:
            data = (src / v['name']).read_bytes()
            (bad / v['name']).write_bytes(data + b'\n' if v is u else data)
        expect_error(lambda: prep.prepare(bad, nso, t / ('c%d' % k)), 'unapproved source hash of ' + u['name'])
        assert not (t / ('c%d' % k)).exists(), 'nothing may be written when one unit is refused'
    for u in prep.UNITS:
        text = norm(src / u['name'])
        expect_error(lambda: prep.patch_unit_text(u, text + u['anchor']), 'duplicated anchor in ' + u['name'])
        expect_error(lambda: prep.patch_unit_text(u, text.replace(u['anchor'], '')), 'missing anchor in ' + u['name'])
        moved = text.replace(u['anchor'], '') + 'void f_7fffffffff(Cpu *c) {\n' + u['anchor'] + '}\n'
        expect_error(lambda: prep.patch_unit_text(u, moved), 'anchor outside ' + u['function'])
        start, end = prep.function_span(text, u['function'])
        body = text[start:end]
        expect_error(lambda: prep.patch_unit_text(u, text[:start] + body.replace('FN_ENTER', 'L_dispatch:; FN_ENTER', 1) + text[end:]),
                     'indirect-dispatch section in ' + u['function'])
        expect_error(lambda: prep.patch_unit_text(u, text[:start] + body.replace('FN_ENTER', 'za_x(); FN_ENTER', 1) + text[end:]),
                     'an earlier za_ hook in ' + u['function'])
        for needle in u['must_contain']:  # each audited line, changed inside the function only
            assert needle in body, needle
            mutated = text[:start] + body.replace(needle, needle[:-1] + ' ' + needle[-1:], 1) + text[end:]
            expect_error(lambda: prep.patch_unit_text(u, mutated), 'audited code changed in %s: %.50s' % (u['function'], needle.strip()))
    (t / 'd').mkdir(); (t / 'd' / 'main_287.c').write_text('other')
    expect_error(lambda: prep.prepare(src, nso, t / 'd'), 'overwrite of a different output')
    expect_error(lambda: prep.prepare(src, nso, src), 'output aliases source')
assert all(hashlib.sha256((src / n).read_bytes()).hexdigest() == h for n, h in before.items())
assert hashlib.sha256(nso.read_bytes()).hexdigest() == nso_before
ok('inputs unchanged')
print('patcher tests passed:', passed)
