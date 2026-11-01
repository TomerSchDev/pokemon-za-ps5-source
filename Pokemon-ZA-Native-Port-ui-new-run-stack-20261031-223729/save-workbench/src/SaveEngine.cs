using PKHeX.Core;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
namespace ZaSaveWorkbench;

public record Position(string Map, float X, float Y, float Z, float RX, float RY, float RZ, float RW);
public record PartyRow(int Slot, int Species, string Name, int Level, bool ChecksumValid);
public record StoryRow(string Group, string Key, string Name, string Value);
public record BlockRow(string Key, string Type, int Bytes, string Sha256);
public record SaveInfo(string Sha256, int Bytes, int Revision, string Trainer, uint Money, Position Position,
    PartyRow[] Party, StoryRow[] Story, BlockRow[] Blocks, bool RoundtripIdentical);
public record Bookmark(int Schema, string Label, string SourceSha256, int Revision, string Phase,
    Position Position, string Validation);
public record StoryChange(string Group, string Key, string Name, string? Before, string? After);
public record ExportReceipt(int Schema, string Operation, string SourceSha256, string OutputSha256,
    string[] ChangedBlocks, bool AllOtherBlocksIdentical, bool StoryUnchanged, string HardwareStatus, string Note);

public static class SaveEngine {
    public const uint CoordinatesKey = 0x910D381F;
    public static readonly JsonSerializerOptions Json = new() { WriteIndented=true, PropertyNameCaseInsensitive=true };
    public static string Hash(byte[] data) => Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();
    static readonly string[] Groups = ["System work", "Quest work", "Event flags", "System flags"];
    public static (byte[] Raw,SAV9ZA Save) Open(string path) {
        var file=new FileInfo(path);
        if (!file.Exists || file.Length<1024 || file.Length>32*1024*1024) throw new InvalidDataException("Invalid save file size.");
        byte[] raw=File.ReadAllBytes(path);
        if (!SwishCrypto.GetIsHashValid(raw)) throw new InvalidDataException("Save checksum failed. No changes were made.");
        if (SaveUtil.GetSaveFile(raw.ToArray()) is not SAV9ZA save) throw new InvalidDataException("Choose a Pokémon Legends: Z-A main save.");
        if (save.SaveRevision is <0 or >2 || save.PartyCount is <0 or >6) throw new InvalidDataException("Unsupported save revision or party count.");
        if (!raw.SequenceEqual(save.Write().ToArray())) throw new InvalidDataException("This save does not round-trip exactly with the pinned parser.");
        for(int i=0;i<save.PartyCount;i++) if(!save.GetPartySlotAtIndex(i).ChecksumValid) throw new InvalidDataException("Party Pokémon checksum failed.");
        return (raw,save);
    }
    public static Position PositionOf(SAV9ZA s) { var p=s.Coordinates; return new(p.Map,p.X,p.Y,p.Z,p.RX,p.RY,p.RZ,p.RW); }
    public static string PhaseOf(SAV9ZA s) {
        int index=s.Blocks.Work.GetIndex(FnvHash.HashFnv1a_64("SYS_WORK_PHASE"));
        return index<0?"unknown":s.Blocks.Work.GetValue(index).ToString();
    }
    static Dictionary<string,string> Names() {
        string path=Path.Combine(AppContext.BaseDirectory,"assets","key-names.json");
        if(!File.Exists(path))return [];
        using var doc=JsonDocument.Parse(File.ReadAllText(path));
        return doc.RootElement.EnumerateObject().ToDictionary(x=>x.Name.ToUpperInvariant(),x=>x.Value.GetProperty("name").GetString()??"");
    }
    public static SaveInfo Inspect(string path) {
        var (raw,s)=Open(path);var names=Names();var rows=new List<StoryRow>();
        void Add(string group,ulong key,string value) { string hex=key.ToString("X16");rows.Add(new(group,hex,names.GetValueOrDefault(hex,"Unmapped"),value)); }
        for(int i=0;i<s.Blocks.Work.CountUsed;i++)Add(Groups[0],s.Blocks.Work.GetKey(i),s.Blocks.Work.GetValue(i).ToString());
        for(int i=0;i<s.Blocks.Quest.CountUsed;i++)Add(Groups[1],s.Blocks.Quest.GetKey(i),s.Blocks.Quest.GetValue(i).ToString());
        for(int i=0;i<s.Blocks.Event.CountUsed;i++)Add(Groups[2],s.Blocks.Event.GetKey(i),s.Blocks.Event.GetValue(i).ToString());
        for(int i=0;i<s.Blocks.Flags.CountUsed;i++)Add(Groups[3],s.Blocks.Flags.GetKey(i),s.Blocks.Flags.GetValue(i).ToString());
        return new(Hash(raw),raw.Length,s.SaveRevision,s.OT,s.Money,PositionOf(s),
            Enumerable.Range(0,s.PartyCount).Select(i=>{var p=s.GetPartySlotAtIndex(i);return new PartyRow(i+1,p.Species,p.Nickname,p.CurrentLevel,p.ChecksumValid);}).ToArray(),
            rows.ToArray(),s.AllBlocks.Select(b=>new BlockRow(b.Key.ToString("X8"),b.Type.ToString(),b.Data.Length,Hash(b.Data.ToArray()))).ToArray(),true);
    }
    public static Bookmark Mark(string path,string label) {
        var (raw,s)=Open(path);
        if(string.IsNullOrWhiteSpace(label)||label.Length>100)throw new ArgumentException("Use a bookmark name of 1–100 characters.");
        return new(1,label,Hash(raw),s.SaveRevision,PhaseOf(s),PositionOf(s),"Position read from a save; moving another save here is not hardware-validated.");
    }
    public static void Validate(Position p) {
        if(!Regex.IsMatch(p.Map,"^[A-Za-z0-9_-]{1,31}$"))throw new InvalidDataException("Map ID must contain 1–31 ASCII letters, digits, _ or -.");
        float[] numbers=[p.X,p.Y,p.Z,p.RX,p.RY,p.RZ,p.RW];
        if(numbers.Any(x=>!float.IsFinite(x)))throw new InvalidDataException("Coordinates must be finite numbers.");
        if(new[]{p.X,p.Y,p.Z}.Any(x=>Math.Abs(x)>100000))throw new InvalidDataException("Coordinates exceed the editor bounds.");
        double norm=(double)p.RX*p.RX+(double)p.RY*p.RY+(double)p.RZ*p.RZ+(double)p.RW*p.RW;
        if(norm<.5||norm>1.5)throw new InvalidDataException("Unexpected rotation quaternion; choose a valid saved position.");
    }
    static string[] Diff(SAV9ZA before,SAV9ZA after) {
        if(before.AllBlocks.Count!=after.AllBlocks.Count)throw new InvalidDataException("Block count changed.");
        var changed=new List<string>();
        for(int i=0;i<before.AllBlocks.Count;i++) {
            var a=before.AllBlocks[i];var b=after.AllBlocks[i];
            if(a.Key!=b.Key||a.Type!=b.Type||a.Data.Length!=b.Data.Length)throw new InvalidDataException("Block structure changed.");
            if(!a.Data.SequenceEqual(b.Data))changed.Add(a.Key.ToString("X8"));
        }
        return changed.ToArray();
    }
    static string Publish(string input,string outputFolder,byte[] original,byte[] output,ExportReceipt receipt,object? request=null) {
        string destination=Path.GetFullPath(outputFolder);
        if(Directory.Exists(destination)||File.Exists(destination))throw new IOException("Choose a new output folder; existing exports are never replaced.");
        if(!File.ReadAllBytes(input).SequenceEqual(original))throw new IOException("Input changed during editing; export cancelled.");
        string parent=Path.GetDirectoryName(destination)!;Directory.CreateDirectory(parent);
        string stage=Path.Combine(parent,".za-export-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(stage);
        try {
            File.WriteAllBytes(Path.Combine(stage,"main"),output);
            File.WriteAllBytes(Path.Combine(stage,"original-main.backup"),original);
            File.WriteAllText(Path.Combine(stage,"verification.json"),JsonSerializer.Serialize(receipt,Json));
            string contexts=Path.Combine(AppContext.BaseDirectory,"assets","source-contexts.json");
            JsonElement? context=null;
            if(File.Exists(contexts)) {
                using var doc=JsonDocument.Parse(File.ReadAllText(contexts));
                if(doc.RootElement.TryGetProperty(receipt.SourceSha256,out var found))context=found.Clone();
            }
            File.WriteAllText(Path.Combine(stage,"run-binding.json"),JsonSerializer.Serialize(new {
                SourceSaveSha256=receipt.SourceSha256,SourceContext=context,
                Requirement="Import into this same randomizer run only. External seed/ROMFS files are not included or modified. No automatic console import is performed."
            },Json));
            if(request!=null)File.WriteAllText(Path.Combine(stage,"request.json"),JsonSerializer.Serialize(request,Json));
            if(Hash(File.ReadAllBytes(Path.Combine(stage,"main")))!=receipt.OutputSha256||Hash(File.ReadAllBytes(Path.Combine(stage,"original-main.backup")))!=receipt.SourceSha256)
                throw new IOException("Export readback failed.");
            _=Open(Path.Combine(stage,"main"));
            Directory.Move(stage,destination);return destination;
        } catch { if(Directory.Exists(stage))Directory.Delete(stage,true);throw; }
    }
    public static string Move(string input,string outputFolder,Bookmark target,bool allowCrossMap=false) {
        var (raw,s)=Open(input);var baseline=new SAV9ZA(raw.ToArray());Validate(target.Position);
        if(target.Schema!=1||!Regex.IsMatch(target.SourceSha256,"^[0-9a-f]{64}$"))throw new InvalidDataException("Invalid bookmark provenance.");
        // A location editor does not unlock maps or reconcile progression state.
        if(s.SaveRevision!=target.Revision)throw new InvalidDataException("Bookmark and save revisions differ.");
        bool crossMap=s.Coordinates.Map!=target.Position.Map;
        if(crossMap&&!allowCrossMap)throw new InvalidDataException("Enable experimental map changes to export this destination. Console validation is still required.");
        var p=target.Position; // Same map: retain its raw name buffer, including unused bytes.
        if(crossMap)s.Coordinates.Map=p.Map;
        s.Coordinates.X=p.X;s.Coordinates.Y=p.Y;s.Coordinates.Z=p.Z;
        s.Coordinates.RX=p.RX;s.Coordinates.RY=p.RY;s.Coordinates.RZ=p.RZ;s.Coordinates.RW=p.RW;
        byte[] output=s.Write().ToArray();
        if(!SwishCrypto.GetIsHashValid(output))throw new InvalidDataException("Export checksum failed.");
        var reopened=new SAV9ZA(output.ToArray());string[] changed=Diff(baseline,reopened);
        if(changed.Any(x=>x!=CoordinatesKey.ToString("X8")))throw new InvalidDataException("An unrelated block changed.");
        if(PositionOf(reopened)!=p)throw new InvalidDataException("Position readback mismatch.");
        var before=baseline.AllBlocks.Single(b=>b.Key==CoordinatesKey).Data;
        var after=reopened.AllBlocks.Single(b=>b.Key==CoordinatesKey).Data;
        for(int i=0;i<before.Length;i++)if(before[i]!=after[i] && !(i<0x2c||(i>=0x30&&i<0x40)))throw new InvalidDataException("Unknown coordinate metadata changed.");
        var receipt=new ExportReceipt(1,crossMap?"experimental-map-and-position":"position-only",Hash(raw),Hash(output),changed,true,true,"pending-console-load",
            "All non-coordinate blocks preserved byte-for-byte: team, items, story, spawners and revision. Destination availability/collision is not proven.");
        return Publish(input,outputFolder,raw,output,receipt,target);
    }
    public static object Compare(string left,string right) {
        var(_,a)=Open(left);var(_,b)=Open(right);var ia=Inspect(left);var ib=Inspect(right);
        var old=ia.Story.ToDictionary(x=>x.Group+":"+x.Key);
        var differences=ib.Story.Where(x=>!old.TryGetValue(x.Group+":"+x.Key,out var previous)||previous.Value!=x.Value)
            .Select(x=>new StoryChange(x.Group,x.Key,x.Name,old.GetValueOrDefault(x.Group+":"+x.Key)?.Value,x.Value)).ToList();
        foreach(var row in ia.Story.Where(x=>!ib.Story.Any(y=>y.Group==x.Group&&y.Key==x.Key)))differences.Add(new(row.Group,row.Key,row.Name,row.Value,null));
        return new {Left=ia.Sha256,Right=ib.Sha256,LeftPhase=PhaseOf(a),RightPhase=PhaseOf(b),LeftPosition=ia.Position,RightPosition=ib.Position,
            ChangedBlocks=a.SaveRevision==b.SaveRevision?Diff(a,b):["Different save revisions; no block transplant allowed"],StoryDifferences=differences};
    }
}
