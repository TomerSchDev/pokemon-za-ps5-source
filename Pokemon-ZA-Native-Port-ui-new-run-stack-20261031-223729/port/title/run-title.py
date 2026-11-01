"""Launch only the new native title; capture startup klog and sandbox evidence."""
import datetime
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import run_r3 as r

ROOT = Path(__file__).resolve().parents[2]
TITLE = sys.argv[2] if len(sys.argv)>2 else 'PPSA91761'
if TITLE not in {'PPSA91761','PPSA91762'}: raise ValueError('Not an owned native title')
APP = f'/mnt/sandbox/{TITLE}_000'
LAUNCH_NAME = 'za_native_title_launch' if TITLE=='PPSA91761' else 'za_native_randomizer_launch'
LAUNCH = r.PAYLOAD_MANAGER + '/loadpayload:/data/pldmgr/payloads/'+LAUNCH_NAME+'/'+LAUNCH_NAME+'.elf'
LAUNCH_LOG = '/data/za-native-title-launch.log' if TITLE=='PPSA91761' else '/data/za-native-randomizer-launch.log'

def main():
    if r.eboot_processes():
        raise RuntimeError('Another app is running; refusing to launch')
    stamp = r.stamp()
    tag = sys.argv[1] if len(sys.argv) > 1 else 'r2'
    if not tag.replace('-', '').isalnum(): raise ValueError('Invalid run tag')
    dest = ROOT / 'evidence' / ('title-' + tag + '-run-' + stamp)
    klog = r.KlogCapture(dest.with_suffix('.klog.log'))
    c = r.Console()
    try:
        deadline = time.monotonic()+55
        while not c.read('/user/app/' + TITLE + '/mount.lnk'):
            if time.monotonic() >= deadline:
                raise RuntimeError('ShadowMount has not registered the new title')
            r.log('Waiting for automatic title registration')
            time.sleep(5)
        klog.start()
        time.sleep(2.5)
        record = dict(title=TITLE, started_utc=r.utc_now(), samples=[], klog=str(klog.output))
        record['launch_response'] = r.http_text(LAUNCH)
        r.log('Launch request sent for ' + TITLE)
        time.sleep(3)
        record['launcher_log'] = (c.read(LAUNCH_LOG) or b'').decode(errors='replace')
        r.log(record['launcher_log'].strip().replace('\n',' | '))
        seen_process = False
        for i in range(36):
            procs = r.eboot_processes()
            try:
                mounted = c.read(APP + '/app0/sce_sys/param.json', 65536) is not None
            except Exception:
                mounted = False
            seen_process |= bool(procs) and mounted
            sample = dict(utc=r.utc_now(), processes=procs, own_sandbox=mounted)
            record['samples'].append(sample)
            r.log(f'title sample {i}: sandbox={mounted}, eboot={procs}')
            if mounted:
                for rel in ('download0/zarecomp/lasrecomp.log',):
                    data = c.read(APP+'/'+rel, 4<<20)
                    if data:
                        dest.with_suffix('.runtime.log').write_bytes(data)
            if not procs and (seen_process or i >= 6):
                record['exited'] = True
                break
            time.sleep(5)
        record['ended_utc'] = r.utc_now()
        record['running_at_end'] = r.eboot_processes()
        dest.with_suffix('.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        r.log('Saved ' + str(dest))
    finally:
        c.close()
        if klog.is_alive():
            # Keep the end of process teardown and any correlated fatal signal.
            time.sleep(2)
            klog.stop()

if __name__ == '__main__':
    main()
