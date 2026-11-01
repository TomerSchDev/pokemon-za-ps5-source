"""Reorder blocks of the story phase table in place (permutes the root vector's uoffsets; no re-encode).

usage: phase_reorder.py IN_phase.bin OUT_phase.bin --move FIRST:LAST --before IDX
  moves entries [FIRST..LAST] (0-based vector indices) so they come right before entry IDX (original numbering).
OUT must be outside git (it is game data). Prints the new order of phase ids.
"""
import argparse, struct

ap = argparse.ArgumentParser()
ap.add_argument('inp'); ap.add_argument('out')
ap.add_argument('--move', required=True); ap.add_argument('--before', type=int, required=True)
a = ap.parse_args()
d = bytearray(open(a.inp, 'rb').read())
u32 = lambda p: struct.unpack_from('<I', d, p)[0]
root = u32(0)
vt = root - struct.unpack_from('<i', d, root)[0]
f0 = struct.unpack_from('<H', d, vt + 4)[0]
vec = root + f0 + u32(root + f0)
n = u32(vec)
slots = [vec + 4 + 4 * i for i in range(n)]
targets = [s + u32(s) for s in slots]


def pid(t):
    v = t - struct.unpack_from('<i', d, t)[0]
    o = struct.unpack_from('<H', d, v + 4)[0] if struct.unpack_from('<H', d, v)[0] > 4 else 0
    return struct.unpack_from('<i', d, t + o)[0] if o else 0


lo, hi = map(int, a.move.split(':'))
order = list(range(n))
block = order[lo:hi + 1]
rest = [i for i in order if not lo <= i <= hi]
k = rest.index(a.before)
new = rest[:k] + block + rest[k:]
assert sorted(new) == order
for s, i in zip(slots, new):
    struct.pack_into('<I', d, s, targets[i] - s)
open(a.out, 'wb').write(d)
print(n, 'entries; new order of phase ids:', [pid(targets[i]) for i in new])
