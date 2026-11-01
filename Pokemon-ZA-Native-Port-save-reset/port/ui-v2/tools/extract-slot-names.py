"""Builds slot-names.json (schema za-slot-names-1) for the launcher's save-slot cards from the game's own data.

usage: extract-slot-names.py GAME_REF_DIR OUT_JSON [--language English] [--hebrew-tools DIR] [--cell 4]
                             [--check-save SAVE_MAIN]

GAME_REF_DIR is a read-only own-dump game folder (romfs.bin + exefs/main), e.g. hebrew-lab/qa-game-reference-20261030.
The game files are never written. OUT_JSON holds extracted game text, so it must stay OUTSIDE git (package time only).
Reuses hebrew-lab/tools/za_romfs.py (RomFS + ONEPACK + Oodle) and gfmsg.py (message files); default location is
GAME_REF_DIR/../tools.

How the names are derived (all from the game's data):

Missions (SYS_WORK_PHASE -> current main mission)
  ik_event/bin/quest/main_quest.bin (flatbuffer, root f0 = quests): per quest f0 id ("main_02_01"), f1 display order,
  f6 title label ("msg_mainquest_title_2_1"), f11 start condition groups. 40 of 42 quests start on
  phase_condition op 5 (phase >= N); main_05_00 starts on flag_Ev_m04_5050, which is exactly the condition that sets
  phase 42030 in ik_event/bin/phase/phase.bin, so it starts at 42030; main_10_05 starts on three flags no phase sets
  (not placeable by phase, left out). Two missions are hard-coded in the exe, not in main_quest.bin: title_1_0 and
  title_10_99 (+ purpose_1_0_10 / purpose_10_99_10) are referenced only by f_70004187a4 (atlas). 1_0 is the opening
  before main_01_01 (phase 0..10099). 10_99 is not phase-placeable (left out).
  A phase maps to the quest(s) with the greatest start <= phase; quests sharing a start (the parallel rogue-mega sets,
  10_3+10_4) form one range: title = first in display order, "also_active" lists the others.
  The range ends one below the next start; the last range is open-ended.
  DLC: ik_event/bin/quest/dlc_quest.bin, same layout, starts on work_condition(SYS_WORK_DLC_PHASE, op, N):
  op 5 (>=) -> [N, next-1]; op 1 (==) -> [N, N] listed first (first match wins).
  Labels: the game shows no mission number. "Main Mission 2-1" / "Hyperspace Mission 3-1-2" are built from the
  internal ids (main_02_01, dlc3_1_2), not game text. Titles are the game's text (questlist_main / sk/questlist_dlc).

Places (coordinates block: map id + x/z)
  Area table: world/ik_data/field/area/area_config/*.bin (flatbuffers in pack ...area_config_data.bin.trpak; schemas
  ik.FieldMainAreaArray/FieldSubAreaArray/FieldLocationArray/FieldWildZoneArray in the same pack): values[] =
  {areaInfo{areaName 0, mainAreaName 24, subAreaName 25, locationName 26}, layer 1}. Layer 0 = maps ("t1", "t1_i001"
  - the coordinates block's id is this areaName), 1 = districts, 2 = sub-areas (sectors/streets), 3 = locations,
  7 = wild zones. Names are message labels in common/place_name (PLACENAME_*), place_name_spe (MAPNAME_*).
  Map names: mainAreaName, else subAreaName; ", "-joined when both; + PLACENAME_<areaName> when it exists (rooms).
  "t1" has no name label: it uses the label MAPNAME_LUMIOSE (place_name_spe, the game's name for the city).
  Geometry: world/ik_scene/field/area/t1/sub_scene/t1_field_area_/t1_field_area_0.trscn (districts, sub-areas,
  locations) and .../t1_zone/area_collision_/area_collision_0.trscn (+ its SubScenes; wild zones): each scene object
  is named after its areaName and carries a trinity_CollisionComponent -> a Havok TAG0 .trcol holding an
  hknpMeshShape: a flat ground polygon (y = const). Triangles are read from its geometry sections (u8x4 primitives;
  vertices float3, or u16x3 + section offset in 1/bitScale16 units) and placed with the object's SRT (scale, Euler
  radians, translate). The polygons are rasterized on a CELL-metre grid, each cell taking the most specific layer
  (wild zone > location > sub-area > district) and, inside a layer, the highest polygon (the meshes are stacked on
  purpose: plazas sit above their sectors, i.e. the first hit of a downward ray), then merged into axis-aligned
  boxes (first match wins in the launcher; the boxes do not overlap).
  Validation: the game's own fast-travel/jump points (FieldAreaJumpPointArray, same pack) resolve to the areas their
  debug names describe (the station front, the five district plazas, the central plaza).
"""
import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys

