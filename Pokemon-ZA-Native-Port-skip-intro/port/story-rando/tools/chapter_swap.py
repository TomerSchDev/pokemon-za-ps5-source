"""Swap two adjacent chapter blocks of the Z-A story as a romfs mod (in-place FlatBuffers patches, no re-encode).

What it changes (minimal patch set for two blocks A then B -> B then A, where A's phase ids start with digit DA and
B's with DB, e.g. chapters 5 and 6 -> --digits 5:6):
  1. ik_event/bin/phase/phase.bin: B's entries are moved in the vector before A's, and every entry id 5xxxx<->6xxxx
     is renumbered (so the numeric order matches the new play order).
  2. every phase_condition argument in every ik_event table and the shop lineup: 5-digit values starting with DA/DB
     get the leading digit swapped (same length -> in place). Same for ("SYS_WORK_PHASE", value) string pairs
     (work_condition / set-work commands).
  3. quest start conditions given as flags (--quest-start main_05_00:OLDFLAG=NEWFLAG): same-length string replace,
     only inside that quest's start condition.
Not touched (documented gaps): the 22 Lua phase constants in event_ik.blua, Royale rank thresholds/caps by position.

usage: chapter_swap.py OUTMOD --digits 5:6 --move 110:128 --before 87 [--quest-start main_05_00:flag_a=flag_b]
OUTMOD must be outside git (it holds game data). Writes OUTMOD/romfs/<path> for changed files + OUTMOD/patch-log.json.
"""
import argparse, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
HL = os.path.join(HERE, '..', '..', '..', '..', 'hebrew-lab')
sys.path.insert(0, os.path.join(HL, 'tools'))
import za_romfs  # noqa: E402

TABLES = ['ik_event/bin/phase/phase', 'ik_event/bin/phase/dlc_phase', 'ik_event/bin/quest/main_quest',
          'ik_event/bin/quest/sub_quest', 'ik_event/bin/quest/momiji_quest', 'ik_event/bin/quest/dlc_quest',
          'ik_event/bin/event_control/event_control', 'ik_event/bin/trigger/global/trigger_global',
          'ik_event/bin/trigger/map/trigger_map_t2', 'ik_event/bin/npc_talk_data/npc_talk_data',
          'ik_event/bin/npc_talk_data/za_trainer_talk_data', 'ik_event/bin/return_point/fiexd_return_point',
          'ik_event/bin/return_point/return_point', 'ik_event/bin/return_point/pokecen',
          'ik_event/bin/menu_visible_type/menu_visible_type', 'ik_event/bin/destination_data/destination_data',
          'ik_event/bin/trigger/boss_battle/trigger_boss_battle_global',
          'ik_event/bin/trigger/trainer_battle/trigger_trainer_battle_global',
          'ik_event/bin/trigger/wild_battle/trigger_wild_battle_global',
          'ik_event/bin/trigger/last_battle/trigger_last_battle_global',
          'ik_event/bin/trigger/athletic_time_attack/trigger_athletic_time_attack',
          'ik_event/bin/trigger/minigame/trigger_marugoshi_survivor', 'ik_event/bin/mission_card/mission_card',
          'ik_event/bin/title/title', 'ik_event/bin/tips/tips', 'ik_event/bin/hud_tips/hud_tips',
          'ik_event/bin/event_taxi_data/taxi_destination_data', 'ik_event/bin/door_jump_name_overwrite/door_jump_name_overwrite',
          'world/exl/shop/shop_item_lineup/shop_item_lineup'] + \
         ['ik_event/bin/trigger/main/trigger_main_%02d' % i for i in range(11)] + \
         ['ik_event/bin/trigger/dlc/trigger_dlc_%02d' % i for i in range(1, 10)]


class Buf:
    def __init__(s, d): s.d = d; s.n = len(d)
    def u32(s, p): return struct.unpack_from('<I', s.d, p)[0]
    def i32(s, p): return struct.unpack_from('<i', s.d, p)[0]
    def u16(s, p): return struct.unpack_from('<H', s.d, p)[0]

    def table_ok(s, t):
        if t < 4 or t % 4 or t + 4 > s.n: return False
        v = t - s.i32(t)
        if v < 0 or v + 4 > s.n or v % 2: return False
        vs, ts = s.u16(v), s.u16(v + 2)
        return 4 <= vs <= 256 and vs % 2 == 0 and 4 <= ts <= 8192 and v + vs <= s.n

    def voff(s, t, i):
        v = t - s.i32(t); vs = s.u16(v)
        return s.u16(v + 4 + 2 * i) if 4 + 2 * i < vs else 0

    def strings_at(s, name):
        b = name.encode()
        pat = struct.pack('<I', len(b)) + b + b'\0'
        out, i = [], s.d.find(pat)
        while i >= 0:
            if i % 4 == 0: out.append(i)
            i = s.d.find(pat, i + 1)
        return out

    def refs_to(s, targets):
        tg = set(targets)
        return [p for p in range(0, s.n - 3, 4) if (p + s.u32(p)) in tg and s.u32(p)]

    def str_at(s, p):
        n = s.u32(p)
        return bytes(s.d[p + 4:p + 4 + n]).decode('utf-8', 'replace') if 0 < n < 64 and p + 4 + n <= s.n else None

    def vec_strings(s, slot):
        v = slot + s.u32(slot); n = s.u32(v)
        if not 0 < n < 16: return []
        return [e + s.u32(e) for e in (v + 4 + 4 * k for k in range(n))]


