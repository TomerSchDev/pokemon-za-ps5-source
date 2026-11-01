// za-skip-save: build the "start at chapter 4" save of a randomizer run (PKHeX.Core, host only).
//
//   build   SAVE SPEC.json NEWDIR             apply the chapter-4 spec to a COPY of SAVE -> NEWDIR/save_0/main
//   deltas  CITY STARTERS.json SPEC.json OUT.json [--only N]
//                                             for every starter of starter-deltas.json: city + starter patches ->
//                                             build -> byte diff; writes chapter4-deltas.json (common + per-starter
//                                             patches on the encrypted file, output SHA-256 per starter) and
//                                             re-applies every patch set to prove it reproduces the build
//   inspect SAVE [NAMES.txt]                  phase, Royale rank block, ticket points, money, party, bag summary
//
// SPEC (game-derived, made by make_spec.py, never in git):
//   { "schema": 1, "format": "za-chapter4-spec-v1", "target_phase": 40100,
//     "ops": ["flag:NAME=1", "sysflag:NAME=0", "work:NAME=N", "quest:NAME=N", ...],
//     "raw": [{"block": "1866780C", "offset": 0, "u32": 5}, ...],
//     "money": 30000, "items": [{"id": 4, "count": 30}, ...],
//     "starter_level": 30, "gifts": [{"species": 359, "level": 30}] }
// Inputs are never modified (re-read and compared at the end); outputs must not exist yet.
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using PKHeX.Core;

static class P {
    static string Sha(ReadOnlySpan<byte> b) => Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();

    static SAV9ZA Open(byte[] raw) {
        if (!SwishCrypto.GetIsHashValid(raw)) throw new InvalidDataException("save checksum");
        if (SaveUtil.GetSaveFile(raw.ToArray()) is not SAV9ZA s) throw new InvalidDataException("not a Z-A main save");
        return s;
    }

    static int Main(string[] a) {
        try {
            return a.Length switch {
                >= 4 when a[0] == "build" => Build(a[1], a[2], a[3]),
                >= 5 when a[0] == "deltas" => Deltas(a[1], a[2], a[3], a[4], a.Length > 6 && a[5] == "--only" ? int.Parse(a[6]) : 0),
                >= 2 when a[0] == "inspect" => Inspect(a[1], a.Length > 2 ? a[2] : null),
                _ => Usage(),
            };
        } catch (Exception e) {
            Console.Error.WriteLine("error: " + e.Message);
            return 1;
        }
    }

    static int Usage() {
        Console.Error.WriteLine("usage: build SAVE SPEC NEWDIR | deltas CITY STARTERS SPEC OUT [--only N] | inspect SAVE [NAMES]");
        return 2;
    }