GAME_BUILD = 'b1f12fd919eae86ab8a978317677e64bce443d1f'
AREA_PACK = 'arc/worldik_datafieldareaarea_configarea_config_data.bin.trpak'
MAIN_QUEST = 'ik_event/bin/quest/main_quest.bin'
DLC_QUEST = 'ik_event/bin/quest/dlc_quest.bin'
PHASE = 'ik_event/bin/phase/phase.bin'
AREA_SCENES = {'t1': ['world/ik_scene/field/area/t1/sub_scene/t1_field_area_/t1_field_area_0.trscn',
                      'world/ik_scene/field/area/t1/sub_scene/t1_zone/area_collision_/area_collision_0.trscn']}
MAP_NAME_OVERRIDE = {'t1': ('common/place_name_spe', 'MAPNAME_LUMIOSE')}
LAYER_PRIORITY = {7: 0, 3: 1, 2: 2, 1: 3}      # lower = more specific (wins)
HARDCODED_OPENING = ('main_01_00', 'msg_mainquest_title_1_0', 0)   # f_70004187a4; before main_01_01 (10100)
U32_MAX = 0xFFFFFFFF


# ---------------------------------------------------------------- flatbuffers
class FB:
    def __init__(s, d): s.d = d
    def u32(s, p): return struct.unpack_from('<I', s.d, p)[0]
    def i32(s, p): return struct.unpack_from('<i', s.d, p)[0]
    def u16(s, p): return struct.unpack_from('<H', s.d, p)[0]
    def root(s): return s.u32(0)

    def field(s, t, i):
        v = t - s.i32(t)
        n = (s.u16(v) - 4) // 2
        if i >= n:
            return None
        o = s.u16(v + 4 + 2 * i)
        return t + o if o else None

    def int_(s, t, i, dflt=0):
        p = s.field(t, i)
        return dflt if p is None else s.i32(p)

    def str_(s, t, i):
        p = s.field(t, i)
        if p is None:
            return ''
        q = p + s.u32(p)
        return s.d[q + 4:q + 4 + s.u32(q)].decode('utf-8')

    def tab(s, t, i):
        p = s.field(t, i)
        return None if p is None else p + s.u32(p)

    def vec(s, t, i):
        p = s.field(t, i)
        if p is None:
            return []
        q = p + s.u32(p)
        return [q + 4 + 4 * k + s.u32(q + 4 + 4 * k) for k in range(s.u32(q))]

    def strvec(s, t, i):
        return [s.d[q + 4:q + 4 + s.u32(q)].decode('utf-8') for q in s.vec(t, i)]

    def bytes_(s, t, i):
        p = s.field(t, i)
        if p is None:
            return b''
        q = p + s.u32(p)
        return s.d[q + 4:q + 4 + s.u32(q)]

    def floats(s, t, i, n, dflt):
        p = s.field(t, i)
        return dflt if p is None else struct.unpack_from('<%df' % n, s.d, p)


# ---------------------------------------------------------------- messages
class Messages:
    def __init__(self, game, gfmsg, language):
        self.g, self.gfmsg, self.lang, self.cache = game, gfmsg, language, {}

    def file(self, name):
        if name not in self.cache:
            p = 'ik_message/dat/%s/%s' % (self.lang, name)
            m = self.gfmsg.MsgFile(self.g.read(p + '.dat'))
            t = self.gfmsg.read_tbl(self.g.read(p + '.tbl'))
            self.cache[name] = {lab: clean(self.gfmsg.decode_units(u)) for (_, lab), u in zip(t, m.lines)}
        return self.cache[name]

    def get(self, name, label):
        return self.file(name).get(label, '')


def clean(s):
    s = re.sub(r'\{VAR [^}]*\}', '', s).replace('{{', '{').replace('}}', '}')
    return re.sub(r'\s+', ' ', s).strip()


