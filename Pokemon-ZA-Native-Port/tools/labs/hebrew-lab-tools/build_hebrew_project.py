"""Cumulative editorial Hebrew build; reports every category's remaining work.

Existing deliverables are read-only inputs. New keyed translations are bound to
the current source and validated before being merged with the previous mod.
The output is a local candidate, not an automatic console installation.
"""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

from audit_text_coverage import audit
from gfmsg import MsgFile, decode_units
from pack_translation import build_package, sha256
from reuse_translation_memory import reuse
from translation_memory import iter_tm
from translation_validate import plain_text
from localization_exemptions import preserved_alphabet_index, preserved_story_code, preserved_credit_attribution, preserved_literal
from ui_layout_overrides import ui_layout_override

LAB = Path(__file__).resolve().parents[1]
BASE = LAB / 'build/opening-20261030-r2'
HEADINGS = LAB / 'headers/build/full-ui-text-20261030-r7'
MODULES = ['chapter01-completion-20261030-r1.py', 'main-menu-full-20261030-r1.py',
           'interface-core-20261030-r1.py', 'cinematics-hud-20261030-r1.py',
           'chapter02-morning-20261030-r1.py', 'chapter02-catching-20261030-r1.py',
           'chapter02-royale-20261030-r1.py', 'bag-full-20261030-r1.py',
           'chapter03-tower-20261030-r1.py', 'chapter03-detective-20261030-r1.py',
           'chapter03-friends-20261030-r1.py', 'chapter03-rogue-20261030-r1.py',
           'boxes-full-20261030-r1.py', 'types-natures-abilities-20261030-r1.py',
           'chapter04-quasartico-20261030-r1.py', 'chapter04-history-20261030-r1.py',
           'chapter04-strategy-20261030-r1.py', 'chapter04-rescues-20261030-r1.py',
           'chapter04-quiz-round1-20261030-r1.py', 'chapter04-quiz-finals-20261030-r1.py',
           'chapter04-canari-20261030-r1.py', 'chapter05-morning-20261030-r1.py',
           'chapter05-rescues-20261030-r1.py', 'chapter05-search-20261030-r1.py',
           'chapter05-sewers-20261030-r1.py', 'chapter05-gwynn-20261030-r1.py',
           'chapter06-debt-20261030-r1.py', 'lumiose-citizens-a01-20261030-r1.py',
           'field-actions-full-20261030-r1.py', 'moves-battle-full-20261030-r1.py',
           'species-full-20261030-r1.py', 'items-full-20261030-r1.py',
           'battle-set-full-20261030-r1.py', 'battle-ui-full-20261030-r1.py',
           'chapter06-obligations-20261030-r1.py', 'chapter06-city-work-20261030-r1.py',
           'chapter06-corbeau-20261030-r1.py', 'item-descriptions-reviewed-20261030-r1.py',
           'chapter07-team-battles-20261030-r1.py','chapter07-invitation-20261030-r1.py',
           'chapter07-gala-20261030-r1.py','chapter07-rescues-20261030-r1.py',
           'chapter07-tournament-20261030-r1.py','chapter07-finale-20261030-r1.py',
           'donut-flavor-full-20261030-r1.py','pokedex-forms-full-20261030-r1.py',
           'chapter08-quasartico-20261030-r1.py','chapter08-rescues-20261030-r1.py',
           'chapter08-investigation-20261030-r1.py','chapter08-flare-labs-20261030-r1.py',
           'chapter08-az-history-20261030-r1.py','chapter08-promotion-20261030-r1.py',
           'chapter09-crisis-20261030-r1.py','chapter09-alliance-20261030-r1.py',
           'chapter09-city-rescue-20261030-r1.py','chapter09-finale-20261030-r1.py',
           'chapter10-wishes-20261030-r1.py','chapter10-family-20261030-r1.py',
           'chapter10-legends-20261030-r1.py','pokedex-categories-full-20261030-r2.py',
           'places-full-20261030-r2.py','donut-names-full-20261030-r2.py',
           'dlc00-donuts-20261030-r1.py','dlc00-hyperspace-20261030-r1.py',
           'dlc01-survey-20261030-r1.py','dlc01-korrina-20261030-r1.py',
           'dlc02-bodyguards-20261030-r1.py','dlc02-staraptor-20261030-r1.py',
           'dlc03-museum-20261030-r1.py','dlc03-cafe-20261030-r1.py',
           'dlc03-dreams-20261030-r1.py','dlc04-canari-plush-20261030-r1.py',
           'dlc04-richissime-20261030-r1.py','dlc05-emma-canari-20261030-r1.py',
           'dlc05-heatran-dream-20261030-r1.py',
           'dlc06-worlds-merge-20261030-r1.py','dlc06-mega-donut-20261030-r1.py',
           'dlc06-darkrai-20261030-r1.py',
           'dlc07-legends-20261030-r1.py','dlc07-primal-20261030-r1.py',
           'dlc07-rayquaza-wish-20261030-r1.py','dlc07-dream-fulfilled-20261030-r1.py','apparel-full-20261030-r2.py','rogue-battle-full-20261030-r1.py',
           'battle-state-full-20261030-r1.py',
           'battle-standard-opening-20261030-r1.py','battle-standard-effects-20261030-r1.py',
           'battle-standard-bonds-20261030-r1.py','battle-standard-allies-20261030-r1.py',
           'battle-standard-finale-20261030-r1.py','battle-spot-full-20261030-r1.py',
           'battle-online-extras-20261030-r1.py',
           'appearance-pokedex-status-20261030-r1.py','hud-and-gifts-20261030-r1.py',
           'royale-hud-20261030-r1.py','network-photo-input-20261030-r1.py',
           'competition-giftcards-errors-20261030-r1.py','pokemon-events-misc-ui-20261030-r1.py',
           'city-information-boards-20261030-r1.py','ribbons-marks-20261030-r1.py',
           'alphabet-index-label-20261030-r1.py','lumiose-citizens-a02-west-20261030-r1.py',
           'lumiose-citizens-a02-south-20261030-r1.py','lumiose-citizens-a02-rooftops-20261030-r1.py',
           'lumiose-citizens-a02-east-20261030-r1.py','lumiose-citizens-a03-cafes-20261030-r1.py',
           'lumiose-citizens-a03-workers-20261030-r1.py','lumiose-citizens-a03-plazas-20261030-r1.py',
           'lumiose-citizens-a03-canal-20261030-r1.py','lumiose-citizens-a04-fashion-20261030-r1.py',
           'lumiose-citizens-a04-museum-20261030-r1.py','lumiose-citizens-a05-neighbors-20261030-r1.py',
           'lumiose-citizens-a05-dojo-20261030-r1.py','lumiose-citizens-a05-plazas-20261030-r1.py',
           'lumiose-citizens-a05-outer-20261030-r1.py','lumiose-citizens-ring-west-20261030-r1.py',
           'lumiose-citizens-ring-tower-20261030-r1.py','sidequests-001-005-20261030-r1.py',
           'sidequests-006-010-20261030-r1.py','sidequests-011-015-20261030-r1.py',
           'sidequests-016-020-20261030-r1.py','sidequests-021-025-20261030-r1.py',
           'sidequests-026-028-20261030-r1.py','sidequest-029-soothing-20261030-r1.py',
           'sidequests-030-034-20261030-r1.py','sidequests-035-040-20261030-r1.py',
           'sidequests-041-046-20261030-r1.py','sidequests-047-052-20261030-r1.py',
           'sidequests-053-056-20261030-r1.py','sidequests-057-060-20261030-r1.py',
           'sidequest-061-furfrou-league-20261030-r1.py','sidequests-062-065-20261030-r1.py',
           'sidequests-066-068-20261030-r1.py','sidequests-069-071-20261030-r1.py',
           'sidequests-072-075-20261030-r1.py','sidequests-076-077-20261030-r1.py',
           'sidequests-078-080-20261030-r1.py','sidequests-085-087-20261030-r1.py',
           'sidequest-088-jacinthe-only-20261030-r1.py','sidequests-089-090-20261030-r1.py',
           'sidequests-091-093-20261030-r1.py','sidequests-094-096-20261030-r1.py',
           'sidequests-097-099-20261030-r1.py','sidequests-100-101-20261030-r1.py',
           'sidequests-102-103-20261030-r1.py','sidequest-104-spewpa-museum-20261030-r1.py',
           'sidequests-105-107-20261030-r1.py','sidequests-108-110-20261030-r1.py',
           'sidequests-111-112-20261030-r1.py','sidequest-113-froakie-course-20261030-r1.py',
           'sidequests-114-116-20261030-r1.py','sidequest-117-missing-gengar-20261030-r1.py',
           'sidequests-118-120-121-20261030-r1.py','sidequest-119-diancie-20261030-r1.py',
           'sidequests-123-124-20261030-r1.py','sidequest-125-husbands-letter-20261030-r1.py',
           'sidequest-126-cemetery-riddle-20261030-r1.py','sidequest-127-rotom-appliances-20261030-r1.py',
           'sidequests-128-129-20261030-r1.py','sidequest-130-neighbor-misunderstanding-20261030-r1.py',
           'sidequest-131-spice-fiesta-20261030-r1.py','sidequests-132-135-20261030-r1.py',
           'sidequest-136-street-name-20261030-r1.py','sidequest-137-adventure-novel-20261030-r1.py',
           'sidequest-138-romance-novel-20261030-r1.py','sidequest-139-mystery-novel-20261030-r1.py',
           'sidequest-140-password-and-rematch-20261030-r1.py','sidequest-140-rooftop-memories-20261030-r1.py',
           'sidequests-141-142-friends-dreams-20261030-r1.py','sidequests-143-147-20261030-r1.py',
           'sidequests-148-150-20261030-r1.py','sidequests-151-153-20261030-r1.py',
           'sidequests-154-155-20261030-r1.py','sidequests-156-159-20261030-r1.py',
           'sidequests-160-162-20261030-r1.py','sidequests-163-165-20261030-r1.py',
           'sidequests-166-167-20261030-r1.py','sidequests-168-169-20261030-r1.py',
           'sidequests-170-171-20261030-r1.py','sidequest-172-fated-rivals-20261030-r1.py',
           'sidequests-173-174-20261030-r1.py','sidequest-175-frigibax-friends-20261030-r1.py',
           'sidequest-176-three-leeks-20261030-r1.py','sidequests-177-179-20261030-r1.py',
           'sidequest-180-museum-drill-20261030-r1.py','sidequests-181-182-20261030-r1.py',
           'sidequests-183-184-20261030-r1.py','sidequest-185-sushi-coffee-20261030-r1.py',
           'sidequest-186-million-coffee-20261030-r1.py','sidequests-187-188-20261030-r1.py',
           'sidequests-189-190-20261030-r1.py','sidequests-191-193-20261030-r1.py',
           'sidequests-194-195-20261030-r1.py','sidequests-196-198-20261030-r1.py',
           'sidequest-199-magearna-20261030-r1.py','sidequest-200-meltan-20261030-r1.py',
           'sidequest-201-volcanion-20261030-r1.py','sidequest-202-hoopa-20261030-r1.py',
           'sidequest-203-zeraora-20261030-r1.py','dlc-side-services-20261030-r1.py',
           'dlc-repeat-activities-20261030-r1.py','city-services-basics-20261030-r1.py',
           'city-farewells-20261030-r1.py','city-training-services-20261030-r1.py',
           'pokemon-center-service-20261030-r1.py','city-fashion-services-20261030-r1.py',
           'city-shop-service-20261030-r1.py','city-market-stands-20261030-r1.py',
           'city-battle-restaurants-20261030-r1.py','city-cafe-service-20261030-r1.py',
           'city-taxi-destinations-20261030-r1.py','city-taxi-zach-stories-20261030-r1.py',
           'city-taxi-driver-stories-20261030-r1.py','interiors-hotel-agency-lab-20261030-r1.py',
           'interiors-restaurant-patrons-20261030-r1.py','interiors-factions-and-richissime-20261030-r1.py',
           'museum-visitors-and-masterpieces-20261030-r1.py','museum-kalos-and-hisui-20261030-r1.py',
           'postgame-rematch-services-20261030-r1.py','finale-guidance-and-hotel-rooms-20261030-r1.py',
           'finale-cinematics-and-field-messages-20261030-r1.py','city-arrival-and-field-guidance-20261030-r1.py',
           'city-gifts-and-advice-20261030-r1.py','royale-gifts-and-healing-20261030-r1.py',
           'reward-match-dialogues-20261030-r1.py','hyperspace-survey-interface-20261030-r1.py',
           'donut-workshop-interface-20261030-r1.py','ansha-donut-conversations-20261030-r1.py',
           'dlc-quest-journal-20261030-r1.py','pokemon-titles-and-small-names-20261030-r1.py',
           'pokemon-origin-names-20261030-r1.py','lumiose-map-descriptions-20261030-r1.py',
           'trainer-class-names-20261030-r1.py','pokemon-memories-20261030-r1.py',
           'npc-names-full-20261030-r1.py','main-quest-journal-summaries-20261030-r1.py',
           'main-quest-journal-objectives-20261030-r1.py','mable-research-journal-20261030-r1.py',
           'sidequest-journal-titles-20261030-r1.py','sidequest-journal-summaries-a-20261030-r1.py',
           'sidequest-journal-summaries-b-20261030-r1.py','sidequest-journal-objectives-a-20261030-r1.py',
           'sidequest-journal-objectives-b-20261030-r1.py','item-descriptions-legacy-a-20261030-r1.py',
           'item-descriptions-legacy-b-20261030-r1.py','item-descriptions-legacy-c-20261030-r1.py',
           'item-descriptions-technical-records-20261030-r1.py','item-descriptions-galar-hisui-20261030-r1.py',
           'item-descriptions-paldea-food-20261030-r1.py','item-descriptions-picnic-indigo-20261030-r1.py',
           'ability-descriptions-a-20261030-r1.py','ability-descriptions-b-20261030-r1.py',
           'move-descriptions-a-20261030-r1.py','move-descriptions-b-20261030-r1.py','move-descriptions-c-20261030-r1.py',
           'pokedex-descriptions-a-20261030-r1.py','pokedex-descriptions-b-20261030-r1.py',
           'pokedex-descriptions-c-20261030-r1.py','pokedex-descriptions-d-20261030-r1.py',
           'pokedex-descriptions-e-20261030-r1.py','pokedex-descriptions-f-20261030-r1.py',
           'trainer-messages-a-20261030-r1.py','trainer-messages-b-20261030-r1.py',
           'trainer-messages-repeated-20261030-r1.py','trainer-messages-c-20261030-r1.py','trainer-messages-d-20261030-r1.py',
           'trainer-messages-e-20261030-r1.py','tourist-tips-a-20261030-r1.py','tourist-tips-b-20261030-r1.py',
           'loading-tips-a-20261030-r1.py','loading-tips-b-20261030-r1.py','credits-reviewed-20261030-r1.py']


