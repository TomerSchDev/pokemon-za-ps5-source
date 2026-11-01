// za-story-save: story-state research tool for COPIED Pokemon Legends Z-A saves (PKHeX.Core).
//   dump <save main> <names.txt> [out.json]      phase + every event flag / system flag / system work / quest work,
//                                                named from names.txt (one identifier per line, hashed FNV-1a-64)
//   set  <save main> <NEW out dir> ops...        writes <dir>/save_0/main; ops:
//        flag:NAME=0|1   sysflag:NAME=0|1   work:NAME=N   quest:NAME=N
// The output folder must not exist. The input is re-read at the end and must be unchanged.
using System.Security.Cryptography;
using System.Text.Json;
using PKHeX.Core;

static class P {
    static string Sha(byte[] b) => Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();

    static (byte[] raw, SAV9ZA sav) Open(string path) {
        var raw = File.ReadAllBytes(path);
        if (!SwishCrypto.GetIsHashValid(raw)) throw new InvalidDataException("checksum");
        if (SaveUtil.GetSaveFile(raw.ToArray()) is not SAV9ZA s) throw new InvalidDataException("not a Z-A main save");
        return (raw, s);
    }

    static Dictionary<ulong, string> Names(string path) {
        var d = new Dictionary<ulong, string>();
        foreach (var l in File.ReadAllLines(path)) {
            var n = l.Trim();
            if (n.Length == 0) continue;
            d[FnvHash.HashFnv1a_64(n)] = n;
        }
        return d;
    }