def swap_digit(txt, a, b):
    if len(txt) == 5 and txt.isdigit() and txt[0] in (a, b):
        return (b if txt[0] == a else a) + txt[1:]
    return None


def patch_conditions(d, a, b, log, path):
    B = Buf(d)
    done = set()
    n = 0
    names = B.strings_at('phase_condition')
    for slot in B.refs_to(names):
        for o in range(4, 68, 4):
            t = slot - o
            if B.table_ok(t) and B.voff(t, 0) == o:
                o2 = B.voff(t, 2)
                if not o2: break
                for sp in B.vec_strings(t + o2):
                    txt = B.str_at(sp)
                    new = swap_digit(txt or '', a, b)
                    if new and sp not in done:
                        d[sp + 4:sp + 9] = new.encode(); done.add(sp); n += 1
                break
    # ("SYS_WORK_PHASE", value) pairs anywhere (work_condition args / set-work commands)
    for e in B.refs_to(B.strings_at('SYS_WORK_PHASE')):
        nxt = e + 4
        if nxt + 4 <= B.n:
            sp = nxt + B.u32(nxt)
            txt = B.str_at(sp) if sp < B.n else None
            new = swap_digit(txt or '', a, b)
            if new and sp not in done:
                d[sp + 4:sp + 9] = new.encode(); done.add(sp); n += 1
    if n: log.append(dict(file=path, phase_args_swapped=n))
    return n


def patch_phase_table(d, a, b, lo, hi, before, log):
    B = Buf(d)
    root = B.u32(0)
    f0 = B.voff(root, 0)
    vec = root + f0 + B.u32(root + f0)
    n = B.u32(vec)
    slots = [vec + 4 + 4 * i for i in range(n)]
    targets = [s + B.u32(s) for s in slots]
    ids = []
    for t in targets:
        o = B.voff(t, 0)
        if o:
            v = B.i32(t + o)
            s = str(v)
            new = swap_digit(s, a, b)
            if new:
                struct.pack_into('<i', d, t + o, int(new))
                v = int(new)
            ids.append(v)
        else:
            ids.append(0)
    order = list(range(n))
    block = order[lo:hi + 1]
    rest = [i for i in order if not lo <= i <= hi]
    k = rest.index(before)
    new_order = rest[:k] + block + rest[k:]
    for s, i in zip(slots, new_order):
        struct.pack_into('<I', d, s, targets[i] - s)
    seq = [ids[i] for i in new_order]
    mono = all(x < y for x, y in zip(seq[1:], seq[2:]))
    log.append(dict(file='ik_event/bin/phase/phase.bin', moved=[lo, hi], before=before, new_order=seq, monotonic=mono))
    return mono


def patch_quest_start(d, quest, old, new, log):
    assert len(old) == len(new)
    B = Buf(d)
    root = B.u32(0)
    vec = root + B.voff(root, 0); vec += B.u32(vec)
    hits = 0
    for k in range(B.u32(vec)):
        e = vec + 4 + 4 * k; q = e + B.u32(e)
        if B.str_at(q + B.voff(q, 0) + B.u32(q + B.voff(q, 0))) != quest: continue
        o11 = B.voff(q, 11)
        gv = q + o11 + B.u32(q + o11)
        for gi in range(B.u32(gv)):
            ge = gv + 4 + 4 * gi; g = ge + B.u32(ge)
            cv = g + B.voff(g, 0); cv += B.u32(cv)
            for ci in range(B.u32(cv)):
                ce = cv + 4 + 4 * ci; c = ce + B.u32(ce)
                o2 = B.voff(c, 2)
                for sp in B.vec_strings(c + o2):
                    if B.str_at(sp) == old:
                        users = B.refs_to([sp])
                        if len(users) != 1: raise SystemExit('string %s shared by %d refs; needs a re-encode' % (old, len(users)))
                        d[sp + 4:sp + 4 + len(new)] = new.encode(); hits += 1
    log.append(dict(file='ik_event/bin/quest/main_quest.bin', quest=quest, start_flag=[old, new], hits=hits))
    if hits != 1: raise SystemExit('quest start patch hit %d times' % hits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--digits', required=True)
    ap.add_argument('--move', required=True); ap.add_argument('--before', type=int, required=True)
    ap.add_argument('--quest-start', action='append', default=[])
    ap.add_argument('--romfs', default=os.path.join(HL, 'qa-game-reference-20261030', 'romfs.bin'))
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    repo = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
    if os.path.commonpath([out, repo]) == repo: sys.exit('OUTMOD must be outside git')
    da, db = a.digits.split(':')
    lo, hi = map(int, a.move.split(':'))
    g = za_romfs.Game(a.romfs)
    log = []
    for base in TABLES:
        path = base + '.bin'
        if not g.has(path): continue
        d = bytearray(g.read(path)); orig = bytes(d)
        if path.endswith('phase/phase.bin'):
            if not patch_phase_table(d, da, db, lo, hi, a.before, log): sys.exit('new phase order is not monotonic')
        patch_conditions(d, da, db, log, path)
        if path.endswith('quest/main_quest.bin'):
            for qs in a.quest_start:
                q, rest = qs.split(':', 1); old, new = rest.split('=')
                patch_quest_start(d, q, old, new, log)
        if bytes(d) != orig:
            dst = os.path.join(out, 'romfs', path); os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(d)
    json.dump(log, open(os.path.join(out, 'patch-log.json'), 'w'), indent=1)
    for l in log:
        print({k: (v if k != 'new_order' else '%d ids' % len(v)) for k, v in l.items()})


if __name__ == '__main__':
    main()
