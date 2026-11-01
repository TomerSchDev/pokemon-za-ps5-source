// Offline verification for the randomizer player-name writer (port/rando-v2/za_player_name.cpp).
// Uses PKHeX.Core (GPL-3.0-or-later). Inputs are copies; nothing is written next to a real save.
//   inspect  SAVE                      trainer data, party/box owners, every UTF-16 copy of the OT name
//   fixtures TEMPLATE OUTDIR           template copy + a mixed save with owned and foreign Pokemon
//   verify   BEFORE AFTER NAME         hash, OT, owned/foreign Pokemon, block-level byte comparison
using PKHeX.Core;
using System.Text;
using System.Text.Json;

const uint KMyStatus = 0xE3E89BD1, KParty = 0x3AA1A9AD, KBox = 0x0d66012c;
const int PartySlot = 0x1E0, BoxSlot = 0x158 + 0x40, PartyData = 0x158;
const int OtOffset = 0xF8, OtLength = 0x1A, MyOt = 0x10;

string Hash(byte[] b) => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(b)).ToLowerInvariant();
SAV9ZA Load(string path)
{
    var raw = File.ReadAllBytes(path);
    if (!SwishCrypto.GetIsHashValid(raw)) throw new InvalidDataException($"{path}: SwishCrypto hash invalid");
    return new SAV9ZA(raw);
}
SCBlock Block(SAV9ZA s, uint key) => s.AllBlocks.Single(b => b.Key == key);
byte[] Decrypted(ReadOnlySpan<byte> slot)
{
    var d = slot[..PartyData].ToArray();
    PokeCrypto.DecryptIfEncrypted8(d);
    return d;
}