def load_module(name):
    path = LAB / 'translations' / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def authored_rows(module, records):
    by_index = {r['line_index']: r for r in records if r['file'] == module.FILE}
    expected = {i for i, r in by_index.items() if module.FIRST <= i < module.STOP and r['requires_translation']}
    output = {}
    for indices, text in module.GROUPS:
        for index in indices:
            if index in output or index not in expected:
                raise ValueError(f'Duplicate or out-of-scope editorial row {module.FILE}:{index}')
            record = by_index[index]
            if hasattr(module, 'SOURCE_BY_INDEX') and module.SOURCE_BY_INDEX.get(index) != record['source']:
                raise ValueError('Frozen editorial source changed: ' + record['key'])
            voices = re.findall(r'\{VAR 0114:[0-9A-F,]+\}', record['source'])
            if '@VOICE@' in text and len(voices) != 1:
                raise ValueError('Voice control cannot be inferred: ' + record['key'])
            output[index] = dict(key=record['key'], he=text.replace('@VOICE@', voices[0] if voices else ''),
                                 new_terms=[], note='assistant editorial review; ' + module.__name__)
            if index in getattr(module, 'NEUTRAL_GENDER_ROWS', {}):
                from translation_validate import parse_tokens
                branches = list(dict.fromkeys(t['atom'] for t in parse_tokens(record['source']) if t['code'] == 0x1100))
                if not branches:
                    raise ValueError('Declared gender-neutral rewrite has no source gender branch')
                output[index]['neutral_gender_rewrite'] = dict(
                    source_sha256=hashlib.sha256(record['source'].encode('utf-8')).hexdigest(),
                    omitted_tokens=branches, reason=module.NEUTRAL_GENDER_ROWS[index])
    if set(output) != expected:
        raise ValueError(f'Incomplete authored scope {module.FILE}; missing indices {sorted(expected-set(output))}')
    return list(output.values())


