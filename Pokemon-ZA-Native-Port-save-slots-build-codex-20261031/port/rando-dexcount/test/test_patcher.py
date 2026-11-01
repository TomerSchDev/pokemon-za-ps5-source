"""Guard tests for prepare-dexcount-hooks.py: approved inputs only, exact single anchor inside each audited function,
all-or-nothing, idempotent output, never writes its inputs. usage: test_patcher.py AOT_MAIN_DIR GAME_NSO"""
from pathlib import Path
import difflib, hashlib, importlib.util, sys, tempfile

own = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prep', own / 'prepare-dexcount-hooks.py')
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
    for u, marker, extra in (('main_310.c', 'za_dexcount_combine(za_dex_lumiose', 1),
                             ('main_261.c', 'za_dexcount_display(za_dex_lumiose', 2)):
        out, orig = (t / 'a' / u).read_text(), norm(src / u)
        assert out.count(marker) == 1, u
        assert out.count('f_700033e770(c);') == orig.count('f_700033e770(c);') + extra, u
        # every original line is kept, in order: the patch only inserts lines
        ops = difflib.SequenceMatcher(None, orig.splitlines(), out.splitlines(), autojunk=False).get_opcodes()
        assert all(tag in ('equal', 'insert') for tag, *_ in ops), (u, [x for x in ops if x[0] != 'equal'])
        assert sum(j2 - j1 for tag, i1, i2, j1, j2 in ops if tag == 'insert') in (9, 12), u
    ok('both units patched once, idempotent, original lines all kept (insertions only)')
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
        for needle in u['must_contain']:  # each audited line, changed inside the function only
            body = text[start:end]
            assert needle in body
            mutated = text[:start] + body.replace(needle, needle[:-1] + ' ' + needle[-1:], 1) + text[end:]
            expect_error(lambda: prep.patch_unit_text(u, mutated), 'audited code changed in %s: %.40s' % (u['function'], needle))
    (t / 'd').mkdir(); (t / 'd' / 'main_310.c').write_text('other')
    expect_error(lambda: prep.prepare(src, nso, t / 'd'), 'overwrite of a different output')
    expect_error(lambda: prep.prepare(src, nso, src), 'output aliases source')
assert all(hashlib.sha256((src / n).read_bytes()).hexdigest() == h for n, h in before.items())
assert hashlib.sha256(nso.read_bytes()).hexdigest() == nso_before
ok('inputs unchanged')
print('patcher tests passed:', passed)
