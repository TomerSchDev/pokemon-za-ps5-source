# -*- coding: utf-8 -*-
"""P5 knowledge harvest: addresses that the existing research already identified, with the file:line that says so.

Nothing here is derived from the game code anew; every row cites the repo document or script that established it.
Confidence follows the sources' own tags: proven = read directly in code/binary/log or tested; derived = direct
conclusion from proven facts; assumed = plausible, not checked. harvest.py verifies that each address exists in
the translated code (function definition, label, or literal / ADRP+ADD constant) before it is written.

Row: (addr without 0x, name, subsystem, confidence, source file:line, note)
Naming: functions as Area::Name; 'site:' = a label inside a function (hook anchor); 'data:'/'global:'/'got:'/
'vtable:'/'typeinfo:'/'string:' = non-code guest addresses; 'region:' = runtime memory-map constant (not code).
"""

RV = 'analysis/rando-v2-name-cheats-cutscenes-HE.md'
DT = 'analysis/dynamic-timing-design-HE.md'
CR27 = 'port/cheats-r27/README-HE.md'
PM = 'port/cheats-r27/prepare-money-hooks.py'
PD = 'port/rando-dexcount/prepare-dexcount-hooks.py'
TD = 'port/rando-dexcount/test/test_dexcount.c'
FD = 'port/rando-dexcount/research/find-dex-missions.py'
PI = 'port/cheats-r28/prepare-items-hooks.py'
ZI = 'port/cheats-r28/za_items.c'
PC = 'port/randomizer/prepare-cheat-hooks.py'
CH = 'port/randomizer/cheats.cpp'
DG = 'port/dynamic-timing/za_dyn_glue.h'
PH = 'port/dynamic-timing/prepare-dynamic-hooks.py'
FH = 'port/title/prepare-fps-hook.py'
HA = 'analysis/fps-headroom-audit-HE.md'
HT = 'analysis/hebrew-text-plan-HE.md'
NS = 'analysis/new-species-feasibility-HE.md'
CG = 'analysis/ps5-runtime-compile-gaps.md'
RP = 'analysis/pokeza-runtime-platform.md'
R26 = 'port/perf-r26/README-HE.md'
ST = 'STATUS-HANDOFF-20261029-HE.md'
PK = 'save-workbench/deps/PKHeX/PKHeX.Core/Saves/Access/SaveBlockAccessor9ZA.cs'

