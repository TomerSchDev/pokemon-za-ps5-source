"""Bind the 380 manually reviewed battle callouts to all 697 exact source rows."""
import hashlib,json,re
from pathlib import Path
from translation_memory import iter_tm
LAB=Path(__file__).resolve().parents[1]
OUT=LAB/'translations/rogue-battle-editorial-20261030-r1.json'
def main():
    if OUT.exists():raise FileExistsError('Preserve frozen revision')
    inventory_path=LAB/'coordination/rogue-battle-source-20261030.json'
    inventory=json.loads(inventory_path.read_text(encoding='utf-8'))
    reviewed_path=LAB/'translations/rogue-battle-reviewed-20261030-r1.txt'
    pairs=[line.split('|',1) for line in reviewed_path.read_text(encoding='utf-8').splitlines() if line]
    translated={int(i):he for i,he in pairs}
    if len(translated)!=len(pairs) or set(translated)!=set(range(len(inventory))):raise ValueError('Incomplete or duplicate editorial scope')
    records=[r for r in iter_tm(LAB/'memory/english-source.jsonl') if r['file'].endswith('/btl_bousou.dat') and r['requires_translation']]
    normal=lambda s:re.sub(r'\s+',' ',s).strip()
    current=list(dict.fromkeys(normal(r['source']) for r in records))
    if current!=inventory:raise ValueError('Source inventory changed; review required')
    by_source={s:translated[i] for i,s in enumerate(inventory)}
    rows=[dict(index=r['line_index'],source=r['source'],he=by_source[normal(r['source'])]) for r in records]
    OUT.write_text(json.dumps(dict(file=records[0]['file'],rows=rows,editorial_inventory_sha256=hashlib.sha256(inventory_path.read_bytes()).hexdigest(),visual_qa='Pending: battle callout timing, icon position, line wrapping and gender-neutral address.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),reviewed_templates=len(inventory))))
if __name__=='__main__':main()
