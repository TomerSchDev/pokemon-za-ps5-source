param([string]$SourceSave,[string]$Manifest,[string]$OutputSave,[int]$PartyStart=0,[string]$CoordinatesFrom='',[switch]$CoordinatesOnly,[int]$TemplateSlot=0,[switch]$KeepNativeControl,[int]$InitialLevelOverride=0)
$ErrorActionPreference='Stop'
$taskPk='\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\PS5-13.60\species-lab\pilot\tools\savecheck\bin-out\PKHeX.Core.dll'
[void][Reflection.Assembly]::LoadFrom($taskPk)
$taskRefs=@(Get-ChildItem -LiteralPath (Join-Path $PSHOME 'ref') -Filter '*.dll' | Select-Object -ExpandProperty FullName)+@($taskPk)
$taskSource=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'ConsoleFiftyFixture.cs.txt') -Raw -Encoding UTF8
Add-Type -TypeDefinition $taskSource -ReferencedAssemblies $taskRefs
[ConsoleFiftyFixture]::Run([string[]]@($SourceSave,$Manifest,$OutputSave,$PartyStart.ToString(),$CoordinatesFrom,$CoordinatesOnly.IsPresent.ToString(),$TemplateSlot.ToString(),$KeepNativeControl.IsPresent.ToString(),$InitialLevelOverride.ToString()))
