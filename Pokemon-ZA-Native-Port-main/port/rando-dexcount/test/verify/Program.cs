// Read-only PKHeX inspection of Z-A test saves for the dex-count proof.
//   info SAVE                 -> JSON: story phase, quest work, party, Pokedex caught lists split Lumiose/Hyperspace
//   compare BEFORE AFTER      -> JSON: newly caught species, counts before/after, changed blocks, integrity
// Never writes to a save. Copies of test saves only.
using PKHeX.Core;
using System.Security.Cryptography;
using System.Text.Json;

static SAV9ZA Read(string path) {
    var raw = File.ReadAllBytes(path);
    if (!SwishCrypto.GetIsHashValid(raw)) throw new InvalidDataException("Invalid save hash: " + path);
    return new SAV9ZA(raw);
}
static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
static ulong? Work(EventWorkValueStorage s, string name) => s.TryGetValue(name, out var v) ? v : null;
static bool? Flag(EventWorkFlagStorage s, string name) => s.TryGetValue(name, out var v) ? v : null;

static object Dex(SAV9ZA sav) {
    var pt = sav.Personal;
    var lumiose = new List<object>(); var hyper = new List<object>();
    int lumioseSeen = 0, hyperSeen = 0, lumioseTotal = 0, hyperTotal = 0;
    for (ushort sp = 1; sp <= sav.MaxSpeciesID; sp++) {
        if (!pt.IsSpeciesInGame(sp)) continue;
        var pi = pt[sp, 0];
        if (!pi.IsInDex) continue;
        bool isHyper = pi.IsHyperspaceNative;
        if (isHyper) hyperTotal++; else lumioseTotal++;
        var e = sav.Zukan.GetEntry(sp);
        if (e.IsSeen) { if (isHyper) hyperSeen++; else lumioseSeen++; }
        if (!e.IsCaught) continue;
        var item = new { species = sp, name = SpeciesName.GetSpeciesName(sp, 2), dex = pi.DexIndex };
        (isHyper ? hyper : lumiose).Add(item);
    }
    return new {
        lumiose_total = lumioseTotal, hyperspace_total = hyperTotal,
        lumiose_caught = lumiose.Count, hyperspace_caught = hyper.Count,
        lumiose_seen = lumioseSeen, hyperspace_seen = hyperSeen,
        lumiose = lumiose, hyperspace = hyper,
    };
}

static object Info(string path) {
    var sav = Read(path);
    var b = sav.Blocks;
    var party = Enumerable.Range(0, sav.PartyCount).Select(i => sav.GetPartySlotAtIndex(i)).Select(p => new {
        species = p.Species, name = SpeciesName.GetSpeciesName(p.Species, 2), form = p.Form, level = p.CurrentLevel,
        ball = p.Ball, checksum_valid = p.ChecksumValid,
        hyperspace_native = sav.Personal[p.Species, p.Form].IsHyperspaceNative }).ToArray();
    string[] works = ["SYS_WORK_PHASE", "SYS_WORK_DLC_PHASE"];
    string[] quests = ["SYS_WORK_MAINQUEST_02_01", "SYS_WORK_MAINQUEST_02_02", "SYS_WORK_MAINQUEST_03_01"];
    string[] flags = ["flag_Ev_m02_0134", "flag_Ev_m02_0138", "flag_Ev_m02_0140", "flag_Ev_m02_0141",
                      "flag_Ev_m02_1010", "flag_Ev_m02_1030", "flag_Ev_m02_1040"];
    string[] sysflags = ["flag_pokedex_regist_disable", "FLAG_POKEDEX_ENABLE", "FLAG_MOMIJI_ENABLE", "FLAG_BOX_ENABLE",
                         "FLAG_DLC_DEX_ENABLE", "FLAG_DLC_ANOTHER_DIMENSION_ENABLE", "FLAG_DLC_QUEST_ENABLE",
                         "FLAG_DLC_QUEST_POINT_ENABLE", "FLAG_DLC_DONUTS_ENABLE"];
    return new {
        file = path, sha256 = Hash(path), hash_valid = true, revision = sav.SaveRevision,
        money = sav.Money,
        work = works.ToDictionary(n => n, n => Work(b.Work, n)),
        quest_work = quests.ToDictionary(n => n, n => Work(b.Quest, n)),
        event_flags = flags.ToDictionary(n => n, n => Flag(b.Event, n)),
        system_flags = sysflags.ToDictionary(n => n, n => Flag(b.Flags, n)),
        party, dex = Dex(sav),
    };
}

var opts = new JsonSerializerOptions { WriteIndented = true };
var mode = args.Length > 0 ? args[0] : "";
if (mode == "info") {
    Console.WriteLine(JsonSerializer.Serialize(Info(args[1]), opts));
} else if (mode == "compare") {
    var before = Read(args[1]); var after = Read(args[2]);
    var changed = after.AllBlocks.Where(x => !before.AllBlocks.Single(y => y.Key == x.Key).Data.SequenceEqual(x.Data))
        .Select(x => x.Key.ToString("X8")).ToArray();
    var newly = new List<object>();
    for (ushort sp = 1; sp <= after.MaxSpeciesID; sp++) {
        if (!after.Personal.IsSpeciesInGame(sp)) continue;
        if (after.Zukan.GetEntry(sp).IsCaught && !before.Zukan.GetEntry(sp).IsCaught) {
            var pi = after.Personal[sp, 0];
            newly.Add(new { species = sp, name = SpeciesName.GetSpeciesName(sp, 2), dex = pi.DexIndex,
                            hyperspace_native = pi.IsHyperspaceNative });
        }
    }
    bool party = Enumerable.Range(0, after.PartyCount).All(i => after.GetPartySlotAtIndex(i).ChecksumValid);
    Console.WriteLine(JsonSerializer.Serialize(new {
        before = Info(args[1]), after = Info(args[2]), newly_caught = newly,
        changed_blocks = changed, party_checksums_valid = party }, opts));
} else if (mode == "set-system-flag") {
    // Test fixtures only: SRC is a copy of a test save, DST must be a new file.
    if (File.Exists(args[2])) throw new IOException("Refusing to overwrite: " + args[2]);
    var sav = Read(args[1]);
    var name = args[3]; var value = bool.Parse(args[4]);
    sav.Blocks.Flags.SetValue(name, value);
    File.WriteAllBytes(args[2], sav.Write().ToArray());
    var check = Read(args[2]);
    Console.WriteLine(JsonSerializer.Serialize(new { fixture = args[2], flag = name, value = Flag(check.Blocks.Flags, name),
        source_sha256 = Hash(args[1]), sha256 = Hash(args[2]) }, opts));
} else {
    Console.Error.WriteLine("usage: info SAVE | compare BEFORE AFTER | set-system-flag SRC NEW_DST NAME true|false");
    return 2;
}
return 0;
