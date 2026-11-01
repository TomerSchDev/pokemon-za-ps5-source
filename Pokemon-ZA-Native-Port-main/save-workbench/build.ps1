param([string]$DotnetExe = 'dotnet', [switch]$Publish)
$ErrorActionPreference='Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
$zaVendor=Join-Path $PSScriptRoot 'vendor\PKHeX'
if(-not (Test-Path -LiteralPath $zaVendor)){$zaVendor=Join-Path $PSScriptRoot 'deps\PKHeX'}
& $DotnetExe build (Join-Path $zaVendor 'PKHeX.Core\PKHeX.Core.csproj') -c Release --nologo -p:SourceRevisionId=8e3eb3d47bb496746c3eaa9d160329d295a5e2e5
if($LASTEXITCODE -ne 0){throw 'PKHeX.Core build failed'}
$zaThirdParty=Join-Path $PSScriptRoot 'third-party'
New-Item -ItemType Directory -Path $zaThirdParty -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $zaVendor 'PKHeX.Core\bin\Release\net10.0\PKHeX.Core.dll') -Destination $zaThirdParty
$zaProject=Join-Path $PSScriptRoot 'src\ZaSaveWorkbench.csproj'
if($Publish){ & $DotnetExe publish $zaProject -c Release -r win-x64 --self-contained true -p:PublishTrimmed=false -o (Join-Path $PSScriptRoot 'publish') --nologo }
else { & $DotnetExe build $zaProject -c Release --nologo }
if($LASTEXITCODE -ne 0){throw 'Workbench build failed'}
