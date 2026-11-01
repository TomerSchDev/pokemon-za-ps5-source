"""fb_codec (reconstruction, scalar fields only): absolute offsets of FlatBuffers scalar fields in a game table.

The original fb_codec.py (launcher-v0.2.0/source) that encoded the r15 templates is lost. The randomizer never
needed its *encoder* at run time: the templates it produced (encoded with force_defaults=True, so every scalar is
materialised) are pinned by SHA-256, and the C++ core only rewrites fields in place from {"offset","bytes","signed"}
records. This module rebuilds the part that produces those records: schema (.bfbs) + per-row vtable lookup
(reflection_reader.Schema/Buffer) -> {field: {offset, bytes, signed}} (or {"float": True} for float fields,
which core/randomizer.cpp cannot write but rando-v3's patch() can).

Out of scope, and NOT reconstructed: encoding a modified tree (adding sub-tables such as the wild holdItem, growing
vectors, new strings). Anything that needs a field that is absent from the file still needs a real encoder.

    from fb_codec import Table
    t = Table(bfbs_bytes, table_bytes)
    for row in t.rows('ik.fb.wild_pokemon.EncountData'):      # every table object of that type, decode order
        row.fields(('devNo', 'formNo', 'sex'))                   # -> {'devNo': {'offset': ..., 'bytes': 4, 'signed': True}, ...}
"""
import sys
from pathlib import Path

# FlatBuffers reflection BaseType -> (struct width, signed, float)
SCALARS = {1: (1, False, False), 2: (1, False, False), 3: (1, True, False), 4: (1, False, False), 5: (2, True, False), 6: (2, False, False),
           7: (4, True, False), 8: (4, False, False), 9: (8, True, False), 10: (8, False, False), 11: (4, False, True), 12: (8, False, True)}
STRING = 13


def _import_reader(search):
    for d in search:
        if (Path(d) / 'reflection_reader.py').is_file():
            sys.path.insert(0, str(d))
            break
    import reflection_reader  # noqa: E402
    return reflection_reader


class Row:
    """One table (row) of a known object type, with absolute scalar offsets."""

    def __init__(self, table, node, obj):
        self._t = table; self.node = node; self.obj = obj

    @property
    def offset(self): return self.node['$offset']

    def value(self, name): return self.node[name]

    def fields(self, names):
        out = {}
        types = {f['name']: f['type'] for f in self.obj['fields']}
        for name in names:
            if name not in types: raise KeyError(f"{self.obj['name']} has no field {name}")
            if name not in self.node['$fields']: raise ValueError(f'{name} is not materialised in this row (default omitted); a re-encode is needed')
            base = types[name]['base']; pos = self.node['$fields'][name]
            if base == STRING:
                target = self._t.buffer.pointer(pos)
                out[name] = {'length': target, 'data': target + 4, 'capacity': 128}  # the r15 convention for reserved strings
            elif base in SCALARS:
                width, signed, is_float = SCALARS[base]
                out[name] = {'offset': pos, 'bytes': width, 'float': True} if is_float else {'offset': pos, 'bytes': width, 'signed': signed}
            else:
                raise ValueError(f'{name}: not a scalar field (base type {base})')
        return out


class Table:
    def __init__(self, bfbs, data, reader_search=()):
        rr = _import_reader(reader_search)
        self.schema = rr.Schema(bfbs); self.buffer = rr.Buffer(data); self.data = data
        self.tree = self.schema.decode(data)
        self._by_name = {o['name']: o for o in self.schema.objects}
        self._layouts = {}
        for o in self.schema.objects:
            self._layouts.setdefault(frozenset(f['name'] for f in o['fields']), []).append(o)

    def _object_of(self, node):
        keys = frozenset(k for k in node if not k.startswith('$'))
        objs = self._layouts.get(keys)
        if not objs: raise ValueError('no reflected object has this field set')
        return objs[0]

    def rows(self, object_name):
        """Every decoded table of that object type, in decode order."""
        obj = self._by_name[object_name]; want = frozenset(f['name'] for f in obj['fields'])
        for node in self._walk(self.tree):
            if frozenset(k for k in node if not k.startswith('$')) == want:
                yield Row(self, node, obj)

    @staticmethod
    def _walk(v):
        if isinstance(v, dict):
            yield v
            for k, x in v.items():
                if not k.startswith('$'): yield from Table._walk(x)
        elif isinstance(v, list):
            for x in v: yield from Table._walk(x)

    def plain(self):
        """The tree without offsets (semantic equality between an original file and its force_defaults template)."""
        return self.schema.decode(self.data, offsets=False)
