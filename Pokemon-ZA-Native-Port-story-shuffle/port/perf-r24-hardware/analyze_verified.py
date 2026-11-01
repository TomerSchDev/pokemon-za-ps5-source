"""Fail-closed, offline analysis of r24 / r23c observer measurements.

Requires a recorded console identity, exact artifact hash, verified measurement
receipt and CSV, and one full log boot containing the identity's observer SID.
Never contacts the console. This certifies evidence consistency, not equivalent
camera/scene, scanout FPS, GPU utilization, or causal bottlenecks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'port/preparation-r21-hardware'))
from analyze_suite import read_intervals, TIMER_PATTERNS

BASE_KEYS = ('frame', 'frames', 'logic_ns', 'logic_n', 'present_ns', 'present_n',
             'klock_takes', 'klock_blocked', 'klock_wait_ns', 'dcache_tables',
             'dcb', 'kwords', 'flush_ns', 'dcb_submit_ns', 'kick_ns', 'gaps')
GPU_KEYS = ('spans', 'gpu_span_ns', 'gpu_busy_ns', 'idle_ns', 'idle_between_ns',
            'idle_within_ns', 'idle_unknown_ns', 'ngaps', 'gap_lt100us',
            'gap_lt500us', 'gap_lt2ms', 'gap_lt8ms', 'gap_ge8ms', 'spans_dropped')
HIST = ('gap_lt100us', 'gap_lt500us', 'gap_lt2ms', 'gap_lt8ms', 'gap_ge8ms')
CAVEATS = [
    'FPS is the rate of CPU present-submission intervals, not display scanout or simulation speed.',
    'Source identity binds a recorded remote binary hash, SID, PID and run. It is not an independent rehash of a currently running process.',
    'GPU busy means union of observed submission timestamp spans from first command to ALL_COMMANDS completion; it includes waits/stalls and is not GPU-engine utilization.',
    'GPU spans are harvested on slot reuse, so their report-frame attribution lags work by a depth-dependent amount. Dividing by report frames is approximate.',
    'Gaps across report boundaries are omitted. Failed/unavailable timestamp harvests are silently skipped by runtime; spans_dropped counts buffer overflow only.',
    'Between/within classifications refer to vkQueueSubmit2 groups, not necessarily individual native AGC DCB submissions.',
    'CPU/GPU/profiler timers use different clocks and overlap. Never add them into a critical path or infer starvation from their subtraction.',
    'logic is present-return to first subsequent queue-submit entry, not complete guest game logic time.',
    'kwords is floor(command words / 1024) per report; aggregation loses less than 1024 words per selected report.',
    'Thread CPU is guest-host threads only; unavailable stays null. Top rows cover only windows in which a thread was among the busiest six.',
    'No scene/camera equivalence, visual correctness, long-run stability or causal improvement is established by this analyzer.',
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), sha(raw)


def uint(v):
    return type(v) is int and 0 <= v < 2**64


def fields(text):
    pairs = re.findall(r'(\w+)=(\S*)', text)
    if len({k for k, v in pairs}) != len(pairs):
        raise ValueError('duplicate field')
    return dict(pairs)


def perf_values(text):
    v = fields(text)
    required = set(BASE_KEYS) | {'threads'}
    if not required <= v.keys():
        raise ValueError('missing r24 fields: ' + ','.join(sorted(required - v.keys())))
    for k in BASE_KEYS:
        v[k] = int(v[k])
        if not uint(v[k]):
            raise ValueError('invalid unsigned ' + k)
    if not v['frames'] or v['frames'] > v['frame'] or v['gaps'] not in (0, 1):
        raise ValueError('invalid frame/gaps values')
    if v['klock_blocked'] > v['klock_takes']:
        raise ValueError('klock partition mismatch')
    if v['gaps']:
        if not set(GPU_KEYS) <= v.keys():
            raise ValueError('missing GPU fields')
        for k in GPU_KEYS:
            v[k] = int(v[k])
            if not uint(v[k]):
                raise ValueError('invalid GPU counter ' + k)
        if v['idle_ns'] != sum(v[k] for k in ('idle_between_ns', 'idle_within_ns', 'idle_unknown_ns')):
            raise ValueError('gap partition mismatch')
        # Each disjoint bucket and the total are independently truncated from
        # timestampPeriod * ticks, allowing at most three nanoseconds difference.
        if abs(v['gpu_span_ns'] - v['gpu_busy_ns'] - v['idle_ns']) > 3:
            raise ValueError('span union invariant')
        if sum(v[k] for k in HIST) != v['ngaps']:
            raise ValueError('histogram invariant')
    v['threads'] = int(v['threads'])
    if v['threads'] < -1:
        raise ValueError('invalid threads availability')
    v['top_rows'] = []
    if v['threads'] >= 0:
        if 'thread_cpu_ns' not in v or 'top' not in v:
            raise ValueError('missing thread counters')
        v['thread_cpu_ns'] = int(v['thread_cpu_ns'])
        if not uint(v['thread_cpu_ns']):
            raise ValueError('invalid thread CPU')
        ids = set()
        for item in filter(None, v['top'].split(',')):
            tid, ns, priority, core, entry = item.split(':')
            tid, ns = int(tid), int(ns)
            if not uint(tid) or not uint(ns) or tid in ids or not re.fullmatch('[0-9a-fA-F]+', entry):
                raise ValueError('invalid or duplicate thread row')
            ids.add(tid)
            v['top_rows'].append(dict(id=tid, ns=ns, priority=int(priority), core=int(core), entry='0x'+entry))
        if len(ids) > min(6, v['threads']) or sum(t['ns'] for t in v['top_rows']) > v['thread_cpu_ns']:
            raise ValueError('thread partition invariant')
    return v


def parse_log(text):
    boots = []
    b = None
    pending = {}
    previous = None
    for lineno, line in enumerate(text.splitlines(), 1):
        title = re.search(r'\[za-title-([^\]]+)\] main reached', line)
        if title:
            b = dict(title=title[1], start_line=lineno, sessions=set(), windows=[], controls=[],
                     captures=[], options={}, dispatch=None, timeline=None, modes=[], errors=[])
            boots.append(b)
            pending, previous = {}, None
        if b is None:
            continue  # A log tail without a complete boot is not identity proof.
        for sid in re.findall(r'session_([0-9a-f]{16})(?:/|\b)', line):
            b['sessions'].add(sid)
        cap = re.search(r'session_([0-9a-f]{16})/frame_(\d+)_(\d+)\.png', line)
        if cap:
            b['captures'].append(dict(session=cap[1], frame=int(cap[2]), seq=int(cap[3]), line=lineno))
        opt = re.search(r'\[za-r24-options\] (dcache|gaps|prof|prof_every|mode)=(\S+)', line)
        if opt:
            if opt[1] in b['options']:
                b['errors'].append(dict(line=lineno, reason='duplicate startup option '+opt[1]))
            b['options'][opt[1]] = opt[2]
        dispatch = re.search(r'\[za-r24\] dispatch cache: (.*)', line)
        if dispatch:
            b['dispatch'] = 'cpu' if dispatch[1].startswith('per Cpu ') else 'tls' if dispatch[1].startswith('thread-local ') else 'unknown'
        timeline = re.search(r'\[za-r24\] GPU timeline: (on|off|unavailable)\b', line)
        if timeline:
            b['timeline'] = timeline[1]
        if 'SDL3_PS5_MODE=' in line or 'mode(s)' in line or 'display mode' in line:
            b['modes'].append(dict(line=lineno, text=line))
        control = re.search(r'\[(?:za-r23-slots\] switch|za-r21-prep\] applied|za-r22-immutable\] applied|za-r20b?-submit\] applied)\b(.*)', line)
        if control:
            f = re.search(r'\bframe=(\d+)', control[1])
            if not f:
                b['errors'].append(dict(line=lineno, reason='malformed control record'))
            else:
                b['controls'].append(dict(frame=int(f[1]), line=lineno, text=line))
            pending = {}
        slot = re.search(r'\[za-r23-slots\] active=(\d+) capacity=(\d+) (.*)', line)
        if slot:
            v = fields(slot[3])
            pending['slots'] = dict(active=int(slot[1]), capacity=int(slot[2]), preparation=v.get('preparation'), immutable=v.get('immutable'))
        submit = re.search(r'\[za-r20b?-submit\] profile=([\w-]+) logical=', line)
        if submit:
            pending['submission'] = submit[1]
        prep = re.search(r'\[za-r21-prep\] profile=([\w-]+) flags=(\d+)', line)
        if prep:
            pending['preparation'] = (prep[1], int(prep[2]))
        perf = re.search(r'\[za-r24-perf\] (.*)', line)
        if perf:
            if 'perf' in pending:
                b['errors'].append(dict(line=lineno, reason='duplicate perf before vk report'))
            try:
                pending['perf'] = perf_values(perf[1])
                pending['perf_line'] = lineno
            except (ValueError, TypeError) as exc:
                b['errors'].append(dict(line=lineno, reason='malformed perf: '+str(exc)))
        vk = re.search(r'\[vk\] t=[\d.]+ frame (\d+) [\d.]+ fps', line)
        if vk:
            frame = int(vk[1])
            if previous is not None and frame <= previous:
                b['errors'].append(dict(line=lineno, reason='nonmonotonic frame in boot'))
            perfv = pending.get('perf')
            w = dict(frame=frame, line=lineno, **pending)
            if perfv:
                if perfv['frame'] != frame:
                    b['errors'].append(dict(line=lineno, reason='perf/vk frame mismatch'))
                if previous is not None and perfv['frames'] != frame - previous:
                    b['errors'].append(dict(line=lineno, reason='missing/overlapping perf counter interval'))
                w['start'] = frame - perfv['frames'] + 1
                w['frames'] = perfv['frames']
            elif previous is not None:
                w['start'], w['frames'] = previous + 1, frame - previous
            w['timers'] = {k: int(m[1]) for k, pattern in TIMER_PATTERNS.items() if (m := re.search(pattern, line))}
            b['windows'].append(w)
            previous, pending = frame, {}
    for boot in boots:
        boot['sessions'] = sorted(boot['sessions'])
    return boots


def summarize(windows):
    frames = sum(w['frames'] for w in windows)
    v = [w['perf'] for w in windows]
    totals = {k: sum(r[k] for r in v) for k in BASE_KEYS if k not in ('frame', 'frames', 'gaps', 'dcache_tables')}
    totals['frames'] = frames
    out = dict(whole_windows=len(v), covered_frames=frames, counter_totals=totals,
               logic_ms_mean=totals['logic_ns']/totals['logic_n']/1e6 if totals['logic_n'] else None,
               present_ms_mean=totals['present_ns']/totals['present_n']/1e6 if totals['present_n'] else None,
               cpu_ms_per_report_frame={k: totals[k]/frames/1e6 for k in ('logic_ns','present_ns','klock_wait_ns','flush_ns','dcb_submit_ns','kick_ns')},
               dcb_submissions_per_report_frame=totals['dcb']/frames,
               kwords_per_report_frame=totals['kwords']/frames,
               dcache_tables_range=[min(r['dcache_tables'] for r in v),max(r['dcache_tables'] for r in v)],
               gpu=None, threads=None)
    if {r['gaps'] for r in v} == {1}:
        g = {k: sum(r[k] for r in v) for k in GPU_KEYS}
        out['gpu'] = dict(counter_totals=g,
            observed_span_union_ms_per_report_frame=g['gpu_busy_ns']/frames/1e6,
            observed_gaps_ms_per_report_frame=g['idle_ns']/frames/1e6,
            between_vk_submit_groups_ms_per_report_frame=g['idle_between_ns']/frames/1e6,
            within_vk_submit_group_ms_per_report_frame=g['idle_within_ns']/frames/1e6,
            unknown_group_ms_per_report_frame=g['idle_unknown_ns']/frames/1e6,
            union_fraction_of_observed_span=g['gpu_busy_ns']/g['gpu_span_ns'] if g['gpu_span_ns'] else None,
            histogram={k:g[k] for k in HIST}, spans_dropped=g['spans_dropped'])
    available = [r for r in v if r['threads'] >= 0]
    ts = {}
    for r in available:
        for t in r['top_rows']:
            row = ts.setdefault(t['id'], dict(id=t['id'], cpu_ns=0, top_windows=0, appearances=[]))
            row['cpu_ns'] += t['ns']; row['top_windows'] += 1
            row['appearances'].append(dict(frame=r['frame'], priority=t['priority'], core=t['core'], entry=t['entry']))
    if available:
        af = sum(r['frames'] for r in available)
        out['threads'] = dict(available_windows=len(available), unavailable_windows=len(v)-len(available),
            available_frames=af, cpu_ms_per_available_report_frame=sum(r['thread_cpu_ns'] for r in available)/af/1e6,
            busiest=sorted(ts.values(),key=lambda t:-t['cpu_ns']))
    out['vk_profiler_per_report_frame'] = {k:sum(w['timers'][k] for w in windows)/frames for k in TIMER_PATTERNS if all(k in w['timers'] for w in windows)}
    out['window_lines'] = [w['line'] for w in windows]
    return out


def analyze(identity_path, receipt_path, csv_path, klog_path, expected_sha, expected_slots=16,
            expected_gaps=1, expected_dcache='tls', min_seconds=19.85):
    result = dict(status='invalid', caveats=CAVEATS)
    try:
        identity, ih = load(identity_path)
        receipt, rh = load(receipt_path)
        phase = None
        if 'measurement' in receipt:
            if receipt.get('completed') is not True:
                raise ValueError('phase incomplete')
            phase = receipt
            receipt = receipt['measurement']
        if identity.get('client') not in ('r24', 'r23c') or identity.get('backup_verified') is not True:
            raise ValueError('identity client/backup not verified')
        sid = identity.get('session')
        if not isinstance(sid,str) or not re.fullmatch('[0-9a-f]{16}',sid) or not uint(identity.get('pid')) or not identity['pid'] or not identity.get('run'):
            raise ValueError('invalid SID/PID/run')
        if not re.fullmatch('[0-9a-f]{64}',expected_sha) or identity.get('eboot_sha256') != expected_sha:
            raise ValueError('artifact hash differs from expected')
        if phase is not None:
            if any(phase.get(k) != identity[k] for k in ('session','pid','run')) or phase.get('fps_mode') != 0:
                raise ValueError('phase identity/FPS context mismatch')
            if ('client' in phase and phase['client'] != identity['client']) or ('eboot_sha256' in phase and phase['eboot_sha256'] != expected_sha):
                raise ValueError('phase client/artifact mismatch')
        ack = receipt['ack']
        seq = ack.get('seq')
        if not uint(seq) or not seq or ack.get('session') != sid or ack.get('op') != 'measure' or ack.get('result') != 'complete':
            raise ValueError('invalid measurement acknowledgement')
        name = f'measure_{seq}.csv'
        if ack.get('file') != name or Path(csv_path).name != name:
            raise ValueError('measurement filename/sequence mismatch')
        rows, timing = read_intervals(csv_path)
        files = receipt.get('files',[])
        if len(files) != 1 or files[0].get('name') != name or files[0].get('readback_verified') is not True or files[0].get('sha256') != timing['csv_sha256'] or files[0].get('bytes') != timing['csv_bytes']:
            raise ValueError('CSV not bound to exact verified receipt')
        for i,row in enumerate(rows):
            if any(not uint(v) for v in row.values()) or (i and row['frame'] != rows[i-1]['frame']+1):
                raise ValueError('invalid/noncontiguous CSV')
        result.update(identity=identity, identity_sha256=ih, receipt_sha256=rh, timing=timing)
        if timing['fps_modes'] != [0]:
            raise ValueError('measurement contains nonzero FPS mode')
        if timing['shader_affected_intervals']:
            raise ValueError('measurement contains shader work')
        if any(r['represented_interval'] or r['submitted_interval'] != 1 for r in rows):
            raise ValueError('measurement includes represented/unsubmitted interval')
        if timing['all_intervals']['duration_s'] < min_seconds:
            raise ValueError('measurement shorter than requested minimum')
        lo,hi = timing['csv_frames']
        if phase is not None:
            for key in ('before','after'):
                cap = phase.get(key,{})
                ca = cap.get('ack',{})
                if ca.get('session') != sid or ca.get('op') != 'snapshot' or ca.get('result') != 'saved' or not uint(ca.get('seq')):
                    raise ValueError('invalid '+key+' snapshot acknowledgement')
                match = re.fullmatch(r'frame_([1-9][0-9]*)_'+str(ca['seq'])+r'\.png',ca.get('file',''))
                if not match or (key=='before' and int(match[1])>=lo-1) or (key=='after' and int(match[1])<=hi):
                    raise ValueError(key+' snapshot overlaps measurement interval')
                cf = cap.get('files',[])
                if len(cf)!=1 or cf[0].get('name')!=ca['file'] or cf[0].get('readback_verified') is not True:
                    raise ValueError('unverified '+key+' snapshot file')
                cr = (Path(csv_path).parent/ca['file']).read_bytes()
                if cf[0].get('sha256') != sha(cr) or cf[0].get('bytes') != len(cr):
                    raise ValueError(key+' snapshot hash/size mismatch')
        raw = Path(klog_path).read_bytes()
        boots = parse_log(raw.decode('utf-8',errors='replace'))
        matches = [b for b in boots if sid in b['sessions']]
        if len(matches) != 1:
            raise ValueError('missing/ambiguous log boot for exact SID')
        b = matches[0]
        if identity['client'] not in b['title'] or b['sessions'] != [sid]:
            raise ValueError('title/SID boot mismatch or multiple sessions')
        if b['errors']:
            raise ValueError('malformed log boot: '+json.dumps(b['errors']))
        if not b['windows'] or max(w['frame'] for w in b['windows']) < hi:
            raise ValueError('log does not extend beyond measured CSV')
        if any(lo-1 <= e['frame'] <= hi for e in b['controls']):
            raise ValueError('control transition overlaps measurement interval')
        if any(lo-1 <= c['frame'] <= hi for c in b['captures']):
            raise ValueError('capture overlaps measurement interval')
        inside = [w for w in b['windows'] if w.get('start',-1) >= lo and w['frame'] <= hi]
        if not inside:
            raise ValueError('no complete profiler window within measurement')
        for w in inside:
            slots = w.get('slots',{})
            if slots.get('active') != expected_slots or slots.get('capacity') not in (16,64) or slots.get('preparation') != '0' or slots.get('immutable') != '0' or w.get('preparation') != ('baseline',0) or w.get('submission') != 'batch4':
                raise ValueError('runtime slot/preparation/submission state mismatch')
        result.update(log_sha256=sha(raw), log_bytes=len(raw), boot_title=b['title'], boot_start_line=b['start_line'],
                      options=b['options'], dispatch=b['dispatch'], timeline=b['timeline'], display_log=b['modes'],
                      slot_depth=expected_slots, whole_window_frames=sum(w['frames'] for w in inside),
                      coverage_fraction=sum(w['frames'] for w in inside)/len(rows))
        if identity['client'] == 'r24':
            if b['dispatch'] != expected_dcache:
                raise ValueError('actual dispatch mode mismatch')
            if any('perf' not in w or w['perf']['gaps'] != expected_gaps for w in inside):
                raise ValueError('missing r24 report or actual gaps setting mismatch')
            if b['timeline'] != ('on' if expected_gaps else 'off'):
                raise ValueError('actual GPU timeline mode mismatch')
            result['r24'] = summarize(inside)
        else:
            result['r24'] = None
        result['status'] = 'verified'
    except (ValueError, TypeError, KeyError, OSError, IndexError) as exc:
        result['reason'] = str(exc)
    return result


def compare_aba(a, b, c, scene_tag):
    if any(x.get('status') != 'verified' for x in (a,b,c)):
        raise ValueError('ABA requires three verified measurements')
    if any(x.get('comparison_eligible') is False for x in (a,b,c)):
        raise ValueError('ABA includes a phase with known external interference')
    if not scene_tag:
        raise ValueError('explicit human/visual scene tag required')
    if len({x['identity']['run'] for x in (a,b,c)}) != 1:
        raise ValueError('different randomizer runs')
    if a['identity']['eboot_sha256'] != c['identity']['eboot_sha256'] or a['slot_depth'] != c['slot_depth'] or a['options'] != c['options']:
        raise ValueError('A return does not restore binary/slots/options')
    stats = [x['timing']['all_intervals'] for x in (a,b,c)]
    n = stats[0]['intervals']+stats[2]['intervals']
    sec = stats[0]['duration_s']+stats[2]['duration_s']
    pooled = n/sec
    return dict(scene_tag=scene_tag, baseline_pooled_fps=pooled, candidate_fps=stats[1]['interval_rate_fps'],
                candidate_gain_pct=100*(stats[1]['interval_rate_fps']/pooled-1),
                baseline_return_drift_pct=100*(stats[2]['interval_rate_fps']/stats[0]['interval_rate_fps']-1),
                warning='Scene tag is an external attestation, not a computed equality check; this is one short ABA observation.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('identity','receipt','csv','klog'):
        p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--expected-sha',required=True)
    p.add_argument('--slots',type=int,choices=(8,16,32,64),default=16)
    p.add_argument('--gaps',type=int,choices=(0,1),default=1)
    p.add_argument('--dcache',choices=('tls','cpu'),default='tls')
    p.add_argument('--min-seconds',type=float,default=19.85)
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    result=analyze(a.identity,a.receipt,a.csv,a.klog,a.expected_sha,a.slots,a.gaps,a.dcache,a.min_seconds)
    text=json.dumps(result,indent=2)+'\n'
    if a.out:a.out.write_text(text,encoding='utf-8')
    print(text)
    raise SystemExit(0 if result['status']=='verified' else 2)


if __name__=='__main__':main()
