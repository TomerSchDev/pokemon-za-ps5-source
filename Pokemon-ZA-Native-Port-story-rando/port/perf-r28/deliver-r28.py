"""Assemble verified offline binaries, user instructions and authored sources.
Copies final deliverables to NAS with content verification; no console transport.
"""
from pathlib import Path
import hashlib,json,shutil,zipfile,datetime
root=Path(__file__).resolve().parents[2]
own=root/'port/cheats-r28';perf=root/'port/perf-r28'
build=Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\r28-play-20261030\r28')
out=root/'artifacts/randomizer-r28-play'
assert not out.exists(),'Final destination must be new'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def copy(src,rel):
 target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target);assert sha(src)==sha(target);return target
for n in ['registration.json','imports.json','linked-calls.json','archive.json','image-preservation.json']:
 assert (build/'evidence'/n).is_file(),n
p=json.loads((own/'evidence/pc-proof.json').read_text());assert all(p[n] for n in ['items_verified','save_verified','reload_verified','cap_verified'])
copy(build/'eboot.bin','PPSA91762/eboot.bin')
fallback=root.parent/'hebrew-lab/trial/build-r5/eboot.bin'
assert sha(fallback)=='cd1eb5f6044ab99d56161c6009d6d0972df475d269c0522dee650fab31d4f618'
copy(fallback,'rollback/r27b-hebrew-trial/eboot.bin')
for folder in [build/'evidence',own/'evidence']:
 for source in folder.iterdir():
  if source.is_file() and source.suffix in ['.json','.txt','.log']:copy(source,'evidence/'+source.name)
copy(perf/'test-results/menu-test.log','evidence/menu-test.log')
for run,name in [('pc-batch-02','added-items'),('pc-reload-cap-01','reloaded-items')]:
 copy(own/f'work/{run}/build/frames/frame_01100.png',f'evidence/{name}.png')
eboot=sha(out/'PPSA91762/eboot.bin')
info=dict(revision='randomizer-r28-play',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 title_id='PPSA91762',game_version='2.0.2 + Mega Dimension',eboot_sha256=eboot,
 original_r27b_sha256='c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153',
 latest_hebrew_trial_baseline_sha256=sha(fallback),items=dict(enabled=True,count=199,consumables=39,tms=160,amounts=[1,10,99,999],tm_cap=1),
 alpha=p['alpha'],console_access_performed=False,console_tested=False,real_saves_written=False,
 overlay_tests='ASan + UBSan: pages, all 199 labels, item/amount API bindings, pending, disabled rows, retained FPS and Hebrew',
 installation='eboot replacement only, by console operator after closing game and fresh backup',
 ps5_archive=json.loads((build/'evidence/archive.json').read_text()),pc_source_hashes=p['source_hashes'])
