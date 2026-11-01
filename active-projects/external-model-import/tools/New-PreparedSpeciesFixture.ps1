param(
 [Parameter(Mandatory)][string]$WorkspaceRoot,
 [Parameter(Mandatory)][string]$InputCheck,
 [Parameter(Mandatory)][string]$ToolsRoot,
 [Parameter(Mandatory)][string]$SourceSave,
 [Parameter(Mandatory)][string]$OutputSave,
 [Parameter(Mandatory)][ushort]$National,
 [Parameter(Mandatory)][ushort]$InternalSpecies,
 [Parameter(Mandatory)][byte]$Level,
 [Parameter(Mandatory)][ushort]$Move1,
 [Parameter(Mandatory)][ushort]$Move2
)
$ErrorActionPreference='Stop'
$taskLab=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$taskWork=[IO.Path]::GetFullPath($WorkspaceRoot)
if([IO.Path]::GetDirectoryName($taskWork) -ne $taskLab -or [IO.Path]::GetFileName($taskWork) -notmatch '^pc-species-validation-fresh-[A-Za-z0-9-]+$'){throw 'Use a declared fresh workspace'}
if((Get-Content -LiteralPath (Join-Path $taskWork 'RESTART.json') -Raw|ConvertFrom-Json).old_execution_plan_superseded -ne $true){throw 'Fresh restart declaration missing'}
$taskOutput=[IO.Path]::GetFullPath($OutputSave)
if(-not $taskOutput.StartsWith($taskWork+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Output outside fresh workspace'}
if(Test-Path -LiteralPath $taskOutput){throw 'Private output exists; use a new version'}
foreach($taskStart in @($taskOutput,$taskWork,[IO.Path]::GetFullPath($ToolsRoot))) {
 $taskWalk=$taskStart
 while($taskWalk){
  if((Test-Path -LiteralPath $taskWalk) -and ((Get-Item -LiteralPath $taskWalk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Linked fixture input/output is forbidden'}
  $taskParent=[IO.Directory]::GetParent($taskWalk);if(-not $taskParent){break};$taskWalk=$taskParent.FullName
 }
}
$taskCheck=Get-Content -LiteralPath $InputCheck -Raw -Encoding utf8|ConvertFrom-Json
if($taskCheck.status -ne 'READY_FOR_SCOPED_BUILD' -or $taskCheck.allowed_to_start -ne $true -or @($taskCheck.blockers).Count -gt 0){throw 'Current-input check is blocked'}
if([IO.Path]::GetFullPath($taskCheck.workspace) -ne $taskWork){throw 'Workspace differs'}
if((Get-FileHash -LiteralPath (Join-Path $taskLab 'Pokemon-ZA-Native-Port/docs/testing/BUILD_DEPENDENCY_MAP.json')).Hash.ToLower() -ne $taskCheck.map_sha256){throw 'Dependency map changed'}
$taskPins=@{}
foreach($taskFile in $taskCheck.files){
 $taskPath=[IO.Path]::GetFullPath($taskFile.path)
 if(-not $taskFile.approved_current -or -not $taskFile.authority -or $taskFile.current_counterpart -ne $taskPath){throw 'Unresolved current input'}
 if((Get-FileHash -LiteralPath $taskPath).Hash.ToLower() -ne $taskFile.sha256){throw ('Input changed: '+$taskPath)}
 $taskPins[$taskPath]=$true
}
$taskManifestPath=Join-Path $ToolsRoot 'compiled-tools.json'
$taskManifest=Get-Content -LiteralPath $taskManifestPath -Raw -Encoding utf8|ConvertFrom-Json
foreach($taskRequired in @($SourceSave,$PSCommandPath,$taskManifestPath,(Join-Path $ToolsRoot 'PKHeX.Core.dll'),(Join-Path $ToolsRoot 'PreparedSpeciesTools.dll'))){
 if(-not $taskPins.ContainsKey([IO.Path]::GetFullPath($taskRequired))){throw ('Fixture input omitted: '+$taskRequired)}
}
foreach($taskFile in $taskManifest.files){if((Get-FileHash -LiteralPath $taskFile.path).Hash.ToLower() -ne $taskFile.sha256){throw ('Compiled input changed: '+$taskFile.path)}}
[void][Reflection.Assembly]::LoadFrom((Join-Path $ToolsRoot 'PKHeX.Core.dll'))
[void][Reflection.Assembly]::LoadFrom((Join-Path $ToolsRoot 'PreparedSpeciesTools.dll'))
[PreparedSpeciesFixture]::Run([IO.Path]::GetFullPath($SourceSave),$taskOutput,$National,$InternalSpecies,$Level,$Move1,$Move2)
