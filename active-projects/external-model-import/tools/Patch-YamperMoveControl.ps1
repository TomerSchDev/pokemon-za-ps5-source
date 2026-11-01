param([Parameter(Mandatory)][string]$SourceSave,[Parameter(Mandatory)][string]$OutputSave,[switch]$KeepTwoMoves,
 [ushort]$CompareNational=835,[ushort]$CompareMoveA=33,[ushort]$CompareMoveB=209,
 [ushort]$ControlNational=706,[switch]$NativeOnly)
$ErrorActionPreference='Stop'
$taskPk='\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\PS5-13.60\species-lab\pilot\tools\savecheck\bin-out\PKHeX.Core.dll'
[void][Reflection.Assembly]::LoadFrom($taskPk)
$taskRefs=@(Get-ChildItem -LiteralPath (Join-Path $PSHOME 'ref') -Filter '*.dll' | Select-Object -ExpandProperty FullName)+@($taskPk)
$taskSource=@'
using System;using System.IO;using System.Linq;using System.Text.Json;using PKHeX.Core;
public static class YamperMoveControl {
 static void Moves(PA9 p,ushort a,ushort b,ushort c,ushort d){p.Move1=a;p.Move2=b;p.Move3=c;p.Move4=d;p.HealPP();p.FixMoves();p.RefreshChecksum();}
 public static void Compare(string input,string output,ushort species,ushort moveA,ushort moveB,ushort nativeSpecies,bool nativeOnly){
  if(File.Exists(output))throw new IOException("Output exists");var raw=File.ReadAllBytes(input);if(!SwishCrypto.GetIsHashValid(raw))throw new Exception("Invalid source");
  var sav=new SAV9ZA(raw.ToArray());var before=sav.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());
  var native=(PA9)sav.GetPartySlotAtIndex(0);if(native.Species!=706)throw new Exception("Requires original native Goodra in slot0");
  var target=Enumerable.Range(1,sav.PartyCount-1).Select(i=>(PA9)sav.GetPartySlotAtIndex(i)).Single(p=>p.Species==species);
  var control=(PA9)native.Clone();if(nativeSpecies!=706){control.Species=nativeSpecies;control.IsNicknamed=false;control.ResetPartyStats();}Moves(control,moveA,moveB,0,0);Moves(target,moveA,moveB,0,0);
  sav.SetPartySlotAtIndex(control,0);sav.SetPartySlotAtIndex(target,1);
  if(nativeOnly){for(int i=1;i<6;i++)sav.SetPartySlotAtIndex((PA9)control.Clone(),i);}
  // Import helpers update the Pokedex; a diagnostic control must not claim a new catch.
  sav.AllBlocks.Single(b=>b.Key==0x2D87BE5C).ChangeData(before[0x2D87BE5C]);
  var bytes=sav.Write().ToArray();var check=new SAV9ZA(bytes.ToArray());
  var unexpected=check.AllBlocks.Where(b=>b.Key!=0x0D66012C&&b.Key!=0x3AA1A9AD&&!before[b.Key].AsSpan().SequenceEqual(b.Data)).Select(b=>b.Key.ToString("X8")+":"+Enumerable.Range(0,b.Data.Length).Count(i=>b.Data[i]!=before[b.Key][i])).ToArray();
  if(!SwishCrypto.GetIsHashValid(bytes)||unexpected.Length!=0){
   var names=typeof(SAV9ZA).Assembly.GetTypes().SelectMany(t=>t.GetFields(System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Static)).Where(f=>f.IsLiteral&&f.FieldType==typeof(uint)&&(uint)f.GetRawConstantValue()==0x2D87BE5C).Select(f=>f.DeclaringType.FullName+"."+f.Name);
   throw new Exception("Unexpected block change: "+string.Join(",",unexpected)+"; named key "+string.Join(",",names));
  }
  if(!raw.AsSpan().SequenceEqual(File.ReadAllBytes(input)))throw new Exception("Source changed");
  if(check.GetPartySlotAtIndex(0).Species!=nativeSpecies||!check.GetPartySlotAtIndex(0).ChecksumValid||(!nativeOnly&&(check.GetPartySlotAtIndex(1).Species!=species||!check.GetPartySlotAtIndex(1).ChecksumValid))||(nativeOnly&&Enumerable.Range(0,check.PartyCount).Any(i=>check.GetPartySlotAtIndex(i).Species!=nativeSpecies)))throw new Exception("Comparison fixture failed verification");
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));File.WriteAllBytes(output,bytes);
  Console.WriteLine(JsonSerializer.Serialize(new{PC_only=true,diagnostic_only=true,QA_pass_allowed=false,source_unchanged=true,nativeSpecies,nativeOnly,comparedSpecies=species,moves=new[]{moveA,moveB},nativeLevel=control.CurrentLevel,targetLevel=target.CurrentLevel,partyCount=check.PartyCount}));
 }
 public static void Run(string input,string output,bool twoMoves){
  if(File.Exists(output))throw new IOException("Output exists");var raw=File.ReadAllBytes(input);if(!SwishCrypto.GetIsHashValid(raw))throw new Exception("Invalid source");
  var sav=new SAV9ZA(raw.ToArray());var before=sav.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());
  var g=(PA9)sav.GetPartySlotAtIndex(0);var y=(PA9)sav.GetPartySlotAtIndex(1);if(g.Species!=706||y.Species!=835)throw new Exception("Wrong fixture");
  Moves(y,33,209,(ushort)(twoMoves?0:84),(ushort)(twoMoves?0:129));sav.SetPartySlotAtIndex(y,1);
  var gc=(PA9)g.Clone();Moves(gc,33,209,84,129);sav.SetPartySlotAtIndex(gc,2);
  var yc=(PA9)g.Clone();yc.Species=835;yc.Nickname="Yamper";yc.IsNicknamed=false;yc.ResetPartyStats();yc.HealPP();yc.FixMoves();yc.RefreshChecksum();
  sav.SetPartySlotAtIndex(y,0);sav.SetPartySlotAtIndex(gc,1);sav.SetPartySlotAtIndex(yc,2);sav.SetPartySlotAtIndex(g,3);
  var bytes=sav.Write().ToArray();var check=new SAV9ZA(bytes.ToArray());
  if(!SwishCrypto.GetIsHashValid(bytes)||check.AllBlocks.Any(b=>b.Key!=0x0D66012C&&b.Key!=0x3AA1A9AD&&!before[b.Key].AsSpan().SequenceEqual(b.Data)))throw new Exception("Unexpected block change");
  if(!raw.AsSpan().SequenceEqual(File.ReadAllBytes(input)))throw new Exception("Source changed");
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));File.WriteAllBytes(output,bytes);
  Console.WriteLine(JsonSerializer.Serialize(new{PC_only=true,diagnostic_only=true,QA_pass_allowed=false,source_unchanged=true,
   party=Enumerable.Range(0,6).Select(i=>{var p=(PA9)check.GetPartySlotAtIndex(i);return new{slot=i,p.Species,p.CurrentLevel,moves=new[]{p.Move1,p.Move2,p.Move3,p.Move4},p.ChecksumValid};})}));
 }
}
'@
Add-Type -TypeDefinition $taskSource -ReferencedAssemblies $taskRefs
if($CompareNational -ne 835 -or $CompareMoveA -ne 33 -or $CompareMoveB -ne 209){
 [YamperMoveControl]::Compare($SourceSave,$OutputSave,$CompareNational,$CompareMoveA,$CompareMoveB,$ControlNational,$NativeOnly.IsPresent)
}else{[YamperMoveControl]::Run($SourceSave,$OutputSave,$KeepTwoMoves.IsPresent)}
