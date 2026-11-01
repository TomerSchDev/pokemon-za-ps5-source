"""Publish reviewed PC evidence and a source-only fix package; no game data or saves."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,zipfile


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    tools=Path(__file__).resolve().parent;lab=tools.parents[2];work=lab/'pc-fifty-20261031-r1'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=work/('icon-evidence-'+stamp);out.mkdir()
    report=json.loads((work/'icon-identity-repair-r2.json').read_text())
    report.update(full_species_qa_passed=0,full_species_qa_total=50,
                  normal_icon_file_identity_review=dict(reviewed=100,method='Decoded effective icons viewed in a labelled sheet',result='Species identities match labels'),
                  runtime_icon_verified=['Yamper party slot','Yamper active HP portrait'],
                  toast_icon_runtime_verified=True,console_deployed=False,
                  existing_wrong_icons=4,missing_registry_icons_added=2,
                  previous_count_correction='The earlier 36 count included 32 valid Violet icons with different artwork; their originals are retained in r2.',
                  supersedes='icon-evidence-20261031T133424Z',
                  native_battle_control='Goodra Breaking Swipe caused visible enemy HP loss, with and without cohort mods (r15/r17)',
                  yamper_attack_status='Failed to execute; received damage, correct HUD and toast icon verified in r16',
                  further_diagnostics=dict(native_control_in_prepared_save='Passed, r21',low_level_5='No attack confirmed, r20',
                    transition_loop_override='No attack confirmed, r22',native_model_override='Inconclusive: donor body not clearly rendered, r23'),
                  diagnostic_overlays_disabled=True)
    (out/'status.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    shutil.copyfile(work/'icon-review-r2/cohort-icon-identity.png',out/'cohort-icon-identity.png')
    shutil.copyfile(lab/'hebrew-lab/runs/pc-fifty-yamper-icons-r13/build/frames/frame_02110.png',out/'yamper-PC-correct-icon.png')
    shutil.copyfile(lab/'hebrew-lab/runs/pc-fifty-yamper-toast-r16/build/frames/frame_03200.png',out/'yamper-PC-correct-toast.png')
    shutil.copyfile(work/'all-imports-icon-audit-r1.json',out/'all-imports-icon-audit.json')
    with zipfile.ZipFile(out/'icon-mapping-source-fix.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('sword_icon_identity.py','import_source_icons.py','repair_pc_fifty_icons.py','review_pc_fifty_icons.py','audit_sword_icon_imports.py'):
            archive.write(tools/name,'tools/'+name)
        archive.writestr('README-HE.txt',
            'תיקון מיפוי אייקונים — בדיקת מחשב בלבד\n'
            'האייקונים מ-Sword נבחרים לפי מספר המשאב בקטלוג המקור, ולא לפי מספר הפוקימון.\n'
            'במדגם נמצאו ארבעה אייקונים שגויים ושתי הפניות חסרות. אייקונים תקינים מ-Violet נשמרים.\n'
            'התיקון של Yamper אומת ליד מד החיים ובחלונית ההודעות. מצב בדיקות הקרב וההתפתחות המלאות: 0/50.\n'
            'קובצי המקור מיועדים לתיקיית tools הקיימת בפרויקט species-lab/import-all-20261030.\n'
            'מהשורש Pokemon-ZA-Native-Port: zw species-all repair_pc_fifty_icons, ואחריו zw species-all review_pc_fifty_icons.\n'
            'נדרשים קובצי המקור הפרטיים שכבר קיימים ב-NAS; הם אינם כלולים בארכיון.\n'
            'לבדיקה: הרצת PC נפרדת עם שמירה מועתקת ותיקיית המודים; השוואת האייקון למודל ולחלונית ההודעות.\n'
            'לשחזור במחשב: השבתת התיקייה 00-icon-identity-r2 באמצעות קידומת _. קובצי הבסיס אינם משתנים.\n'
            'התיקון לא הותקן ולא נבדק בקונסולה.\n')
    nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\PC-QA-50-20261031-r1')/out.name
    nas.mkdir(parents=True,exist_ok=False)
    copied=[]
    for file in sorted(out.iterdir()):
        target=nas/file.name;shutil.copyfile(file,target);assert sha(file)==sha(target)
        copied.append(dict(file=file.name,sha256=sha(file),bytes=file.stat().st_size))
    receipt=dict(nas=str(nas),local=str(out),sha256_verified=True,files=copied)
    (out/'nas-copy.json').write_text(json.dumps(receipt,indent=1),encoding='utf-8')
    shutil.copyfile(out/'nas-copy.json',nas/'nas-copy.json');assert sha(out/'nas-copy.json')==sha(nas/'nas-copy.json')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
