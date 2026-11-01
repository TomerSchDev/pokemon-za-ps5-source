"""Evidence evaluation. Unknown/missing evidence is never truthy success."""
from __future__ import annotations
import math
from pathlib import Path
import re
import statistics
from contracts import digest

FPS = re.compile(r'\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps max ([\d.]+)ms')
PACE = re.compile(r'\[pace\] period ([\d.]+) blocked ([\d.]+) busy ([\d.]+) ms')
CRASH = re.compile(r'FATAL|fatal error|access violation|EXCEPTION_ACCESS_VIOLATION|\*\*\*|device lost|VK_ERROR_DEVICE_LOST|unhandled exception|exception [0-9a-f]{8}', re.I)


def completed_record(record):
    # run_poc reuses a dict across ASLR attempts. Initial records can retain the
    # previous attempt's exit fields; finished_utc is written only after the loop.
    return bool(record and record.get('finished_utc') and record.get('exit_code') is not None)


def runtime_exit_analysis(record, monitor):
    complete = completed_record(record)
    root_pid = monitor.get('current_runtime_pid')
    root_created = monitor.get('current_runtime_created_filetime')
    exits = monitor.get('exits', [])
    current = [e for e in exits if e['pid'] == root_pid or
               (root_created is not None and e['created_filetime'] >= root_created)]
    prior = [e for e in exits if e not in current]
    planned_legacy_stop = complete and record.get('terminated_by_harness') is True
    unexpected = (any(e['exit_code'] != 0 for e in current) and not planned_legacy_stop) or (
        complete and record['exit_code'] != 0 and not planned_legacy_stop)
    return {'legacy_record_complete': complete, 'known': complete or root_created is not None,
            'unexpected_exit': bool(unexpected), 'current_runtime_exits': current, 'prior_attempt_exits': prior}


def png(path):
    from PIL import Image
    with Image.open(path) as probe:
        if probe.format != 'PNG':
            raise ValueError('not a PNG')
        probe.verify()  # reject incomplete writes/CRC corruption before a frame-bound stop
    with Image.open(path) as im:
        if im.format != 'PNG':
            raise ValueError('not a PNG')
        im.load()
        return {'width': im.width, 'height': im.height, 'bytes': Path(path).stat().st_size,
                'sha256': digest(path)}


def shot_path(root, frame):
    return Path(root) / 'build' / 'frames' / f'frame_{frame:05d}.png'


def compare(capture, baseline):
    from PIL import Image, ImageChops
    if digest(baseline['path']) != baseline['sha256']:
        raise ValueError('baseline identity changed')
    with Image.open(capture) as a, Image.open(baseline['path']) as b:
        a, b = a.convert('RGB'), b.convert('RGB')
        if a.size != b.size:
            return {'passed': False, 'reason': 'image dimensions differ', 'capture_size': a.size, 'baseline_size': b.size}
        diff = ImageChops.difference(a, b)
        hist = diff.histogram()
        rmse = math.sqrt(sum(n * (i % 256) ** 2 for i, n in enumerate(hist)) / (a.width * a.height * 3)) / 255
        r, g, bl = diff.split()
        max_channel = ImageChops.lighter(ImageChops.lighter(r, g), bl)
        changed = sum(max_channel.histogram()[baseline['pixel_threshold'] + 1:]) / (a.width * a.height)
        return {'passed': rmse <= baseline['rmse_max'] and changed <= baseline['changed_fraction_max'],
                'normalized_rmse': rmse, 'changed_fraction': changed,
                'rmse_max': baseline['rmse_max'], 'changed_fraction_max': baseline['changed_fraction_max'],
                'pixel_threshold': baseline['pixel_threshold'], 'baseline_sha256': baseline['sha256']}


def percentile(values, p):
    if not values:
        return None
    a = sorted(values)
    n = (len(a) - 1) * p
    lo, hi = math.floor(n), math.ceil(n)
    return a[lo] + (a[hi] - a[lo]) * (n - lo)


