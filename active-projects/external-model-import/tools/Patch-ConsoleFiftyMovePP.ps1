param([Parameter(Mandatory)][string]$SourceSave,[Parameter(Mandatory)][string]$OutputSave)
$ErrorActionPreference='Stop'
$taskPk='\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\PS5-13.60\species-lab\pilot\tools\savecheck\bin-out\PKHeX.Core.dll'
[void][Reflection.Assembly]::LoadFrom($taskPk)
$taskRefs=@(Get-ChildItem -LiteralPath (Join-Path $PSHOME 'ref') -Filter '*.dll' | Select-Object -ExpandProperty FullName)+@($taskPk)
$taskSource=@'
using System;using System.IO;using System.Linq;using System.Collections.Generic;using System.Text.Json;using PKHeX.Core;
public static class PatchFiftyPP {
 public static void Run(string input,string output){
  if(File.Exists(output))throw new IOException("Output exists");var raw=File.ReadAllBytes(input);
  if(!SwishCrypto.GetIsHashValid(raw))throw new InvalidDataException("Invalid source save");
  var sav=new SAV9ZA(raw.ToArray());var before=sav.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());var changes=new List<object>();
  for(int i=0;i<6;i++){
   var p=(PA9)sav.GetPartySlotAtIndex(i);var old=new[]{p.Move1_PP,p.Move2_PP,p.Move3_PP,p.Move4_PP};
   p.HealPP();p.FixMoves();p.RefreshChecksum();sav.SetPartySlotAtIndex(p,i);
   changes.Add(new{slot=i,species=p.Species,before=old,after=new[]{p.Move1_PP,p.Move2_PP,p.Move3_PP,p.Move4_PP}});
  }
  for(int i=0;i<50;i++){var p=(PA9)sav.GetBoxSlotAtIndex(i/sav.BoxSlotCount,i%sav.BoxSlotCount);p.HealPP();p.FixMoves();p.RefreshChecksum();sav.SetBoxSlotAtIndex(p,i/sav.BoxSlotCount,i%sav.BoxSlotCount);}
  var bytes=sav.Write().ToArray();var check=new SAV9ZA(bytes.ToArray());
  if(!SwishCrypto.GetIsHashValid(bytes)||check.AllBlocks.Any(b=>b.Key!=0x0D66012C&&b.Key!=0x3AA1A9AD&&!before[b.Key].AsSpan().SequenceEqual(b.Data)))throw new InvalidDataException("Unexpected block change");
  if(!raw.AsSpan().SequenceEqual(File.ReadAllBytes(input)))throw new InvalidDataException("Source changed");
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));File.WriteAllBytes(output,bytes);
  Console.WriteLine(JsonSerializer.Serialize(new{PC_only=true,changed_only="Move PP and checksums in copied party/box records",source_unchanged=true,changes}));
 }
}
'@
Add-Type -TypeDefinition $taskSource -ReferencedAssemblies $taskRefs
[PatchFiftyPP]::Run($SourceSave,$OutputSave)
