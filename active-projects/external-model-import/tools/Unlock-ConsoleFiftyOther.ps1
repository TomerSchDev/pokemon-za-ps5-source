param([string]$SourceSave,[string]$OutputSave)
$ErrorActionPreference='Stop'
$taskPk='\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\PS5-13.60\species-lab\pilot\tools\savecheck\bin-out\PKHeX.Core.dll'
[void][Reflection.Assembly]::LoadFrom($taskPk)
$taskRefs=@(Get-ChildItem -LiteralPath (Join-Path $PSHOME 'ref') -Filter '*.dll' | Select-Object -ExpandProperty FullName)+@($taskPk)
$taskSource=@'
using System;using System.IO;using System.Linq;using System.Text.Json;using PKHeX.Core;
public static class UnlockOtherFifty {
 public static void Run(string source,string target) {
  if(File.Exists(target))throw new IOException("Use a new version");
  var raw=File.ReadAllBytes(source);if(!SwishCrypto.GetIsHashValid(raw))throw new Exception("Invalid source");
  var sav=new SAV9ZA(raw.ToArray());var old=sav.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());
  if(sav.Items.GetItemQuantity(50)!=999)throw new Exception("Unexpected trial candy count");
  sav.Items.UnlockedOther=true;var result=sav.Write().ToArray();var check=new SAV9ZA(result.ToArray());
  var changed=check.AllBlocks.Where(b=>!old[b.Key].AsSpan().SequenceEqual(b.Data)).Select(b=>b.Key).ToArray();
  if(changed.Length!=1||changed[0]!=0x21C9BD44||!SwishCrypto.GetIsHashValid(result)||!check.Items.UnlockedOther)throw new Exception("Unexpected changes");
  if(!raw.AsSpan().SequenceEqual(File.ReadAllBytes(source)))throw new Exception("Source changed");
  File.WriteAllBytes(target,result);Console.WriteLine(JsonSerializer.Serialize(new{only_other_pouch_unlocked=true,rare_candies=check.Items.GetItemQuantity(50),species_and_levels_unchanged=true,changed_block=changed[0].ToString("X8")}));
 }
}
'@
Add-Type -TypeDefinition $taskSource -ReferencedAssemblies $taskRefs
[UnlockOtherFifty]::Run($SourceSave,$OutputSave)