# ---------------------------------------------------------------- missions
def quests(data):
    fb = FB(data)
    out = []
    for q in fb.vec(fb.root(), 0):
        groups = [[(fb.str_(c, 0), fb.int_(c, 1), fb.strvec(c, 2)) for c in fb.vec(g, 0)] for g in fb.vec(q, 11)]
        out.append(dict(id=fb.str_(q, 0), order=fb.int_(q, 1), work=fb.str_(q, 5), title_label=fb.str_(q, 6), start=groups))
    return out


def phase_by_flag(data):
    """flag -> the phase value whose (single) transition condition is that flag"""
    fb = FB(data)
    out = {}
    for t in fb.vec(fb.root(), 0):
        groups = [[(fb.str_(c, 0), fb.int_(c, 1), fb.strvec(c, 2)) for c in fb.vec(g, 0)] for g in fb.vec(t, 1)]
        if len(groups) == 1 and len(groups[0]) == 1 and groups[0][0][0] == 'flag_condition':
            out.setdefault(groups[0][0][2][0], fb.int_(t, 0))
    return out


def label_for(qid):
    m = re.fullmatch(r'main_(\d+)_(\d+)', qid)
    if m:
        return 'Main Mission %d-%d' % (int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r'dlc(\d+(?:_\d+)*)', qid)
    if m:
        return 'Hyperspace Mission ' + m.group(1).replace('_', '-')
    return qid


def build_ranges(entries, msgs, msgfile):
    """entries: [(start, exact, quest)] -> list of ranges, == ranges first, then >= ranges in order"""
    exact = [e for e in entries if e[1]]
    ge = sorted([e for e in entries if not e[1]], key=lambda e: (e[0], e[2]['order']))
    starts = sorted(set(e[0] for e in ge))
    out = []
    for s, _, q in sorted(exact, key=lambda e: e[0]):
        out.append(dict(phase_min=s, phase_max=s, label=label_for(q['id']), title=msgs.get(msgfile, q['title_label']),
                        quest=q['id'], work=q['work']))
    for i, s in enumerate(starts):
        group = [e[2] for e in ge if e[0] == s]
        hi = starts[i + 1] - 1 if i + 1 < len(starts) else U32_MAX
        first = group[0]
        r = dict(phase_min=s, phase_max=hi, label=label_for(first['id']) + (' (+%d)' % (len(group) - 1) if len(group) > 1 else ''),
                 title=msgs.get(msgfile, first['title_label']), quest=first['id'], work=first['work'])
        if len(group) > 1:
            r['also_active'] = [dict(label=label_for(q['id']), title=msgs.get(msgfile, q['title_label']), quest=q['id'],
                                     work=q['work']) for q in group[1:]]
        out.append(r)
    return out


def missions(game, msgs, notes):
    pf = phase_by_flag(game.read(PHASE))
    entries = []
    for q in quests(game.read(MAIN_QUEST)):
        st = q['start']
        if len(st) == 1 and len(st[0]) == 1 and st[0][0][0] == 'phase_condition' and st[0][0][1] == 5:
            entries.append((int(st[0][0][2][0]), False, q))
        elif len(st) == 1 and len(st[0]) == 1 and st[0][0][0] == 'flag_condition' and st[0][0][2][0] in pf:
            entries.append((pf[st[0][0][2][0]], False, q))
            notes.append('%s starts on %s = the condition of phase %d' % (q['id'], st[0][0][2][0], pf[st[0][0][2][0]]))
        else:
            notes.append('%s not placeable by phase (start %s)' % (q['id'], st))
    qid, lab, start = HARDCODED_OPENING
    entries.append((start, False, dict(id=qid, order=0, work='', title_label=lab)))
    story = build_ranges(entries, msgs, 'common/questlist_main')
    for r in story:
        if r['quest'] == qid:
            r['label'] = 'Main Mission 1-0'
            r.pop('work')
    dentries = []
    for q in quests(game.read(DLC_QUEST)):
        st = q['start']
        c = st[0][0] if len(st) == 1 and len(st[0]) == 1 else None
        if c and c[0] == 'work_condition' and c[2][0] == 'SYS_WORK_DLC_PHASE' and c[1] in (1, 5):
            dentries.append((int(c[2][1]), c[1] == 1, q))
        else:
            notes.append('%s not placeable by DLC phase (start %s)' % (q['id'], st))
    return story, build_ranges(dentries, msgs, 'sk/questlist_dlc')


