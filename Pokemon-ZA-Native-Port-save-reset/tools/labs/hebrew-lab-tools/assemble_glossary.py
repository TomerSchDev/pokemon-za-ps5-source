"""Coordinator-owned draft assembly; never creates or assumes human approval."""
import csv
import json
from pathlib import Path
import re
import shutil
import unicodedata
from collections import Counter
from glossary_manager import read_glossary,write_glossary,category_collisions,glossary_digest

LAB=Path(__file__).resolve().parents[1]
FIELDS=('english','hebrew','category','note')
ALLOWED={'Z-A','HP','PP','TM','Mega','Alpha'}

def main():
    inventory=[json.loads(x) for x in (LAB/'terminology/inventory.jsonl').read_text(encoding='utf-8').splitlines() if x]
    seed=read_glossary(LAB/'terminology/seed.tsv')
    locked={r['english']:r for r in seed}
    shared=read_glossary(LAB/'terminology/shared-terms.tsv')
    shared_by_en={r['english']:r for r in shared if r['category']=='core'}
    shared_by_key={(r['english'],r['category']):r for r in shared}
    candidates={}
    layers=[('curated','curated.tsv'),('reviewed_missing','reviewed-missing.tsv'),
            ('moves_reviewed_extra','moves-reviewed-extra.tsv'),('items_reviewed','items-reviewed.tsv'),
            ('ui_forms_reviewed','ui-forms-reviewed.tsv'),('species_reviewed','species-reviewed.tsv'),
            ('species_reviewed_extra','species-reviewed-extra.tsv'),
            ('proper_fallback','proper-nouns-auto.tsv')]
    ranking={name:index for index,(name,_) in enumerate(layers)}
    ranking['local_marian']=100
    for name,filename in layers:
        path=LAB/'terminology/proposals'/filename
        if not path.exists():continue
        for row in read_glossary(path):
            key=(row['english'],row['category']);candidates.setdefault(key,[]).append((name,row))
    for line in (LAB/'terminology/proposals/local-marian.jsonl').read_text(encoding='utf-8').splitlines():
        row=json.loads(line);candidates.setdefault((row['english'],row['category']),[]).append(('local_marian',row))
    rows=[];audit=[];origins=Counter();missing=[]
    for rec in inventory:
        en,cat=rec['english'],rec['category'];key=(en,cat);options=candidates.get(key,[])
        if en in locked:
            chosen=dict(locked[en]);origin='locked_seed';chosen['category']=cat
        elif key in shared_by_key:
            chosen=dict(shared_by_key[key]);origin='shared_decision'
        elif en in shared_by_en:
            chosen=dict(shared_by_en[en]);origin='shared_decision';chosen['category']=cat
        else:
            ranked=sorted(options,key=lambda x:ranking[x[0]])
            if ranked:origin,chosen=ranked[0];chosen={k:str(chosen.get(k,'')) for k in FIELDS}
            else:origin='missing';chosen=dict(english=en,hebrew='',category=cat,note='טרם הוצע תרגום')
        heb=chosen['hebrew']
        # Remove only Hebrew combining marks, never base letters or punctuation.
        without_marks=''.join(c for c in heb if not (0x591<=ord(c)<=0x5c7 and unicodedata.category(c).startswith('M')))
        if without_marks!=heb:chosen['note']+='; ניקוד הוסר לטובת הגופן';heb=without_marks
        latin=set(re.findall(r'[A-Za-z]+(?:-[A-Za-z]+)*',heb))
        bad_latin=latin-ALLOWED
        if origin=='local_marian' and (not heb or bad_latin or (not re.search('[א-ת]',heb) and not latin)):
            chosen['note']+='; ההצעה הגולמית נשמרה בתור הביקורת אך לא התקבלה כעברית'
            heb='';origin='machine_requires_manual_translation'
        chosen['hebrew']=heb
        if origin!='locked_seed':chosen['note']='טיוטה; דרושה ביקורת ואישור; '+chosen['note']
        else:chosen['note']='מונח יסוד מחייב מהפרומפט; '+chosen['note']
        rows.append(chosen);origins[origin]+=1
        if not heb:missing.append(dict(english=en,category=cat,sources=rec['sources'],candidates=[dict(origin=n,**r) for n,r in options]))
        distinct={r['hebrew'] for _,r in options if r.get('hebrew')}
        if distinct-{heb}:
            audit.append(dict(english=en,category=cat,chosen=heb,origin=origin,
                alternatives=[dict(origin=n,hebrew=r.get('hebrew','')) for n,r in options if r.get('hebrew')!=heb],
                status='draft_precedence_not_human_approval'))
    keys={(r['english'],r['category']) for r in rows}
    for r in seed+shared:
        if (r['english'],r['category']) not in keys:
            is_locked=r['english'] in locked
            rows.append(dict(r,note=('מונח יסוד מחייב מהפרומפט; ' if is_locked else 'טיוטת מונח משותף; ')+r['note']))
            origins['locked_seed' if is_locked else 'shared_decision']+=1
    glossary=LAB/'glossary.tsv'
    approval=LAB/'glossary-approval.json'
    if approval.exists() and json.loads(approval.read_text(encoding='utf-8')).get('approved'):
        raise ValueError('Do not rebuild an approved master from drafts; merge reviewed proposals into a new version')
    if glossary.exists():
        previous=LAB/'terminology/versions'/('glossary-'+glossary_digest(glossary)[:12]+'.tsv')
        previous.parent.mkdir(parents=True,exist_ok=True)
        if not previous.exists():shutil.copyfile(glossary,previous)
        assert glossary_digest(previous)==glossary_digest(glossary)
    write_glossary(glossary,rows)
    report=dict(status='draft_not_approved',terms=len(rows),inventory_terms=len(inventory),
        filled=sum(bool(r['hebrew']) for r in rows),untranslated=len(missing),by_category=dict(Counter(r['category'] for r in rows)),
        origins=dict(origins),alternative_proposals=len(audit),cross_category_collisions=len(category_collisions(rows)),
        glossary_sha256=glossary_digest(glossary),approval_required_before_translation=True)
    for name,value in [('reports/glossary-build.json',report),('terminology/review/missing.json',missing),
                       ('terminology/review/alternative-proposals.json',audit),
                       ('terminology/review/cross-category.json',category_collisions(rows))]:
        p=LAB/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
