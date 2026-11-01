"""Minimal Lua 5.4 bytecode reader: prototypes, constants, code (for naming closures). Read-only."""
import struct, sys, json


class R:
    def __init__(s, d): s.d = d; s.p = 0
    def b(s):
        v = s.d[s.p]; s.p += 1; return v
    def n(s, k):
        v = s.d[s.p:s.p + k]; s.p += k; return v
    def vu(s):
        x = 0
        while True:
            c = s.b(); x = (x << 7) | (c & 0x7f)
            if c & 0x80: return x
    def st(s):
        n = s.vu()
        if n == 0: return None
        return s.n(n - 1).decode('utf-8', 'replace')


def func(r, depth=0):
    f = {}
    f['source'] = r.st()
    f['line'] = r.vu(); f['lastline'] = r.vu()
    f['nparams'] = r.b(); f['vararg'] = r.b(); f['maxstack'] = r.b()
    nc = r.vu(); f['code'] = struct.unpack_from('<%dI' % nc, r.d, r.p); r.p += 4 * nc
    nk = r.vu(); ks = []
    for _ in range(nk):
        t = r.b()
        if t == 0: ks.append(None)
        elif t == 1: ks.append(False)
        elif t == 0x11: ks.append(True)
        elif t == 3: ks.append(struct.unpack('<q', r.n(8))[0])
        elif t == 0x13: ks.append(struct.unpack('<d', r.n(8))[0])
        elif t in (4, 0x14): ks.append(r.st())
        else: raise ValueError('const type %d at %x' % (t, r.p))
    f['k'] = ks
    nu = r.vu(); r.n(3 * nu); f['nup'] = nu
    np_ = r.vu(); f['p'] = [func(r, depth + 1) for _ in range(np_)]
    n = r.vu(); r.n(n)
    n = r.vu()
    for _ in range(n): r.vu(); r.vu()
    n = r.vu()
    for _ in range(n): r.st(); r.vu(); r.vu()
    n = r.vu()
    for _ in range(n): r.st()
    return f


def load(d):
    assert d[:5] == b'\x1bLuaT'
    r = R(d); r.p = 4 + 1 + 1 + 6 + 3 + 8 + 8
    r.b()  # sizeupvalues
    return func(r)


# opcodes 5.4
OP = {9: 'GETUPVAL', 11: 'GETTABUP', 12: 'GETTABLE', 13: 'GETI', 14: 'GETFIELD', 15: 'SETTABUP', 16: 'SETTABLE', 17: 'SETI', 18: 'SETFIELD', 79: 'CLOSURE', 3: 'LOADK', 68: 'CALL'}


def ins(i):
    op = i & 0x7f; a = (i >> 7) & 0xff; k = (i >> 15) & 1; b = (i >> 16) & 0xff; c = (i >> 24) & 0xff
    bx = i >> 15
    return op, a, k, b, c, bx


def name_closures(f, path='main'):
    """map child proto index -> name, from CLOSURE rX,i followed by SETFIELD/SETTABUP with a string constant key"""
    names = {}
    code = f['code']
    for pc, i in enumerate(code):
        op, a, k, b, c, bx = ins(i)
        if op == 79:  # CLOSURE A Bx
            for j in range(pc + 1, min(pc + 4, len(code))):
                op2, a2, k2, b2, c2, bx2 = ins(code[j])
                if op2 in (15, 18) and k2 == 1 and c2 == a:  # SETTABUP/SETFIELD A B C(RK) with C = register? (k flag => C is K)
                    pass
                if op2 in (15, 18):
                    key = f['k'][b2] if b2 < len(f['k']) else None
                    val_is_reg = (k2 == 0 and c2 == a)
                    if val_is_reg and isinstance(key, str):
                        names[bx] = key; break
    return names


def walk(f, path, out):
    names = name_closures(f)
    strs = [k for k in f['k'] if isinstance(k, str)]
    out.append(dict(path=path, nk=len(f['k']), ncode=len(f['code']), strs=strs, nchild=len(f['p'])))
    for i, ch in enumerate(f['p']):
        walk(ch, path + '/' + names.get(i, '#%d' % i), out)


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    f = load(d)
    out = []
    walk(f, 'root', out)
    json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False)
    print(len(out))
