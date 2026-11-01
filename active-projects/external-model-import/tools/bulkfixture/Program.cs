using PKHeX.Core;
using System.Text.Json;
using System.Reflection;
if(args.Length!=3 || File.Exists(args[2]))throw new ArgumentException("SOURCE_TEST_SAVE MANIFEST NEW_OUTPUT");
var dst=Path.GetFullPath(args[2]);var qa=Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,"../../../qa/all-pokemon-20261030-r2"));
if(!dst.StartsWith(qa+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Only this QA output tree is permitted");
var raw=File.ReadAllBytes(args[0]);if(!SwishCrypto.GetIsHashValid(raw))throw new InvalidDataException("Invalid baseline save");
var s=new SAV9ZA(raw.ToArray());if(s.OT!="Test")throw new InvalidOperationException("Only Test trainer fixtures permitted");
var before=s.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());
using var doc=JsonDocument.Parse(File.ReadAllText(args[1]));var root=doc.RootElement;var entries=root.GetProperty("targets").EnumerateArray().ToArray();
bool boxed=root.GetProperty("mode").GetString()=="box";
if(entries.Length<1 || entries.Length>(boxed?s.BoxSlotCount:6))throw new ArgumentException("Wrong fixture size");
var template=(PA9)s.GetPartySlotAtIndex(0);var mons=new List<object>();
PA9 Make(ushort species,byte form,byte gender,int index){
 var p=(PA9)template.Clone();p.Species=species;p.Form=form;
 p.Gender=p.PersonalInfo.Gender==255?(byte)2:p.PersonalInfo.Gender==254?(byte)1:gender;
 p.PID=template.PID+(uint)index+1;if(p.IsShiny)p.PID^=0x10000000;
 p.Nickname=GameInfo.Strings.Species[species];p.IsNicknamed=false;p.CurrentLevel=50;
 p.Move1=33;p.Move2=64;p.Move3=670;p.Move4=45;p.Move1_PP=35;p.Move2_PP=35;p.Move3_PP=40;p.Move4_PP=40;
 p.RelearnMove1=33;p.RelearnMove2=64;p.RelearnMove3=670;p.RelearnMove4=45;
 p.ClearMovePlusFlags();p.ClearMoveRecordFlags();p.ResetPartyStats();p.RefreshChecksum();return p;
}
void Dex(PA9 p){var d=s.Zukan.GetEntry(p.Species);d.SetIsFormCaught(p.Form,true);d.SetIsFormSeen(p.Form,true);d.SetIsGenderSeen(p.Gender,true);d.SetLanguageFlag(p.Language,true);d.DisplayForm=p.Form;d.SetDisplayGender((Gender)p.Gender,p.Species,p.Form);}
// Six native party controls avoid loading unrelated imported models when testing a box.
for(int i=0;i<6;i++){var p=Make(498,0,0,100+i);s.SetPartySlotAtIndex(p,i);Dex(p);}
for(int i=0;i<entries.Length;i++){
 var e=entries[i];var p=Make(e.GetProperty("national").GetUInt16(),e.GetProperty("form").GetByte(),e.GetProperty("gender").GetByte(),i);
 if(p.SpeciesInternal!=e.GetProperty("internal").GetUInt16())throw new InvalidDataException("Species internal mapping differs: "+p.Species);
 if(boxed)s.SetBoxSlotAtIndex(p,0,i);else s.SetPartySlotAtIndex(p,i);
 Dex(p);mons.Add(new{key=e.GetProperty("key").GetString(),national=p.Species,internal_species=p.SpeciesInternal,form=p.Form,gender=p.Gender,name=GameInfo.Strings.Species[p.Species],p.ChecksumValid});
}
var output=s.Write().ToArray();if(!SwishCrypto.GetIsHashValid(output))throw new InvalidDataException("Generated save invalid");var check=new SAV9ZA(output.ToArray());
for(int i=0;i<entries.Length;i++){var p=boxed?check.GetBoxSlotAtIndex(0,i):check.GetPartySlotAtIndex(i);if(!p.ChecksumValid||p.Species!=entries[i].GetProperty("national").GetUInt16()||p.Form!=entries[i].GetProperty("form").GetByte())throw new InvalidDataException("Fixture readback differs");}
var changed=check.AllBlocks.Where(b=>!before[b.Key].AsSpan().SequenceEqual(b.Data)).Select(b=>b.Key).ToArray();
var allowed=new HashSet<uint>{0x3AA1A9AD,0x2D87BE5C};
foreach(var f in typeof(SAV9ZA).Assembly.GetTypes().Where(t=>t.Name.Contains("9ZA")).SelectMany(t=>t.GetFields(BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)).Where(f=>f.IsLiteral&&f.FieldType==typeof(uint)&&f.Name.Contains("Box")))allowed.Add((uint)f.GetRawConstantValue()!);
if(changed.Any(k=>!allowed.Contains(k)))throw new InvalidDataException("Unrelated save blocks changed: "+string.Join(",",changed.Select(k=>k.ToString("X8"))));
Directory.CreateDirectory(Path.GetDirectoryName(dst)!);File.WriteAllBytes(dst,output);
Console.WriteLine(JsonSerializer.Serialize(new{PC_only=true,original_save_unchanged=true,boxed,mons,changed_blocks=changed.Select(k=>k.ToString("X8")).ToArray(),box_count=s.BoxCount,box_slots=s.BoxSlotCount}));
