$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port'
$sr = 'C:\WINDOWS\TEMP\claude\C--Users-Tomer-Documents-ChatGPT--------PS5-13-60-Pokemon-ZA-Native-Port\c6537e68-bfb3-5bc4-932b-0556e7ba642a\scratchpad\sr'
$input_ = '240:A:8,420:A:8,750:STICK_UP:60,900:X:8,1000:A:8,1100:R:8,1400:A:8,1700:B:8'
$shots = '600,800,1050,1200,1410,1500,2200,3000'
$runs = @(
  @('story-rando-e0-control-r1', 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\hebrew-lab\saves\city-orig'),
  @('story-rando-e1-rewind10000-r1', "$sr\saves\e1-rewind10000"),
  @('story-rando-e2-jump30100-r1', "$sr\saves\e2-jump30100"),
  @('story-rando-e3-jump50200-r1', "$sr\saves\e3-jump50200")
)
foreach ($r in $runs) {
  "=== $($r[0]) $(Get-Date -Format o)"
  & .\zw pc run $r[0] --seconds 200 --save-src $r[1] --input $input_ --shot-at $shots 2>&1 | Select-Object -Last 15
}
"=== done $(Get-Date -Format o)"
