param([Parameter(Mandatory)][string]$SourceSave,[Parameter(Mandatory)][string]$OutputSave,[Parameter(Mandatory)][ushort]$National,[Parameter(Mandatory)][byte]$Level)
$ErrorActionPreference='Stop'
$taskLab=Split-Path (Split-Path (Split-Path $PSScriptRoot))
$taskWork=Join-Path $taskLab 'pc-fifty-20261031-r1'
$taskReview=@(Get-Content -LiteralPath (Join-Path $taskWork 'reviewed-cohort-progress.json') -Raw | ConvertFrom-Json | Where-Object species -eq $National)
if($taskReview.Count -ne 1 -or !$taskReview[0].manually_viewed -or $taskReview[0].level_up -ne 'observed_pass' -or $taskReview[0].observed_level -ne $Level){throw 'An actual manually reviewed in-game level-up is required'}
$taskImage=Join-Path (Join-Path (Join-Path $taskLab 'hebrew-lab\runs') $taskReview[0].evidence.level30.run) $taskReview[0].evidence.level30.path
$taskProofHash=(Get-FileHash -LiteralPath $taskImage -Algorithm SHA256).Hash.ToLower()
$taskPk='\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\PS5-13.60\species-lab\pilot\tools\savecheck\bin-out\PKHeX.Core.dll'
[void][Reflection.Assembly]::LoadFrom($taskPk)
$taskRefs=@(Get-ChildItem -LiteralPath (Join-Path $PSHOME 'ref') -Filter '*.dll' | Select-Object -ExpandProperty FullName)+@($taskPk)
$taskSource=@'
using System;using System.IO;using System.Linq;using System.Text.Json;using PKHeX.Core;
public static class StageObservedLevel {
 public static void Run(string input,string output,ushort species,byte level,int candy,string proof,string proofHash){
  if(File.Exists(output))throw new IOException("Output exists");var raw=File.ReadAllBytes(input);
  if(!SwishCrypto.GetIsHashValid(raw))throw new Exception("Invalid source");var save=new SAV9ZA(raw.ToArray());
  var before=save.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());var p=(PA9)save.GetPartySlotAtIndex(0);
  if(p.Species!=species||p.CurrentLevel+1!=level||save.Items.GetItemQuantity(50)-1!=candy)throw new Exception("This recovery only reconstructs the single observed Candy level-up");
  p.CurrentLevel=level;p.ResetPartyStats();p.RefreshChecksum();save.SetPartySlotAtIndex(p,0);save.Items.SetItemQuantity(50,candy);
  var bytes=save.Write().ToArray();var check=new SAV9ZA(bytes.ToArray());uint[] allowed={0x0D66012C,0x3AA1A9AD,0x2D87BE5C,0x21C9BD44};
  if(!SwishCrypto.GetIsHashValid(bytes)||check.AllBlocks.Any(b=>!allowed.Contains(b.Key)&&!before[b.Key].AsSpan().SequenceEqual(b.Data)))throw new Exception("Unexpected change");
  if(!raw.AsSpan().SequenceEqual(File.ReadAllBytes(input)))throw new Exception("Source changed");
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));File.WriteAllBytes(output,bytes);
  var report=JsonSerializer.Serialize(new{PC_only=true,staged_continuation_only=true,forced_evolution=false,QA_pass_inferred=false,source_unchanged=true,
   species,level,candy,observed_in_game_image=proof,observed_image_sha256=proofHash,output_sha256=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLower()});
  File.WriteAllText(Path.Combine(Path.GetDirectoryName(Path.GetDirectoryName(output)),"observed-level-provenance.json"),report);Console.WriteLine(report);
 }
}
'@
Add-Type -TypeDefinition $taskSource -ReferencedAssemblies $taskRefs
[StageObservedLevel]::Run($SourceSave,$OutputSave,$National,$Level,$taskReview[0].observed_candy_count,$taskImage,$taskProofHash)