def merge_mod(target, baseline, original_root):
    """Keep old translated rows except where the new batch explicitly replaces them."""
    for path in sorted(baseline.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(baseline)
        dest = target / relative
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        elif path.read_bytes() != dest.read_bytes():
            if relative.suffix != '.dat' or relative.parts[:2] != ('romfs', 'ik_message'):
                raise ValueError('Unexpected non-message asset difference: ' + str(relative))
            old = MsgFile(path.read_bytes())
            new = MsgFile(dest.read_bytes())
            original = MsgFile((original_root / relative).read_bytes())
            if not (old.params == new.params == original.params and
                    len(old.lines) == len(new.lines) == len(original.lines)):
                raise ValueError('Merge would change message structure')
            for i, line in enumerate(new.lines):
                if line != original.lines[i]:
                    old.lines[i] = line
            dest.write_bytes(old.encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,90}', args.revision):
        raise ValueError('Use a simple versioned revision')
    output = LAB / 'build' / args.revision
    if output.exists():
        raise FileExistsError('Existing build is preserved')
    tm = LAB / 'memory/english-source.jsonl'
    records = list(iter_tm(tm))
    keyed = {r['key']: r for r in records}
    loaded = [load_module(name) for name in MODULES]
    modules = [table for module in loaded for table in getattr(module, 'TABLES', [module])]
    rows = [row for module in modules for row in authored_rows(module, records)]
    terms = {'Pokémon': 'פוקימון', 'Lumiose City': 'לומיוז', 'Lumiose': 'לומיוז',
             'Hotel Z': 'מלון זי', 'Z-A Royale': 'רויאל Z-A', 'Pancham': "פנצ'אם",
             'Andre': 'אנדרה'}
    for module in modules:
        terms.update(module.TERMS)
    # Generic trainer titles inflect for gender; review their forms explicitly
    # rather than enforcing the masculine glossary spelling in female dialogue.
    inflected_phrases = {'Pokémon Trainer', 'Mega Stone', 'Mega Stones', 'Battle Zone', 'Wild Zone', 'Shiny Pokémon',
                        'Rotom Phone', 'Pokémon Center', 'Attack', 'Speed',
                        'Defense', 'Sp. Atk', 'Sp. Def'}
    invariant_terms = {en: he for en, he in terms.items() if en not in inflected_phrases}
    authored_keys = {row['key'] for row in rows}
    for record in records:
        if ('/common/' in record['file'] and record['source'] in terms and record['key'] not in authored_keys
                and preserved_literal(record) is None):
            rows.append(dict(key=record['key'], he=terms[record['source']], new_terms=[],
                             note='contextual name/term used by the completed chapter or menu'))
    # Review corrections to the earlier opening batch without overwriting its source.
    corrections = {
        'msg_Ev_m01_0050_talk_12_f': 'אה, מאמנים מאתמול בלילה? סליחה, אני לא זוכר אתכם. כנראה שלא הייתם אתגר גדול במיוחד.{VAR 0114:0006}',
        'msg_Ev_m01_0070_talk_03': 'זה קרב הפוקימונים הראשון שלך! אין סיכוי שאפסיד!{VAR 0114:002C}',
    }
    for label, he in corrections.items():
        key = 'ik_message/dat/English/script/main_01_01.dat:' + label
        rows.append(dict(key=key, he=he, new_terms=[], note='review of previous batch; natural speech and gender-neutral address'))
    from pack_translation import poc_records
    edited = {r['key']: r for r in poc_records(LAB / 'extract')[1]}
    edited.update({r['key']: r for r in iter_tm(LAB / 'translations/opening-20261030-r2.jsonl')})
    edited.update({r['key']: r for r in rows})
    reused_rows = reuse(records, edited)
    rows.extend(reused_rows)
    if len({r['key'] for r in rows}) != len(rows):
        raise ValueError('Repeated cumulative batch key')
    rows.sort(key=lambda r: (keyed[r['key']]['file'], keyed[r['key']]['line_index']))
    translations = LAB / 'translations' / (args.revision + '.jsonl')
    glossary = LAB / 'translations' / (args.revision + '-terms.tsv')
    for path in (translations, glossary):
        if path.exists():
            raise FileExistsError('Preserve previous authored batch artifacts')
    translations.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    with glossary.open('w', encoding='utf-8', newline='') as out:
        writer = csv.writer(out, delimiter='\t')
        writer.writerow(['english', 'hebrew', 'category', 'note'])
        writer.writerows((en, he, 'editorial', 'assistant-reviewed subset; inflections checked separately') for en, he in invariant_terms.items())
        for module in modules:
            writer.writerows((en, he, 'file:'+module.FILE, 'frozen editorial spelling scoped to source file')
                             for en, he in getattr(module, 'LOCAL_TERMS', {}).items())
    from translation_memory import load_glossary
    from translation_validate import validate_translation
    glossary_values = load_glossary(glossary)
    invalid = [verdict for row in rows
               if not (verdict := validate_translation(keyed[row['key']], row, glossary_values))['valid']]
    if invalid:
        raise ValueError('Editorial preflight errors: ' + json.dumps(invalid, ensure_ascii=False))
    overrides = {}
    for row in rows:
        record = keyed[row['key']]
        if record['file'].endswith('/common/main_menu.dat'):
            index = record['line_index']
            if index in (53, 54, 55, 56, 57, 61, 62, 63, 64, 79, 80, 81, 86, 87, 88, 89, 90, 91, 92, 93, 172, 174, 175):
                overrides[row['key']] = dict(width_em=30, max_lines=4, scroll=True,
                                             provenance='message-window estimate; visual QA pending')
            elif index in (82, 83):
                overrides[row['key']] = dict(width_em=45, max_lines=2, scroll=False,
                                             provenance='retained prior PoC obedience text; wider summary field')
        elif record['file'].endswith('/common/option.dat') and record['line_index'] in (5, 18, 35, 37, 39, 51, 56, 58, 71, 77, 88):
            overrides[row['key']] = dict(width_em=32, max_lines=3, scroll=False,
                                         provenance='settings description estimate; screen QA required')
        elif record['file'].endswith('/common/map.dat') and record['line_index'] in (27, 28, 46, 61, 62, 63, 64, 65, 66):
            overrides[row['key']] = dict(width_em=30, max_lines=4, scroll=False,
                                         provenance='map text panel/message estimate; screen QA required')
        elif ((re.search(r'/script/t1_(?:A0[1-5]|R)\.dat$',record['file']) and '_speech_' in record['label'])
              or (record['file'].endswith('/script/sub_026.dat') and record['line_index'] in range(36,41))
              or (record['file'].endswith('/script/sub_029.dat') and record['line_index'] in (17,18,33,34,49,50,65,66,81,82))
              or (record['file'].endswith('/script/sub_103.dat') and record['line_index'] in (1,2))
              or (record['file'].endswith('/sk/sub_131.dat') and '_speech_' in record['label'])
              or (record['file'].endswith('/sk/sub_136.dat') and record['line_index'] in (41,42,43,47,48,49,53,54,55,59,60,61))
              or (record['file'].endswith('/sk/sub_153.dat') and record['line_index'] in (0,11,18))
              or (record['file'].endswith('/sk/sub_155.dat') and record['line_index'] in (27,28))
              or (record['file'].endswith('/sk/sub_180.dat') and record['line_index'] in (33,34))
              or (record['file'].endswith('/sk/megashards_san.dat') and record['line_index']==5)
              or (record['file'].endswith('/script/fossil.dat') and record['line_index']==0)
              or (record['file'].endswith('/script/lostball.dat') and record['line_index']==0)
              or (record['file'].split('/')[-1] in ('training.dat','reset.dat','moveplus.dat','coordination.dat') and record['line_index']==0)
              or (record['file'].endswith('/script/taxi.dat') and record['line_index'] in (65,66,67))
              or (record['file'].split('/')[-1] in ('t1.dat','t1_ev001_3.dat','t1_i004a.dat','t1_i004b.dat','t1_i004c.dat','t1_i004d.dat','t1_i008_1.dat','t1_i011.dat','t1_i012_1.dat','t1_i012_2.dat','t1_last_battle.dat') and '_speech_' in record['label'])
              or (record['file'].split('/')[-1] in ('npc_event.dat','royale_event.dat','reward.dat') and '{VAR BD0A:000A}Text_icon1' in record['source'])):
            overrides[row['key']] = dict(width_em=18, max_lines=4, scroll=False,
                                         provenance='ambient bubble estimate; actual PC screen QA required')
        elif (record['file'].endswith('/script/main_hud.dat') or record['file'].endswith('/sk/sa_main_hud.dat')
              or (record['file'].endswith('/script/t1.dat') and record['label'].startswith('msg_hud_simple_'))):
            overrides[row['key']] = dict(width_em=24, max_lines=2, scroll=False,
                                         provenance='two-line story HUD estimate; no scrolling controls; screen QA required')
        elif '/script/demo_' in record['file']:
            overrides[row['key']] = dict(width_em=45, max_lines=2, scroll=False,
                                         provenance='cinematic subtitle estimate; native centering and timing QA pending')
        elif record['file'].endswith('/common/box.dat'):
            index = record['line_index']
            if 219 <= index <= 243:
                overrides[row['key']] = dict(width_em=45, max_lines=2, scroll=False,
                                             provenance='nature-effect panel estimate; screen QA pending')
            elif index in (61, 62, 63, 64, 67, 68, 70, 71, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82,
                            139, 140, 141, 143, 144, 145, 146, 147, 148, 149, 150, 156, 157, 158, 159,
                            160, 161, 162, 197, 291, 292, 293, 294, 295):
                overrides[row['key']] = dict(width_em=30, max_lines=4, scroll=True,
                                             provenance='box message-window estimate; screen QA pending')
    for row in rows:
        ui_override=ui_layout_override(keyed[row['key']])
        if ui_override:
            overrides[row['key']]=ui_override
    manifest = build_package(output=output, tm=tm, translations=translations,
                             glossary=glossary, reviewed_candidate=True, layout_overrides=overrides)
    merge_mod(output / 'mods/hebrew', BASE / 'mods/hebrew', LAB / 'extract')
    heading_checks = json.loads((HEADINGS/'verification.json').read_text(encoding='utf-8'))
    for check in heading_checks:
        relative = Path(check['file'])
        source = HEADINGS/'mods/hebrew/romfs'/relative
        target = output/'mods/hebrew/romfs'/relative
        if sha256(source) != check['sha256']:
            raise ValueError('Unexpected heading source hash')
        if target.exists() and sha256(target) not in (check.get('prior_sha256'),check['sha256']):
            raise ValueError('Unexpected heading baseline overlap')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    coverage = audit(tm, output / 'mods/hebrew/romfs', LAB / 'extract')
    (output / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    table_progress = {}
    for file in sorted({module.FILE for module in modules}):
        source_rows = [r for r in records if r['file'] == file and r['requires_translation']]
        original = MsgFile((LAB / 'extract/romfs' / file).read_bytes())
        candidate = MsgFile((output / 'mods/hebrew/romfs' / file).read_bytes())
        self_covered = sum(candidate.lines[r['line_index']] != original.lines[r['line_index']] for r in source_rows)
        technical = [r for r in source_rows if preserved_literal(r) is not None]
        technical_valid = sum(decode_units(candidate.lines[r['line_index']])==preserved_literal(r) for r in technical)
        lexical = [r for r in source_rows if any(ch.isalpha() for ch in plain_text(r['source']))
                   and preserved_literal(r) is None]
        localized = sum(bool(re.search('[א-ת]', plain_text(decode_units(candidate.lines[r['line_index']]))))
                        and candidate.lines[r['line_index']] != original.lines[r['line_index']] for r in lexical)
        table_progress[file] = dict(visible_rows=len(source_rows), changed_rows=self_covered,
                                   language_neutral_rows=len(source_rows)-len(lexical)-len(technical),
                                   technical_identifier_rows=len(technical),verified_identifier_rows=technical_valid,
                                   alphabet_index_rows=sum(preserved_alphabet_index(r) is not None for r in technical),
                                   story_code_rows=sum(preserved_story_code(r) is not None for r in technical),
                                   credit_attribution_rows=sum(preserved_credit_attribution(r) is not None for r in technical),
                                   language_rows=len(lexical), localized_language_rows=localized,
                                   complete_message_table=localized == len(lexical) and technical_valid==len(technical))
    changed = 0
    final_sources = []
    for path in (output / 'mods/hebrew/romfs/ik_message/dat/English').rglob('*.dat'):
        relative = path.relative_to(output / 'mods/hebrew')
        original = MsgFile((LAB / 'extract' / relative).read_bytes())
        candidate = MsgFile(path.read_bytes())
        if candidate.params != original.params or len(candidate.lines) != len(original.lines):
            raise ValueError('Final GFMSG structure changed')
        changed_here = sum(a != b for a, b in zip(original.lines, candidate.lines))
        changed += changed_here
        final_sources.append(dict(file=Path(*relative.parts[1:]).as_posix(),
                                  original_sha256=sha256(LAB / 'extract' / relative),
                                  table_sha256=sha256((LAB / 'extract' / relative).with_suffix('.tbl')),
                                  changed_lines=changed_here, total_lines=len(original.lines),
                                  params_preserved=True,
                                  provenance='final cumulative comparison against original source'))
    manifest.update(scope='cumulative_editorial_translation_candidate', complete_game_translation=False,
                    translations=changed, checked_batch_rows=len(rows), table_progress=table_progress,
                    reused_edited_records=len(reused_rows),
                    message_files=len(final_sources), source_files=final_sources,
                    baseline=str(BASE.relative_to(LAB)), baseline_manifest_sha256=sha256(BASE / 'manifest.json'),
                    editorial_sources={name: sha256(LAB / 'translations' / name) for name in MODULES},
                    native_heading_archives=heading_checks,
                    ps5_installation_performed=False, visual_qa='new chapter/menu content pending')
    manifest['files'] = [dict(path=p.relative_to(output).as_posix(), bytes=p.stat().st_size, sha256=sha256(p))
                         for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'manifest.json']
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(changed_rows=changed, checked_batch_rows=len(rows), table_progress=table_progress), ensure_ascii=False))


if __name__ == '__main__':
    main()
