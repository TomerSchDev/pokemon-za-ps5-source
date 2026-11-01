param(
 [Parameter(Mandatory)][string]$WorkspaceRoot,
 [Parameter(Mandatory)][string]$OutputRoot,
 [Parameter(Mandatory)][string]$InputCheck,
 [Parameter(Mandatory)][string]$PkhexPath,
 [switch]$ValidateOnly
)
$ErrorActionPreference='Stop'
function Assert-NoLinks([string]$Path) {
 $taskWalk=[IO.Path]::GetFullPath($Path)
 while($taskWalk) {
  if(Test-Path -LiteralPath $taskWalk) {
   $taskItem=Get-Item -LiteralPath $taskWalk -Force
   if($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint){throw ('Linked path is not allowed: '+$taskWalk)}
  }
  $taskParent=[IO.Directory]::GetParent($taskWalk)
  if(-not $taskParent){break}
  $taskWalk=$taskParent.FullName
 }
}
$taskLab=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$taskWork=[IO.Path]::GetFullPath($WorkspaceRoot)
Assert-NoLinks $taskWork
if([IO.Path]::GetDirectoryName($taskWork) -ne $taskLab -or [IO.Path]::GetFileName($taskWork) -notmatch '^pc-species-validation-fresh-[A-Za-z0-9-]+$'){throw 'Use a declared fresh species workspace directly under the lab'}
$taskRestart=Get-Content -LiteralPath (Join-Path $taskWork 'RESTART.json') -Raw|ConvertFrom-Json
if($taskRestart.old_execution_plan_superseded -ne $true){throw 'Fresh restart declaration missing'}
$taskOut=[IO.Path]::GetFullPath($OutputRoot)
Assert-NoLinks $taskOut
if(-not $taskOut.StartsWith($taskWork+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Output outside fresh workspace'}
if(Test-Path -LiteralPath $taskOut){throw 'Use a new compiler output directory'}
$taskCheck=Get-Content -LiteralPath $InputCheck -Raw -Encoding utf8|ConvertFrom-Json
if($taskCheck.status -ne 'READY_FOR_SCOPED_BUILD' -or $taskCheck.allowed_to_start -ne $true -or @($taskCheck.blockers).Count -gt 0){throw 'Current-input check is blocked'}
if([IO.Path]::GetFullPath($taskCheck.workspace) -ne $taskWork){throw 'Input-check workspace differs'}
$taskMap=Join-Path $taskLab 'Pokemon-ZA-Native-Port/docs/testing/BUILD_DEPENDENCY_MAP.json'
if((Get-FileHash -LiteralPath $taskMap -Algorithm SHA256).Hash.ToLower() -ne $taskCheck.map_sha256){throw 'Dependency map changed'}
$taskSupplement=Get-Content -LiteralPath $taskCheck.dependency_supplement.path -Raw -Encoding utf8|ConvertFrom-Json
if((Get-FileHash -LiteralPath $taskCheck.dependency_supplement.path -Algorithm SHA256).Hash.ToLower() -ne $taskCheck.dependency_supplement.sha256){throw 'Dependency supplement changed'}
$taskMapped=@{}
foreach($taskNode in $taskSupplement.nodes){if($taskNode.path){$taskMapped[[IO.Path]::GetFullPath($taskNode.path)]=$true}}
$taskPins=@{}
foreach($taskFile in $taskCheck.files) {
 $taskPath=[IO.Path]::GetFullPath($taskFile.path)
 Assert-NoLinks $taskPath
 if($taskPath -match '[\\/]pc-fifty-20261031-r1[\\/]|[\\/]prepared-suite-20261101-r1[\\/]' -or [IO.Path]::GetExtension($taskPath) -eq '.pyc'){throw ('Retired input path: '+$taskPath)}
 if(-not $taskMapped.ContainsKey($taskPath) -or -not $taskFile.approved_current -or -not $taskFile.authority -or $taskFile.current_counterpart -ne $taskPath){throw ('Unresolved current input: '+$taskPath)}
 if((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLower() -ne $taskFile.sha256){throw ('Input changed: '+$taskPath)}
 $taskPins[$taskPath]=$taskFile
}
$taskPk=[IO.Path]::GetFullPath($PkhexPath)
$taskCs=Join-Path $PSScriptRoot 'PreparedSpeciesTools.cs'
$taskRefs=@(Get-ChildItem -LiteralPath (Join-Path $PSHOME 'ref') -Filter '*.dll'|Select-Object -ExpandProperty FullName)+@($taskPk)
foreach($taskRequired in @($taskCs,$PSCommandPath,(Join-Path $PSHOME 'pwsh.exe'))+$taskRefs) {
 if(-not $taskPins.ContainsKey([IO.Path]::GetFullPath($taskRequired))){throw ('Compiler input omitted from closure: '+$taskRequired)}
}
if($ValidateOnly){@{boundary_valid=$true;inputs_valid=$true;compiled=$false;output=$taskOut}|ConvertTo-Json;return}
[void][IO.Directory]::CreateDirectory($taskOut)
$taskLocalPk=Join-Path $taskOut 'PKHeX.Core.dll'
Copy-Item -LiteralPath $taskPk -Destination $taskLocalPk
if((Get-FileHash -LiteralPath $taskLocalPk).Hash -ne (Get-FileHash -LiteralPath $taskPk).Hash){throw 'Dependency copy differs'}
[void][Reflection.Assembly]::LoadFrom($taskLocalPk)
$taskDll=Join-Path $taskOut 'PreparedSpeciesTools.dll'
Add-Type -Path $taskCs -ReferencedAssemblies $taskRefs -OutputAssembly $taskDll
$taskFiles=@($taskCs,$taskPk,$taskLocalPk,$taskDll)+$taskRefs|Select-Object -Unique|ForEach-Object {
 $f=Get-Item -LiteralPath $_
 @{path=$f.FullName;sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLower();bytes=$f.Length}
}
$taskManifest=@{schema_version=3;compiled_before_queue=$true;game_launched=$false;files=$taskFiles;input_check=[IO.Path]::GetFullPath($InputCheck);input_check_sha256=(Get-FileHash -LiteralPath $InputCheck).Hash.ToLower();source='Reviewed current single-case generator and read-only inspector; source-owned pinned PKHeX'}
$taskManifest|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $taskOut 'compiled-tools.json') -Encoding utf8
@{compiled=$true;tools_root=$taskOut;manifest=(Join-Path $taskOut 'compiled-tools.json');game_launched=$false}|ConvertTo-Json
