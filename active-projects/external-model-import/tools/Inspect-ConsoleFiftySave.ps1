param([string[]]$SourceSave,[string]$SaveTree)
$ErrorActionPreference='Stop'
$taskPk='\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\PS5-13.60\species-lab\pilot\tools\savecheck\bin-out\PKHeX.Core.dll'
[void][Reflection.Assembly]::LoadFrom($taskPk)
$taskRefs=@(Get-ChildItem -LiteralPath (Join-Path $PSHOME 'ref') -Filter '*.dll' | Select-Object -ExpandProperty FullName)+@($taskPk)
$taskSource=@'
using System;using System.IO;using System.Linq;using System.Text.Json;using PKHeX.Core;
public static class InspectFiftySave {
 public static void Run(string path){var raw=File.ReadAllBytes(path);if(!SwishCrypto.GetIsHashValid(raw))throw new Exception("Invalid source");
 var sav=new SAV9ZA(raw.ToArray());var party=Enumerable.Range(0,6).Select(i=>{var p=(PA9)sav.GetPartySlotAtIndex(i);return new{slot=i,species=p.Species,internalSpecies=p.SpeciesInternal,level=p.CurrentLevel,moves=new[]{p.Move1,p.Move2,p.Move3,p.Move4},pp=new[]{p.Move1_PP,p.Move2_PP,p.Move3_PP,p.Move4_PP},ppups=new[]{p.Move1_PPUps,p.Move2_PPUps,p.Move3_PPUps,p.Move4_PPUps},footer=Convert.ToHexString(sav.PartyInfo.GetSlot(i).Span.Slice(0x158)),p.ChecksumValid,p.Status_Condition,p.IsEgg,p.Stat_HPCurrent,p.Ability,p.CurrentHandler,p.OriginalTrainerName,p.ID32,p.ObedienceLevel,p.MetLevel};}).ToArray();
 Console.WriteLine(JsonSerializer.Serialize(new{path,party,played_hours=sav.PlayedHours,played_minutes=sav.PlayedMinutes,party_count=sav.PartyCount,candy=sav.Items.GetItemQuantity(50),balls=sav.Items.GetItemQuantity(4),other_pouch_unlocked=sav.Items.UnlockedOther}));}
}
'@
Add-Type -TypeDefinition $taskSource -ReferencedAssemblies $taskRefs
if($SaveTree){$SourceSave=@(Get-ChildItem -LiteralPath $SaveTree -Filter main -Recurse -File | Select-Object -ExpandProperty FullName)}
foreach($taskPath in $SourceSave){[InspectFiftySave]::Run($taskPath)}
