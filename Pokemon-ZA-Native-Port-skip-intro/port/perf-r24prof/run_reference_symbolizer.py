"""Run the provided symbolizer for each measurement on the verified stable-scene files."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main(a):
    state=json.loads((a.out/'state.json').read_text())
    profile=json.loads((a.out/'Profile-functions-and-threads.json').read_text())
    files=[str(a.out/'samples'/n) for n in profile['files']]
    script=Path(__file__).with_name('symbolize_samples.py')
    for phase in state['phases']:
        if not phase['sampling']:continue
        dest=a.out/('reference-symbolized-'+phase['label']+'.json')
        args=[sys.executable,str(script),'--pie',str(a.pie),*files,'--from-ns',str(phase['from_ns']),
              '--to-ns',str(phase['to_ns']),'--top','20','--pairs','20','--json',str(dest)]
        with dest.with_suffix('.log').open('w') as log:
            subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
        print(dest,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--pie',required=True,type=Path)
    main(p.parse_args())