(out/'BUILD-INFO.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
readme=f'''# r28-play — ITEMS עבור Pokémon Legends: Z-A

ל־PPSA91762 בלבד, גרסת משחק 2.0.2 עם Mega Dimension. הבנייה מוכנה לבדיקה ידנית ב־PS5; לא ניגשנו לקונסולה ולא התקנו אותה.

## מה נוסף

- עמוד שני בתפריט L3+R3. מעבר עמוד עם L1 / R1.
- ITEMS: ‏39 פריטים ו־160 TMs שנבדקו מול PKHeX וטבלת המשחק החיה. כמויות 1 / 10 / 99 / 999, עם תקרת המשחק. TMs מוגבלים לעותק אחד.
- שורות ALPHA RATE, EXP, MEGA GAUGE ו־ENCOUNTER RATE מוצגות כמושבתות עם הסבר. לא הוכח חיבור ל־spawn עבור ALPHA ולא בוצעה בדיקת לכידה של Alpha; לכן אין שינוי בהסתברויות.
- נשמרו SHINY, CAPTURE, MONEY, FPS COUNTER, FPS TRIAL, RESET וכפתור HEBREW TRIAL עם טעינה מחדש.

## שימוש

1. טען שמירה ופתח את Satchel פעם אחת.
2. פתח L3+R3 ועבור לעמוד 2 עם R1.
3. בשורת ITEM בחר עם שמאלה/ימינה; משולש מדלג עשרה פריטים. בשורת AMOUNT בחר כמות.
4. עבור ל־ADD ITEM ולחץ X פעם אחת. סגור את חלונית הצ'יטים ופתח את תפריט המשחק / Satchel. אם התיק כבר פתוח, צא ופתח אותו מחדש כדי לרענן את התצוגה.
5. READY = מוכן, QUEUED = ממתין, ADDED = נוסף, ITEM / POCKET FULL = הפריט כבר בתקרה או שהמשחק לא הוסיף אותו. אין צורך ללחוץ שוב בזמן QUEUED.
6. שמור במשחק כדי לשמר את התוספת. טעינה/הפעלה מחדש מבטלת בקשה ממתינה; היא אינה מנגנת מחדש תוספות.

"פריטים נתמכים" פירושו פריטים ש־Z-A יודע לאחסן ולהציג, ללא קשר לחוקיות משפטית. Max Elixir, PP Max, Ability Capsule ו־Ability Patch אינם ברשימת הפריטים הנתמכים של PKHeX ל־Z-A ולכן הושמטו. מזהים ממשחקים אחרים בעלי שם זהה הושמטו גם הם. אין key items, אבני Mega או פריטי עלילה ברשימה.

## מה הוכח במחשב

המשחק האמיתי רץ עם קלט מתוסרט, data root ותיקיית שמירה נפרדים. כל 199 הפריטים נוספו באמצעות מסלול המשחק, נשמרו ונקראו ב־PKHeX. בטעינה מחדש נבדקו הכמויות והתקרות. כסף, כמויות פריטים אחרים ו־checksums של הקבוצה נבדקו. בדיקת קטלוג מרוכזת משתמשת בבקר אבחון במחשב בלבד, שמזין בקשות נפרדות לאותו API ולאותו מסלול הוספה; הבקר אינו חלק מבניית PS5. ראיות ומגבלות מדויקות ב־evidence/pc-proof.json.

## התקנה ידנית — רק כשהמשחק סגור

1. שמור במשחק, סגור אותו וודא שאין תהליך של PPSA91762 פעיל. צור גיבוי חדש של השמירה הנוכחית ושל eboot.bin הנוכחי; שמור את הגיבויים במחשב.
2. היעד הוא `/data/homebrew/PPSA91762/eboot.bin`. ודא שמדובר ב־91762. אל תשתמש בקובץ עבור PPSA91761.
3. קרא את eboot.bin הקיים בחזרה והשווה SHA-256 לגיבוי. הבסיס האחרון שאומת בשיחה כולל עברית: `cd1eb5f6044ab99d56161c6009d6d0972df475d269c0522dee650fab31d4f618`. אם הקובץ שונה, בדוק איזו גרסה מותקנת לפני ההחלפה.
4. העלה **רק** את `PPSA91762/eboot.bin` מהחבילה בשם זמני, למשל `eboot.bin.r28-new`. קרא אותו בחזרה וחשב SHA-256. חייב להתאים לערך שלהלן. אל תחליף שמירה, INI, active.json, תיקיית ריצה או נכסי עברית.
5. שנה את שם הקובץ הנוכחי לשם גיבוי חדש וייחודי; שנה את שם הקובץ הזמני ל־eboot.bin. קרא שוב את eboot.bin והשווה לאותו SHA-256. אל תפעיל אם הקריאה החוזרת אינה תואמת.
6. הפעל Continue ובצע את TEST-HE.md. זו בדיקת PS5 הראשונה של r28; בדיקות המחשב אינן בדיקת חומרה.

SHA-256 של r28 eboot.bin:
`{eboot}`

## חזרה לגרסה הקודמת

כשהמשחק סגור, החזר את הגיבוי העדכני שנוצר לפני r28 באותו תהליך העלאה זמנית / readback / rename / readback. החבילה כוללת גם `rollback/r27b-hebrew-trial/eboot.bin` מאומת, SHA-256 ‏`{sha(fallback)}`, לשימור כפתור העברית. חזרה ל־r27b המקורית ללא תוספת העברית משתמשת ב־SHA-256 ‏`c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153` מהחבילה הישנה. החזרת eboot אינה מסירה פריטים שכבר נשמרו; אין לשחזר שמירה ישנה אוטומטית.
'''
(out/'README-HE.md').write_text(readme,encoding='utf-8')
(out/'TEST-HE.md').write_text('''# בדיקת r28 על PS5

1. אחרי התקנה מאומתת, Continue לשמירה הנוכחית. ודא שהעברית וביצועי המשחק כרגיל.
2. L3+R3: בדוק שכל השורות בעמוד הראשון קיימות, כולל FPS TRIAL ו־HEBREW TRIAL. מעבר לעמוד השני עם R1 וחזרה עם L1.
3. פתח Satchel פעם אחת. בחר Rare Candy וכמות 1; לחץ X רק ב־ADD ITEM. סגור את החלונית ופתח שוב את תפריט המשחק והתיק. הכמות צריכה לעלות באחד. בדוק גם כמות 10.
4. בחר Full Restore וכמות 99; ודא שהוא בתא התרופות. בדוק Mint או ויטמין בתא הפריטים.
5. בחר TM שחסר: הוסף 999. צריך להתקבל עותק אחד בלבד. בקשה נוספת לאותו TM צריכה להראות ITEM / POCKET FULL.
6. שמור, סגור וטען מחדש. הכמויות חייבות להישאר ללא תוספת אוטומטית נוספת.
7. ALPHA RATE ושאר השורות המסומנות DISABLED לא אמורות לשנות דבר. אל תחפש שינוי ב־Alpha בגרסה זו.
8. אם יש תקלה: רשום את הפריט, הכמות, הודעת הסטטוס והפעולה האחרונה. צא לאחר שמירה לפי שיקולך והחזר את eboot המגובה כשהמשחק סגור.
''',encoding='utf-8')
sources=out/'r28-authored-sources.zip'
with zipfile.ZipFile(sources,'w',zipfile.ZIP_DEFLATED) as z:
 for folder in [own,perf]:
  for file in sorted(folder.rglob('*')):
   rel=file.relative_to(folder)
   if not file.is_file() or any(n in rel.parts for n in ['work','__pycache__','bin','obj','test-results','evidence']):continue
   if file.suffix in ['.py','.c','.cpp','.h','.inc','.sh','.json','.cs','.csproj','.md']:
    z.write(file,file.relative_to(root).as_posix())
manifest={f.relative_to(out).as_posix():sha(f) for f in sorted(out.rglob('*')) if f.is_file()}
(out/'SHA256SUMS.txt').write_text(''.join(f'{h}  {n}\n' for n,h in manifest.items()),encoding='utf-8')
archive=out.parent/'Randomizer-r28-play-20261030.zip'
assert not archive.exists()
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted(out.rglob('*')):
  if f.is_file():z.write(f,'randomizer-r28-play/'+f.relative_to(out).as_posix())
record=dict(local=str(archive),sha256=sha(archive),eboot_sha256=eboot,nas_completed=False)
nas=Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port\Randomizer-r28-play-20261030')
try:
 nas.mkdir(exist_ok=True,parents=True)
 for file in [archive,out/'README-HE.md',out/'BUILD-INFO.json',out/'SHA256SUMS.txt']:
  target=nas/file.name
  if target.exists() and sha(target)!=sha(file):target=nas/(file.stem+'-'+datetime.datetime.now().strftime('%H%M%S')+file.suffix)
  if not target.exists():shutil.copy2(file,target)
  assert sha(target)==sha(file),'NAS content mismatch'
 record.update(nas_completed=True,nas=str(nas))
except OSError as e:record['nas_error']=str(e)
(perf/'delivery.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record,ensure_ascii=False,indent=2))
