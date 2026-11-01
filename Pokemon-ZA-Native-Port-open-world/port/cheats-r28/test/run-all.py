from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[3]
own=Path(__file__).resolve().parents[1]
ref=r'C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc\update-2.0.2-20261025'
route=['240:A:8','420:A:8','900:X:8','960:DOWN:8','1020:A:8']
for i in range(199):route.extend([f'{1200+i*25}:B:6',f'{1212+i*25}:A:6'])
route.extend(['6300:B:8','6400:R:8','6550:A:8','6750:A:8','6900:B:8'])
args=[sys.executable,str(own/'test/run-pc.py'),'--exe',str(own/'work/runtime/lasrecomp.exe'),'--game',ref+'/game','--dll',str(own/'work/pc-build-03/lasgame.dll'),'--save',str(root.parent/'pc-perf-c2/saves/updated/save_0/main'),'--out',str(own/'work/pc-all-01'),'--seconds','300','--cache',str(own/'work/pc-proof-03/cache'),'--input',','.join(route),'--shots','950,1100,1650,3000,5500,6350,6500,6650,6950','--money-after-shot','950','--amount','999','--all-items']
subprocess.run(args,check=True)
