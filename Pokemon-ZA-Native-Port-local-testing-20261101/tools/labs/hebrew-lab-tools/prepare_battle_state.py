"""Freeze all battle-state labels and descriptions against inspected source."""
import hashlib,json,re
from pathlib import Path
from translation_memory import iter_tm
LAB=Path(__file__).resolve().parents[1]
OUT=LAB/'translations/battle-state-editorial-20261030-r1.json'
def main():
    if OUT.exists():raise FileExistsError('Preserve frozen revision')
    inventory_path=LAB/'coordination/battle-state-source-20261030.json'
    inventory=json.loads(inventory_path.read_text(encoding='utf-8'))
    pairs=[line.split('|',1) for line in (LAB/'translations/battle-state-reviewed-20261030-r1.txt').read_text(encoding='utf-8').splitlines() if line]
    translated={int(i):he for i,he in pairs}
    if len(translated)!=len(pairs):raise ValueError('Duplicate editorial ID')
    moves_data=json.loads((LAB/'translations/moves-battle-editorial-20261030-r1.json').read_text(encoding='utf-8'))
    moves={r['source']:r['he'] for r in moves_data['tables']['ik_message/dat/English/common/wazaname.dat']}
    reused={}
    for i,s in enumerate(inventory):
        if i not in translated and s in moves:translated[i]=moves[s];reused[s]=moves[s]
    if set(translated)!=set(range(len(inventory))):raise ValueError('Missing reviewed state: '+repr(set(range(len(inventory)))-set(translated)))
    records=[r for r in iter_tm(LAB/'memory/english-source.jsonl') if r['file'].endswith('/btl_state.dat') and r['requires_translation']]
    normal=lambda s:re.sub(r'\s+',' ',s).strip()
    if list(dict.fromkeys(normal(r['source']) for r in records))!=inventory:raise ValueError('Source inventory changed')
    by_source={s:translated[i] for i,s in enumerate(inventory)}
    rows=[dict(index=r['line_index'],source=r['source'],he=by_source[normal(r['source'])]) for r in records]
    OUT.write_text(json.dumps(dict(file=records[0]['file'],rows=rows,reused_reviewed_move_labels=reused,source_inventory_sha256=hashlib.sha256(inventory_path.read_bytes()).hexdigest(),visual_qa='Pending state-description panel and long-label checks.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),unique=len(inventory),reused_reviewed_titles=len(reused))))
if __name__=='__main__':main()
