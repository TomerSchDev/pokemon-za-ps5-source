$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port'
$sr = 'C:\WINDOWS\TEMP\claude\C--Users-Tomer-Documents-ChatGPT--------PS5-13-60-Pokemon-ZA-Native-Port\c6537e68-bfb3-5bc4-932b-0556e7ba642a\scratchpad\sr'
$cache = 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\hebrew-lab\runs\story-rando-e1-rewind10000-r1'
$in = '240:A:8,420:A:8,900:A:8,1000:A:8,1100:STICK_UP:150,1300:X:8,1450:B:8,1600:STICK_UP:300,1950:STICK_LEFT:120,2100:A:8,2200:A:8,2300:STICK_UP:400,2750:A:8,2850:A:8,2950:A:8,3100:X:8,3250:B:8,3400:STICK_RIGHT:200,3650:STICK_UP:400,4100:A:8,4200:A:8,4300:X:8,4450:R:8,4750:A:8,5050:B:8,5200:B:8'
$shots = '700,850,1000,1150,1350,1500,1800,2100,2400,2700,3000,3150,3500,3900,4200,4350,4800,5300'
"=== swap3 $(Get-Date -Format o)"
& .\zw pc run story-rando-swap56-ch6play-r1 --seconds 230 --save-src "$sr\saves3\x3" --input $in --shot-at $shots --cache-src $cache --mods "$sr\swapmods2" 2>&1 | Select-Object -Last 4
"=== done $(Get-Date -Format o)"
