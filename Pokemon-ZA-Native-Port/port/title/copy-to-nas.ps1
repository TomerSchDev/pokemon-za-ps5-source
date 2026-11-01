param(
    [Parameter(Mandatory=$true)][string]$Source,
    [string]$DestinationRoot = '\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port'
)
$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $Source).Path.TrimEnd('\')
if (-not (Test-Path -LiteralPath $DestinationRoot)) {
    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
}
$destPath = Join-Path $DestinationRoot ((Split-Path $sourcePath -Leaf) + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $destPath) { throw "Destination already exists: $destPath" }
New-Item -ItemType Directory -Path $destPath | Out-Null
$rows = @()
foreach ($file in Get-ChildItem -LiteralPath $sourcePath -Recurse -File) {
    $relative = $file.FullName.Substring($sourcePath.Length + 1)
    $target = Join-Path $destPath $relative
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $target
    $originalHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    $copiedHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($originalHash -ne $copiedHash) { throw "SHA-256 mismatch: $relative" }
    $rows += [pscustomobject]@{Path=$relative;Bytes=$file.Length;SHA256=$copiedHash}
}
$report = [pscustomobject]@{Destination=$destPath;Files=$rows.Count;Verified=$true;Manifest=$rows}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $sourcePath 'NAS-COPY-VERIFIED.json') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $sourcePath 'NAS-COPY-VERIFIED.json') -Destination (Join-Path $destPath 'NAS-COPY-VERIFIED.json')
if ((Get-FileHash -LiteralPath (Join-Path $sourcePath 'NAS-COPY-VERIFIED.json')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $destPath 'NAS-COPY-VERIFIED.json')).Hash) { throw 'Manifest verification failed' }
Write-Output "Verified $($rows.Count) files: $destPath"