switch (args.FirstOrDefault())
{
case "inspect":
{
    var s = Load(args[1]);
    var name = s.OT;
    var report = new Dictionary<string, object>
    {
        ["ot"] = name, ["id32"] = s.ID32.ToString("X8"), ["gender"] = s.Gender, ["language"] = s.Language,
        ["revision"] = s.SaveRevision, ["party_count"] = s.PartyCount, ["money"] = s.Money,
    };
    var party = new List<object>();
    for (int i = 0; i < s.PartyCount; i++)
    {
        var pk = (PA9)s.GetPartySlotAtIndex(i);
        party.Add(new { slot = i, pk.Species, pk.CurrentLevel, ot = pk.OriginalTrainerName, id32 = pk.ID32.ToString("X8"), pk.ChecksumValid });
    }
    report["party"] = party;
    int boxed = 0;
    for (int b = 0; b < s.BoxCount; b++)
        for (int i = 0; i < 30; i++)
            if (s.GetBoxSlotAtIndex(b, i).Species != 0) boxed++;
    report["boxed"] = boxed;
    // Every plain UTF-16 copy of the OT name in any decrypted block (encrypted entities are not plain).
    var needle = Encoding.Unicode.GetBytes(name);
    var hits = new List<object>();
    foreach (var blk in s.AllBlocks)
    {
        var d = blk.Data;
        for (int at = d.IndexOf(needle); at >= 0;)
        {
            hits.Add(new { key = blk.Key.ToString("X8"), offset = at, size = d.Length });
            var next = d[(at + 1)..].IndexOf(needle);
            at = next < 0 ? -1 : at + 1 + next;
        }
    }
    report["plain_name_copies"] = hits;
    Console.WriteLine(JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
    break;
}
case "fixtures":
{
    var raw = File.ReadAllBytes(args[1]);
    Directory.CreateDirectory(args[2]);
    File.WriteAllBytes(Path.Combine(args[2], "plain.bin"), raw);
    var s = Load(args[1]);
    var starter = (PA9)s.GetPartySlotAtIndex(0);
    // Foreign party member: different trainer, different name.
    var foreign = (PA9)starter.Clone();
    foreign.ID32 = starter.ID32 ^ 0x00010001;
    foreign.OriginalTrainerName = "Rival";
    foreign.EncryptionConstant ^= 0x5A5A5A5A; foreign.PID ^= 0x00F00000;
    foreign.RefreshChecksum();
    s.SetPartySlotAtIndex(foreign, 1, EntityImportSettings.None);
    // Same trainer ID but a different OT name (not ours by name) and a true copy (ours), in box 1.
    var sameIdOtherName = (PA9)starter.Clone();
    sameIdOtherName.OriginalTrainerName = "Testy";
    sameIdOtherName.EncryptionConstant ^= 0x13579BDF; sameIdOtherName.RefreshChecksum();
    var ours = (PA9)starter.Clone();
    ours.EncryptionConstant ^= 0x2468ACE0; ours.Species = 25; ours.RefreshChecksum();
    s.SetBoxSlotAtIndex(ours, 0, 0, EntityImportSettings.None);
    s.SetBoxSlotAtIndex(sameIdOtherName, 0, 1, EntityImportSettings.None);
    s.SetBoxSlotAtIndex(foreign, 0, 2, EntityImportSettings.None);
    var mixed = s.Write().ToArray();
    if (!SwishCrypto.GetIsHashValid(mixed)) throw new InvalidDataException("mixed fixture hash");
    File.WriteAllBytes(Path.Combine(args[2], "mixed.bin"), mixed);
    Console.WriteLine(JsonSerializer.Serialize(new { plain = Hash(raw), mixed = Hash(mixed), ot = s.OT,
        owned_expected = 2, foreign_expected = 2 }));
    break;
}
case "verify":
{
    var before = Load(args[1]);
    var after = Load(args[2]);
    var want = args[3];
    var oldName = before.OT;
    var fail = new List<string>();
    if (after.OT != want) fail.Add($"MyStatus OT is '{after.OT}', expected '{want}'");
    if (before.AllBlocks.Count != after.AllBlocks.Count) fail.Add("block count changed");
    int changedBlocks = 0, ownedChanged = 0, foreignKept = 0;
    for (int i = 0; i < before.AllBlocks.Count && i < after.AllBlocks.Count; i++)
    {
        var a = before.AllBlocks[i]; var b = after.AllBlocks[i];
        if (a.Key != b.Key || a.Type != b.Type || a.Data.Length != b.Data.Length) { fail.Add($"layout {a.Key:X8}"); continue; }
        if (a.Data.SequenceEqual(b.Data)) continue;
        changedBlocks++;
        if (a.Key == KMyStatus)
        {
            for (int o = 0; o < a.Data.Length; o++)
                if (a.Data[o] != b.Data[o] && (o < MyOt || o >= MyOt + OtLength)) fail.Add($"MyStatus byte {o:X} changed outside the name");
            continue;
        }
        int slotSize = a.Key == KParty ? PartySlot : a.Key == KBox ? BoxSlot : 0;
        if (slotSize == 0) { fail.Add($"unexpected changed block {a.Key:X8}"); continue; }
        int slots = a.Data.Length / slotSize;
        for (int s = 0; s < slots; s++)
        {
            var ra = a.Data.Slice(s * slotSize, slotSize); var rb = b.Data.Slice(s * slotSize, slotSize);
            if (ra.SequenceEqual(rb))
            {
                if (EntityDetection.IsPresent(ra))
                {
                    var pk = new PA9(Decrypted(ra));
                    if (pk.ID32 == before.ID32 && pk.OriginalTrainerName == oldName && oldName != want)
                        fail.Add($"{a.Key:X8} slot {s}: owned Pokemon was not renamed");
                    else foreignKept++;
                }
                continue;
            }
            if (!ra[PartyData..].SequenceEqual(rb[PartyData..])) fail.Add($"{a.Key:X8} slot {s}: footer/gap changed");
            var da = Decrypted(ra); var db = Decrypted(rb);
            var pa = new PA9(da.ToArray()); var pb = new PA9(db.ToArray());
            if (!(pa.ID32 == before.ID32 && pa.OriginalTrainerName == oldName)) fail.Add($"{a.Key:X8} slot {s}: changed but not owned");
            if (pb.OriginalTrainerName != want) fail.Add($"{a.Key:X8} slot {s}: OT '{pb.OriginalTrainerName}'");
            if (!pb.ChecksumValid) fail.Add($"{a.Key:X8} slot {s}: checksum invalid");
            for (int o = 0; o < PartyData; o++)
                if (da[o] != db[o] && !(o >= OtOffset && o < OtOffset + OtLength) && o is not (6 or 7))
                    fail.Add($"{a.Key:X8} slot {s}: decrypted byte {o:X} changed outside OT/checksum");
            ownedChanged++;
        }
    }
    Console.WriteLine(JsonSerializer.Serialize(new { result = fail.Count == 0 ? "PASS" : "FAIL", name = after.OT, oldName,
        changedBlocks, ownedChanged, foreignKept, failures = fail.Take(20) }));
    Environment.Exit(fail.Count == 0 ? 0 : 1);
    break;
}
default:
    Console.Error.WriteLine("usage: inspect SAVE | fixtures TEMPLATE OUTDIR | verify BEFORE AFTER NAME");
    Environment.Exit(2);
    break;
}