CURATED = [
    # ------------------------------------------------------------------ Pokedex / missions & conditions
    ('7000a1158c', 'Condition::HavePokemonEncyclopediaTotal::Evaluate', 'missions-conditions', 'proven', f'{PD}:3-8',
     'Evaluator of have_pokemon_encyclopedia_total_condition (vtable slot +0x78): main mission 2 "register at least '
     'five species", its two lab triggers in trigger_main_02 and Mable\'s 46 "Filling Your Pokedex" requests. Parses '
     'the args with f_7000a11604, asks f_700033e770(manager, 0, 0) for the Lumiose caught count and compares with '
     'f_7000a11670. rando-dexcount hooks it to add the Hyperspace count (kind 1).'),
    ('700033e770', 'Pokedex::GetCaughtCount(manager, kind, mode)', 'pokedex', 'proven', f'{PD}:5-6',
     'Returns the caught count of the asked dex list: kind 0 = Lumiose dex (232 species), kind 1 = Hyperspace / Mega '
     'Dimension dex (132 species). The manager pointer comes from the GOT slot 0x7003ec6230. Called by the condition '
     'evaluator f_7000a1158c; "who counts the Pokedex" for the missions.'),
    ('7000a11604', 'Condition::ParseArgs', 'missions-conditions', 'proven', f'{TD}:5',
     'Argument parser of the condition object: returns x0 = op | arg0 << 32, x1 = arg1.'),
    ('7000a11670', 'Condition::Compare(op)', 'missions-conditions', 'proven', f'{TD}:8',
     'Comparator with runtime op codes decoded from its jump table at 0x7003393e84: 2 ==, 3 !=, 4 <, 5 <=, 6 >, 7 >=. '
     'The table-side codes (1 ==, 4 <, 5 >=) are mapped by the loader (find-dex-missions.py:12-14).'),
    ('7003ec6230', 'got:PokedexManager', 'pokedex', 'proven', f'{TD}:10',
     'GOT entry holding the Pokedex manager, read by the condition evaluator before calling f_700033e770.'),
    ('7003393e84', 'data:ConditionCompareJumpTable', 'missions-conditions', 'proven', f'{TD}:53',
     'Jump table (rodata) of the condition comparator f_7000a11670.'),

    # ------------------------------------------------------------------ Save blocks (SwishCrypto / SCBlock store)
    ('70008b01e0', 'SaveBlock::GetAccessor', 'save-blocks', 'proven', f'{RV}:89',
     'Returns the save-block accessor (528 callers). Its input comes from the constant globals 0x7003ec28d8 and '
     '0x7003ec2900 (e.g. main_384.c:5045-5058). Blocks are a sorted array of 0x20-byte records, key u32 at +0, '
     'begin/end at obj+8 / obj+0x10.'),
    ('7003ec28d8', 'global:SaveBlockAccessorSource', 'save-blocks', 'proven', f'{RV}:90',
     'Constant global read before SaveBlock::GetAccessor (first of two; see main_384.c:5045-5058).'),
    ('7003ec2900', 'global:SaveBlockAccessorSource2', 'save-blocks', 'proven', f'{RV}:90',
     'Constant global read before SaveBlock::GetAccessor (second of two).'),
    ('7000c2790c', 'SaveBlock::BinarySearch / Pokedex::LoadBlock', 'save-blocks', 'proven', f'{RV}:92',
     'Binary search over the sorted 0x20-byte block records (main_344.c:21268-21282); the same function is the '
     'KPokedex (0x2D87BE5C) load site at main_344.c:21270 with the item-style copy context. Runtime copy of the '
     'Pokedex block is derived, its layout vs PKHeX Zukan9a is assumed (' + RV + ':230-232).'),
    ('70005da6f8', 'SaveBlock::FindByKey', 'save-blocks', 'proven', f'{RV}:93',
     'Finds a block record by key (98 callers); runs under the lock at accessor+0x68.'),
    ('7000b49538', 'SaveBlock::SCXorShift32Seed', 'save-blocks', 'proven', f'{RV}:94-96',
     'Derives the stream seed from the block key with the popcount loop x^=x<<2; x^=x>>15; x^=x<<13 (main_333.c:3819 '
     'ff.). Identical to PKHeX SCXorShift32 (Saves/Encryption/SwishCrypto/SCXorShift32.cs:18-53). Block contents '
     'are encrypted in memory.'),
    ('7000700460', 'SaveBlock::CopyToBuffer (decrypting)', 'save-blocks', 'derived', f'{RV}:97-98',
     'Copies a block into the destination buffer with the SCXorShift32 seed (main_226.c:25269, 91 callers). That the '
     'copy also decrypts is derived from the seed being PKHeX\'s.'),
    ('7000976bac', 'SaveBlock::GetU32(accessor, &key)', 'save-blocks', 'derived', f'{RV}:104',
     'Reads a u32 block by key: Money::Load calls f_7000976bac(acc,&key) and stores the result at this+0x40. Also the '
     'next call after the KPictureCurrent/Initial/SBC Width/Height keys (block-key-sites: 7 sites).'),
    ('70009c19bc', 'SaveBlock::SetU32(accessor, &key, &value)', 'save-blocks', 'derived', f'{RV}:104',
     'Writes a u32 block by key: Money::Save calls f_70009c19bc(acc,&key,&v) after clamping to 0x98967F.'),

    # ------------------------------------------------------------------ Money (fully mapped, cheats-r27)
    ('700291eaf0', 'Money::Reset', 'money', 'proven', f'{RV}:137', 'Sets the money field (component+0x40, u32) to 0. main_1035.c:3427. cheats-r27 hooks its entry (za_money_lifecycle_reset).'),
    ('700291eb00', 'Money::Set', 'money', 'proven', f'{RV}:138', 'Sets component+0x40 with a clamp to 9,999,999. main_1035.c:3435.'),
    ('700291eb18', 'Money::Get', 'money', 'proven', f'{RV}:139', 'Returns component+0x40. main_1035.c:3445. cheats-r27 hooks its entry (za_cheat_money_component callback before the read).'),
    ('700291eb20', 'Money::Sub', 'money', 'proven', f'{RV}:140', 'Subtracts with a floor of 0. main_1035.c:3451.'),
    ('700291eb44', 'Money::Max', 'money', 'proven', f'{RV}:141', 'Returns the cap 9,999,999. main_1035.c:3464.'),
    ('7000a7184c', 'Money::Add', 'money', 'proven', f'{RV}:143', 'Adds with the 9,999,999 clamp, then calls f_70009218b0(8). main_315.c:20981.'),
    ('70009218b0', 'Money::Add::post-call(8)', 'money', 'assumed', f'{RV}:143',
     'Called by Money::Add with argument 8 after the clamp; role not researched (possibly a dirty/notify).'),
    ('7000a718c8', 'Money::FindComponent', 'money', 'proven', f'{RV}:145-147',
     'Unique lookup: walks the component list and compares the type descriptor with 0x7003d59948 (main_315.c:21021). '
     'All 7 callers are money wrappers: f_7000a717e8 (Add), f_7002919ac4 (Set), f_7002919b28 (Get), f_7002d6a5e0 / '
     'f_7002d6a634 / f_7002d6a674 (Set/Max/Sub) and f_7002a54efc. cheats-r27 hook anchor: label L_7000a7195c.'),
    ('7000a7195c', 'site:Money::FindComponent::result', 'money', 'proven', f'{CR27}:21',
     'Label inside f_7000a718c8 reached after the type-descriptor check (x19 = component or 0); the MONEY cheat hook '
     'of cheats-r27 is inserted here before x0 = x19 (' + PM + ':16-17).'),
    ('7003d59948', 'typeinfo:MoneyComponent', 'money', 'proven', f'{RV}:146',
     'Type descriptor that Money::FindComponent (f_7000a718c8) and the UI money reader (f_70006bfce0) compare against.'),
    ('7000a717e8', 'Money::AddWrapper', 'money', 'proven', f'{RV}:146', 'Caller of Money::FindComponent; adds money.'),
    ('7002919ac4', 'Money::SetWrapper', 'money', 'proven', f'{RV}:146', 'Caller of Money::FindComponent; sets money.'),
    ('7002919b28', 'Money::GetWrapper', 'money', 'proven', f'{RV}:146', 'Caller of Money::FindComponent; reads money.'),
    ('7002d6a5e0', 'Money::SetWrapper2', 'money', 'proven', f'{RV}:146-147', 'Caller of Money::FindComponent (Set).'),
    ('7002d6a634', 'Money::MaxWrapper', 'money', 'proven', f'{RV}:146-147', 'Caller of Money::FindComponent (Max).'),
    ('7002d6a674', 'Money::SubWrapper', 'money', 'proven', f'{RV}:146-147', 'Caller of Money::FindComponent (Sub).'),
    ('7002a54efc', 'Money::Wrapper (role not researched)', 'money', 'proven', f'{RV}:147', 'Seventh caller of Money::FindComponent; the research lists it among the money wrappers without a role.'),
    ('7000dbb28c', 'Money::Load (KMoney -> this+0x40)', 'money', 'proven', f'{RV}:104',
     'Virtual Load of the money component (main_384.c:5038): f_7000976bac(acc,&KMoney) -> u32 -> ST32 [this+0x40]. '
     'KMoney 0x4F35D0DD is built as MOVZ+MOVK at main_384.c:5059-5060. cheats-r27 hooks the entry (lifecycle reset) '
     'and the post-store (readiness).'),
    ('70009c18d8', 'Money::Save (this+0x40 -> KMoney)', 'money', 'proven', f'{RV}:104',
     'Save of the money component (main_303.c:21518): LD32 [this+0x40], min(., 0x98967F), f_70009c19bc(acc,&KMoney,&v). '
     'The block is overwritten on every save, so cheats must write the live object. KMoney built at main_303.c:21539-21540. '
     'cheats-r27 hook at the entry label L_70009c18d8.'),
    ('70006bfce0', 'UI::MoneyReader', 'money', 'proven', f'{CR27}:19',
     'UI function that reads the money component (x23+0x40) after checking the money type descriptor; the compiler '
     'inlined the Get here, which is why the lookup-only hook of r26p missed it. cheats-r27/r28 hook anchor: label L_70006bfd98.'),
    ('70006bfd98', 'site:UI::MoneyReader::after-type-check', 'money', 'proven', f'{PM}:14',
     'Label inside f_70006bfce0 after the money type-descriptor check, before reading x23+0x40 (MONEY and ITEMS hook anchor).'),

    # ------------------------------------------------------------------ Bag / items (cheats-r28)
    ('7000b49360', 'Items::Load (KItem -> this+0x40)', 'bag-items', 'proven', f'{RV}:105',
     'Loads the bag (main_333.c:3678): copies and decrypts 0xBC00 bytes of KItem 0x21C9BD44 to this+0x40, and KFusedCalyrex '
     '0x916BCA9E (0x158 bytes) to this+0xBC40. Layout = PKHeX MyItem9a: 3000 records x 16 bytes indexed by item id, '
     '{Pouch u32 (0xFFFFFFFF none), Count i32, Flags u32 (1 new, 2 fav, 4 notify, 8 shop, 0x10 held), pad}; pouch flags '
     'at +0xBB80 (derived). cheats-r28 hooks the entry (za_items_reset).'),
    ('7000c3c3e8', 'Items::Save (this+0x40 -> KItem)', 'bag-items', 'derived', f'{RV}:105',
     'Writes the bag back to KItem (main_345.c:18886), same key, this+0x40, under the accessor lock; also the second '
     'KFusedCalyrex site (main_345.c:19114). Direction derived.'),
    ('70002bc8ec', 'Items::GetCount(id)', 'bag-items', 'proven', f'{ZI}:44',
     'Typed item-count getter: x0 = id, returns the count in the upper 32 bits of x0 (main_097.c). cheats-r28 hooks '
     'its entry label L_70002bc8ec with za_items_pump (the game calls run synchronously inside this getter).'),
    ('70002bc9d0', 'ItemTable::Lookup(table, id)', 'bag-items', 'derived', f'{ZI}:48-49',
     'Returns nonzero when the item id exists in the loaded item table (table pointer from 0x7003ec3320); used by '
     'cheats-r28 to validate every catalog id against the game\'s own table.'),
    ('7000a5a228', 'ItemTable::GetCap(table, id)', 'bag-items', 'derived', f'{ZI}:50-51',
     'Returns the per-item quantity cap (999 for consumables, 1 for TMs) from the loaded item table.'),
    ('700099e47c', 'ItemTable::GetPocket(table, id)', 'bag-items', 'derived', f'{ZI}:52-53',
     'Returns the pocket index of an item from the loaded item table (PKHeX pockets: 0 Medicine, 1 Balls, 2 Other, 6 TM).'),
    ('700048963c', 'Items::Add(manager, id, amount, 0, 0)', 'bag-items', 'proven', f'{ZI}:2-3',
     'Original add-item path head: x0 = item manager singleton 0x700610d800, x1 = id, x2 = amount. Continues through '
     'f_700048994c to the inventory write f_7000a5a268. cheats-r28 ITEMS calls it (inventory writes stay in game code).'),
    ('700048994c', 'Items::Add (inner)', 'bag-items', 'proven', f'{PI}:37', 'Second step of the game add-item path f_700048963c -> f_700048994c -> f_7000a5a268.'),
    ('7000a5a268', 'Items::AddWriteInventory', 'bag-items', 'proven', f'{PI}:37', 'Last step of the add-item path: the inventory write.'),
    ('7000bba2cc', 'Items::QueuedGrantHandler (hook site)', 'bag-items', 'derived', f'{PI}:14',
     'Second cheats-r28 pump site (main_339.c, label L_7000bba2cc): the game\'s queued item-grant handler, guarded by '
     'the same singleton readiness flags 0x700610d940 / 0x700610dec0 as the add-item wrapper.'),
    ('7003ec3320', 'global:ItemTablePointer', 'bag-items', 'proven', f'{ZI}:46',
     'Holds the loaded item table pointer; cheats-r28 requires it nonzero (>= 0x10000) before any lookup.'),
    ('700610d800', 'global:ItemManagerSingleton', 'bag-items', 'proven', f'{ZI}:86',
     'Item manager singleton passed as x0 to Items::Add.'),
    ('700610d940', 'global:ItemsReadyFlag1', 'bag-items', 'proven', f'{ZI}:60',
     'Readiness flag (u32) checked by the game\'s add-item wrapper and queued grant handler; cheats-r28 reads it.'),
    ('700610dec0', 'global:ItemsReadyFlag2', 'bag-items', 'proven', f'{ZI}:60', 'Second readiness flag checked before item operations.'),

    # ------------------------------------------------------------------ Party / PA9 crypto
    ('7000a0ccd8', 'Party::Load (KParty)', 'party-pokemon', 'proven', f'{RV}:106',
     'Loads KParty 0x3AA1A9AD (main_309.c:25589): 0xB40 bytes (6 x 0x1E0) into a stack buffer, then virtual deserialize '
     '(+0x220) into the party object.'),
    ('7000a3e064', 'Party::Save (second KParty site)', 'party-pokemon', 'derived', f'{RV}:106',
     'Second KParty site (main_311.c:28238); the save direction is derived.'),
    ('7000dbb13c', 'Box::Save (KBox)', 'party-pokemon', 'proven', f'{RV}:107',
     'Saves the boxes (main_384.c:4938): 32 x 30 slots x 0x198 bytes are serialized virtually (+0x218) into staging, then '
     'written to KBox 0x0D66012C.'),
    ('7000e5d8c0', 'PA9::LCG (0x41C64E6D / 0x6073)', 'party-pokemon', 'proven', f'{RV}:204-205',
     'Pokemon-crypto LCG step (main_398.c:26515); 325 callers in main_397/main_398, in pairs (decrypt before, encrypt after each field access).'),
    ('7000e5d940', 'PA9::LCG2 (0x41C64E6D / 0x6073)', 'party-pokemon', 'proven', f'{RV}:204', 'Second LCG function (main_398.c:26554).'),
    ('7000e48a40', 'PA9::DecryptCore', 'party-pokemon', 'proven', f'{RV}:206-207',
     'Locks +0x1c..0x1f and decrypts the core (0x140 bytes from +8, seed = EC) and the calc block (0x10 bytes) (main_398.c:1775). '
     'Store layout: [+0x8] calc, [+0x10] core (EC at 0, checksum at 6 over [8,0x148)), +0x18 encrypted flag.'),

    # ------------------------------------------------------------------ Player status
    ('7000ba1c44', 'MyStatus::Load (KMyStatus -> this+0x40, 0x78 bytes)', 'player-status', 'proven', f'{RV}:108',
     'Loads KMyStatus 0xE3E89BD1 as {ptr=this+0x40, size=0x78} (main_338.c:4902). PKHeX MyStatus9a: OT at 0x10, '
     'MegaGaugePercent float at 0x68 (=> runtime status+0xA8, derived), HP u32 at 0x70.'),

    # ------------------------------------------------------------------ Spawn / capture (randomizer cheat hooks)
    ('7000656f80', 'Spawn::FixInitSpec', 'spawn-encounters', 'proven', f'{PC}:21-30',
     'Spawn spec initialisation (main_209.c). The randomizer SHINY cheat wraps it: spec+0x28 = extra shiny rolls, '
     'spec+0x18 = TID, spec+0x20 = PID (' + CH + ':55-65).'),
    ('7000447400', 'Capture::ScoreFormula', 'battle-capture', 'proven', f'{RV}:195',
     'Capture formula (uses 2.5f + 1.5f), main_145.c; the CAPTURE cheat hook sits at label L_7000447554 after the '
     'target eligibility check, before the score/roll (' + PC + ':14-18).'),
    ('7000447554', 'site:Capture::after-eligibility', 'battle-capture', 'proven', f'{PC}:14-18',
     'Label in main_145.c after the target\'s virtual eligibility check; za_cheat_capture_score(v8, x19) is inserted here.'),

    # ------------------------------------------------------------------ Frame timing (dynamic-timing research)
    ('7001b2921c', 'FrameClock::Tick', 'frame-timing', 'proven', f'{DT}:130-134',
     'Virtual tick of the frame clock (main_660.c:5232; in vtables 0x7003be53d0 and 0x7003c19dd0). Reads the first '
     'holder slot duration (this+0x258), passes float seconds to f_7001d4a2a4 / f_7001d698a0, picks the frame cost '
     '(max of gfx+0x138 GPU timestamp delta via f_70017fb654 and [gfx+0x70]+0x118), calls f_7001b29660, pushes '
     '{holder,0,1} to f_7001b53f20 (61-step history) and f_7001cf5680, increments the frame counter at this+0x278.'),
    ('7001b29660', 'FrameClock::ApplyFrameMode', 'frame-timing', 'proven', f'{DT}:135-140',
     'main_660.c:5543. Classifies the frame cost (<=16.67ms 0, <=33.33 1, <=50 2, <=66.67 3, else 4), reads the config '
     'object [clock+0x40]: +0x20 configured mode (int8; 1 = 30 FPS on Switch 1), +0x21 variable-step flag; sends the '
     'mode to graphics via f_70017fafd4(gfx, w20); loops the holder slots calling SetFrameMode(i, mode) or '
     'SetDuration(i, 0) for paused slots (f_7001ce6d10). Hook sites: main+0x1b296d8 (H1, static-60 of r13/r16 and '
     'dynamic H1), main+0x1b296f0 (H2 present mode); anchor label L_7001b296d4.'),
    ('7001b296d4', 'site:FrameClock::ApplyFrameMode::read-config', 'frame-timing', 'proven', f'{FH}:27-31',
     'Label before the LD64 [x19+0x40] / LDRSB [x9+0x20] that reads the configured frame mode; prepare-fps-hook.py '
     '(r13/r16 za_title_frame_cfg) and prepare-dynamic-hooks.py H1 replace the statement after it.'),
    ('70017fafd4', 'Gfx::SetFrameMode (gfx+0x140 = w1)', 'frame-timing', 'proven', f'{DT}:138',
     'Stores the frame mode in the graphics object at +0x140; the present interval becomes +0x140 + 1.'),
    ('70017fb5e0', 'Gfx::ApplyPresentInterval', 'render-nvn', 'proven', f'{DT}:138',
     'main_589.c:24546: calls SetPresentInterval(+0x140 + 1); the klog line "SetPresentInterval 1 (lr 70017fb630)" comes from here.'),
    ('70017fb654', 'Gfx::GpuTimestampDelta (gfx+0x138)', 'frame-timing', 'proven', f'{DT}:132', 'GPU timestamp difference used as one of the two frame-cost candidates.'),
    ('7001d4a2a4', 'FrameClock::DeltaConsumer1', 'frame-timing', 'derived', f'{DT}:131', 'Receives the frame step as float seconds from FrameClock::Tick.'),
    ('7001d698a0', 'FrameClock::DeltaConsumer2', 'frame-timing', 'derived', f'{DT}:131', 'Receives the frame step as float seconds from FrameClock::Tick.'),
    ('7001b53f20', 'FrameHistory::Push (61 steps)', 'frame-timing', 'proven', f'{DT}:133', 'Receives the time context {holder, 0, 1}; keeps a 61-step history.'),
    ('7001cf5680', 'FrameClock::TimeContextSink', 'frame-timing', 'derived', f'{DT}:133', 'Second receiver of the time context {holder, 0, 1}.'),
    ('7001ce6d10', 'UpdateGroup::IsPaused(bit)', 'frame-timing', 'derived', f'{DT}:140', 'Pause bit test for holder slots with index >= 2; paused slots get SetDuration(i, 0).'),
    ('7001b2a0d8', 'UpdateHolder2::GetEntry', 'frame-timing', 'proven', f'{DT}:145', 'Holder with 2 slots (frame clock), vtable 0x7003c1a138, main_660.c:6370-6398.'),
    ('7001b2a0e4', 'UpdateHolder2::SetFrameMode', 'frame-timing', 'proven', f'{DT}:145,155',
     'ns = table[mode] (ldr x2,[x8,w2,sxtw #3] at main+0x1b2a0ec, main_660.c:6382), then SetDuration(i, ns). Dynamic timing hook H3.'),
    ('7001b2a0fc', 'UpdateHolder2::SetDuration', 'frame-timing', 'proven', f'{DT}:145', 'Stores the slot duration in integer ns.'),
    ('7001b2a108', 'UpdateHolder2::GetCount (=2)', 'frame-timing', 'proven', f'{DT}:145', 'Returns 2.'),
    ('7001b54048', 'UpdateHolderVector::GetEntry', 'frame-timing', 'proven', f'{DT}:146', 'Vector holder, vtable 0x7003c1cbf8, main_665.c:1316.'),
    ('7001b5407c', 'UpdateHolderVector::SetFrameMode', 'frame-timing', 'proven', f'{DT}:146,156', 'Table read at main+0x1b54084 (main_665.c:1321). Dynamic timing hook H4.'),
    ('7001b54054', 'UpdateHolderVector::SetDuration', 'frame-timing', 'proven', f'{DT}:146', 'Stores the slot duration.'),
    ('70029f4208', 'UpdateHolder11::GetEntry', 'frame-timing', 'proven', f'{DT}:147', 'Holder with 11 slots, vtable 0x7003d84a40, main_1049.c:13328; created in main_339.c:12659 (object at +0x2a8).'),
    ('70029f4214', 'UpdateHolder11::SetFrameMode', 'frame-timing', 'proven', f'{DT}:147,157', 'Table read at main+0x29f421c (main_1049.c:13333). Dynamic timing hook H5.'),
    ('70029f422c', 'UpdateHolder11::SetDuration', 'frame-timing', 'proven', f'{DT}:147', 'Stores the slot duration.'),
    ('7001015260', 'Anim::PlayRate (global mode)', 'anim', 'proven', f'{DT}:158',
     'main_467.c:7938: rate = (double)step_slot0 / (double)(table[mode] - 1), mode from main+0x61316c8; result goes to '
     'f_7000ffcf74 per element and to f_7001015400. Table read at main+0x101537c (optional hook H6).'),
    ('70010273f0', 'Anim::PlayRate (this+0x48 mode)', 'anim', 'proven', f'{DT}:159',
     'main_468.c:1212: same formula with the mode from this+0x48; the table address comes from the GOT (+0x978). Optional hook H7.'),
    ('7000ffcf74', 'Anim::ApplyRatePerElement', 'anim', 'derived', f'{DT}:158', 'Receives the animation play rate for each element.'),
    ('7001015400', 'Anim::ApplyRate', 'anim', 'derived', f'{DT}:158', 'Receives the animation play rate after the per-element loop.'),
    ('7000112e74', 'DRS::Controller', 'drs-gpu-budget', 'proven', f'{DT}:160-161',
     'Dynamic resolution (3DBufferWidthScale / 3DBufferHeightScale), main_039.c:1108 and :1368: budget = table[cost class], '
     'thresholds 0.95 / 0.80, 7 levels (1.0 .. 0.55).'),
    ('7001b2e294', 'GpuBudget::Controller2', 'drs-gpu-budget', 'proven', f'{DT}:162',
     'main_660.c:11755: averages every 5 frames (umulh by 0xcccc...cccd, divide by 5.0), steps down after 30; mode index at this+8.'),
    ('7003393e20', 'data:FrameDurationTableNs[5]', 'frame-timing', 'proven', f'{DT}:14,59',
     'rodata table main+0x3393e20: 16,666,667 / 33,333,334 / 50,000,000 / 66,666,667 / 83,333,334 ns (modes 0-4). Read at 8 '
     'sites in 7 functions (SetFrameMode x3, Anim::PlayRate x2, DRS x2 sites, GpuBudget). GOT entry 0x7003ec6978.'),
    ('7003ec6978', 'got:FrameDurationTable', 'frame-timing', 'proven', f'{DT}:151', 'GOT entry pointing at the frame-duration table (used by f_70010273f0 and f_7001b2e294).'),
    ('70012789f0', 'Callback::ParseGlobalBlurRadius', 'render-nvn', 'proven', f'{DT}:198-201',
     'main_521.c:6721: loads the strings "Global" (0x70032281ca) and "BlurRadius" (0x700328b74e) and hashes with FNV-1a '
     '(0xcbf29ce484222645); one of four callbacks built as a table in f_7001270dd0 (main_520.c:1958-1966). The Dynamic60 '
     'RC3 mod empties it to use its body as a code cave; not touched by the port.'),
    ('7001270dd0', 'Callback::BuildParamCallbackTable', 'render-nvn', 'proven', f'{DT}:200', 'Builds the 4-entry callback table that includes f_70012789f0 (main_520.c:1958-1966).'),
    ('70032281ca', 'string:Global', 'render-nvn', 'proven', f'{DT}:199', 'rodata string used by f_70012789f0.'),
    ('700328b74e', 'string:BlurRadius', 'render-nvn', 'proven', f'{DT}:199', 'rodata string used by f_70012789f0.'),
    ('700610b900', 'global:LockedHashMapSingleton (RC3 "flag" owner)', 'frame-timing', 'proven', f'{DT}:181-186',
     'BSS singleton main+0x610b900 with guard at +0x100, vptr 0x7003d2dde0, spin lock at +0x50 (0x5f = free), buckets at '
     '+0x58, second map at +0x90, element count (u64) at +0x80. The Dynamic60 RC3 "flag" main+0x610b980 is the low byte of '
     'that count ("list not empty"). What the list holds is not proven (assumed: active actions/effects).'),
    ('7003d2dde0', 'vtable:LockedHashMapSingleton', 'frame-timing', 'proven', f'{DT}:182', 'vptr of the singleton at main+0x610b900.'),
    ('7000770c5c', 'LockedHashMapSingleton::Construct', 'frame-timing', 'proven', f'{DT}:183', 'main_244.c:27435 builds the singleton at main+0x610b900.'),
    ('700077067c', 'LockedHashMapSingleton::Register', 'frame-timing', 'proven', f'{DT}:183', 'main_244.c:26964 registers the singleton.'),
    ('70028f5a1c', 'LockedHashMapSingleton::Destroy', 'frame-timing', 'proven', f'{DT}:183', 'main_1030.c:7077 destroys the singleton.'),
    ('70001db070', 'LockedHashMap::Erase', 'frame-timing', 'proven', f'{DT}:185', 'main_061.c:19607: element deletion does [this+0x80] -= 1 (lines 20306-20308), proving +0x80 is the element count.'),
    ('70061316c8', 'global:AnimFrameMode?', 'anim', 'assumed', f'{DT}:158,490', 'Global read by Anim::PlayRate f_7001015260 as the mode index; whether it is the frame mode is an open question.'),
    ('7003160900', 'plt:nn::os::GetSystemTick', 'frame-timing', 'proven', f'{DT}:84', 'PLT stub main+0x3160900 -> GOT 0x7003ee8180 = nn::os::GetSystemTick (relocation 67, JUMP_SLOT); maps to rt_ticks() (19.2 MHz) in the port.'),
    ('7003ee8180', 'got:nn::os::GetSystemTick', 'frame-timing', 'proven', f'{DT}:84', 'GOT slot of nn::os::GetSystemTick.'),
    ('7003be53d0', 'vtable:FrameClockA', 'frame-timing', 'proven', f'{DT}:130', 'First vtable containing FrameClock::Tick f_7001b2921c.'),
    ('7003c19dd0', 'vtable:FrameClockB', 'frame-timing', 'proven', f'{DT}:130', 'Second vtable containing FrameClock::Tick f_7001b2921c.'),
    ('7003c1a138', 'vtable:UpdateHolder2', 'frame-timing', 'proven', f'{DT}:145', 'GetEntry f_7001b2a0d8, SetFrameMode f_7001b2a0e4, SetDuration f_7001b2a0fc, GetCount f_7001b2a108.'),
    ('7003c1cbf8', 'vtable:UpdateHolderVector', 'frame-timing', 'proven', f'{DT}:146', 'GetEntry f_7001b54048, SetFrameMode f_7001b5407c, SetDuration f_7001b54054.'),
    ('7003d84a40', 'vtable:UpdateHolder11', 'frame-timing', 'proven', f'{DT}:147', 'GetEntry f_70029f4208, SetFrameMode f_70029f4214, SetDuration f_70029f422c.'),

    # ------------------------------------------------------------------ SDK (libgui present path, not used by the port's HLE NVN)
    ('7008197a30', 'sdk:libgui Surface::queueBuffer', 'render-nvn', 'derived', f'{DT}:167-175',
     'sdk_035.c:10705: locks +0xf38, finds one of 64 slots (0x38 wide) by buffer, builds QueueBufferInput {timestamp(+0xee8), '
     'isAuto, crop[4], scaling(+0xf00), transform(+0xf04), sticky(+0xf08|8), 0, swapInterval(+0xf24), fence}, calls '
     '[+0xd0]->vtbl[10], writes back +0xf0c/+0xf10 and +0xf28. The Dynamic60 RC3 SDK patch forces +0xf24 = 1. In the port '
     'NVN is HLE and this never runs for presentation (expected count 0 in fnprof).'),
    ('7008197690', 'sdk:libgui Surface::setSwapInterval', 'render-nvn', 'derived', f'{DT}:174', 'sdk_035.c:10435: clamps to [+0x4c, +0x50] (min/maxSwapInterval) and writes +0xf24.'),
    ('7008196d3c', 'sdk:libgui Surface::ctor', 'render-nvn', 'derived', f'{DT}:174', 'Initialises +0xf24 (swap interval) to 1 (sdk_035.c:10000, 10034).'),

    # ------------------------------------------------------------------ Render thread (profile r24prof)
    ('7001810220', 'RenderThread::HotGiant1 (NVN command building)', 'render-thread', 'derived', f'{HA}:60,123',
     'main_591, compiled at -O0 (giant); leads the game-code share (17.8%) of the render thread in the r24prof profile: '
     'building NVN commands on the submitting game thread.'),
    ('7001835250', 'RenderThread::HotGiant2', 'render-thread', 'derived', f'{HA}:123', 'main_594, -O0 giant, hot on the render thread in the r24prof profile.'),
    ('7001b517f8', 'RenderThread::HotGiant3', 'render-thread', 'derived', f'{HA}:123', 'main_664, -O0 giant, hot on the render thread in the r24prof profile.'),

    # ------------------------------------------------------------------ Text / GFMSG
    ('7001035170', 'GFMSG::DecodeLine', 'text-gfmsg', 'proven', f'{HT}:45',
     'main_468.c: decodes a .dat message line: XOR key 0x7C89 + i*0x2983, key = rol16(key, 3) after every UTF-16 unit; '
     'also has a path for unencrypted lines. Format: header u16 sections=1, u16 lines, u32 total, u32 initialKey, u32 '
     'sectionOffset=0x10; rows (u32 offset, u16 length, u16 flags).'),

    # ------------------------------------------------------------------ FlatBuffers tables / species
    ('7000e380c0', 'Personal::BuildPersonalArrayPath', 'flatbuffers-tables', 'proven', f'{NS}:326',
     'main_397.c: builds the personal_array.bin path; 5 of the 12 species-id guard checks (u16 > 0x3f2 / >= 0x3f3, i.e. '
     'the 1010 species limit) sit in the same address area (0x7000e3.. - 0x7000e4..). Other guards: main_1003, main_1055, '
     'main_130 (x2), main_160, main_167 (x2); loops to 1010/1011 in main_211, main_292, main_356; one unclassified in main_1058.'),

    # ------------------------------------------------------------------ Build facts (giant functions)
    ('7001aa18a0', 'giant:main_655 (8,593 labels)', 'build-giants', 'proven', f'{CG}:202',
     'The largest single-function unit, main_655.c (1,058,439 bytes of C): clang -O1 needs 631 s on it, so the giant '
     'policy (>1000 labels) compiles it at -O0.'),
]