    // ------------------------------------------------------------------ the chapter-4 edit of one save
    static byte[] Apply(byte[] input, JsonNode spec, List<string> log) {
        if ((int?)spec["schema"] != 1 || (string?)spec["format"] != "za-chapter4-spec-v1") throw new InvalidDataException("spec format");
        var s = Open(input);
        var b = s.Blocks;
        foreach (var node in spec["ops"]!.AsArray()) {
            var op = (string)node!;
            int c = op.IndexOf(':'), e = op.IndexOf('=');
            if (c < 0 || e < c) throw new ArgumentException(op);
            string kind = op[..c], name = op[(c + 1)..e], val = op[(e + 1)..];
            switch (kind) {
                case "flag": PutF(b.Event, name, val == "1"); break;
                case "sysflag": PutF(b.Flags, name, val == "1"); break;
                case "work": PutV(b.Work, name, ulong.Parse(val)); break;
                case "quest": PutV(b.Quest, name, ulong.Parse(val)); break;
                default: throw new ArgumentException(op);
            }
        }
        log.Add($"story ops {spec["ops"]!.AsArray().Count} (phase {spec["target_phase"]})");
        foreach (var r in spec["raw"]?.AsArray() ?? []) {
            var key = Convert.ToUInt32((string)r!["block"]!, 16);
            var blk = s.AllBlocks.Single(x => x.Key == key);
            int off = (int)r["offset"]!;
            uint v = (uint)r["u32"]!;
            if (off < 0 || off + 4 > blk.Data.Length) throw new InvalidDataException($"raw {key:X8}+{off:X} out of range");
            uint was = BitConverter.ToUInt32(blk.Data.Slice(off, 4));
            BitConverter.TryWriteBytes(blk.Data.Slice(off, 4), v);
            log.Add($"raw {key:X8}+0x{off:X}: {was} -> {v}");
        }
        if (spec["money"] is JsonNode m) { log.Add($"money {s.Money} -> {(uint)m}"); s.Money = (uint)m; }
        if (spec["items"] is JsonArray items && items.Count > 0) {
            var bag = (PlayerBag9a)s.Inventory;
            var pouches = bag.Pouches;
            foreach (var it in items) {
                int id = (int)it!["id"]!, count = (int)it["count"]!;
                var slot = pouches.SelectMany(p => p.Items).FirstOrDefault(x => x.Index == id)
                           ?? throw new InvalidDataException($"item {id} has no slot in any pouch");
                if (slot.Count < count) slot.Count = count;
                log.Add($"item {id} -> {slot.Count}");
            }
            bag.CopyTo(s);
        }
        if (spec["starter_level"] is JsonNode lv) {
            byte level = (byte)(int)lv;
            if (s.PartyCount < 1) throw new InvalidDataException("no starter in the party");
            var pk = s.GetPartySlotAtIndex(0);
            byte was = pk.CurrentLevel;
            if (level > was) {
                pk.CurrentLevel = level;
                SetLevelMoves(pk, level);
                pk.ResetPartyStats();
                pk.Heal();
                pk.RefreshChecksum();
                s.SetPartySlotAtIndex(pk, 0, EntityImportSettings.None);
            }
            log.Add($"starter {pk.Species}: level {was} -> {pk.CurrentLevel}, moves {string.Join(",", pk.Moves)}");
        }
        foreach (var g in spec["gifts"]?.AsArray() ?? []) {
            ushort species = (ushort)(int)g!["species"]!;
            byte level = (byte)(int)g["level"]!;
            var enc = Gifts().Single(x => x.Species == species && x.Level == level);
            // One gift per process: every starter of a deltas build gets the same Absol (same PID/IVs), so the
            // gift lands in the common patches instead of 343 random copies.
            var key = (species, level, s.ID32, s.OT);
            if (!GiftCache.TryGetValue(key, out var cached)) GiftCache[key] = cached = enc.ConvertToPKM(s);
            var pk = (PA9)cached.Clone();
            pk.Heal();
            pk.RefreshChecksum();
            int slot = s.PartyCount;
            if (slot >= 6) throw new InvalidDataException("party full");
            s.SetPartySlotAtIndex(pk, slot, EntityImportSettings.None);
            s.Zukan.SetDex(pk);
            log.Add($"gift {species} level {pk.CurrentLevel} -> party slot {slot}, moves {string.Join(",", pk.Moves)}");
        }
        var output = s.Write().ToArray();
        if (!SwishCrypto.GetIsHashValid(output) || output.Length != input.Length) throw new InvalidDataException("output checksum/size");
        _ = Open(output);
        return output;
    }

    // Last four level-up moves learned at or below `level` (the game's own wild/gift rule).
    static void SetLevelMoves(PKM pk, byte level) {
        var src = new LearnSource9ZA();
        var learn = src.GetLearnset(pk.Species, pk.Form);
        var moves = learn.GetBaseEggMoves(level).ToArray();
        if (moves.Length == 0) return;
        Span<ushort> four = stackalloc ushort[4];
        moves.AsSpan(Math.Max(0, moves.Length - 4)).CopyTo(four);
        pk.SetMoves(four);
        pk.HealPP();
    }

    static readonly Dictionary<(ushort, byte, uint, string), PA9> GiftCache = new();

