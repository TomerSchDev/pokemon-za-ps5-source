$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port'
$sr = 'C:\WINDOWS\TEMP\claude\C--Users-Tomer-Documents-ChatGPT--------PS5-13-60-Pokemon-ZA-Native-Port\c6537e68-bfb3-5bc4-932b-0556e7ba642a\scratchpad\sr'
while (-not (Select-String -Path "$sr\run_exps.log" -Pattern '=== done' -Quiet)) { Start-Sleep 5 }
$cache = 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\hebrew-lab\runs\story-rando-e1-rewind10000-r1'
$input_ = '240:A:8,420:A:8,750:STICK_UP:60,900:X:8,1000:A:8,1100:R:8,1400:A:8,1700:B:8'
$shots = '600,800,1050,1200,1410,1500,2200,3000'
$runs = @(
  @('story-rando-e0-control-r2', 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\hebrew-lab\saves\city-orig', $null),
  @('story-rando-e4-ch2flags-r1', "$sr\saves\e4-ch2flags", $null),
  @('story-rando-e5-ch4partial-vanilla-r1', "$sr\saves\e5-ch2-ch4partial", $null),
  @('story-rando-e6-ch4partial-reordered-r1', "$sr\saves\e5-ch2-ch4partial", "$sr\mods")
)
foreach ($r in $runs) {
  "=== $($r[0]) $(Get-Date -Format o)"
  if ($r[2]) { & .\zw pc run $r[0] --seconds 200 --save-src $r[1] --input $input_ --shot-at $shots --cache-src $cache --mods $r[2] 2>&1 | Select-Object -Last 12 }
  else { & .\zw pc run $r[0] --seconds 200 --save-src $r[1] --input $input_ --shot-at $shots --cache-src $cache 2>&1 | Select-Object -Last 12 }
}
"=== done $(Get-Date -Format o)"
