"""Helpers for the chapter-swap PC experiment (writes into an existing mod folder OUTMOD/romfs/...; outside git).

  trainer-level OUTMOD TRID LEVEL      every Pokemon of trainer TRID (trdata_array) to LEVEL (in place)
  cut-chain OUTMOD BATTLE_ID PHASE FIRST_EVENT
        in trigger_trainer_battle_global: in the WIN case (trigger type 12) of BATTLE_ID with phase==PHASE, end the
        command list right before the first command whose args contain FIRST_EVENT (vector length shrunk in place).
        Used to cut the next chapter's intro events that the vanilla game hard-chains onto a chapter's promotion win.
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
HL = os.path.join(HERE, '..', '..', '..', '..', 'hebrew-lab')
sys.path.insert(0, os.path.join(HL, 'tools'))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'tools', 'labs', 'randomizer-lab'))
import za_romfs  # noqa: E402
import reflection_reader as rr  # noqa: E402
from chapter_swap import Buf  # noqa: E402

ROMFS = os.path.join(HL, 'qa-game-reference-20261030', 'romfs.bin')
SIZES = {1: 1, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2, 7: 4, 8: 4, 9: 8, 10: 8}


def load(out, g, path):
    dst = os.path.join(out, 'romfs', path)
    return dst, bytearray(open(dst, 'rb').read() if os.path.exists(dst) else g.read(path))


def save(dst, d):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(d)


def trainer_level(out, trid, level):
    g = za_romfs.Game(ROMFS)
    p = 'world/ik_data/trainer/trdata/trdata_array'
    sch = rr.Schema(g.read(p + '.bfbs'))
    dst, d = load(out, g, p + '.bin')
    t = sch.decode(bytes(d))
    obj = {o['name']: o for o in sch.objects}
    n = 0
    for r in t['values']:
        if r['trid'] != trid: continue
        for k in ('poke1', 'poke2', 'poke3', 'poke4', 'poke5', 'poke6'):
            pk = r[k]
            if not pk or not pk.get('devId') or 'level' not in pk['$fields']: continue
            typ = next(f['type']['base'] for o in obj.values() if not o['name'].startswith('trainer') for f in o['fields']
                       if f['name'] == 'level' and 'isOybn' in [x['name'] for x in o['fields']])
            w = SIZES[typ]
            off = pk['$fields']['level']
            old = int.from_bytes(d[off:off + w], 'little')
            d[off:off + w] = level.to_bytes(w, 'little')
            print('%s %s devId %s level %d -> %d (%d-byte field @%d)' % (trid, k, pk['devId'], old, level, w, off)); n += 1
    if not n: sys.exit('trainer not found: ' + trid)
    save(dst, d)


def cut_chain(out, battle, phase, first_event):
    g = za_romfs.Game(ROMFS)
    p = 'ik_event/bin/trigger/trainer_battle/trigger_trainer_battle_global.bin'
    dst, d = load(out, g, p)
    B = Buf(d)
    root = B.u32(0)
    vec = root + B.voff(root, 0); vec += B.u32(vec)

    def tab(slot): return slot + B.u32(slot)

    def strs(slot):
        v = tab(slot); return [B.str_at(e + B.u32(e)) for e in (v + 4 + 4 * k for k in range(B.u32(v)))]
    done = 0
    for k in range(B.u32(vec)):
        w = tab(vec + 4 + 4 * k)                      # wrapper
        t = tab(w + B.voff(w, 0))                      # trigger {0 type, 1 [target], 2 [cases]}
        if not (B.voff(t, 0) and B.voff(t, 1) and B.voff(t, 2)): continue
        try:
            if B.i32(t + B.voff(t, 0)) != 12 or strs(t + B.voff(t, 1)) != [battle]: continue
        except struct.error:
            continue
        cv = tab(t + B.voff(t, 2))
        for ci in range(B.u32(cv)):
            case = tab(cv + 4 + 4 * ci)
            gv = tab(case + B.voff(case, 1))           # [ {0: [commands]} ]
            for gi in range(B.u32(gv)):
                grp = tab(gv + 4 + 4 * gi)
                cmds = tab(grp + B.voff(grp, 0))
                n = B.u32(cmds)
                names = []
                for j in range(n):
                    c = tab(cmds + 4 + 4 * j)
                    o1 = B.voff(c, 1)
                    names.append(strs(c + o1) if o1 else [])
                hit = next((j for j, a in enumerate(names) if first_event in a), None)
                if hit is None: continue
                struct.pack_into('<I', d, cmds, hit)
                print('%s win case: %d commands -> %d (cut before %s); kept: %s' % (battle, n, hit, first_event, names[:hit]))
                done += 1
    if done != 1: sys.exit('cut-chain matched %d cases' % done)
    save(dst, d)


def cut_case(out, path, ttype, target, keep):
    """trigger file PATH: every case of trigger (type TTYPE, first target string TARGET) keeps only KEEP commands"""
    g = za_romfs.Game(ROMFS)
    dst, d = load(out, g, path)
    B = Buf(d)
    tab = lambda slot: slot + B.u32(slot)
    root = B.u32(0); vec = tab(root + B.voff(root, 0))
    done = 0
    for k in range(B.u32(vec)):
        w = tab(vec + 4 + 4 * k); t = tab(w + B.voff(w, 0))
        if not (B.voff(t, 0) and B.voff(t, 1) and B.voff(t, 2)) or B.i32(t + B.voff(t, 0)) != ttype: continue
        tv = tab(t + B.voff(t, 1))
        if not B.u32(tv) or B.str_at(tab(tv + 4)) != target: continue
        cv = tab(t + B.voff(t, 2))
        for ci in range(B.u32(cv)):
            case = tab(cv + 4 + 4 * ci); gv = tab(case + B.voff(case, 1))
            for gi in range(B.u32(gv)):
                grp = tab(gv + 4 + 4 * gi); cmds = tab(grp + B.voff(grp, 0))
                print('%s %s/%d: %d commands -> %d' % (path, target, ttype, B.u32(cmds), keep))
                struct.pack_into('<I', d, cmds, keep); done += 1
    if not done: sys.exit('cut-case matched nothing')
    save(dst, d)


def rename_exit(out, phase_id, old, new):
    """phase.bin: the exit-condition flag string OLD of entry PHASE_ID becomes NEW (same length, must be unshared)"""
    assert len(old) == len(new)
    g = za_romfs.Game(ROMFS)
    dst, d = load(out, g, 'ik_event/bin/phase/phase.bin')
    B = Buf(d)
    hits = B.strings_at(old)
    refs = B.refs_to(hits)
    if len(hits) != 1 or len(refs) != 1: sys.exit('%s: %d strings, %d refs' % (old, len(hits), len(refs)))
    d[hits[0] + 4:hits[0] + 4 + len(new)] = new.encode()
    print('phase %s exit flag %s -> %s' % (phase_id, old, new))
    save(dst, d)


if __name__ == '__main__':
    if sys.argv[1] == 'cut-case': cut_case(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5], int(sys.argv[6]))
    if sys.argv[1] == 'rename-exit': rename_exit(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    if sys.argv[1] == 'trainer-level': trainer_level(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    elif sys.argv[1] == 'cut-chain': cut_chain(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