    static IEnumerable<EncounterGift9a> Gifts() {
        var t = typeof(SAV9ZA).Assembly.GetTypes().Single(x => x.Name == "Encounters9a");
        return (EncounterGift9a[])t.GetField("Gifts", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;
    }

    // PKHeX 9ZA SetValue(key, v) only ensures the key exists and does not write the value: write it by index.
    static void PutF(EventWorkFlagStorage st, string name, bool v) {
        var h = FnvHash.HashFnv1a_64(name); st.SetValue(h, v); var i = st.GetIndex(h); st.SetValue(i, v);
        if (st.GetValue(i) != v) throw new InvalidDataException("readback " + name);
    }
    static void PutV(EventWorkValueStorage st, string name, ulong v) {
        var h = FnvHash.HashFnv1a_64(name); st.SetValue(h, v); var i = st.GetIndex(h); st.SetValue(i, v);
        if (st.GetValue(i) != v) throw new InvalidDataException("readback " + name);
    }

    static JsonNode ReadSpec(string path) => JsonNode.Parse(File.ReadAllText(path)) ?? throw new InvalidDataException("spec");

    // ------------------------------------------------------------------ build
    static int Build(string savePath, string specPath, string outDir) {
        outDir = Path.GetFullPath(outDir);
        if (Directory.Exists(outDir) || File.Exists(outDir)) throw new IOException("output folder exists; use a new one");
        var raw = File.ReadAllBytes(savePath);
        var log = new List<string>();
        var output = Apply(raw, ReadSpec(specPath), log);
        var d = Path.Combine(outDir, "save_0");
        Directory.CreateDirectory(d);
        File.WriteAllBytes(Path.Combine(d, "main"), output);
        _ = Open(File.ReadAllBytes(Path.Combine(d, "main")));
        if (Sha(File.ReadAllBytes(savePath)) != Sha(raw)) throw new IOException("input changed");
        File.WriteAllLines(Path.Combine(outDir, "ops.log"), log.Prepend($"source {Sha(raw)}").Append($"output {Sha(output)}"));
        foreach (var l in log) Console.WriteLine(l);
        Console.WriteLine($"wrote {outDir}");
        return 0;
    }

    // ------------------------------------------------------------------ deltas
    record Patch(int Offset, string Hex);

    static List<Patch> Diff(byte[] a, byte[] b) {
        var list = new List<Patch>();
        for (int i = 0; i < a.Length;) {
            if (a[i] == b[i]) { i++; continue; }
            int j = i;
            while (j < a.Length && (a[j] != b[j] || (j + 1 < a.Length && a[j + 1] != b[j + 1]))) j++;  // join gaps of one byte
            list.Add(new Patch(i, Convert.ToHexString(b, i, j - i).ToLowerInvariant()));
            i = j;
        }
        return list;
    }

    static void ApplyPatches(byte[] d, IEnumerable<Patch> ps) {
        int previous = 0;
        foreach (var p in ps) {
            var bytes = Convert.FromHexString(p.Hex);
            if (p.Offset < previous || p.Offset + bytes.Length > d.Length) throw new InvalidDataException("patch range");
            bytes.CopyTo(d, p.Offset);
            previous = p.Offset + bytes.Length;
        }
    }

    static int Deltas(string cityPath, string startersPath, string specPath, string outPath, int only) {
        if (File.Exists(outPath)) throw new IOException("output exists; use a new name");
        var city = File.ReadAllBytes(cityPath);
        var starters = JsonNode.Parse(File.ReadAllText(startersPath))!;
        if ((string?)starters["format"] != "za-city-starter-deltas-v1" || (string?)starters["template_sha256"] != Sha(city))
            throw new InvalidDataException("starter-deltas does not belong to this city template");
        var spec = ReadSpec(specPath);
        var entries = starters["entries"]!.AsArray().Take(only > 0 ? only : int.MaxValue).ToList();
        var built = new List<(int species, byte[] start, byte[] ch4)>();
        string? firstLog = null;
        foreach (var e in entries) {
            var save = (byte[])city.Clone();
            ApplyPatches(save, e!["patches"]!.AsArray().Select(p => new Patch((int)p!["offset"]!, (string)p["hex"]!)));
            if (Sha(save) != (string)e["output_sha256"]!) throw new InvalidDataException($"starter {e["species"]} integrity");
            var log = new List<string>();
            var ch4 = Apply(save, spec, log);
            firstLog ??= string.Join("\n", log);
            built.Add(((int)e["species"]!, save, ch4));
        }
        // common bytes: same offset and same new value for every starter (and changed from the starter save)
        int n = city.Length;
        var common = new bool[n];
        for (int i = 0; i < n; i++) {
            bool all = true;
            byte v = built[0].ch4[i];
            foreach (var x in built) if (x.ch4[i] != v || x.start[i] == v) { all = false; break; }
            common[i] = all;
        }
        // Common patches are exact runs of common bytes (never joined across a byte that differs per starter).
        var commonPatches = Runs(common, built[0].ch4);
        var outEntries = new JsonArray();
        long perBytes = 0;
        foreach (var (species, start, ch4) in built) {
            var mid = (byte[])start.Clone();
            ApplyPatches(mid, commonPatches);
            var own = Diff(mid, ch4);
            var check = (byte[])mid.Clone();
            ApplyPatches(check, own);
            if (Sha(check) != Sha(ch4)) throw new InvalidDataException($"reconstruct {species}");
            perBytes += own.Sum(p => p.Hex.Length / 2);
            outEntries.Add(new JsonObject {
                ["species"] = species,
                ["start_sha256"] = Sha(start),
                ["output_sha256"] = Sha(ch4),
                ["patches"] = new JsonArray(own.Select(p => (JsonNode)new JsonObject { ["offset"] = p.Offset, ["hex"] = p.Hex }).ToArray()),
            });
        }
        var doc = new JsonObject {
            ["schema"] = 1,
            ["format"] = "za-chapter4-start-v1",
            ["game_version"] = "2.0.2",
            ["template_sha256"] = Sha(city),
            ["starter_deltas_sha256"] = Sha(File.ReadAllBytes(startersPath)),
            ["spec_sha256"] = Sha(File.ReadAllBytes(specPath)),
            ["target_phase"] = spec["target_phase"]!.DeepClone(),
            ["starter_level"] = spec["starter_level"]?.DeepClone(),
            ["species_count"] = built.Count,
            ["common_bytes"] = commonPatches.Sum(p => p.Hex.Length / 2),
            ["per_starter_bytes"] = perBytes,
            ["apply_order"] = "city template -> starter patches (verify starter output_sha256) -> common_patches -> entry patches (verify entry output_sha256)",
            ["common_patches"] = new JsonArray(commonPatches.Select(p => (JsonNode)new JsonObject { ["offset"] = p.Offset, ["hex"] = p.Hex }).ToArray()),
            ["entries"] = outEntries,
        };
        File.WriteAllText(outPath, doc.ToJsonString());
        if (Sha(File.ReadAllBytes(cityPath)) != Sha(city)) throw new IOException("input changed");
        Console.WriteLine(firstLog);
        Console.WriteLine($"starters {built.Count} common_bytes {doc["common_bytes"]} per_starter_bytes {perBytes} -> {outPath}");
        return 0;
    }

    static List<Patch> Runs(bool[] mask, byte[] src) {
        var list = new List<Patch>();
        for (int i = 0; i < mask.Length;) {
            if (!mask[i]) { i++; continue; }
            int j = i;
            while (j < mask.Length && mask[j]) j++;
            list.Add(new Patch(i, Convert.ToHexString(src, i, j - i).ToLowerInvariant()));
            i = j;
        }
        return list;
    }

    // ------------------------------------------------------------------ inspect
    static int Inspect(string savePath, string? namesPath) {
        var s = Open(File.ReadAllBytes(savePath));
        var b = s.Blocks;
        var o = new JsonObject {
            ["phase"] = b.Work.TryGetValue("SYS_WORK_PHASE", out var ph) ? (long)ph : -1,
            ["money"] = s.Money,
            ["ticket_points_royale"] = s.TicketPointsRoyale,
            ["royale_block_1866780C"] = Hex(s.AllBlocks.Single(x => x.Key == 0x1866780C).Data[..16]),
            ["block_041137D8"] = Hex(s.AllBlocks.Single(x => x.Key == 0x041137D8).Data),
            ["party"] = new JsonArray(Enumerable.Range(0, s.PartyCount).Select(i => {
                var p = s.GetPartySlotAtIndex(i);
                return (JsonNode)new JsonObject { ["species"] = p.Species, ["level"] = p.CurrentLevel, ["moves"] = string.Join(",", p.Moves), ["ot"] = p.OriginalTrainerName };
            }).ToArray()),
        };
        Console.WriteLine(o.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        return 0;
    }
    static string Hex(ReadOnlySpan<byte> d) => Convert.ToHexString(d);
}