# ---------------------------------------------------------------- area table
def area_table(game):
    """areaName -> dict(layer, main, sub, loc) from every FieldArea-shaped flatbuffer in the area_config pack"""
    recs = dict(game.packs)[AREA_PACK]
    areas = {}
    for r in recs:
        d = game.unpack(r)
        if d[4:8] == b'BFBS' or len(d) < 16:
            continue
        try:
            fb = FB(d)
            rows = []
            for v in fb.vec(fb.root(), 0):
                a = fb.tab(v, 0)
                name = fb.str_(a, 0)
                if not re.fullmatch(r'[A-Za-z0-9_]+', name):
                    raise ValueError
                rows.append((name, dict(layer=fb.int_(v, 1), cat=fb.str_(a, 2), main=fb.str_(a, 24), sub=fb.str_(a, 25),
                                        loc=fb.str_(a, 26), map_id=fb.str_(a, 29))))
        except Exception:
            continue
        if rows:
            for name, x in rows:
                areas.setdefault(name, x)
    return areas


def place_label(msgs, label):
    if not label:
        return ''
    for f in ('common/place_name', 'common/place_name_spe'):
        s = msgs.get(f, label)
        if s:
            return s
    return ''


def map_names(areas, msgs):
    out = {}
    for name, a in sorted(areas.items()):
        if a['layer'] != 0:
            continue
        if name in MAP_NAME_OVERRIDE:
            out[name] = msgs.get(*MAP_NAME_OVERRIDE[name])
            continue
        parts = [place_label(msgs, a['main']), place_label(msgs, a['sub'])]
        own = place_label(msgs, 'PLACENAME_' + name)
        parts = [p for i, p in enumerate(parts + [own]) if p and p not in parts[:i] and p not in ('???',)]
        if parts:
            out[name] = ', '.join(parts)
    return out


def area_name(msgs, a):
    for lab in (a['loc'], a['sub'], a['main']):
        s = place_label(msgs, lab)
        if s:
            return s
    return ''


# ---------------------------------------------------------------- scenes + Havok meshes
def _hk_sections(d, p, end):
    out = {}
    while p + 8 <= end:
        h = struct.unpack_from('>I', d, p)[0]
        size = h & 0x3FFFFFFF
        if size < 8:
            break
        out.setdefault(d[p + 4:p + 8].decode('latin1'), (p + 8, p + size))
        p += size
    return out


def _packed(d, p):
    b = d[p]
    if b < 0x80: return b, p + 1
    if b < 0xC0: return ((b & 0x3F) << 8) | d[p + 1], p + 2
    if b < 0xE0: return ((b & 0x1F) << 16) | (d[p + 1] << 8) | d[p + 2], p + 3
    if b < 0xE8: return ((b & 0x07) << 24) | int.from_bytes(d[p + 1:p + 4], 'big'), p + 4
    if b < 0xF0: return ((b & 0x07) << 32) | int.from_bytes(d[p + 1:p + 5], 'big'), p + 5
    return int.from_bytes(d[p + 1:p + 9], 'big'), p + 9


