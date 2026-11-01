"""Reproducible random sample for real console motion/attack/level evolution QA."""
import collections,json,random,secrets
from pathlib import Path
from build_smoliv_model import ROOT,Z
from movesets import is_dummied

QA=ROOT/'qa/all-pokemon-20261030-r2'
OUT=QA/'console-fifty-20261031-r1'
LOCAL=Path(__file__).resolve().parents[3]/'console-qa-fifty-20261031-r1'
# Existing native damaging moves suitable for visible basic attack tests.
# The selected moves are also required to be present in the actual mod learnset.
DAMAGE={1,2,3,4,5,6,7,8,9,10,11,15,16,17,19,20,21,22,23,24,25,26,27,29,30,31,33,34,35,36,37,38,40,41,42,44,51,52,53,55,56,57,58,59,60,61,62,63,64,65,66,67,69,70,71,72,75,76,80,82,83,84,85,87,88,89,90,91,93,94,98,99,101,122,123,124,125,126,127,128,129,132,136,141,145,146,152,154,155,157,158,161,162,163,168,172,175,179,181,185,188,189,196,200,202,205,209,210,211,225,228,229,231,232,237,239,242,245,247,249,250,253,257,263,265,276,280,282,290,292,301,304,305,306,307,309,310,311,314,315,317,318,324,325,326,327,331,332,337,340,341,342,343,344,345,348,350,351,352,354,358,359,360,362,364,365,369,370,372,386,387,389,394,395,396,398,399,400,401,402,403,404,406,407,409,410,411,412,413,414,418,419,420,421,422,423,424,425,426,427,428,430,431,434,435,436,438,440,442,444,447,449,450,451,452,453,458,466,473,474,479,480,482,484,486,488,490,492,496,498,500,503,506,507,509,510,512,514,517,518,520,521,522,523,524,525,527,528,529,530,531,533,534,535,540,541,542,544,547,550,551,552,555,556,557,558,559,560,562,566,570,572,577,583,584,585,586,592,595,605,610,611,612,614,615,616,618,619,620,621,622,623,625,626,630,632,640,642,662,663,664,665,667,669,670,675,676,677,680,681,682,684,690,692,693,696,699,700,701,704,706,707,710,711,713,716,720,721,722,723,724,725,726,730,733,735,737,738,742,744,751,754,757,760,761,762,763,766,767,771,776,784}

