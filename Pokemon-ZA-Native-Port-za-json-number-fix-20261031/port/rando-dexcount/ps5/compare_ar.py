"""Compare two System V/GNU ar archives member by member (name order and SHA-256 of every member).
usage: compare_ar.py BASE.a NEW.a ALLOWED_CHANGED_MEMBER [...]  -> JSON; exit 1 unless exactly the allowed members differ
"""
import hashlib, json, sys


def members(path):
    out = []
    with open(path, 'rb') as f:
        if f.read(8) != b'!<arch>\n':
            raise ValueError('not an ar archive: ' + path)
        names = b''
        while True:
            h = f.read(60)
            if not h:
                break
            if len(h) != 60 or h[58:60] != b'`\n':
                raise ValueError('bad member header in ' + path)
            name = h[0:16].decode().rstrip()
            size = int(h[48:58].decode().strip())
            data = f.read(size)
            if size % 2:
                f.read(1)
            if name == '//':
                names = data
                continue
            if name in ('/', '/SYM64/'):
                continue  # symbol table: rebuilt by ar, not a member
            if name.startswith('/') and name[1:].isdigit():
                off = int(name[1:])
                name = names[off:names.index(b'\n', off)].decode().rstrip('/')
            else:
                name = name.rstrip('/')
            out.append((name, hashlib.sha256(data).hexdigest(), size))
    return out


base, new, allowed = members(sys.argv[1]), members(sys.argv[2]), set(sys.argv[3:])
same_order = [m[0] for m in base] == [m[0] for m in new]
changed = sorted({b[0] for b, n in zip(base, new) if b[1] != n[1]})
result = dict(base=sys.argv[1], new=sys.argv[2], members=len(base), new_members=len(new), same_order=same_order,
              changed=changed, changed_detail={b[0]: dict(base=b[1], new=n[1]) for b, n in zip(base, new) if b[1] != n[1]})
print(json.dumps(result, indent=2))
sys.exit(0 if same_order and len(base) == len(new) and set(changed) == allowed else 1)