# Runtime memory map and NSO segment layout: guest address ranges, not code references (kind region).
REGIONS = [
    ('7000000000', 'region:MAIN_BASE', 'runtime-memory-map', 'proven', f'{RP}:105', 'NSO main loaded here (text/ro/data as RW, not exec); main is about 0x5f7c000 bytes.'),
    ('7008000000', 'region:SDK_BASE', 'runtime-memory-map', 'proven', f'{RP}:106', 'NSO sdk loaded here (0xc60000 bytes).'),
    ('7080000000', 'region:HLE_BASE', 'runtime-memory-map', 'proven', f'{RP}:107', '1 MB of fake addresses for host HLE functions (16 bytes per stub, dispatch.c:14-57); never executed as code.'),
    ('7090000000', 'region:TLS_BASE', 'runtime-memory-map', 'proven', f'{RP}:108', '1 MB; 0x200 per guest thread (kernel.c:292-294).'),
    ('7092000000', 'region:HLE_HEAP', 'runtime-memory-map', 'proven', f'{RP}:109', '224 MB bump allocator hle_alloc (dispatch.c:93-106).'),
    ('7200000000', 'region:STACK_BASE', 'runtime-memory-map', 'proven', f'{RP}:110', '1 GB of guest stacks (kernel.c:312-318, svcMapMemory).'),
    ('7240000000', 'region:HEAP_BASE', 'runtime-memory-map', 'proven', f'{RP}:111', 'svcSetHeapSize heap (HEAP_MAX 3.25 GB); Z-A does not use it (heap 0).'),
    ('7400000000', 'region:ALIAS_BASE', 'runtime-memory-map', 'proven', f'{RP}:112', '16 GB alias region up to GUEST_HI 0x7800000000 (svcMapPhysicalMemory).'),
    ('7676b00000', 'region:GuestPhysicalWindow', 'runtime-memory-map', 'proven', f'{RP}:114', 'The one large physical mapping of Z-A: 0x7676b00000 + 0xc9500000 (3,221 MB) in the alias region; the renderer imports it as a VkBuffer (r5/r9 pin).'),
    ('7003164000', 'region:main.rodata', 'runtime-memory-map', 'proven', f'{DT}:59', 'main segments (2.0.2): text 0..0x3163f70, rodata 0x3164000..0x3bc2000, data 0x3bc2000..0x3f7e430, BSS 0x3f7e440..0x617a608.'),
    ('7003bc2000', 'region:main.data', 'runtime-memory-map', 'proven', f'{DT}:59', 'main .data 0x3bc2000..0x3f7e430 (2.0.2).'),
    ('7003f7e440', 'region:main.bss', 'runtime-memory-map', 'proven', f'{DT}:59', 'main BSS 0x3f7e440..0x617a608 (2.0.2).'),
]

