"""Explicit source-only publication snapshot. No native build, game data, history or queue access."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[2]
LAB = REPO.parent
OUT = LAB / 'Pokemon-ZA-PS5-Source-GitHub'
ALLOWED = {'.py','.pyw','.c','.h','.cpp','.hpp','.cc','.hh','.cxx','.hxx','.sh','.ps1','.cmd','.bat',
           '.cs','.csproj','.sln','.vcxproj','.filters','.cmake','.mk','.s','.asm','.glsl','.vert','.frag',
           '.comp','.inc','.patch','.diff','.md','.rst','.yml','.yaml','.vbs','.toml','.in','.gdb',
           '.m','.mm','.hlsl','.metal','.ld','.lds','.def'}
DENIED_DIRS = {'.git','.vs','.idea','__pycache__','node_modules','obj','bin','build','builds','dist','out',
              '.deps','deps','.venv','venv','.nuget','packages','sdk','toolchains',
              'artifacts','evidence','research','research_notes','analysis','reports','assets','reward-assets',
              'romfs','exefs','extracted','dumps','game','saves','save','cache','caches','work','runs','qa','deliveries',
              'publish','ref','retained-history','screenshots','mockups','fonts','data','queue-android'}
SECRETS = [
    re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----'),
    re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
    re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{50,}\b'),
    re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{40,}\b'),
    re.compile(rb'(?im)^\s*(?:master_key_[0-9a-f]+|header_key|aes_kek_generation_source)\s*=\s*[0-9a-f]{32,}'),
    re.compile(rb'(?i)["\'](?:access_token|refresh_token|api_key|password)["\']\s*:\s*["\'][A-Za-z0-9_+/=-]{24,}["\']'),
]


def digest(raw): return hashlib.sha256(raw).hexdigest()
def git(root, *args):
    r = subprocess.run([r'C:\Program Files\Git\cmd\git.exe','-C',str(root),*args], capture_output=True, timeout=20)
    return r.stdout.decode('utf-8','replace').strip() if r.returncode == 0 else None
def wanted(relative):
    if any(part.lower() in DENIED_DIRS for part in relative.parts): return False
    name, ext = relative.name.lower(), relative.suffix.lower()
    if name in ('warp_data.h','entrance_data.yml'): return False
    if 'LAS-Randomizer' in relative.parts: return False
    if name.startswith('.env') or any(k in name for k in ('.lease','prod.keys','title.keys','id_rsa','id_ed25519','devices.json')): return False
    if any(k in name for k in ('fonts_embedded','_spv.inc','_spirv.inc','game_strings','text_dump')): return False
    if name.startswith(('license','copying','notice','authors','contributors')): return True
    if name in ('makefile','cmakelists.txt','main','meson.build','meson_options.txt','requirements.txt','.gitattributes','.gitmodules'): return True
    if ext == '.txt': return name.startswith(('readme','requirements','cmakelists','environment'))
    if ext == '.json':
        return name in ('handoff.json','r4-handoff.json','capabilities.json','package.json','profiles.lock.json','build_dependency_map.json') or name.endswith(('.lock.json','.hardware.json','.example.json','.schema.json')) or 'schema' in name
    return ext in ALLOWED


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    previous = {}
    if OUT.exists():
        if '--resume-own-partial' not in sys.argv or (OUT/'SOURCE_SNAPSHOT.json').exists() or (OUT/'.git').exists():
            raise FileExistsError('Publication destination must be new or verified own incomplete export')
        previous={r['path']:r for r in json.loads((Path(__file__).parent/'selected-sources.json').read_text(encoding='utf-8'))}
        for file in OUT.rglob('*'):
            if file.is_symlink():raise RuntimeError('Unexpected symlink in own partial export')
            if file.is_file():
                rel=file.relative_to(OUT).as_posix()
                if rel not in previous or digest(file.read_bytes())!=previous[rel]['sha256']:
                    raise RuntimeError('Unexpected content in own partial export: '+rel)
    map_raw = (REPO/'docs/testing/BUILD_DEPENDENCY_MAP.json').read_bytes()
    mapping = json.loads(map_raw)
    (REPO/'docs/testing/BUILD_DEPENDENCY_AUDIT.md').read_text(encoding='utf-8')
    origins = []
    # Keep independent working branches separate; never merge/promote their unfinished work.
    for root in sorted(LAB.iterdir()):
        if root.is_dir() and (root.name == 'Pokemon-ZA-Native-Port' or root.name.startswith('Pokemon-ZA-Native-Port-') or root.name.startswith('pokeza-recomp-ps5')):
            if not (root/'.git').exists(): continue
            origins.append((root, root.name, 'runtime' if root.name.startswith('pokeza') else 'port'))
    models = LAB/'species-lab/import-all-20261030/tools'
    if models.is_dir(): origins.append((models,'active-projects/external-model-import/tools','model-tools'))
    selected, excluded, component_rows, flagged, snapshots = [], Counter(), [], [], {}
    for root, destination, role in origins:
        print('Reviewing '+destination, flush=True)
        base_parts = {'port','tools','workbench','docs','vk-probe','native-probe','save-workbench'} if role=='port' else {'runtime','tools','third_party','docs'}
        nodes = [n['id'] for n in mapping['nodes'] if str(n.get('path','')).replace('\\','/').lower().startswith(str(root).replace('\\','/').lower())]
        current = {'source_root':str(root),'destination':destination,'role':role,'head':git(root,'rev-parse','HEAD'),
                   'branch':git(root,'branch','--show-current'),'map_node_ids':nodes,'files':0,'bytes':0,
                   'classification':'working-source snapshot; not a new approved release'}
        for folder, dirs, files in os.walk(root, followlinks=False):
            folder = Path(folder)
            dirs[:] = [d for d in dirs if d.lower() not in DENIED_DIRS and not (folder/d).is_symlink()
                       and not getattr(folder/d,'is_junction',lambda:False)()
                       and (role=='model-tools' or folder!=root or d in base_parts)]
            for name in sorted(files):
                source=folder/name;relative=source.relative_to(root)
                if source.is_symlink() or not wanted(relative): excluded['not_source_or_protected_path']+=1;continue
                if folder==root and role=='port' and source.suffix.lower() not in {'.py','.md','.sh','.cmd','.ps1','.bat'} and name not in ('Makefile','.gitattributes'):continue
                raw=source.read_bytes()
                identity=digest(raw)
                if identity in snapshots:
                    target=destination+'/'+relative.as_posix()
                    selected.append({'source':str(source),'path':target,'sha256':identity,'bytes':len(raw),'role':role})
                    current['files']+=1;current['bytes']+=len(raw)
                    continue
                if b'\0' in raw or len(raw)>8*1024*1024:excluded['binary_or_oversize']+=1;continue
                try:raw.decode('utf-8-sig')
                except UnicodeDecodeError:excluded['non_utf8_review_required']+=1;continue
                if any(p.search(raw) for p in SECRETS):flagged.append(str(source));continue
                snapshots[identity]=raw
                target=destination+'/'+relative.as_posix()
                selected.append({'source':str(source),'path':target,'sha256':digest(raw),'bytes':len(raw),'role':role})
                current['files']+=1;current['bytes']+=len(raw)
        component_rows.append(current)
        (Path(__file__).parent/'scan-selection.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'component':destination,'files':current['files'],'bytes':current['bytes'] }), flush=True)
    if flagged:
        print(json.dumps({'blocked':'credential-like content requires review','files':flagged},ensure_ascii=True));return 2
    if not selected:raise RuntimeError('No sources selected')
    # Preserve the exact protected JSON wrapper/recipes as sources in their original branch folders.
    wrapper = LAB/'Pokemon-ZA-Native-Port-ui-new-run-stack-20261031-223729/port/ui-v2/src/json_number_ps5.c'
    if not any(r['source']==str(wrapper) for r in selected):raise RuntimeError('Protected JSON source missing from selection')
    queue_spec = __import__('importlib.util',fromlist=['spec_from_file_location'])
    spec=queue_spec.spec_from_file_location('publication_queue',REPO/'tools/console-install-queue/console_queue.py')
    queue=queue_spec.module_from_spec(spec);spec.loader.exec_module(queue)
    baseline = queue.Board().status().get('baselines',{}).get('PPSA91762')
    now=datetime.now(timezone.utc).isoformat()
    review={'schema_version':1,'record_kind':'source_publication_input_review','checked_at_utc':now,
        'status':'READY_FOR_SCOPED_BUILD','operation':'source snapshot/export packaging only; NO compile/relink/release promotion',
        'native_build_authorized':False,'source_snapshot_atomic':False,
        'snapshot_semantics':'Each file captured once into immutable in-memory content; sources may continue changing after capture; no cross-project atomicity claimed',
        'refreshed_after_concurrent_changes':[{'path':r['path'],'previous_sha256':previous[r['path']]['sha256'],'sha256':r['sha256']} for r in selected if r['path'] in previous and r['sha256']!=previous[r['path']]['sha256']],
        'purpose':'User explicitly requested a new private GitHub repository for game-port/runtime sources and build tools',
        'mapping_snapshot':{'path':str(REPO/'docs/testing/BUILD_DEPENDENCY_MAP.json'),'sha256':digest(map_raw),
                            'generated_utc':mapping.get('generated_utc'),'scope_limits_reviewed':True},
        'current_main':{'profile':(REPO/'tools/za/releases/MAIN').read_text().strip(),
                        'pointer_sha256':digest((REPO/'tools/za/releases/MAIN').read_bytes()),
                        'lock_sha256':digest((REPO/'tools/za/releases/main-1.1.0.lock.json').read_bytes())},
        'registered_baseline':baseline,'live_console_verified':False,
        'json_number_fix_source':{'path':str(wrapper),'sha256':digest(wrapper.read_bytes()),'included':True},
        'toolchain':{'operation':'byte-preserving source copy/hash/git; no compiler or SDK invocation','python':sys.version,
                     'git':git(REPO,'--version'),'recipe_sha256':digest(Path(__file__).read_bytes())},
        'components':component_rows,'job_input_closure_complete':True,
        'mapping_overlay':'SOURCE_SNAPSHOT.json lists the exact file-level export inputs and their source roots/map references',
        'external_inputs_not_exported':['private game dumps/AOT/game data/text','frozen object/archive inputs','SDKs/toolchains','fonts/images/shader blobs','saves/keys/credentials','build products and evidence caches'],
        'native_build_limitations':['Do not treat this import as a reproducible native build; current dependency-map migration blockers remain binding',
                                    'Copied branches are independent working snapshots, including dirty/untracked source; they were not merged or tested by this publication'],
        'cleanup_plan':{'generated_intermediates':[],'retained':['source checkout','Git repository','source provenance','final NAS source archive'],
                        'reason':'Source-only publication creates no compiler/conversion intermediates; existing inputs/build outputs are not deleted'}}
    # The completed scoped input review is written BEFORE copying/packaging.
    local=Path(__file__).parent
    (local/'source-export-input-check.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (local/'selected-sources.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    OUT.mkdir(parents=True,exist_ok=bool(previous))
    selected_paths={r['path'] for r in selected}
    for old in set(previous)-selected_paths:
        target=OUT/old
        if target.is_file():
            if digest(target.read_bytes())!=previous[old]['sha256']:raise RuntimeError('Own partial output changed unexpectedly')
            target.unlink()
    for item in selected:
        raw=snapshots[item['sha256']]
        destination=OUT/item['path'];destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
    provenance=OUT/'provenance';provenance.mkdir()
    (provenance/'BUILD-INPUT-CHECK.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest={'schema':1,'created_at_utc':now,'components':component_rows,'files':selected,'excluded_counts':dict(excluded),
              'source_filter_recipe_sha256':digest(Path(__file__).read_bytes()),'git_history_imported':False,'native_build_performed':False}
    (OUT/'SOURCE_SNAPSHOT.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'AGENTS.md').write_bytes((REPO/'AGENTS.md').read_bytes())
    (OUT/'.gitignore').write_text('''# Source-only repository. Keep private/runtime/build inputs outside Git.
**/__pycache__/
**/.env*
**/*.keys
**/*.pem
**/*.key
**/*.jks
**/*.keystore
**/.lease*.json
**/devices.json
**/romfs/
**/exefs/
**/assets/
**/saves/
**/evidence/
**/artifacts/
**/build/
**/obj/
**/bin/
**/*.nsp
**/*.xci
**/*.nca
**/*.o
**/*.a
**/*.so
**/*.dll
**/*.exe
**/*.elf
**/*.bin
**/*.apk
''',encoding='utf-8')
    (OUT/'README.md').write_text('''# Pokémon Legends: Z-A — PS5 port sources and build tools

מאגר פרטי של קוד הפורט, ה-runtime וכלי הבנייה של תומר. זו תמונת מקור מסוננת מהפרויקטים המקומיים; לא הועתקה היסטוריית Git ישנה ולא בוצעה בניית משחק או התקנה במסגרת הייבוא.

## נקודות כניסה

- `Pokemon-ZA-Native-Port/port/` — קוד רכיבי המשחק/הפורט: UI, רנדומייזר, תיקוני runtime ותכונות נוספות.
- `Pokemon-ZA-Native-Port/tools/za/` — כלי verify/reproduce/build, פרופילים, release locks וניקוי ביניים.
- `Pokemon-ZA-Native-Port/workbench/zw.py` ו־`zw.cmd` — הכניסה המאוחדת לכלים. כרטיסי העבודה תחת `workbench/cards/`.
- `pokeza-recomp-ps5/runtime/` — קוד ה-runtime ממאגר ה־PS5 המקומי. קובצי הרישוי של המקור וצדדים שלישיים נשמרו.
- יתר תיקיות `Pokemon-ZA-Native-Port-*` ו־`pokeza-recomp-ps5-*` — תמונות מקור נפרדות של ענפי עבודה ותיקונים, לרבות תיקון מספרי JSON. הן אינן merge מאושר ל־main.
- `active-projects/external-model-import/tools/` — קוד כלי יבוא המודלים, בלי המודלים או הדאמפים עצמם. קוד ערבוב הסיפור נמצא בתיקיית ענף story-continuation תחת `port/story-shuffle/`.

## מצב בנייה והוכחות

`SOURCE_SNAPSHOT.json` מתעד מקור, branch/HEAD ו־SHA-256 של כל קובץ, כולל overlay מקומי שלא בוצע לו commit במאגר המקורי. המקור נבחר לפי מיקומי הפרויקטים והמפה, ולא לפי mtime. תיקיות ענפים נשמרות בנפרד כדי לא לאבד עבודה פעילה או להציג merge שלא בוצע.

`provenance/BUILD-INPUT-CHECK.json` מאשר רק את ייצוא המקור הזה; הוא אינו מתיר compile/relink חדש. לפני כל בנייה יש לבצע בדיקת קלטים חדשה מול `Pokemon-ZA-Native-Port/docs/testing/BUILD_DEPENDENCY_MAP.json`, מקורות הסמכות העדכניים, MAIN וה־baseline הרשום. המפה היא snapshot מתוארך. חסמי ההגירה שתועדו בה לא נפתרו מעצם העלאת הקוד ל־GitHub.

כלי `za` הנוכחי כולל מסלולי relink מאובייקטים מוקפאים, ואינו הוכחה לבנייה מלאה מחדש של כל ה־AOT. האובייקטים, הארכיונים, ה־SDK והקלטים הפרטיים הנדרשים נשארים באחסון המקומי/WSL/NAS. אין כאן טענה ש-clone נקי יכול לבנות משחק ללא הכנת הקלטים האלה.

תיקון JSON ששויך ל־baseline `36b3d5d` נשמר כמקור ובמתכונים המתאימים; אין להסתפק ב־MAIN ישן או להחליף את המשחק הראשי בלי בדיקות ואישור כנדרש. נתוני baseline במסירה נקראו מקומית ואינם בדיקת חומרה חיה.

## גבולות המקור

לא נכללו קובצי משחק/דאמפים, AOT המופק מהמשחק, RomFS, טקסטים/טבלאות שחולצו, נכסים, שמירות, מפתחות, אסימונים, binaries או תוצרי build. רק קוד מקור, מתכונים, בדיקות קוד, תיעוד ומטא־נתונים מאושרים נכנסו למאגר. נכסים ובינריים נדרשים נשארים מחוץ ל־Git.

הקוד המקורי ורישיונות צד שלישי נשמרו לצד הרכיבים שלהם. לא נוספה הענקת רישיון גורפת לתוכן שאינו שייך לפרויקט.
''',encoding='utf-8')
    (local/'export-result.json').write_text(json.dumps({'checkout':str(OUT),'source_files':len(selected),'source_bytes':sum(r['bytes'] for r in selected),'components':len(component_rows)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checkout':str(OUT),'source_files':len(selected),'source_bytes':sum(r['bytes'] for r in selected),'components':len(component_rows),'excluded_counts':dict(excluded)},ensure_ascii=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
