"""Native tables plus exactly the current console cohort; no unrelated registrations."""
from pathlib import Path
import copy,hashlib,json,sys
from build_smoliv_model import ROOT,Z,encode_checked
import nas_game_cache
from register_species import contents_schema,CONTENTS,key_catalog

def main():
 batch=int(sys.argv[1]);qa=ROOT/'qa/all-pokemon-20261030-r2';out=qa/'console-fifty-20261031-r1'
 scope=json.loads((out/('scope-b%02d.json'%batch)).read_text());keys=set(scope['model_keys'])
 models=[x for x in json.loads((out/'assets.json').read_text())['targets'] if x['key'] in keys]
 selected={(m['internal'],m['form']) for m in models};triples={(m['internal'],m['form'],m['gender']) for m in models}
 full=qa/'bundles/console-fifty-20261031-r1/mods/all-models/romfs';dest=out/('registration-b%02d'%batch)/'romfs';dest.mkdir(parents=True,exist_ok=True)
 nas_game_cache.install()
 def write(p,s,v):
  raw=encode_checked(s,v);target=dest/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 s=Z.personal_schema();base=s.decode(Z.read(Z.PERSONAL));allrows=s.decode((full/Z.PERSONAL).read_bytes())
 built={(r['Info']['SpeciesInternal'],r['Info'].get('Form',0)):r for r in allrows['Table']}
 native={(r['Info']['SpeciesInternal'],r['Info'].get('Form',0)) for r in base['Table'] if r.get('IsPresentInGame')}
 dex={n:365+i for i,n in enumerate(sorted({m['national'] for m in models}))}
 changed=0
 for i,r in enumerate(base['Table']):
  k=(r['Info']['SpeciesInternal'],r['Info'].get('Form',0))
  if k not in selected:continue
  assert k not in native
  n=copy.deepcopy(built[k]);n['Dex']={'Index':dex[n['Info']['SpeciesNational']],'Group':0}
  n['Evolutions']=[e for e in n.get('Evolutions',[]) if (e['SpeciesInternal'],e.get('Form',0)) in native|selected]
  base['Table'][i]=n;changed+=1
 write(Z.PERSONAL,s,base)
 s=Z.catalog_schema();base=s.decode(Z.read(Z.CATALOG));known={key_catalog(r) for r in base['table']}
 assert not triples&known
 base['table'] += [m['catalog'] for m in models];base['table'].sort(key=key_catalog);write(Z.CATALOG,s,base)
 for path,ds,fs in ((Z.MODEL_PARAM,'devId','formId'),(Z.MOVEMENT_PARAM,'devNo','formNo')):
  s=Z.bfbs_schema(path);base=s.decode(Z.read(path+'.bin'));rows=s.decode((full/(path+'.bin')).read_bytes())
  def key(r):return tuple(r['root'][0].get(k,0) for k in (ds,fs,'sex'))
  nativekeys={key(r) for r in base['values']}
  base['values'] += [r for r in rows['values'] if key(r) in triples-nativekeys]
  base['values'].sort(key=key);write(path+'.bin',s,base)
 for path in (Z.WILD_SINGLE_LIST,Z.CHARA_ANIME_LIST):
  s=Z.name_list_schema();base=s.decode(Z.read(path))
  base['names']=sorted(set(base['names'])|{f"{m['internal']:04d}_{m['form']:02d}_{m['gender']:02d}" for m in models})
  write(path,s,base)
 s=contents_schema();base=s.decode(Z.read(CONTENTS))
 for n in sorted(dex):
  m=next(x for x in models if x['national']==n)
  base['entries'].append({'id':max(r['id'] for r in base['entries'])+1,'devNo':m['internal']})
 write(CONTENTS,s,base)
 files=[{'path':p.relative_to(dest.parent).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(dest.rglob('*')) if p.is_file()]
 receipt={'batch':batch,'species':len(selected),'changed_personal_rows':changed,'native_rows_preserved':True,'files':files}
 (dest.parent/'registration-ready.json').write_text(json.dumps(receipt,indent=1));print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
