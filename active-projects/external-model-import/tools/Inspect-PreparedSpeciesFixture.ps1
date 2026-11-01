param([Parameter(Mandatory)][string]$ToolsRoot,[Parameter(Mandatory)][string]$SourceSave,[int]$ExpectedNational=0,[int]$ExpectedLevel=0)
$ErrorActionPreference='Stop'
$taskManifest=Get-Content -LiteralPath (Join-Path $ToolsRoot 'compiled-tools.json') -Raw -Encoding utf8|ConvertFrom-Json
foreach($taskFile in $taskManifest.files){if((Get-FileHash -LiteralPath $taskFile.path -Algorithm SHA256).Hash.ToLower() -ne $taskFile.sha256){throw ('Compiled inspector input changed: '+$taskFile.path)}}
[void][Reflection.Assembly]::LoadFrom((Join-Path $ToolsRoot 'PKHeX.Core.dll'))
[void][Reflection.Assembly]::LoadFrom((Join-Path $ToolsRoot 'PreparedSpeciesTools.dll'))
$taskBefore=(Get-FileHash -LiteralPath $SourceSave -Algorithm SHA256).Hash
[InspectFiftySave]::Run([IO.Path]::GetFullPath($SourceSave))
if($ExpectedNational -or $ExpectedLevel){
 $taskRaw=[IO.File]::ReadAllBytes([IO.Path]::GetFullPath($SourceSave))
 $taskSav=[PKHeX.Core.SAV9ZA]::new($taskRaw)
 $taskPrimary=$taskSav.GetPartySlotAtIndex(0)
 if($ExpectedNational -and $taskPrimary.Species -ne $ExpectedNational){throw 'Wrong primary species'}
 if($ExpectedLevel -and $taskPrimary.CurrentLevel -ne $ExpectedLevel){throw 'Wrong primary level'}
 if(-not $taskPrimary.ChecksumValid){throw 'Invalid primary checksum'}
}
if((Get-FileHash -LiteralPath $SourceSave -Algorithm SHA256).Hash -ne $taskBefore){throw 'Source changed during read-only inspection'}
