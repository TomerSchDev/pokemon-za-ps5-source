"""Compose the already-reviewed Hebrew sample and a scoped r27b menu variant."""
import hashlib
import json
from pathlib import Path
import shutil

LAB=Path(__file__).resolve().parents[1]
PROJECT=LAB.parent/'Pokemon-ZA-Native-Port'
TRIAL=LAB/'trial'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    dest=TRIAL/'assets/mods/000-hebrew-trial'
    if dest.exists():raise FileExistsError('Keep prior trial assets')
    romfs=dest/'romfs';romfs.mkdir(parents=True)
    sources=[LAB/'build/pipeline-poc-20261029/mods/hebrew',LAB/'headers/build/headings-r5/mods/hebrew-headers']
    provenance=[]
    for source in sources:
        for p in (source/'romfs').rglob('*'):
            if not p.is_file():continue
            target=romfs/p.relative_to(source/'romfs')
            if target.exists():raise ValueError('Unexpected file overlap')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
            provenance.append(dict(path=target.relative_to(dest).as_posix(),bytes=p.stat().st_size,sha256=sha(p),source=str(p.relative_to(LAB))))
    shutil.copytree(sources[0]/'licenses',dest/'licenses')
    manifest=dict(magic='za-hebrew-trial-v1',version='20261029-r1',text_scope='60 exact existing PoC interface strings, no bulk glossary approval',
        header_scope='headings-r5: eight native archives',files=provenance,game='2.0.2 + Mega Dimension',title='PPSA91762')
    (dest/'trial-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert len(provenance)==17
    text=(PROJECT/'port/perf-r27/cheats-r27.cpp').read_text(encoding='utf-8')
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Unexpected r27b menu source: '+old[:80])
        text=text.replace(old,new)
    replace('#include "za_money.h"','#include "za_money.h"\n#include "hebrew_trial.h"')
    replace('constexpr int kRows=6;','constexpr int kRows=7;')
    replace('    za_money_lifecycle_reset(); moneyChoice=0; moneyRequestFailed=false;',
        '    za_money_lifecycle_reset(); moneyChoice=0; moneyRequestFailed=false;\n    (void)za_hebrew_trial_status(); // one-time disk probe; render uses cached state')
    replace('        if(r==5){shiny=0;capture=0;}',
        '        if(r==5){ // temporary localization; no cheat/settings/save write\n'
        '            if(b==SDL_GAMEPAD_BUTTON_SOUTH && za_hebrew_trial_request()>0)closeMenu();\n'
        '            return true;\n        }\n        if(r==6){shiny=0;capture=0;}')
    replace('    std::string labels[]={',
        '    int hebrewMode=za_hebrew_trial_status();\n'
        '    std::string hebrew=std::string("HEBREW TRIAL  ")+(hebrewMode==1?"ON - X SWITCH OFF":hebrewMode==0?"OFF - X SWITCH ON":"PACK NOT AVAILABLE");\n'
        '    std::string labels[]={')
    replace('trial,"RESET BOTH TO NORMAL"};','trial,hebrew,"RESET BOTH TO NORMAL"};')
    replace('int y=196+i*42;if(i==row)c.box(124,y,1032,38,','int y=196+i*36;if(i==row)c.box(124,y,1032,32,')
    replace('c.text(144,y+9,labels[i],3,','c.text(144,y+5,labels[i],3,')
    replace('    c.text(136,510,"MONEY  X QUEUES / SAVE IN GAME TO APPLY / NORMAL CANCELS",2,0x91a5bb);',
        '    if(row==5)c.text(136,510,"HEBREW: SAVE FIRST - RELOADS LAST SAVED PROGRESS",2,0xffce80);\n'
        '    else c.text(136,510,"MONEY  X QUEUES / SAVE IN GAME TO APPLY / NORMAL CANCELS",2,0x91a5bb);')
    src=TRIAL/'src';src.mkdir(parents=True,exist_ok=True)
    (src/'cheats-hebrew.cpp').write_text(text,encoding='utf-8')
    (TRIAL/'asset-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(files=len(provenance),bytes=sum(x['bytes'] for x in provenance),menu=str(src/'cheats-hebrew.cpp'))))

if __name__=='__main__':main()
