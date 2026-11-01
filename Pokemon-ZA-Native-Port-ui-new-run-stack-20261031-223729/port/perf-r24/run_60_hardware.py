"""Execute TEST-60FPS-4K-r24-HE.md using the existing scoped observer."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import sys
import time

import hardware_run as h
import analyze_r24
from analyze import stats
from summarize_hardware import vk_windows

INI = h.SANDBOX + '/download0/zarecomp/larecomp.ini'


def logger(out):
    raw = out / 'all.klog.log'
    events = out / 'events.jsonl'
    with socket.create_connection((h.r.HOST, h.r.KLOG_PORT), timeout=5) as peer, raw.open('w', encoding='utf-8') as f, events.open('w', encoding='utf-8') as ev:
        peer.settimeout(.5); pending = b''; started = time.monotonic(); lines = 0
        print('Timestamped logger started', flush=True)
        while not (out / 'stop-logger').exists():
            try:
                data = peer.recv(65536)
            except socket.timeout:
                continue
            if not data:
                raise RuntimeError('Console closed klog connection')
            pending += data
            *complete, pending = pending.split(b'\n')
            now = time.time_ns()
            for item in complete:
                if time.monotonic() - started < 2:
                    continue
                line = item.decode('utf-8', 'replace').rstrip('\r')
                f.write(line + '\n'); lines += 1
                if re.search(r'\[za-performance-r16\]|\[za-title-|\[za-paths\]|\[paths\]|\[za-r24-options\]', line):
                    ev.write(json.dumps(dict(line=lines, received_host_unix_ns=now, text=line)) + '\n')
            f.flush(); ev.flush()
    h.write(out / 'logger.json', dict(lines=lines, error=None))


def replace_ini(c, state, wanted, restoring=False):
    cur = h.owned(c, state)
    if not restoring:
        assert not cur.get('continued'), 'INI must be installed before continue'
    old = c.read(INI, 65536)
    record = dict(at=h.r.utc_now(), virtual_cwd='/download0/zarecomp', path=INI,
                  old=old.decode() if old is not None else None,
                  new=wanted.decode() if wanted is not None else None, before_continue=not cur.get('continued'))
    if old != wanted:
        parent=h.SANDBOX+'/download0';directory=parent+'/zarecomp'
        c.ftp.cwd(parent);lines=[];c.ftp.retrlines('LIST',lines.append);c.ftp.cwd('/')
        listing=next(x for x in lines if x.endswith(' zarecomp'))
        assert listing.startswith('drwxr-xr-x '), listing
        record['directory_before']=listing
        record['temporary_write_permission']=c.ftp.sendcmd('SITE CHMOD 777 '+directory)
        try:
            if wanted is not None:
                stage = INI + '.staged-60-' + str(time.time_ns())
                c.store(stage, wanted); assert c.read(stage, 65536) == wanted
            if old is not None:
                c.ftp.rename(INI, INI + '.before-60-' + str(time.time_ns()))
            if wanted is not None:
                c.ftp.rename(stage, INI)
        finally:
            record['permission_restore']=c.ftp.sendcmd('SITE CHMOD 755 '+directory)
        c.ftp.cwd(parent);lines=[];c.ftp.retrlines('LIST',lines.append);c.ftp.cwd('/')
        record['directory_after']=next(x for x in lines if x.endswith(' zarecomp'))
        assert record['directory_after'].startswith('drwxr-xr-x ')
        assert record['directory_after'].split()[2:4]==listing.split()[2:4]
        record['directory_permissions_restored']=True
    assert c.read(INI, 65536) == wanted
    record['readback_verified'] = True
    h.write(h.OUT / cur['label'] / ('ini-restored.json' if restoring else 'ini.json'), record)
    return record


def adopt(a):
    statefile = h.OUT / 'state.json'; assert not statefile.exists()
    c = h.r.Console()
    try:
        h.title(c)
        ps = h.r.eboot_processes(); assert len(ps) == 1
        installed = c.sha256(h.APP + '/eboot.bin')
        assert installed in {v[1] for v in h.BUILDS.values()}
        sid = h.client.status(c.ftp)['session']; run = json.loads(c.read(h.DATA + '/active.json', 4096))['id']
        h.backup(c, run, h.OUT / 'save-backup')
        previous = c.read(INI, 65536)
        initial = {name: c.read(h.APP + '/' + name, 4096).decode() for name in h.CONFIGS}
        assert initial['performance-options.txt'] == 'optimized\n' and initial['slot-depth-options.txt'] == '16\n'
        perf = c.read(h.APP + '/perf-r24-options.txt', 4096)
        # The new handoff explicitly requires the r24 file to be absent at completion.
        initial['perf-r24-options.txt'] = None
        folder = h.client.BASE + '/session_' + sid
        seqs = [int(m[1]) for n in c.listing(folder) if (m := re.search(r'ack_(\d+)\.json', n))]
        mailbox = c.read(h.APP + '/observer-command.txt', 1024)
        if mailbox:
            parts = mailbox.decode().split()
            if parts[0] == sid:
                seqs.append(int(parts[1]))
        cur = dict(label='initial-owned-title', build=next(k for k,v in h.BUILDS.items() if v[1] == installed),
                   sha256=installed, session=sid, pid=h.r.process_pid(ps[0]), run=run, options=perf.decode() if perf else '',
                   seq=max(seqs, default=0) + 100, klog_offset=0, at=h.r.utc_now(), backup_verified=True, continued=True)
        state = dict(boots=[cur], phases=[], current=cur, initial_configs=initial,
                     initial_ini=previous.decode() if previous is not None else None,
                     initial_perf_content=perf.decode() if perf else None)
        h.write(statefile, state); h.write(h.OUT / cur['label'] / 'identity.json', cur)
        h.verify_save(c, state)
        print(json.dumps(cur), flush=True)
    finally:
        c.close()


def rows_from(path):
    import csv
    with path.open(newline='') as f:
        return [{k:int(v) for k,v in x.items()} for x in csv.DictReader(f)]


def analyze_phase(out, log, mode):
    csvfile = next(out.glob('measure_*.csv')); rows = rows_from(csvfile)
    groups = []; group = []
    for row in rows:
        if group and group[-1]['mode'] != row['mode']:
            groups.append(group); group = []
        group.append(row)
    if group:
        groups.append(group)
    segments = []
    for group in groups:
        first, last = group[0]['frame'], group[-1]['frame']
        windows = analyze_r24.parse(log, first, last)
        segments.append(dict(mode=group[0]['mode'], frame_range=[first,last], first_now_ns=group[0]['now_ns'],
                             last_now_ns=group[-1]['now_ns'], timing=stats(group),
                             over_16_7_ms=sum(r['dt_ns'] > 16700000 for r in group),
                             perf=analyze_r24.summarize(windows), vk=vk_windows(log,first,last),
                             shader_affected_intervals=sum(bool((r['shader_before']&0xffffffff) or (r['shader_after']&0xffffffff) or r['shader_before']!=r['shader_after']) for r in group)))
    selected = [r for r in rows if r['mode'] == mode]
    assert selected, ('Requested mode missing', mode, segments)
    first_time = rows[0]['now_ns'] - rows[0]['dt_ns']
    changes = []
    for previous, current in zip(rows,rows[1:]):
        if previous['mode'] != current['mode']:
            changes.append(dict(from_mode=previous['mode'], to_mode=current['mode'], first_frame=current['frame'],
                                first_now_ns=current['now_ns'], previous_now_ns=previous['now_ns'],
                                measurement_elapsed_s=(current['now_ns']-first_time)/1e9,
                                boundary_interval_ms=current['dt_ns']/1e6))
    return dict(csv=csvfile.name, all_modes=sorted({r['mode'] for r in rows}), fps_modes=sorted({r['mode'] for r in rows}), requested_mode=mode,
                all_intervals=stats(rows), requested_mode_only=stats(selected),
                requested_mode_over_16_7_ms=sum(r['dt_ns']>16700000 for r in selected),
                segments=segments, transitions=changes,
                mode1_observed_duration_s=sum(r['dt_ns'] for r in rows if r['mode']==1)/1e9,
                measurement_clock_origin_ns=first_time,
                mode_boundary_caveat='CSV mode is the state at the end of each interval; one interval at a transition can straddle modes. All intervals are retained.')


def sample(a, state):
    c = h.r.Console()
    try:
        cur = h.owned(c, state); out = h.OUT / cur['label'] / a.label; out.mkdir(exist_ok=False)
        h.command(c,state,out,'fps',0,expected={'requested'})
        before = h.command(c,state,out,'snapshot',expected={'saved'}); h.retire(c,state,before,out)
        started = time.time_ns()
        arm = h.command(c,state,out,'fps',a.fps_mode,expected={'requested'})
        # Arm after the screenshot and archive transfer, so the automatic fallback cannot expire before recording.
        measure = h.command(c,state,out,'measure',20,expected={'complete'})
        completed = time.time_ns()
        after = h.command(c,state,out,'snapshot',expected={'saved'}); h.retire(c,state,after,out)
        log = h.OUT / cur['label'] / 'boot.klog.log'
        log.write_bytes((h.OUT/'all.klog.log').read_bytes()[cur['klog_offset']:])
        analysis = analyze_phase(out,log,a.fps_mode)
        assert analysis['all_intervals']['duration_s'] >= 19.85
        assert a.fps_mode == 1 or analysis['all_modes'] == [0]
        events = [json.loads(line) for line in (h.OUT/'events.jsonl').read_text().splitlines()]
        events = [x for x in events if started <= x['received_host_unix_ns'] <= completed and '[za-performance-r16]' in x['text']]
        armed = next((x for x in events if 'user armed' in x['text']),None)
        fallback = next((x for x in events if 'sustained slow clean' in x['text']),None)
        result = dict(label=a.label,boot=cur['label'],build=cur['build'],options=cur['options'],
                      display=cur['display'],internal=cur['internal'],requested_fps_mode=a.fps_mode,
                      csv=str((out/analysis['csv']).relative_to(h.OUT)),analysis=analysis,
                      arm_receipt=arm,measurement_receipt=measure,before=before,after=after,
                      request_started_host_unix_ns=started,events=events,
                      arm_to_fallback_log_receipt_s=(fallback['received_host_unix_ns']-armed['received_host_unix_ns'])/1e9 if armed and fallback else None,
                      fallback_timing_note='Exact observed fallback frame and title clock are in analysis.transitions; arm-to-fallback duration uses host log receipt times and includes network delivery uncertainty.',
                      save_check=h.verify_save(c,state))
        h.write(out/'phase.json',result);state['phases'].append(result);h.write(h.OUT/'state.json',state)
        selected_segment=next(x for x in analysis['segments'] if x['mode']==a.fps_mode)
        print(json.dumps(dict(boot=cur['label'],label=a.label,fps_modes=analysis['all_modes'],
                              selected_timing=analysis['requested_mode_only'],mode1_observed_duration_s=analysis['mode1_observed_duration_s'],
                              transitions=analysis['transitions'],render_thread=selected_segment['vk'],
                              perf_per_frame=selected_segment['perf']['per_frame'],
                              arm_to_fallback_log_receipt_s=result['arm_to_fallback_log_receipt_s'])),flush=True)
    finally:
        c.close()


def main(a):
    h.OUT = a.out.resolve(); h.OUT.mkdir(parents=True,exist_ok=True)
    if a.op == 'log':
        logger(h.OUT); return
    if a.op == 'adopt':
        adopt(a); return
    if a.op == 'launch':
        a.dcache='tls';a.prof=0
        h.main(a)
        state=json.loads((h.OUT/'state.json').read_text())
        cur=state['current'];cur['continued']=False;cur['display']=a.mode or '3840x2160'
        cur['internal']=cur['display'] if a.scale=='match' else '1920x1080' if a.scale=='1x' else '2880x1620'
        h.write(h.OUT/'state.json',state)
        c=h.r.Console()
        try:
            wanted=None if a.scale=='match' else ('resolution = '+a.scale+'\n').encode()
            replace_ini(c,state,wanted)
        finally:c.close()
        h.write(h.OUT/'state.json',state);h.write(h.OUT/cur['label']/'identity.json',cur)
        return
    state=json.loads((h.OUT/'state.json').read_text())
    if a.op == 'sample':
        sample(a,state);return
    if a.op == 'restore-ini':
        c=h.r.Console()
        try:
            original=state['initial_ini'];replace_ini(c,state,original.encode() if original is not None else None,True)
            state['ini_restored_at']=h.r.utc_now();h.write(h.OUT/'state.json',state)
        finally:c.close()
        return
    h.main(a)
    if a.op == 'ready':
        state=json.loads((h.OUT/'state.json').read_text());state['current']['continued']=True;h.write(h.OUT/'state.json',state)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('op',choices=('log','adopt','launch','ready','sample','close','restore-ini','restore-config','inspect'))
    p.add_argument('--label');p.add_argument('--build',choices=h.BUILDS,default='r24')
    p.add_argument('--mode',choices=('1920x1080',));p.add_argument('--scale',choices=('match','1x','1.5x'),default='match')
    p.add_argument('--fps-mode',type=int,choices=(0,1),default=0)
    main(p.parse_args())
