"""Retain the installed Hebrew-trial overlay; add a second cheat page."""
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source=root.parent/'hebrew-lab/trial/build-r5/src/cheats-hebrew.cpp'
s=source.read_text(encoding='utf-8')
s=s.replace('#include "za_money.h"','#include "za_money.h"\n#include "za_items.h"\n#include <cctype>')
s=s.replace('constexpr int kRows=7;', 'std::atomic<unsigned> page{0},itemChoice{0},amountChoice{0};\nconstexpr unsigned itemAmounts[]={1,10,99,999};\nconstexpr int kRows=7;')
s=s.replace('za_money_lifecycle_reset(); moneyChoice=0;', 'za_items_reset(); page=0; itemChoice=0; amountChoice=0;\n    za_money_lifecycle_reset(); moneyChoice=0;')
needle='    if(b==SDL_GAMEPAD_BUTTON_DPAD_UP)row='
at=s.index(needle)
s=s[:at]+'''    if(b==SDL_GAMEPAD_BUTTON_LEFT_SHOULDER||b==SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER){page=1-page.load();row=0;return true;}
    if(page==1){
        if(b==SDL_GAMEPAD_BUTTON_DPAD_UP)row=(row.load()+kRows-1)%kRows;
        if(b==SDL_GAMEPAD_BUTTON_DPAD_DOWN)row=(row.load()+1)%kRows;
        if(row==0&&b==SDL_GAMEPAD_BUTTON_NORTH){itemChoice=(itemChoice.load()+10)%za_items_count();return true;}
        if(b==SDL_GAMEPAD_BUTTON_DPAD_LEFT||b==SDL_GAMEPAD_BUTTON_DPAD_RIGHT||b==SDL_GAMEPAD_BUTTON_SOUTH){
            int direction=b==SDL_GAMEPAD_BUTTON_DPAD_LEFT?-1:1;
            if(row==0)itemChoice=(itemChoice.load()+za_items_count()+direction)%za_items_count();
            if(row==1)amountChoice=(amountChoice.load()+4+direction)%4;
            if(row==2&&b==SDL_GAMEPAD_BUTTON_SOUTH){za_items_request(itemChoice.load(),itemAmounts[amountChoice.load()]);}
        }
        return true;
    }
'''+s[at:]
needle='    const char* s[]={"NORMAL"'
at=s.index(needle)
s=s[:at]+'''    if(page==1){
        const ZaItem* item=za_items_at(itemChoice.load());
        std::string name=item?item->name:"UNAVAILABLE";
        for(char& ch:name)ch=char(std::toupper(static_cast<unsigned char>(ch)));
        std::string label[]={"ITEM "+FpsReadout::u2s(itemChoice.load()+1)+"/"+FpsReadout::u2s(za_items_count())+"  "+name,
            "AMOUNT  "+FpsReadout::u2s(itemAmounts[amountChoice.load()])+"    CAP "+FpsReadout::u2s(item?item->cap:0),
            std::string("ADD ITEM - X  ")+za_items_status(),"ALPHA RATE  DISABLED","EXP MULTIPLIER  DISABLED","MEGA GAUGE  DISABLED","ENCOUNTER RATE  DISABLED"};
        for(int i=0;i<kRows;i++){int y=196+i*36;if(i==row)c.box(124,y,1032,32,0x24413e);c.text(144,y+5,label[i],3,i>=3?0x91a5bb:i==row?0x54e3aa:0xedf5fc);}
        const char* reason=row==3?"ALPHA: SPAWN READER AND CAUGHT FLAG NOT PROVEN":row==4?"EXP: THE GAME FORMULA HAS NOT BEEN VERIFIED":row==5?"MEGA: NO VERIFIED LIVE GAUGE HOOK":row==6?"ENCOUNTERS: NO VERIFIED SPAWN RATE HOOK":"ADD: CLOSE THIS MENU AND OPEN SATCHEL TO APPLY";
        c.text(136,462,reason,2,0xffce80);
        c.text(136,486,"OPEN SATCHEL ONCE TO ENABLE - SAVE IN GAME AFTER ADDING",2,0x91a5bb);
        c.text(136,510,"LEFT / RIGHT ITEM OR AMOUNT - TRIANGLE JUMPS 10 ITEMS",2,0x91a5bb);
        c.text(136,534,"ONE REQUEST AT A TIME - ITEM LIMITS FOLLOW THE GAME",2,0x91a5bb);
        c.text(136,562,"PAGE 2/2 - L1 / R1 PAGE - CIRCLE CLOSE",2,0xedf5fc);
        c.text(136,586,"R28 ITEMS - SESSION REQUESTS ARE NEVER REPLAYED",2,0x91a5bb);
        return;
    }
'''+s[at:]
s=s.replace('D-PAD SELECT / CHANGE   CIRCLE CLOSE   L3+R3 TOGGLE','PAGE 1/2 - L1 / R1 PAGE - D-PAD SELECT - CIRCLE CLOSE')
dest=Path(__file__).with_name('src');dest.mkdir(exist_ok=True)
(dest/'cheats-r28.cpp').write_text(s,encoding='utf-8',newline='\n')
for name in ['hebrew_trial.h','hebrew_install.h','hebrew_io.h','hebrew_install_files.inc']:
    (dest/name).write_bytes((source.parent/name).read_bytes())
print(dest/'cheats-r28.cpp')
