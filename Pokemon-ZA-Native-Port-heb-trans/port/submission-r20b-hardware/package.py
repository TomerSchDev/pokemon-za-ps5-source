"""Create a versioned r20b candidate/result bundle and verify its NAS copy."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, zipfile
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"evidence/submission-r20b"
H=ROOT/"evidence/submission-r20b-hardware"
ART=ROOT/"artifacts/randomizer-r20b-batch"
EXPECTED="9ee7737bb542eae1b804e644733898dce8808a9b85da3c4929c7031f83268852"

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda:f.read(1<<20),b""):h.update(data)
    return h.hexdigest()
def write(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def main():
    assert sha(ART/"PPSA91762/eboot.bin")==EXPECTED
    audit=json.loads((E/"preservation-audit.json").read_text())
    assert audit["same_dynamic_imports"] and audit["dynamic_import_count"]==325
    now=datetime.now(timezone.utc)
    hardware=json.loads((H/"final-result.json").read_text()) if (H/"final-result.json").exists() else None
    startup=hardware["startup_profile"] if hardware else "each"
    assert startup in ("each","batch2","batch4","batch8")
    out=ROOT/"deliverables"/("ZA-Randomizer-r20b-"+now.strftime("%Y%m%d-%H%M%SZ"))
    out.mkdir(parents=True,exist_ok=False)
    verification=dict(at=now.isoformat(),build="randomizer-r20b-batch",title="PPSA91762",
        eboot_sha256=EXPECTED,host_tests_passed=True,full_ps5_link_passed=True,
        preservation_audit_passed=True,hardware_result=hardware,
        installed=hardware.get("installed",False) if hardware else False,
        hardware_tested=hardware.get("hardware_tested",False) if hardware else False,
        fps_gain_proven=hardware.get("fps_gain_proven",False) if hardware else False,
        packaged_startup_profile=startup,
        note="r20b builds and host tests do not demonstrate GPU correctness or 60FPS.")
    write(out/"Verification.json",verification)
    text=f"""Pokémon Legends: Z-A Randomizer — r20b
