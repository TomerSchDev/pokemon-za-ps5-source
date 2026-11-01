param([Parameter(Mandatory)][string]$SourceSave,[Parameter(Mandatory)][string]$OutputSave,[Parameter(Mandatory)][ushort]$National,[switch]$FromBox,[string]$IntoSave='')
$ErrorActionPreference='Stop'
$taskPk='\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\PS5-13.60\species-lab\pilot\tools\savecheck\bin-out\PKHeX.Core.dll'
[void][Reflection.Assembly]::LoadFrom($taskPk)
$taskRefs=@(Get-ChildItem -LiteralPath (Join-Path $PSHOME 'ref') -Filter '*.dll' | Select-Object -ExpandProperty FullName)+@($taskPk)
$taskSource=@'
using System;using System.IO;using System.Linq;using System.Text.Json;using PKHeX.Core;
public static class SelectFiftyPrimary {
 public static void Transfer(string input,string baseline,string output,ushort species){
  if(File.Exists(output))throw new IOException("Output already exists");
  var sourceRaw=File.ReadAllBytes(input);var baseRaw=File.ReadAllBytes(baseline);
  if(!SwishCrypto.GetIsHashValid(sourceRaw)||!SwishCrypto.GetIsHashValid(baseRaw))throw new Exception("Invalid source hash");
  var source=new SAV9ZA(sourceRaw.ToArray());var save=new SAV9ZA(baseRaw.ToArray());
  var target=(PA9)source.GetPartySlotAtIndex(0);if(target.Species!=species||!target.ChecksumValid)throw new Exception("Wrong captured primary");
  var before=save.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());
  target.HealPP();target.RefreshChecksum();save.SetPartySlotAtIndex(target,0);
  save.AllBlocks.Single(b=>b.Key==0x2D87BE5C).ChangeData(before[0x2D87BE5C]);
  var bytes=save.Write().ToArray();var check=new SAV9ZA(bytes.ToArray());
  var unexpected=check.AllBlocks.Where(b=>b.Key!=0x3AA1A9AD&&!before[b.Key].AsSpan().SequenceEqual(b.Data)).Select(b=>b.Key.ToString("X8")+":"+Enumerable.Range(0,b.Data.Length).Count(i=>b.Data[i]!=before[b.Key][i])).ToArray();
  if(!SwishCrypto.GetIsHashValid(bytes)||unexpected.Length!=0)throw new Exception("Unexpected non-party change: "+string.Join(",",unexpected));
  if(!sourceRaw.AsSpan().SequenceEqual(File.ReadAllBytes(input))||!baseRaw.AsSpan().SequenceEqual(File.ReadAllBytes(baseline)))throw new Exception("Source changed");
  if(check.GetPartySlotAtIndex(0).Species!=species||!check.GetPartySlotAtIndex(0).ChecksumValid)throw new Exception("Transfer verification failed");
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));File.WriteAllBytes(output,bytes);
  var keyNames=typeof(SAV9ZA).Assembly.GetTypes().SelectMany(t=>t.GetFields(System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Static)).Where(f=>f.IsLiteral&&f.FieldType==typeof(uint)&&(uint)f.GetRawConstantValue()==0x3AA1A9AD).Select(f=>f.DeclaringType.FullName+"."+f.Name).ToArray();
  Console.WriteLine(JsonSerializer.Serialize(new{PC_only=true,diagnostic_only=true,source_unchanged=true,world_from_baseline=true,game_created_species=species,level=target.CurrentLevel,only_changed_block="3AA1A9AD",keyNames,combat_pass_inferred=false}));
 }
 public static void Run(string input,string output,ushort species,bool fromBox){
  if(File.Exists(output))throw new IOException("Output already exists");
  var raw=File.ReadAllBytes(input);if(!SwishCrypto.GetIsHashValid(raw))throw new Exception("Invalid source hash");
  var save=new SAV9ZA(raw.ToArray());var before=save.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());
  var native=(PA9)save.GetPartySlotAtIndex(0);int slot=Enumerable.Range(0,save.PartyCount).Where(i=>save.GetPartySlotAtIndex(i).Species==species).DefaultIfEmpty(-1).First();
  PA9 target;
  int boxIndex=-1;
  if(fromBox){
   var matches=Enumerable.Range(0,save.BoxCount*save.BoxSlotCount).Where(i=>save.GetBoxSlotAtIndex(i/save.BoxSlotCount,i%save.BoxSlotCount).Species==species).ToArray();
   if(matches.Length!=1)throw new Exception("Expected one boxed native control, found "+matches.Length);
   boxIndex=matches[0];target=(PA9)save.GetBoxSlotAtIndex(boxIndex/save.BoxSlotCount,boxIndex%save.BoxSlotCount);
   save.SetBoxSlotAtIndex(native,boxIndex/save.BoxSlotCount,boxIndex%save.BoxSlotCount);slot=0;target.ResetPartyStats();
  }
  else if(slot>=0)target=(PA9)save.GetPartySlotAtIndex(slot);
  else {
   int index=Enumerable.Range(0,50).Where(i=>save.GetBoxSlotAtIndex(i/save.BoxSlotCount,i%save.BoxSlotCount).Species==species).DefaultIfEmpty(-1).First();
   if(index<0)throw new Exception("Target is absent from the prepared fifty cohort");
   target=(PA9)save.GetBoxSlotAtIndex(index/save.BoxSlotCount,index%save.BoxSlotCount);slot=5;
  }
  target.HealPP();target.FixMoves();target.RefreshChecksum();
  if(slot!=0)save.SetPartySlotAtIndex(native,slot);
  save.SetPartySlotAtIndex(target,0);
  if(fromBox)save.AllBlocks.Single(b=>b.Key==0x2D87BE5C).ChangeData(before[0x2D87BE5C]);
  var bytes=save.Write().ToArray();var check=new SAV9ZA(bytes.ToArray());
  if(!SwishCrypto.GetIsHashValid(bytes)||check.AllBlocks.Any(b=>b.Key!=0x0D66012C&&b.Key!=0x3AA1A9AD&&!before[b.Key].AsSpan().SequenceEqual(b.Data)))throw new Exception("Unexpected non-party/box change");
  if(!raw.AsSpan().SequenceEqual(File.ReadAllBytes(input)))throw new Exception("Source changed");
  if(check.GetPartySlotAtIndex(0).Species!=species||!check.GetPartySlotAtIndex(0).ChecksumValid)throw new Exception("Primary target verification failed");
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));File.WriteAllBytes(output,bytes);
  Console.WriteLine(JsonSerializer.Serialize(new{PC_only=true,source_unchanged=true,fromBox,boxIndex,combat_or_evolution_pass_inferred=false,
   party=Enumerable.Range(0,6).Select(i=>{var p=(PA9)check.GetPartySlotAtIndex(i);return new{slot=i,p.Species,p.CurrentLevel,moves=new[]{p.Move1,p.Move2,p.Move3,p.Move4},p.ChecksumValid};})}));
 }
}
'@
Add-Type -TypeDefinition $taskSource -ReferencedAssemblies $taskRefs
if($IntoSave){[SelectFiftyPrimary]::Transfer($SourceSave,$IntoSave,$OutputSave,$National)}
else{[SelectFiftyPrimary]::Run($SourceSave,$OutputSave,$National,$FromBox.IsPresent)}
