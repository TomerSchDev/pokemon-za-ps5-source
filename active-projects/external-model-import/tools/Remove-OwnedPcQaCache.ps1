$ErrorActionPreference = 'Stop'
$projectBase = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$cachePath = [IO.Path]::GetFullPath((Join-Path $projectBase 'pc-model-tests'))
if ($cachePath -ne (Join-Path $projectBase 'pc-model-tests') -or -not $cachePath.StartsWith($projectBase + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Cache path escaped the project.' }
$nasQa = '\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\PS5-13.60\species-lab\import-all-20261030\qa\all-pokemon-20261030-r2'
foreach ($marker in @('retests\final-retests-r1-results.json','exact-form-probes-r1\results.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $nasQa $marker) -PathType Leaf)) { throw ('PC QA still incomplete: ' + $marker) }
}
$drivers = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'lasrecomp.exe' -and $_.ExecutablePath -and $_.ExecutablePath.StartsWith($cachePath + '\', [StringComparison]::OrdinalIgnoreCase)) -or
    ($_.Name -in @('python.exe','py.exe') -and $_.CommandLine -and $_.CommandLine -match 'PS5-13\.60[\\/].*import-all-20261030[\\/]tools[\\/]' -and $_.CommandLine -match 'run_pc_(?:nas|wide|second_lane|final_retests|exact_form_probes|material_pilot)\.py')
}
if ($drivers) { throw ('Owned QA processes still running: ' + (($drivers.ProcessId) -join ', ')) }
$cacheItem = Get-Item -LiteralPath $cachePath -Force
if ($cacheItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Cache root is a reparse point.' }
$nestedLinks = @(Get-ChildItem -LiteralPath $cachePath -Force -Recurse -Attributes ReparsePoint)
if ($nestedLinks.Count) { throw ('Inspect unexpected nested reparse points: ' + (($nestedLinks.FullName) -join ', ')) }
$chatRoot = 'C:\Users\Tomer\Documents\ChatGPT'
$garbledName = [Text.Encoding]::GetEncoding(1255).GetString([Text.Encoding]::UTF8.GetBytes('פריצות'))
$garbledRoot = [IO.Path]::GetFullPath((Join-Path $chatRoot $garbledName))
$failedRun = [IO.Path]::GetFullPath((Join-Path $garbledRoot 'PS5-13.60\pc-model-tests\runs\pc-native-baseline-r22'))
if (-not $failedRun.StartsWith($garbledRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($failedRun) -ne 'pc-native-baseline-r22') { throw 'Failed-run cleanup target escaped its exact location.' }
$failedRunExists = Test-Path -LiteralPath $failedRun
if ($failedRunExists) {
    $failedItem = Get-Item -LiteralPath $failedRun -Force
    if ($failedItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Failed-run location is a link.' }
    $failedLinks = @(Get-ChildItem -LiteralPath $failedRun -Force -Recurse -Attributes ReparsePoint)
    if ($failedLinks.Count) { throw 'Failed-run directory contains an unexpected nested link.' }
    $unexpected = @(Get-ChildItem -LiteralPath $failedRun -Force | Where-Object Name -notin @('build','save','cache','larecomp.ini'))
    if ($unexpected.Count -or (Test-Path -LiteralPath (Join-Path $failedRun 'run.json'))) { throw 'Failed-run directory differs from the previously inspected pre-launch failure.' }
}
$removed = [Collections.Generic.List[string]]::new()
$freeBefore = (Get-PSDrive -Name C).Free
$asciiLink = Join-Path $env:LOCALAPPDATA 'Temp\pokemon-za-qa-20261031'
if (Test-Path -LiteralPath $asciiLink) {
    $link = Get-Item -LiteralPath $asciiLink -Force
    if (-not ($link.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'ASCII QA alias is not a link.' }
    $linkTargets = @($link.Target)
    if ($linkTargets.Count -ne 1 -or [IO.Path]::GetFullPath($linkTargets[0]) -ne $cachePath) { throw 'ASCII QA alias points somewhere unexpected.' }
    # Remove only the alias entry, without recursive traversal.
    Remove-Item -LiteralPath $asciiLink -Force
    $removed.Add($asciiLink)
}
Remove-Item -LiteralPath $cachePath -Recurse -Force
if (Test-Path -LiteralPath $cachePath) { throw 'Temporary PC QA cache still exists.' }
$removed.Add($cachePath)

if ($failedRunExists) {
    Remove-Item -LiteralPath $failedRun -Recurse -Force
    $removed.Add($failedRun)
}
$freeAfter = (Get-PSDrive -Name C).Free
$outputDirectory = Join-Path $projectBase 'pc-check-results'
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$record = [ordered]@{
    finished_utc = [DateTime]::UtcNow.ToString('o')
    removed_owned_paths = $removed.ToArray()
    canonical_models_and_game_data_remain_on_NAS = $true
    console_untouched = $true
    C_free_bytes_before = $freeBefore
    C_free_bytes_after = $freeAfter
    C_free_space_delta_bytes = $freeAfter - $freeBefore
}
$record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $outputDirectory ('temporary-cache-cleanup-' + $stamp + '.json')) -Encoding utf8
$record | ConvertTo-Json -Depth 4