def main():
 OUT.mkdir(exist_ok=True);LOCAL.mkdir(exist_ok=True)
 inventory=json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
 models={(x['internal'],x['form']):x for x in inventory if x['gender']==0}
 rows=Z.personal_schema().decode((ROOT/'build/all-species-r1/all-models/romfs'/Z.PERSONAL).read_bytes())['Table']
 personal={(x['Info']['SpeciesInternal'],x['Info'].get('Form',0)):x for x in rows}
 source_results=json.loads((LOCAL.parent/'pc-check-results/pc-model-checks-20261031T014526Z.json').read_text(encoding='utf-8'))
 visual={x['key']:x for x in source_results['targets']}
 names=json.loads((QA/'species-names.json').read_text(encoding='utf-8'))
 parent={k:k for k in personal}
 def find(k):
  if parent[k]!=k:parent[k]=find(parent[k])
  return parent[k]
 for k,r in personal.items():
  for e in r.get('Evolutions',[]):
   child=(e['SpeciesInternal'],e.get('Form',0))
   if child in parent:parent[find(child)]=find(k)
 def attacks(row,level):
  return [m for m in row.get('Learnset',[]) if 0<=m['Level']<=level and m['Move'] in DAMAGE and not is_dummied(m['Move'])]
 eligible=[];reasons=collections.Counter()
 for k,m in models.items():
  if not m['imported'] or m['form'] or m['gender']:continue
  r=personal[k];old=visual.get(m['key'],{})
  # A moving, unobstructed baseline body is required. Broad battle QA remains pending.
  delta=old.get('body_pixels_changed_gt10',0)
  if old.get('render_status') in ('empty_body','missing_capture') or delta<1000:
   reasons['idle_not_clear_enough']+=1;continue
  if m['national'] in (506,507,508,755,555,597):reasons['known_visual_issue']+=1;continue
  evos=[e for e in r.get('Evolutions',[]) if e['Method']==4 and not e.get('Argument') and not e.get('Form') and (e['SpeciesInternal'],0) in models and 2<=e['Level']<=60]
  if len(evos)!=1:reasons['not_one_plain_level_evolution']+=1;continue
  e=evos[0];child=models[(e['SpeciesInternal'],0)];child_row=personal[(e['SpeciesInternal'],0)]
  before=attacks(r,e['Level']-1)
  if len({x['Move'] for x in before})<2 or len({x['Level'] for x in before})<2:
   reasons['insufficient_distinct_damage_moves_before_evolution']+=1;continue
  first=before[0];latest=next(x for x in reversed(before) if x['Move']!=first['Move'])
  initial=[first,latest]
  after=[x for x in attacks(child_row,70) if x['Move'] not in {v['Move'] for v in initial}]
  if not after:reasons['no_different_attack_after_evolution']+=1;continue
  next_move=min(after,key=lambda x:(max(e['Level'],x['Level']),x['Level']))
  n=m['national'];cn=child['national']
  eligible.append({'key':m['key'],'national':n,'name':names[n],'internal':m['internal'],'family_root_internal':find(k)[0],
   'model':m,'source':m['source'],'evolution':{'national':cn,'name':names[cn],'internal':child['internal'],'level':e['Level'],'method':4,'model':child},
   'initial_level':e['Level']-1,'first_candy_target_level':e['Level'],'initial_attack_moves':initial,
   'post_evolution_attack':next_move,'post_evolution_test_level':max(e['Level'],next_move['Level']),
   'PC_idle_delta':delta,'console_status':'pending','attack_status':'pending','level_up_status':'pending','evolution_status':'pending'})
 grouped=collections.defaultdict(list)
 for row in eligible:grouped[row['family_root_internal']].append(row)
 # One initial member per family, preferring an earlier stage when both qualify.
 representatives=[min(group,key=lambda x:(personal[(x['internal'],0)].get('EvoStage',0),x['evolution']['level'],x['national'])) for group in grouped.values()]
 print(json.dumps({'eligible_species':len(eligible),'eligible_families':len(representatives),'exclusions':dict(reasons),'visual_sample_keys':list(source_results['targets'][0])}),flush=True)
 assert len(representatives)>=50,'Fewer than 50 eligible independent families; do not silently weaken criteria.'
 seed_file=OUT/'random-seed.json'
 if seed_file.exists():seed=json.loads(seed_file.read_text())['seed']
 else:seed=secrets.randbits(128);seed_file.write_text(json.dumps({'seed':seed,'method':'OS entropy, saved before selection'}))
 selected=random.Random(seed).sample(sorted(representatives,key=lambda x:x['key']),50)
 report={'selection_seed':seed,'sampling':'Uniform random sample of 50 eligible families, one representative per family.','eligible_families':len(representatives),'criteria':['Imported base form, not a native ZA species.','One plain level evolution (Method 4), target model registered.','At least two implemented damaging moves learned at different levels before evolution.','A different implemented attack available after evolution.','PC body has visible idle movement; excludes known malformed or stationary cases.'],'targets':selected,'completed_console_tests':0}
 for name,value in (('selection.json',report),('eligible.json',{'targets':eligible})):
  data=json.dumps(value,ensure_ascii=False,indent=1).encode('utf-8')
  for folder in (OUT,LOCAL):
   p=folder/name
   if p.exists():assert p.read_bytes()==data
   else:p.write_bytes(data)
 print(json.dumps({'selected':[x['name']+' -> '+x['evolution']['name'] for x in selected],'NAS':str(OUT),'local':str(LOCAL)},ensure_ascii=True),flush=True)

if __name__=='__main__':main()
