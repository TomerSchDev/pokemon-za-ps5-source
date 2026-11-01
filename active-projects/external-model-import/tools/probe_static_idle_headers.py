"""Read the actually requested clip headers for apparently static imported idle poses."""
from pathlib import Path
import json,re
from run_pc_gallery import ROOT,QA
from source_archives import FB

inventory={t['key']:t for t in json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))['targets']}
results=[]
for key,run in [('0555-01-0','pc-exact-form-early-001-r2'),('0597-00-0','pc-wide-import-006-r1-s02')]:
    folder=Path(inventory[key]['model_path']).parent.as_posix()
    log=(ROOT/'qa/runs'/run/'stderr.log').read_text(encoding='utf-8',errors='replace')
    files=list(dict.fromkeys(re.findall(r'\[fs\] read ik_pokemon/data/('+re.escape(folder)+r'/[^\r\n]+\.tranm)',log)))
    clips=[]
    for filename in files[-4:]:
        rel=Path('ik_pokemon/data')/filename
        candidate=QA/'rate-overlay/romfs'/rel
        if not candidate.exists():candidate=ROOT/'build/all-species-r1/all-models/romfs'/rel
        raw=candidate.read_bytes();fb=FB(raw);root=fb.table(fb.u32(0));info=fb.table(root[0]+fb.u32(root[0]))
        values=[fb.u32(info[i]) if i<len(info) and info[i] else 0 for i in range(3)]
        clips.append({'resource':rel.as_posix(),'loop_flag':values[0],'frame_count':values[1],'rate_in_read_only_source':values[2]})
    results.append({'key':key,'run':run,'last_requested_clips':clips,'limitation':'A clip header does not prove pose or material-curve playback. The PC observations remain authoritative.'})
(QA/'wide/static-idle-header-diagnostic-r1.json').write_text(json.dumps(results,indent=1),encoding='utf-8')
print(json.dumps(results),flush=True)
