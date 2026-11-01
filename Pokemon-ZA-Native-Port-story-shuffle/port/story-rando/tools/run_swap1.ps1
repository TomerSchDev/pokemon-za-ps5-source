$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port'
$sr = 'C:\WINDOWS\TEMP\claude\C--Users-Tomer-Documents-ChatGPT--------PS5-13-60-Pokemon-ZA-Native-Port\c6537e68-bfb3-5bc4-932b-0556e7ba642a\scratchpad\sr'
$cache = 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\hebrew-lab\runs\story-rando-e1-rewind10000-r1'
$in = @('240:A:8','420:A:8')
foreach ($f in 800..1500) { if ($f % 50 -eq 0) { $in += "$($f):STICK_UP:12"; $in += "$($f+25):A:6" } }
$in += '1600:ZL:4200'
foreach ($f in 1600..5800) { if ($f % 40 -eq 0) { $in += "$($f):A:6" } }
foreach ($f in 5820..6400) { if ($f % 60 -eq 0) { $in += "$($f):A:6" } }
$in += '6500:X:8','6650:R:8','6950:A:8','7250:B:8','7400:B:8','7600:X:8','7750:R:8','8050:A:8','8350:B:8'
$shots = (@(600) + (900..8400 | Where-Object { $_ % 300 -eq 0 })) -join ','
"=== swap1 $(Get-Date -Format o)"
& .\zw pc run story-rando-swap56-boundary-r1 --seconds 420 --save-src "$sr\saves3\x1" --input ($in -join ',') --shot-at $shots --cache-src $cache --mods "$sr\swapmods" --env LARECOMP_LOG_FILES=1 2>&1 | Select-Object -Last 12
"=== done $(Get-Date -Format o)"
