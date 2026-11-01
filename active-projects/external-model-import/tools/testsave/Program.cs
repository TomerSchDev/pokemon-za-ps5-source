using PKHeX.Core;
using System.Security.Cryptography;
using System.Text.Json;

if (args.Length != 3) throw new ArgumentException("SOURCE_TEST_SAVE NEW_OUTPUT NATIONAL_SPECIES|lead-smoliv");
if (File.Exists(args[1])) throw new IOException("Refusing to overwrite an existing save");
var raw=File.ReadAllBytes(args[0]);
if (!SwishCrypto.GetIsHashValid(raw)) throw new InvalidDataException("Invalid test-save hash");
var save=new SAV9ZA(raw.ToArray());
if (save.OT != "Test") throw new InvalidOperationException("Only the existing Test trainer baseline is accepted");
bool appendUnown=args[2]=="lead-smoliv-plus-unown";
bool reorderOnly=args[2]=="lead-smoliv" || appendUnown;
if (reorderOnly)
{
    int found=Enumerable.Range(0,save.PartyCount).FirstOrDefault(i=>save.GetPartySlotAtIndex(i).Species==928,-1);
    if(found<0) throw new InvalidDataException("No existing Smoliv in this test save");
    var first=save.GetPartySlotAtIndex(0);
    var smoliv=save.GetPartySlotAtIndex(found);
    save.SetPartySlotAtIndex(smoliv,0);
    if(found!=0) save.SetPartySlotAtIndex(first,found);
    if(appendUnown)
    {
        if(save.PartyCount>=6) throw new InvalidDataException("No fixture slot available");
        var unown=first.Clone();
        unown.Species=201; unown.Form=0; unown.Gender=2;
        unown.PID=first.PID+1000; unown.Nickname=GameInfo.Strings.Species[201];
        unown.Move1=33;unown.Move2=0;unown.Move3=0;unown.Move4=0;
        unown.ResetPartyStats();unown.RefreshChecksum();
        save.SetPartySlotAtIndex(unown,save.PartyCount);
    }
}
else
{
    var species=args[2].Split(',').Select(ushort.Parse).ToArray();
    if(species.Length<1 || species.Length>6) throw new ArgumentException("One to six fixture species required");
    var baseline=save.GetPartySlotAtIndex(0);
    for(int i=0;i<species.Length;i++)
    {
    var mon=baseline.Clone();
    mon.Species=species[i];
    mon.Form=0;
    mon.PID=baseline.PID+(uint)i+1;
    mon.Gender=mon.Species==201? (byte)2:(byte)0;
    mon.Nickname=GameInfo.Strings.Species[mon.Species];
    mon.Move1=33; mon.Move2=0; mon.Move3=0; mon.Move4=0;
    mon.ResetPartyStats();
    mon.RefreshChecksum();
    save.SetPartySlotAtIndex(mon,i);
    }
}
var output=save.Write().ToArray();
if (!SwishCrypto.GetIsHashValid(output)) throw new InvalidDataException("Invalid generated test-save hash");
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1]))!);
File.WriteAllBytes(args[1],output);
var check=new SAV9ZA(output.ToArray()).GetPartySlotAtIndex(0);
Console.WriteLine(JsonSerializer.Serialize(new { SourceSha256=Convert.ToHexString(SHA256.HashData(raw)), OutputSha256=Convert.ToHexString(SHA256.HashData(output)), check.Species, Internal=check is PA9 p?p.SpeciesInternal:0, check.ChecksumValid, OnlyTestTrainer=true, ReorderOnly=reorderOnly&&!appendUnown, FixtureUnownAppended=appendUnown }));