    static int Main(string[] a) {
        if (a.Length < 3) { Console.Error.WriteLine("usage: dump SAVE NAMES [OUT] | set SAVE NEWDIR ops..."); return 2; }
        if (a[0] == "dump") {
            var (raw, s) = Open(a[1]);
            var names = Names(a[2]);
            string N(ulong k) => names.TryGetValue(k, out var n) ? n : k.ToString("X16");
            var b = s.Blocks;
            var o = new Dictionary<string, object> {
                ["sha256"] = Sha(raw),
                ["phase"] = b.Work.TryGetValue("SYS_WORK_PHASE", out var ph) ? ph : -1,
                ["event_flags_true"] = Enumerable.Range(0, b.Event.CountUsed).Where(i => b.Event.GetValue(i)).Select(i => N(b.Event.GetKey(i))).OrderBy(x => x).ToArray(),
                ["system_flags_true"] = Enumerable.Range(0, b.Flags.CountUsed).Where(i => b.Flags.GetValue(i)).Select(i => N(b.Flags.GetKey(i))).OrderBy(x => x).ToArray(),
                ["system_work"] = Enumerable.Range(0, b.Work.CountUsed).ToDictionary(i => N(b.Work.GetKey(i)), i => b.Work.GetValue(i)),
                ["quest_work"] = Enumerable.Range(0, b.Quest.CountUsed).ToDictionary(i => N(b.Quest.GetKey(i)), i => b.Quest.GetValue(i)),
                ["sorted"] = new { ev = Sorted(b.Event.CountUsed, b.Event.GetKey), sys = Sorted(b.Flags.CountUsed, b.Flags.GetKey), work = Sorted(b.Work.CountUsed, b.Work.GetKey), quest = Sorted(b.Quest.CountUsed, b.Quest.GetKey) },
                ["coords"] = new { map = s.Coordinates.Map, x = s.Coordinates.X, h = s.Coordinates.Z, z = s.Coordinates.Y, yaw = s.Coordinates.Rotation },
                ["party"] = Enumerable.Range(0, s.PartyCount).Select(i => { var p = s.GetPartySlotAtIndex(i); return new { species = p.Species, level = p.CurrentLevel }; }).ToArray(),
                ["counts"] = new { ev = b.Event.CountUsed, evcap = b.Event.Count, sys = b.Flags.CountUsed, work = b.Work.CountUsed, quest = b.Quest.CountUsed },
            };
            var js = JsonSerializer.Serialize(o, new JsonSerializerOptions { WriteIndented = true });
            if (a.Length > 3) File.WriteAllText(a[3], js); else Console.WriteLine(js);
            return 0;
        }
        if (a[0] == "block") {  // block <save> <keyHex> <outfile>: raw decrypted block bytes
            var (_, s) = Open(a[1]);
            File.WriteAllBytes(a[3], s.AllBlocks.Single(b => b.Key == Convert.ToUInt32(a[2], 16)).Data.ToArray());
            return 0;
        }
        if (a[0] == "find") {  // find <save> <u32 value>: every block offset holding that value (u32 LE)
            var (_, s) = Open(a[1]);
            if (a[2].StartsWith("name:")) {  // FNV-1a-64 of a name, as u64 / its low u32 (block keys)
                ulong h = FnvHash.HashFnv1a_64(a[2][5..]);
                foreach (var blk in s.AllBlocks) {
                    if (blk.Key == (uint)h) Console.WriteLine($"block key {blk.Key:X8} = low32 of the name hash");
                    var d = blk.Data;
                    for (int i = 0; i + 8 <= d.Length; i++)
                        if (BitConverter.ToUInt64(d.Slice(i, 8)) == h) Console.WriteLine($"{blk.Key:X8} type {blk.Type} len {d.Length} off 0x{i:X} u64 next 0x{(i + 16 <= d.Length ? BitConverter.ToUInt64(d.Slice(i + 8, 8)) : 0):X}");
                }
                return 0;
            }
            uint v = uint.Parse(a[2]);
            foreach (var blk in s.AllBlocks) {
                var d = blk.Data;
                for (int i = 0; i + 4 <= d.Length; i++)
                    if (BitConverter.ToUInt32(d.Slice(i, 4)) == v) Console.WriteLine($"{blk.Key:X8} type {blk.Type} len {d.Length} off 0x{i:X}");
            }
            return 0;
        }
        if (a[0] == "rawset") {  // rawset <save> <NEWDIR> <blockKeyHex> <offHex> <u32>: write a u32 into one block
            var (raw, s) = Open(a[1]);
            var outDir = Path.GetFullPath(a[2]);
            if (Directory.Exists(outDir) || File.Exists(outDir)) throw new IOException("output folder exists; use a new one");
            var blk = s.AllBlocks.Single(b => b.Key == Convert.ToUInt32(a[3], 16));
            BitConverter.TryWriteBytes(blk.Data.Slice(Convert.ToInt32(a[4], 16), 4), uint.Parse(a[5]));
            var output = s.Write().ToArray();
            _ = Open(WriteNew(outDir, output));
            File.WriteAllLines(Path.Combine(outDir, "ops.log"), [$"source {Sha(raw)}", $"rawset {a[3]} {a[4]} {a[5]}", $"output {Sha(output)}"]);
            Console.WriteLine($"wrote {outDir}");
            return 0;
        }
        if (a[0] == "set") {
            var (raw, s) = Open(a[1]);
            var outDir = Path.GetFullPath(a[2]);
            if (Directory.Exists(outDir) || File.Exists(outDir)) throw new IOException("output folder exists; use a new one");
            var b = s.Blocks;
            var log = new List<string>();
            foreach (var op in a.Skip(3).Where(x => x != "--sort")) {
                var c = op.IndexOf(':'); var e = op.IndexOf('=');
                if (c < 0 || e < c) throw new ArgumentException(op);
                var kind = op[..c]; var name = op[(c + 1)..e]; var val = op[(e + 1)..];
                switch (kind) {
                    case "flag": { b.Event.TryGetValue(name, out var was); PutF(b.Event, name, val == "1"); log.Add($"event_flag {name}: {was} -> {val == "1"}"); break; }
                    case "sysflag": { b.Flags.TryGetValue(name, out var was); PutF(b.Flags, name, val == "1"); log.Add($"system_flag {name}: {was} -> {val == "1"}"); break; }
                    case "work": { b.Work.TryGetValue(name, out var was); PutV(b.Work, name, ulong.Parse(val)); log.Add($"system_work {name}: {was} -> {val}"); break; }
                    case "quest": { b.Quest.TryGetValue(name, out var was); PutV(b.Quest, name, ulong.Parse(val)); log.Add($"quest_work {name}: {was} -> {val}"); break; }
                    // pos:MAP=x,h,z,yaw  (game order as in trigger warp commands: x / height / z / yaw degrees)
                    case "pos": {
                        var v = val.Split(",").Select(x => float.Parse(x, System.Globalization.CultureInfo.InvariantCulture)).ToArray();
                        var co = s.Coordinates; var was = $"{co.Map} {co.X},{co.Z},{co.Y} {co.Rotation:F1}";
                        co.Map = name; co.X = v[0]; co.Z = v[1]; co.Y = v[2]; var ang = v[3] * Math.PI / 360.0; co.RX = 0; co.RY = 0; co.RZ = (float)Math.Sin(ang); co.RW = (float)Math.Cos(ang);  // yaw lives in the 0x34/0x3C pair (PKHeX names RZ/RW)
                        log.Add($"position: {was} -> {name} {val}"); break; }
                    // level:all=N : every party Pokemon to level N, stats recomputed
                    case "level": {
                        for (int i = 0; i < s.PartyCount; i++) { var p = s.GetPartySlotAtIndex(i); var was = p.CurrentLevel; p.CurrentLevel = byte.Parse(val); p.ResetPartyStats(); p.RefreshChecksum(); s.SetPartySlotAtIndex(p, i); log.Add($"party {i} species {p.Species}: level {was} -> {val}"); }
                        break; }
                    default: throw new ArgumentException(kind);
                }
            }
            // Vanilla saves are NOT key-sorted (checked on city-orig), so sorting is opt-in (--sort).
            if (a.Contains("--sort")) { b.Event.Sort(); b.Flags.Sort(); b.Work.Sort(); b.Quest.Sort(); log.Add("sorted event/system/work/quest tables"); }
            var output = s.Write().ToArray();
            if (!SwishCrypto.GetIsHashValid(output)) throw new InvalidDataException("output checksum");
            _ = Open(WriteNew(outDir, output));
            if (Sha(File.ReadAllBytes(a[1])) != Sha(raw)) throw new IOException("input changed");
            File.WriteAllLines(Path.Combine(outDir, "ops.log"), log.Prepend($"source {Sha(raw)}").Append($"output {Sha(output)}"));
            foreach (var l in log) Console.WriteLine(l);
            Console.WriteLine($"wrote {outDir}");
            return 0;
        }
        return 2;
    }

    // PKHeX 9ZA SetValue(key, v) only ensures the key exists and does NOT write the value: write it by index.
    static void PutF(EventWorkFlagStorage st, string name, bool v) {
        var h = FnvHash.HashFnv1a_64(name); st.SetValue(h, v); var i = st.GetIndex(h); st.SetValue(i, v);
        if (st.GetValue(i) != v) throw new InvalidDataException("readback " + name);
    }
    static void PutV(EventWorkValueStorage st, string name, ulong v) {
        var h = FnvHash.HashFnv1a_64(name); st.SetValue(h, v); var i = st.GetIndex(h); st.SetValue(i, v);
        if (st.GetValue(i) != v) throw new InvalidDataException("readback " + name);
    }

    static bool Sorted(int n, Func<int, ulong> key) {
        for (int i = 1; i < n; i++) if (key(i - 1) > key(i)) return false;
        return true;
    }

    static string WriteNew(string dir, byte[] data) {
        var d = Path.Combine(dir, "save_0");
        Directory.CreateDirectory(d);
        var p = Path.Combine(d, "main");
        File.WriteAllBytes(p, data);
        return p;
    }
}