def mesh_triangles(d):
    """hknpMeshShape in a Havok TAG0 (.trcol) -> [((x,y,z),)*3] in the shape's frame"""
    top = _hk_sections(d, 0, len(d))
    sub = _hk_sections(d, *top['TAG0'])
    data0 = sub['DATA'][0]
    ty = _hk_sections(d, *sub['TYPE'])
    ix = _hk_sections(d, *sub['INDX'])
    tst = [x.decode('latin1') for x in d[ty['TST1'][0]:ty['TST1'][1]].split(b'\0')]
    p = ty['TNA1'][0]
    n, p = _packed(d, p)
    names = [None]
    for _ in range(1, n):
        ni, p = _packed(d, p)
        nt, p = _packed(d, p)
        for _ in range(nt):
            _, p = _packed(d, p)
            _, p = _packed(d, p)
        names.append(tst[ni])
    items = []
    for q in range(ix['ITEM'][0], ix['ITEM'][1], 12):
        t, off, cnt = struct.unpack_from('<III', d, q)
        items.append((names[t & 0xFFFFFF] if t & 0xFFFFFF else None, data0 + off, cnt))
    mesh = [it for it in items if it[0] == 'hknpMeshShape']
    if not mesh:
        return None
    inv = 1.0 / struct.unpack_from('<f', d, mesh[0][1] + 0x20)[0]   # vertexConversionUtil.bitScale16
    tris = []
    for name, off, cnt in items:
        if name != 'hknpMeshShape::GeometrySection':
            continue
        for s in range(cnt):
            base = off + 0x30 * s
            _bvh, ip, iv, _bits = struct.unpack_from('<4I', d, base)
            so = struct.unpack_from('<3i', d, base + 0x10)
            pn, pp, pc = items[ip]
            vn, vp, vc = items[iv]
            if pn != 'hknpMeshShape::GeometrySection::Primitive':
                raise ValueError('unexpected section layout: %s' % pn)
            if so == (0x7FFFFFFF,) * 3:
                verts = [struct.unpack_from('<3f', d, vp + 12 * k) for k in range(vc // 12)]
            else:
                verts = [tuple((so[j] + q) * inv for j, q in enumerate(struct.unpack_from('<3H', d, vp + 6 * k)))
                         for k in range(vc // 6)]
            for k in range(pc):
                i0, i1, i2, i3 = d[pp + 4 * k:pp + 4 * k + 4]
                tris.append((verts[i0], verts[i1], verts[i2]))
                if i3 != i2:
                    tris.append((verts[i0], verts[i2], verts[i3]))
    return tris


def srt_apply(srt, v):
    (sx, sy, sz), (rx, ry, rz), (tx, ty, tz) = srt
    x, y, z = v[0] * sx, v[1] * sy, v[2] * sz
    # Euler X, Y, Z (radians); the area objects only use Y (0 or pi)
    cy, sy_ = math.cos(rx), math.sin(rx)
    y, z = y * cy - z * sy_, y * sy_ + z * cy
    c, s = math.cos(ry), math.sin(ry)
    x, z = x * c + z * s, -x * s + z * c
    c, s = math.cos(rz), math.sin(rz)
    x, y = x * c - y * s, x * s + y * c
    return x + tx, y + ty, z + tz


def _transform(fb, t):
    return (fb.floats(t, 0, 3, (1.0, 1.0, 1.0)), fb.floats(t, 1, 3, (0.0, 0.0, 0.0)), fb.floats(t, 2, 3, (0.0, 0.0, 0.0)))


def scene_area_objects(game, path, depth=0):
    """[(object name, srt, trcol path)] for every collision object of a trinity scene (+ SubScenes)"""
    fb = FB(game.read(path))
    out = []
    folder = path.rsplit('/', 1)[0]
    for e in fb.vec(fb.root(), 4):
        kind = fb.str_(e, 0)
        data = fb.bytes_(e, 1)
        if kind == 'SubScene' and depth < 4:
            sfb = FB(data)
            rel = sfb.str_(sfb.root(), 0)
            target = os.path.normpath(folder + '/' + rel).replace('\\', '/')
            target = target[:-len('.trscn')] + '_0.trscn'
            if game.has(target):
                out += scene_area_objects(game, target, depth + 1)
            continue
        if kind == 'trinity_SceneObject':
            sfb = FB(data)
            name, srt = sfb.str_(sfb.root(), 0), _transform(sfb, sfb.tab(sfb.root(), 1))
        elif kind == 'trinity_ObjectTemplate':
            tfb = FB(data)
            name = tfb.str_(tfb.root(), 0)
            sfb = FB(tfb.bytes_(tfb.root(), 5))
            srt = _transform(sfb, sfb.tab(sfb.root(), 1))
        else:
            continue
        for c in fb.vec(e, 2):
            if fb.str_(c, 0) != 'trinity_CollisionComponent':
                continue
            cfb = FB(fb.bytes_(c, 1))
            t = cfb.tab(cfb.root(), 1)
            paths = cfb.vec(t, 1) if t is not None else []
            if paths:
                q = paths[0]
                out.append((name, srt, cfb.d[q + 4:q + 4 + cfb.u32(q)].decode('utf-8')))
    return out


# ---------------------------------------------------------------- rasterize -> boxes
def rasterize(polys, cell):
    """polys: [(layer priority, name, [(tri xz, y)])] -> non-overlapping boxes [(name, x0, z0, x1, z1)].
    A cell takes the triangle containing its centre with the lowest (layer priority, -y): the most specific layer,
    and inside a layer the highest polygon - the area meshes are stacked on purpose (a plaza
    about 6 m above the sector under it), i.e. the first hit of a downward ray."""
    xs = [p[0] for _, _, tris in polys for t, _ in tris for p in t]
    zs = [p[1] for _, _, tris in polys for t, _ in tris for p in t]
    ox, oz = math.floor(min(xs) / cell) * cell, math.floor(min(zs) / cell) * cell
    nx, nz = int(math.ceil((max(xs) - ox) / cell)) + 1, int(math.ceil((max(zs) - oz) / cell)) + 1
    grid = [[None] * nx for _ in range(nz)]
    best = [[(99,)] * nx for _ in range(nz)]
    names = []
    for layer, name, tris in polys:
        if name not in names:
            names.append(name)
        idx = names.index(name)
        for ((ax, az), (bx, bz), (cx, cz)), ty in tris:
            prio = (layer, -ty)
            den = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(den) < 1e-9:
                continue
            i0 = max(0, int((min(ax, bx, cx) - ox) / cell)); i1 = min(nx - 1, int((max(ax, bx, cx) - ox) / cell))
            j0 = max(0, int((min(az, bz, cz) - oz) / cell)); j1 = min(nz - 1, int((max(az, bz, cz) - oz) / cell))
            for j in range(j0, j1 + 1):
                pz = oz + (j + 0.5) * cell
                for i in range(i0, i1 + 1):
                    px = ox + (i + 0.5) * cell
                    l1 = ((bz - cz) * (px - cx) + (cx - bx) * (pz - cz)) / den
                    l2 = ((cz - az) * (px - cx) + (ax - cx) * (pz - cz)) / den
                    if l1 >= -1e-6 and l2 >= -1e-6 and l1 + l2 <= 1 + 1e-6 and prio < best[j][i]:
                        best[j][i] = prio
                        grid[j][i] = idx
    # row runs, then merge identical runs of consecutive rows into boxes
    boxes, open_ = [], {}
    for j in range(nz + 1):
        runs = {}
        if j < nz:
            row, i = grid[j], 0
            while i < nx:
                if row[i] is None:
                    i += 1
                    continue
                k = i
                while k + 1 < nx and row[k + 1] == row[i]:
                    k += 1
                runs[(i, k, row[i])] = True
                i = k + 1
        nxt = {}
        for key in runs:
            nxt[key] = open_.pop(key, j)
        for (i, k, idx), j0 in open_.items():
            boxes.append((names[idx], ox + i * cell, oz + j0 * cell, ox + (k + 1) * cell, oz + j * cell))
        open_ = nxt
    return boxes


def areas_for_map(game, msgs, areas, map_id, cell, notes):
    polys, missing, skipped = [], [], []
    for sp in AREA_SCENES.get(map_id, []):
        for name, srt, col in scene_area_objects(game, sp):
            a = areas.get(name)
            if not a or a['layer'] not in LAYER_PRIORITY:
                skipped.append(name)
                continue
            label = area_name(msgs, a)
            if not label:
                skipped.append(name)
                continue
            try:
                tris = mesh_triangles(game.read(col))
            except KeyError:
                missing.append(col)
                continue
            if not tris:
                missing.append(col)
                continue
            w = []
            for t in tris:
                q = [srt_apply(srt, v) for v in t]
                w.append((tuple((v[0], v[2]) for v in q), sum(v[1] for v in q) / 3))
            polys.append((LAYER_PRIORITY[a['layer']], label, w))
    notes.append('%s: %d named area polygons; unnamed/other objects skipped: %d; unreadable meshes: %s'
                 % (map_id, len(polys), len(skipped), missing or 'none'))
    if not polys:
        return []
    num = lambda v: int(round(v)) if abs(v - round(v)) < 1e-6 else round(v, 2)
    return [dict(map=map_id, name=n, x0=num(x0), z0=num(z0), x1=num(x1), z1=num(z1))
            for n, x0, z0, x1, z1 in rasterize(polys, cell)]


# ---------------------------------------------------------------- optional save check
def check_save(path, names):
    """decode SYS_WORK_PHASE / DLC phase / coordinates from a save main (SwishCrypto blocks) and resolve them"""
    xor = bytes([0xA0, 0x92, 0xD1, 0x06, 0x07, 0xDB, 0x32, 0xA1, 0xAE, 0x01, 0xF5, 0xC5, 0x1E, 0x84, 0x4F, 0xE3, 0x53, 0xCA,
                 0x37, 0xF4, 0xA7, 0xB0, 0x4D, 0xA0, 0x18, 0xB7, 0xC2, 0x97, 0xDA, 0x5F, 0x53, 0x2B, 0x75, 0xFA, 0x48, 0x16,
                 0xF8, 0xD4, 0x8A, 0x6F, 0x61, 0x05, 0xF4, 0xE2, 0xFD, 0x04, 0xB5, 0xA3, 0x0F, 0xFC, 0x44, 0x92, 0xCB, 0x32,
                 0xE6, 0x1B, 0xB9, 0xB1, 0x2E, 0x01, 0xB0, 0x56, 0x53, 0x36, 0xD2, 0xD1, 0x50, 0x3D, 0xDE, 0x5B, 0x2E, 0x0E,
                 0x52, 0xFD, 0xDF, 0x2F, 0x7B, 0xCA, 0x63, 0x50, 0xA4, 0x67, 0x5D, 0x23, 0x17, 0xC0, 0x52, 0xE1, 0xA6, 0x30,
                 0x7C, 0x2B, 0xB6, 0x70, 0x36, 0x5B, 0x2A, 0x27, 0x69, 0x33, 0xF5, 0x63, 0x7B, 0x36, 0x3F, 0x26, 0x9B, 0xA3,
                 0xED, 0x7A, 0x53, 0x00, 0xA4, 0x48, 0xB3, 0x50, 0x9E, 0x14, 0xA0, 0x52, 0xDE, 0x7E, 0x10, 0x2B, 0x1B, 0x77,
                 0x6E])
    d = open(path, 'rb').read()
    n = len(d) - 32
    p = bytes(d[i] ^ xor[i % 0x7F] for i in range(n))
    M = 0xFFFFFFFF

    def adv(v):
        v ^= (v << 2) & M; v ^= v >> 15; v ^= (v << 13) & M
        return v

    class X:
        def __init__(s, seed):
            s.s, s.c = seed, 0
            for _ in range(bin(seed).count('1')):
                s.s = adv(s.s)

        def nx(s):
            r = (s.s >> (s.c * 8)) & 0xFF
            if s.c == 3:
                s.s, s.c = adv(s.s), 0
            else:
                s.c += 1
            return r

        def n32(s): return s.nx() | s.nx() << 8 | s.nx() << 16 | s.nx() << 24
    ts = {3: 1, 8: 1, 12: 1, 9: 2, 13: 2, 10: 4, 14: 4, 16: 4, 11: 8, 15: 8, 17: 8}
    blocks, at = {}, 0
    while at < n:
        key = struct.unpack_from('<I', p, at)[0]; at += 4
        x = X(key); t = p[at] ^ x.nx(); at += 1
        if t in (1, 2, 3): size = 0
        elif t == 4: size = struct.unpack_from('<I', p, at)[0] ^ x.n32(); at += 4
        elif t == 5:
            cnt = struct.unpack_from('<I', p, at)[0] ^ x.n32(); at += 4
            sub = ts[p[at] ^ x.nx()]; at += 1; size = cnt * sub
        else: size = ts[t]
        if key in (0xFADA7742, 0x910D381F):
            blocks[key] = bytes(p[at + i] ^ x.nx() for i in range(size))
        at += size

    def fnv(s):
        h = 0xCBF29CE484222645
        for ch in s.encode():
            h = ((h ^ ch) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        return h
    want = {fnv('SYS_WORK_PHASE'): 'phase', fnv('SYS_WORK_DLC_PHASE'): 'dlc'}
    vals = {'phase': 0, 'dlc': 0}
    w = blocks[0xFADA7742]
    for i in range(len(w) // 16):
        k, v = struct.unpack_from('<QQ', w, i * 16)
        if k in want:
            vals[want[k]] = v
    c = blocks[0x910D381F]
    map_id = c[:0x20].split(b'\0')[0].decode('ascii', 'replace')
    x, y, z = struct.unpack_from('<3f', c, 0x20)
    print('save: phase %d, dlc phase %d, map %s, position x=%.2f y=%.2f z=%.2f' % (vals['phase'], vals['dlc'], map_id, x, y, z))
    print('  mission:', resolve_mission(names, vals['phase'], vals['dlc']))
    print('  place:  ', resolve_place(names, map_id, x, z))


def resolve_mission(names, phase, dlc):
    """the launcher's Names::mission (launcher_core.cpp)"""
    def find(lst, v):
        return next((r for r in lst if r['phase_min'] <= v <= r['phase_max']), None)

    def join(r):
        return r['title'] if not r.get('label') else r['label'] if not r.get('title') else r['label'] + '  ·  ' + r['title']
    r = find(names['missions'], phase)
    if r:
        return join(r)
    if dlc:
        r = find(names['dlc_missions'], dlc)
        if r:
            return join(r)
    return 'Phase %d' % phase if phase else ''


def resolve_place(names, map_id, x, z):
    """the launcher's Names::place"""
    m = names['maps'].get(map_id, '')
    for a in names['areas']:
        if a['map'] == map_id and min(a['x0'], a['x1']) <= x <= max(a['x0'], a['x1']) and min(a['z0'], a['z1']) <= z <= max(a['z0'], a['z1']):
            return (m or map_id) + ' — ' + a['name']
    return m or map_id


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('game_ref')
    ap.add_argument('out_json')
    ap.add_argument('--language', default='English')
    ap.add_argument('--hebrew-tools', default=None, help='folder with za_romfs.py, gfmsg.py, bin/ooz.dll')
    ap.add_argument('--cell', type=float, default=6.0, help='raster cell (metres) for the area boxes')
    ap.add_argument('--check-save', action='append', default=[], help='a save main to resolve with the result')
    ap.add_argument('--phase', action='append', type=int, default=[], help='phases to resolve with the result')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    tools = a.hebrew_tools or os.path.join(os.path.dirname(os.path.abspath(a.game_ref)), 'tools')
    sys.path.insert(0, tools)
    import za_romfs  # noqa: E402
    import gfmsg  # noqa: E402

    out_abs = os.path.abspath(a.out_json)
    probe = os.path.dirname(out_abs)
    while probe and not os.path.exists(os.path.join(probe, '.git')):
        up = os.path.dirname(probe)
        probe = None if up == probe else up
    # refuse the port's own trees (main checkout + its worktrees, recognised by port/ui-v2): the output holds game text
    if probe and (os.path.isfile(os.path.join(probe, '.git')) or os.path.isdir(os.path.join(probe, 'port', 'ui-v2'))):
        sys.exit('refusing: %s is inside the port work tree %s; the output holds game text' % (out_abs, probe))

    main_nso = open(os.path.join(a.game_ref, 'exefs', 'main'), 'rb').read(0x60)
    build = main_nso[0x40:0x54].hex() if main_nso[:4] == b'NSO0' else ''
    if build != GAME_BUILD:
        print('warning: game build %s != expected %s' % (build, GAME_BUILD))
    game = za_romfs.Game(os.path.join(a.game_ref, 'romfs.bin'))
    msgs = Messages(game, gfmsg, a.language)
    notes = []
    story, dlc = missions(game, msgs, notes)
    areas = area_table(game)
    maps = map_names(areas, msgs)
    boxes = []
    for map_id in AREA_SCENES:
        boxes += areas_for_map(game, msgs, areas, map_id, a.cell, notes)
    result = {'schema': 'za-slot-names-1', 'game_build': build, 'language': a.language,
              'generator': 'port/ui-v2/tools/extract-slot-names.py', 'area_cell_m': a.cell,
              'missions': story, 'dlc_missions': dlc, 'maps': maps, 'areas': boxes}
    text = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    with open(out_abs, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    raw = text.encode('utf-8')
    for n_ in notes:
        print('note:', n_)
    print('missions %d, dlc missions %d, maps %d named (of %d), areas %d boxes (%d names)'
          % (len(story), len(dlc), len(maps), sum(1 for x in areas.values() if x['layer'] == 0), len(boxes),
             len(set(b['name'] for b in boxes))))
    print('wrote %s  %d bytes  sha256 %s' % (out_abs, len(raw), hashlib.sha256(raw).hexdigest()))
    for ph in a.phase:
        print('phase %d -> %s' % (ph, resolve_mission(result, ph, 0)))
    for s in a.check_save:
        check_save(s, result)


if __name__ == '__main__':
    main()
