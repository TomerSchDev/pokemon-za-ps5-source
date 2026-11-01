$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port'
$sr = 'C:\WINDOWS\TEMP\claude\C--Users-Tomer-Documents-ChatGPT--------PS5-13-60-Pokemon-ZA-Native-Port\c6537e68-bfb3-5bc4-932b-0556e7ba642a\scratchpad\sr'
$cache = 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\hebrew-lab\runs\story-rando-e1-rewind10000-r1'
$in = @('240:A:8','420:A:8')
foreach ($f in 800..1500) { if ($f % 50 -eq 0) { $in += "$($f):STICK_UP:12"; $in += "$($f+25):A:6" } }
foreach ($f in 1540..4200) { if ($f % 40 -eq 0) { $in += "$($f):A:6" } }
$in += '4400:X:8','4550:A:8','4650:R:8','4950:A:8','5250:B:8','5400:B:8','5600:X:8','5750:R:8','6050:A:8','6350:B:8','6500:B:8'
$shots = (@(600) + (900..6600 | Where-Object { $_ % 300 -eq 0 })) -join ','
"=== swap2 $(Get-Date -Format o)"
& .\zw pc run story-rando-swap56-boundary-r2 --seconds 300 --save-src "$sr\saves3\x1" --input ($in -join ',') --shot-at $shots --cache-src $cache --mods "$sr\swapmods2" 2>&1 | Select-Object -Last 8
"=== done $(Get-Date -Format o)"