# Block keys whose research established an area; everything else is reported as save-blocks only.
KEY_AREA = {
    'KMoney': 'money', 'KItem': 'bag-items', 'KFusedCalyrex': 'bag-items', 'KLostBalls': 'bag-items',
    'KParty': 'party-pokemon', 'KBox': 'party-pokemon', 'KBoxWallpapers': 'party-pokemon',
    'KPokedex': 'pokedex', 'KTaskWorkCatchSpecies': 'pokedex',
    'KMyStatus': 'player-status', 'KPlayTime': 'player-status', 'KLastSaved': 'player-status',
    'KEnrollmentDate': 'player-status', 'KConfig': 'player-status', 'KCoordinates': 'player-status',
    'KNPLNUserID': 'player-status', 'KStreetName': 'player-status', 'KTimeSecondsPastMidnight': 'player-status',
    'KEventWorkSpawn': 'spawn-encounters', 'KEventSpawner2': 'spawn-encounters', 'KEventSpawner4': 'spawn-encounters',
    'KStoredShinyEntity': 'spawn-encounters', 'KStoredEventEntity': 'spawn-encounters',
    'KEventCountMable': 'missions-conditions', 'KStatusMable': 'missions-conditions', 'KEventReport': 'missions-conditions',
    'KEventCountTitle': 'missions-conditions', 'KEventInfiniteRank': 'battle-royale',
    'KInfiniteRoyale': 'battle-royale', 'KNightRoyaleBonusCards': 'battle-royale',
    'KNightRoyalePostBattleRewards': 'battle-royale', 'KNightRoyaleTrainerStatus': 'battle-royale',
    'KRogueSimulatorRecords': 'battle-royale',
    'KDonuts': 'hyperspace-dlc', 'KDonutDistortionInUse': 'hyperspace-dlc', 'KHyperspaceZones': 'hyperspace-dlc',
    'KOverworld': 'overworld', 'KFieldObjectInteractable': 'overworld',
    'KMysteryGiftRecords': 'mystery-gift',
}
