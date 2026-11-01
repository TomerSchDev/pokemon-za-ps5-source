"""Read-only, bounded performance capture of an already running PPSA91761.

Does not launch, close, replace, or send game input. FPS is reported by the
runtime in aggregate windows, so this cannot calculate per-frame percentiles.
"""
from pathlib import Path
import csv
import json
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import run_r3 as r

ROOT = Path(__file__).resolve().parents[2]
FRAME = re.compile(r'\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps max (\d+)ms level (.*?) \((.*)\)')


def parse_frames(text):
    rows = []
    for match in FRAME.finditer(text):
        sec, frame, fps, maximum, level, detail = match.groups()
        row = dict(runtime_seconds=float(sec), frame=int(frame), fps=float(fps),
                   max_frame_ms=int(maximum), level=level)
        for name, pattern in [('draws', r'(\d+) draws'), ('skipped', r'(\d+) skipped'),
                              ('compiled', r'compile (\d+)'), ('dispatches', r'(\d+) dispatches'),
                              ('gpu_wait_ms', r'wait (\d+)ms'), ('scene_wait_ms', r'scene waits (\d+)ms')]:
            value = re.search(pattern, detail)
            row[name] = int(value[1]) if value else None
        rows.append(row)
    return rows


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 240
    if not 10 <= seconds <= 900:
        raise ValueError('Bound must be 10..900 seconds')
    tag = sys.argv[2] if len(sys.argv) > 2 else 'r13'
    title = sys.argv[3] if len(sys.argv)>3 else 'PPSA91761'
    if title not in {'PPSA91761','PPSA91762'}:raise ValueError('Not an owned native title')
    if not tag.replace('-', '').isalnum(): raise ValueError('Invalid build tag')
    c = r.Console()
    try:
        param = c.read('/mnt/sandbox/'+title+'_000/app0/sce_sys/param.json', 65536)
        if not param:
            raise RuntimeError('Own title sandbox is not mounted; refusing attribution')
        processes = r.eboot_processes()
        if len(processes) != 1:
            raise RuntimeError('Expected one running title, cannot attribute counters')
        pid = r.process_pid(processes[0])
    finally:
        c.close()
    dest = ROOT/'evidence'/('title-'+tag+'-performance-'+r.stamp())
    capture = r.KlogCapture(dest.with_suffix('.klog.log'))
    record = dict(title=title, pid=pid, started_utc=r.utc_now(),
                  requested_seconds=seconds, samples=[], evidence_prefix=str(dest))
    capture.start()
    deadline = time.monotonic()+seconds
    last_print = 0
    try:
        while time.monotonic() < deadline:
            process = next((p for p in r.eboot_processes() if r.process_pid(p) == pid), None)
            record['samples'].append(dict(utc=r.utc_now(), process=process))
            if process is None:
                record['process_exited'] = True
                break
            if time.monotonic()-last_print >= 15:
                text = capture.output.read_text(encoding='utf-8', errors='replace') if capture.output.exists() else ''
                frames = parse_frames(text)
                r.log(f'Performance: PID {pid}, process memory {process.get("memory")} MB; '
                      + (json.dumps(frames[-1]) if frames else 'awaiting fresh frame counter'))
                last_print = time.monotonic()
            time.sleep(min(5, max(0, deadline-time.monotonic())))
    finally:
        capture.stop()
        record['ended_utc'] = r.utc_now()
        record['capture_error'] = capture.error
        text = capture.output.read_text(encoding='utf-8', errors='replace') if capture.output.exists() else ''
        frames = parse_frames(text)
        record['frame_windows'] = frames
        record['shader_wait_events'] = len(re.findall(r'waiting for host:', text))
        record['shader_host_supplied_events'] = len(re.findall(r'host supplied ', text))
        record['limitations'] = 'Aggregate runtime windows, not per-frame telemetry; FPS alone does not verify correct output.'
        dest.with_suffix('.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        if frames:
            with dest.with_suffix('.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(frames[0]))
                writer.writeheader(); writer.writerows(frames)
        r.log('Saved performance capture: '+str(dest))


if __name__ == '__main__':
    main()
