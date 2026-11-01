"""Explicit message-window estimates for tables otherwise classified as menu labels.

These budgets are candidates for PC screen QA, not measured screen dimensions.
Short labels continue to use the normal one-line menu budget.
"""
def ui_layout_override(record):
    file=record['file'].rsplit('/',1)[-1]
    index=record['line_index']
    if file=='dressup.dat' and (index in {9,15,16,60,61,62,64,65,66,67,68,69,70,71,74,75} or 88<=index<=111):
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='appearance confirmation/shop dialogue estimate, based on source message semantics; PC screen QA pending')
    if file=='pokedex.dat' and 99<=index<=113:
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='habitat information panel estimate, not a menu label; PC screen QA pending')
    if file=='status.dat' and index in {76,114,115,116,117}:
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='summary confirmation/message panel estimate; PC screen QA pending')
    if file=='hud.dat' and index in {24,25}:
        return dict(width_em=32,max_lines=2,scroll=False,
            provenance='research reminder uses two source lines; HUD panel estimate, PC screen QA pending')
    if file=='mystery.dat' and 93<=index<=97:
        return dict(width_em=36,max_lines=1,scroll=False,
            provenance='full date/time/time-zone history row, with conservative five-digit variable reservations; PC screen QA pending')
    if file=='mystery.dat' and index in {1,2,4,8,9,10,11,12,13,14,15,16,17,18,19,24,25,32,33,37,38,39,40,41,43,45,47,49,51,53,55,57,59,82,83,84,85,86,87,88,89,109,110,111,112,113,114,116,119,120,121,122,123,124,125,126,318,319}:
        return dict(width_em=42,max_lines=12,scroll=False,
            provenance='gift modal/list estimate from source notices and up to six item rows; PC screen QA pending')
    if file=='hud_tips.dat':
        return dict(width_em=30,max_lines=3,scroll=False,
            provenance='controller tutorial panel has up to three explicit source lines; PC screen QA pending')
    if file=='tips.dat' and '_text_' in record['label']:
        return dict(width_em=32,max_lines=9,scroll=False,
            provenance='Tourist Tips body panel, not four-line item description: original body rows have up to nine explicit lines (type chart row120); 32em width estimate, PC screen QA pending')
    if file=='ryl.dat' and index in {23,24,25,26,27,28,29,32,33,34,35,42}:
        return dict(width_em=32,max_lines=3,scroll=False,
            provenance='Royale status or photo-confirmation message estimate; PC screen QA pending')
    if file=='ryl_bonus.dat' and 2<=index<=20:
        return dict(width_em=30,max_lines=2,scroll=False,
            provenance='bonus-card objective has up to two source lines; PC screen QA pending')
    if (file=='hud_net.dat' and index in {3,24,25,26}) or (file=='net_topmenu.dat' and index==27):
        return dict(width_em=42,max_lines=8,scroll=False,
            provenance='network confirmation/notice modal, not menu label; PC screen QA pending')
    if file=='net_topmenu.dat' and (9<=index<=14 or index in {21,22}):
        return dict(width_em=32,max_lines=2,scroll=False,
            provenance='online-menu description panel estimate; PC screen QA pending')
    if file=='strinput.dat' and index in {31,44}:
        return dict(width_em=32,max_lines=2,scroll=False,
            provenance='text-entry prompt/help estimate; PC screen QA pending')
    if file=='regulation.dat' and 122<=index<=125:
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='rule-description panel, two or three source lines; PC screen QA pending')
    if file=='mystery_card.dat':
        return dict(width_em=36,max_lines=1,scroll=False,
            provenance='gift-card title estimate accounting for multiple full dynamic names; PC screen QA pending')
    if file=='message_error.dat':
        return dict(width_em=40,max_lines=5,scroll=False,
            provenance='system-error dialog estimate, not menu label; PC screen QA pending')
    if file=='level_up.dat' and index==15:
        return dict(width_em=32,max_lines=2,scroll=True,
            provenance='reviewed countdown steps on separate lines, original waits/sounds retained; PC playback QA pending',
            event_break_review={
                'source_sha256':'8f57f4ac6532dc45cd6b27d8f2aa25178748eca730acc8d760f610d65bcccbbb',
                'after_tokens':['{VAR BE02:000A}'],
                'reason':'Separate the two spoken count steps before RTL. The third wait remains before the reveal, and both original hard body lines remain.'})
    if file=='gameover.dat' or (file=='common_text.dat' and index in {0,1}):
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='blackout narrative or backup-data notice, not menu label; PC screen QA pending')
    if file=='information.dat' and (index in range(25,50,2) or index in {64,66,68,70,209,211,212,213}
            or 73<=index<=123 or 146<=index<=156 or index in range(160,199,2)):
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='city signboard body or Trainer Tip estimate, source has multiple lines; PC screen QA pending')
    if file=='ribbon.dat' and 111<=index<=221:
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='ribbon/mark description panel estimate, not name label; PC screen QA pending')
    if file=='dim_info.dat':
        return dict(width_em=30,max_lines=2,scroll=False,
            provenance='hyperspace map detection/detail panel estimate; source row 9 has two lines; PC screen QA pending')
    if file=='dim_task.dat':
        return dict(width_em=30,max_lines=2,scroll=False,
            provenance='hyperspace survey task estimate matching two-line bonus objectives; PC screen QA pending')
    if file=='aoc_error.dat':
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='DLC access notice modal, not menu label; PC screen QA pending')
    if file=='donut_app.dat' and (index in {39,42,43,44,45,46,47,48,49,50,51,74,75,76,77,78,81,84,85,86,87,88,92,93} or 101<=index<=113):
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='donut preparation dialogue/confirmation/detail text; PC screen QA pending')
    if file=='donut_oneword.dat':
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='donut preparation NPC advice panel with two source lines; PC screen QA pending')
    if file=='questlist_dlc.dat' and index>=16:
        return dict(width_em=32,max_lines=6 if index<=31 else 4,scroll=False,
            provenance='DLC quest journal summary or objective description, not menu title; PC screen QA pending')
    if file=='place_info.dat':
        return dict(width_em=32,max_lines=5,scroll=False,
            provenance='map location description panel, source descriptions have up to three lines; PC screen QA pending')
    if file=='trainermemo.dat':
        return dict(width_em=38,max_lines=8 if 26<=index<=53 else 2,scroll=False,
            provenance='Pokemon summary memory panel with multiple date/location lines; day/month/year localized, PC screen QA pending')
    if file=='questlist_main.dat' and index>=50:
        return dict(width_em=32,max_lines=6 if index<=103 else 4,scroll=False,
            provenance='main quest journal summary or objective description; PC screen QA pending')
    if file=='another_name.dat':
        return dict(width_em=32,max_lines=1,scroll=False,
            provenance='expanded Pokemon name plus ribbon epithet, or two dynamic names in row 110; battle-width estimate, not bare species-name field; PC screen QA pending')
    if file=='questlist_mj.dat' and 267<=index<=317:
        return dict(width_em=32,max_lines=4,scroll=False,
            provenance='research journal explanation panel, not task title; PC screen QA pending')
    if file=='questlist_sub.dat' and index>=206:
        return dict(width_em=32,max_lines=6 if index<=409 else 4,scroll=False,
            provenance='side quest journal summary or objective panel; PC screen QA pending')
    return None