גרסת ניסוי להשוואת איחוד הגשות ל־GPU באותה ריצה.
ברירת המחדל בחבילה זו היא {startup}. מצב each שומר הגשה נפרדת.
אפשר לבדוק קבוצות של 2, 4 או 8; batch4 נבחר אחרי ההשוואה בסצנה אחת.
החלפה חיה מתבצעת רק אחרי מסירת פריים וניקוז מסונכרן של עבודת ה־GPU.
הבדיקה מחזירה אישור לפרופיל שהוחל בפועל, ואינה מחליפה פרופיל בזמן מדידה.
בדיקות הקוד במחשב, הקישור ושימור רכיבי המשחק עברו.
מצב ההתקנה והמדידות בקונסולה מפורט ב־Verification.json. אין הבטחה ל־60 FPS.
Update.zip מכיל את eboot.bin והגדרת {startup} לאפליקציה PPSA91762 הקיימת.
Source.zip מכיל את שינויי הקוד, בדיקות וכלי מדידה, עם מקורות העדכונים הקודמים.
לבנייה נדרשים קוד הבסיס והתלויות המקומיים; החבילה אינה כוללת ROMFS,
שמירות, נתוני DLC, מפתחות או חבילות SDK.
אין שינוי בהתקדמות, בסיד או בלוגיקת הרנדומייזר.
"""
    if hardware is None:
        text+="בעת אריזת חבילה זו r20b טרם הותקנה או נמדדה; המשחק עדיין פתוח בקונסולה.\n"
    else:
        text+="תוצאות המדידה בקובץ Hardware-results-HE.txt וב־Verification.json.\n"
    (out/"STATUS-HE.txt").write_text(text,encoding="utf-8-sig")
    shutil.copy2(ROOT/"port/submission-r20b/README.md",out/"Developer-readme.md")
    if hardware:
        with (out/"Developer-readme.md").open("a",encoding="utf-8") as f:
            f.write("\nRelease result: the original build/candidate default above was each. This timestamped hardware-result bundle explicitly overrides its Update.zip startup setting to "+startup+". See Hardware-results-HE.txt and Verification.json for the one-scene scope.\n")
    shutil.copy2(ROOT/"reports/מקור הקוד ושיפורי ביצועים.txt",out/"Source-and-performance-research-HE.txt")
    shutil.copy2(ROOT/"reports/מקור הקוד ושיפורי ביצועים.md",out/"Source-and-performance-research-HE.md")
    shutil.copy2(ROOT/"reports/מודי 60FPS והתאמה לפורט.txt",out/"60FPS-mods-research-HE.txt")
    notes=ROOT/"research_notes/מקור הקוד ושיפורי ביצועים"
    shutil.copy2(notes/"gamebanana-comparison.json",out/"Exact-mod-comparison.json")
    shutil.copy2(notes/"facts.json",out/"Research-facts.json")
    ev=out/"evidence";ev.mkdir()
    for name in ("preservation-audit.json","preparation.json","registration.json","runtime-r20b.patch","tests.log","client-tests.log","eboot.sha256.txt","ready.json"):
        shutil.copy2(E/name,ev/name)
    if hardware is not None:
        shutil.copy2(H/"Hardware-results-HE.txt",out/"Hardware-results-HE.txt")
        for path in H.rglob("*"):
            if path.is_file() and (path.suffix in (".json",".csv",".png") or path.name.endswith("-filtered.log")):
                dest=ev/"hardware"/path.relative_to(H);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    previous=ROOT/"deliverables/ZA-Randomizer-r20-Batching-Candidate-20261028-190254Z/Source.zip"
    with zipfile.ZipFile(previous) as old,zipfile.ZipFile(out/"Source.zip","w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for info in old.infolist():z.writestr(info,old.read(info))
        for folder in (ROOT/"port/submission-r20b",ROOT/"port/submission-r20b-hardware"):
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix in (".h",".c",".inc",".py",".sh",".md",".txt"):
                    z.write(path,path.relative_to(ROOT).as_posix())
        z.write(E/"runtime-r20b.patch","evidence/submission-r20b/runtime-r20b.patch")
    with zipfile.ZipFile(out/"Update.zip","w",zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        z.write(ART/"PPSA91762/eboot.bin","PPSA91762/eboot.bin")
        z.writestr("PPSA91762/submission-options.txt",startup+"\n")
        z.write(out/"STATUS-HE.txt","STATUS-HE.txt")
        z.write(out/"Verification.json","Verification.json")
        with zipfile.ZipFile(out/"Source.zip") as s:
            for name in s.namelist():
                if name.startswith("LICENSES/"):z.writestr(name,s.read(name))
    for name in ("Source.zip","Update.zip"):
        with zipfile.ZipFile(out/name) as z:assert z.testzip() is None
    files={p.relative_to(out).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.rglob("*") if p.is_file()}
    write(out/"SHA256.json",files)
    nas=Path("//TheOnePiece/Software/PS5-13.60/Pokemon-ZA-Native-Port")/out.name
    result=dict(at=now.isoformat(),local=str(out),nas=str(nas),nas_verified=False)
    try:
        nas.mkdir(parents=True,exist_ok=False)
        for path in out.rglob("*"):
            if not path.is_file():continue
            target=nas/path.relative_to(out);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target);assert sha(path)==sha(target)
        result["nas_verified"]=True
    except Exception as ex:result["nas_error"]=str(ex)
    write(ROOT/"port/submission-r20b-hardware"/("delivery-"+now.strftime("%Y%m%d-%H%M%SZ")+".json"),result)
    print(json.dumps(result,ensure_ascii=True),flush=True)
if __name__=="__main__":main()