def metrics(log, samples):
    fps = [(float(t), int(f), float(v), float(gap)) for t, f, v, gap in FPS.findall(log)]
    periods = [float(p) for p, _, _ in PACE.findall(log)]
    runtimes = [p for s in samples for p in s.get('processes', []) if Path(p['image']).name.lower() == 'lasrecomp.exe']
    # The runtime logs rounded timestamps; weighted interval FPS is an estimate, not simulation speed.
    mean = None
    if len(fps) > 1 and fps[-1][0] > fps[0][0]:
        mean = (fps[-1][1] - fps[0][1]) / (fps[-1][0] - fps[0][0])
    return {'fps_intervals': len(fps), 'presentation_fps_from_rounded_counters_estimate': mean,
            'logged_interval_fps_mean': statistics.mean(r[2] for r in fps) if fps else None,
            'worst_logged_gap_ms': max((r[3] for r in fps), default=None),
            'max_logged_presented_frame': max((r[1] for r in fps), default=None),
            'pace_samples': len(periods),
            'pace_period_ms': {str(p): percentile(periods, p / 100) for p in (50, 90, 95, 99)},
            'pace_sampling_limit': 'present thread only; first/loading/>100ms gaps omitted by runtime',
            'peak_sampled_private_bytes': max((r['private_bytes'] for r in runtimes), default=None),
            'peak_sampled_working_set_bytes': max((r['working_set_bytes'] for r in runtimes), default=None),
            'peak_sampled_system_memory_load_percent': max((s['system']['memory_load_percent'] for s in samples if 'system' in s), default=None),
            'runtime_cpu_seconds_sampled': sum(max(p['cpu_seconds'] for p in runtimes if p['created_filetime'] == ident)
                                              for ident in {p['created_filetime'] for p in runtimes}) if runtimes else None,
            'cpu_usage_percent': None, 'cpu_usage_note': 'cumulative sampled process CPU seconds; final exit interval may be missing',
            'simulation_ticks': None, 'simulation_duration_seconds': None, 'simulated_ticks_per_wall_second': None,
            'runtime_initialization_seconds': None, 'gpu_utilization_percent': None,
            'dedicated_gpu_bytes': None, 'screenshot_overhead_seconds': None,
            'unavailable_reason': 'no verified tick/init/GPU/shot-duration instrumentation; no values inferred from FPS'}


def evaluate(manifest, root, log, run_record, stop_reason, measured):
    checks = []
    def record(name, passed, **detail):
        checks.append({'name': name, 'passed': bool(passed), **detail})
    crashes = [line for line in log.splitlines() if CRASH.search(line)]
    record('runtime_loaded_game', '[gamelib]' in log)
    record('vulkan_started', '[vk]' in log)
    record('no_crash_markers', not crashes, lines=crashes[:30])
    record('planned_completion', stop_reason in ('duration_complete', 'frame_complete', 'natural_exit'))
    if completed_record(run_record) and not run_record.get('terminated_by_harness', False):
        record('runtime_exit_code', run_record['exit_code'] == 0, exit_code=run_record['exit_code'])
    captures = {}
    for frame in manifest['screenshots']['frames']:
        try:
            captures[frame] = png(shot_path(root, frame))
            record(f'capture_{frame}', True, **captures[frame])
        except (OSError, ValueError, SyntaxError) as exc:
            record(f'capture_{frame}', False, reason=str(exc))
    periodic_frames = set()
    if manifest['screenshots']['every']:
        periodic = list((Path(root) / 'build').glob('frame_*.png'))
        valid = 0
        for path in periodic:
            try:
                png(path)
                valid += 1
                match = re.fullmatch(r'frame_([0-9]+)\.png', path.name)
                if match:
                    periodic_frames.add(int(match[1]))
            except (OSError, ValueError, SyntaxError):
                record('periodic_capture_decode', False, path=str(path))
        record('periodic_capture_present', valid > 0, count=valid)
    observed = max([measured.get('max_logged_presented_frame') or 0, *captures.keys(), *periodic_frames])
    if manifest['screenshots']['every']:
        step = manifest['screenshots']['every']
        required = set(range(step, observed + 1, step))
        record('periodic_capture_coverage', required.issubset(periodic_frames),
               observed_through_frame=observed, missing_frames=sorted(required - periodic_frames))
    for a in manifest['assertions']:
        kind = a['kind']
        if kind == 'log_contains':
            record(kind, a['text'] in log, text=a['text'])
        elif kind == 'min_presented_frame':
            record(kind, observed >= a['frame'], expected=a['frame'], observed=observed)
        elif kind == 'screenshot_exists':
            record(kind, a['frame'] in captures, frame=a['frame'])
        elif kind == 'fps_at_least':
            value = measured.get('logged_interval_fps_mean')
            record(kind, value is not None and value >= a['value'], expected=a['value'], observed=value)
    visual = {'status': 'NOT_EVALUATED', 'reason': 'capture delivery does not assert visual correctness'}
    if manifest['screenshots']['mode'] == 'reference':
        b = manifest['screenshots']['baseline']
        if b['frame'] not in captures:
            visual = {'status': 'FAIL', 'reason': 'missing valid capture'}
            record('visual_reference', False)
        else:
            comparison = compare(shot_path(root, b['frame']), b)
            visual = {'status': 'PASS' if comparison['passed'] else 'FAIL', **comparison}
            record('visual_reference', comparison['passed'], comparison=comparison)
    return checks, visual
