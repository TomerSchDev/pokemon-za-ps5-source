"""Freeze reviewed NPC spellings against exact source rows. No transliteration engine."""
import json
from pathlib import Path

LAB=Path(__file__).resolve().parents[1]
OUT=LAB/'translations/npc-names-editorial-20261030-r1.json'
if OUT.exists():
    raise FileExistsError('Preserve the frozen editorial version')
known=json.loads((LAB/'translations/npc-names-known-20261030-r1.json').read_text(encoding='utf-8'))
if any(len(v)!=1 for v in known.values()):
    raise ValueError('Resolve ambiguous canonical spellings first')
pairs={k:v[0] for k,v in known.items()}
additions={}
for line in (LAB/'translations/npc-names-editorial-additions-20261030-r1.txt').read_text(encoding='utf-8').splitlines():
    if not line: continue
    en,he=line.split('\t')
    if en in additions: raise ValueError('Duplicate editorial name: '+en)
    additions[en]=he
# Basil is a person's name here; the ingredient Basil is בזיליקום in item tables.
assert set(pairs)&set(additions)=={'Basil'}
pairs.update(additions)
tables={}
seen=set()
for line in (LAB/'memory/english-source.jsonl').open(encoding='utf-8'):
    r=json.loads(line)
    if Path(r['file']).name not in {'namelist.dat','trname.dat'} or not r['requires_translation']:continue
    if r['source'] not in pairs:raise ValueError('Missing editorial name: '+r['source'])
    seen.add(r['source'])
    tables.setdefault(r['file'],[]).append(dict(index=r['line_index'],source=r['source'],he=pairs[r['source']]))
assert set(pairs)==seen, 'Unused/missing name entries require review'
OUT.write_text(json.dumps(dict(status='assistant editorial transliteration and established glossary reconciliation',
    note='Basil the NPC is בזיל, distinct from the ingredient. Taunie/Urbain match the opening. Generic source labels are translated; all original row IDs retained.',
    tables=tables),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print({file:len(rows) for file,rows in tables.items()})
