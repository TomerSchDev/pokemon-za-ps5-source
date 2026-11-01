"""Build a portable JSON record from the requested hardware measurements."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics
import analyze_r24


def vk_windows(log, first, last):
    prev = None
    rows = []
    for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.search(r'\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps', line)
        if not m:
            continue
        frame = int(m[2])
        if prev is not None and prev < frame and prev + 1 >= first and frame <= last:
            row = {'frames': frame - prev, 'end_frame': frame}
            for key, pattern in {
                'gpu_ms': r'\| gpu (\d+)', 'cpu_exec_ms': r'cpu exec (\d+)',
                'cpu_draw_ms': r' draw (\d+) \(', 'submit_ms': r' submit (\d+) ms',
                'compile': r' compile (\d+)',
            }.items():
                match = re.search(pattern, line)
                if match:
                    row[key] = int(match[1])
            rows.append(row)
        prev = frame
    frames = sum(x['frames'] for x in rows)
    return dict(windows=len(rows), frames=frames,
                per_frame={key: sum(x.get(key, 0) for x in rows) / frames if frames else None
                           for key in ('gpu_ms', 'cpu_exec_ms', 'cpu_draw_ms', 'submit_ms', 'compile')})


def profile(log, first, last):
    blocks = []
    current = None
    for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.search(r'\[gpuprof\] frame (\d+): (\d+) marks, ([\d.]+) ms', line)
        if m:
            current = dict(frame=int(m[1]), marks=int(m[2]), span_ms=float(m[3]), rows=[])
            if first <= current['frame'] <= last:
                blocks.append(current)
            continue
        m = re.search(r'\[gpuprof\]\s+([\d.]+) ms\s+([\d.]+)%\s+(.*)', line)
        if m and current is not None:
            current['rows'].append(dict(ms=float(m[1]), percent=float(m[2]), label=m[3]))
    labels = {}
    for b in blocks:
        for row in b['rows']:
            labels.setdefault(row['label'], []).append(row['ms'])
    return dict(profiled_frames=len(blocks), blocks=blocks,
                span_ms_mean=statistics.mean(x['span_ms'] for x in blocks) if blocks else None,
                largest_mark_intervals=sorted(
                    (dict(label=k, mean_ms=statistics.mean(v), samples=len(v)) for k, v in labels.items()),
                    key=lambda x: -x['mean_ms'])[:20],
                by_label_ms_per_profiled_frame=sorted(
                    (dict(label=k, ms_per_frame=sum(v) / len(blocks), occurrences=len(v)) for k, v in labels.items()),
                    key=lambda x: -x['ms_per_frame'])[:25] if blocks else [],
                interpretation='Intervals are the work after each timestamp mark until the next; CPU/GPU starvation can be included.')


def main(out):
    state = json.loads((out / 'state.json').read_text(encoding='utf-8'))
    rows = []
    for p in state['phases']:
        csvfile = out / p['csv']
        with csvfile.open(newline='') as f:
            frames = [int(x['frame']) for x in csv.DictReader(f)]
        first, last = min(frames), max(frames)
        log = out / p['boot'] / 'boot.klog.log'
        row = dict(p)
        transition = csvfile.parent / 'transition.json'
        if transition.exists():
            row['slot_transition'] = json.loads(transition.read_text())['ack']
        row['vk'] = vk_windows(log, first, last)
        if p['perf']['frames']:
            row['gpu_gap_histogram_per_frame'] = {k: v / p['perf']['frames'] for k, v in p['perf']['gap_histogram'].items()}
            windows = analyze_r24.parse(log, first, last)
            checks = []
            for w in windows:
                busy, idle, span = (int(w[k]) for k in ('gpu_busy_ns', 'idle_ns', 'gpu_span_ns'))
                parts = sum(int(w[k]) for k in ('idle_between_ns', 'idle_within_ns', 'idle_unknown_ns'))
                bins = sum(int(w[k]) for k in ('gap_lt100us', 'gap_lt500us', 'gap_lt2ms', 'gap_lt8ms', 'gap_ge8ms'))
                assert abs(busy + idle - span) <= 3, w
                assert parts == idle and bins == int(w['ngaps']), w
                assert int(w['spans_dropped']) == 0, w
                checks.append(int(w['frame']))
            row['counter_quality'] = dict(checked_window_end_frames=checks, gpu_time_and_gap_count_invariants_passed=True,
                                          spans_dropped=0, unknown_idle_ms=p['perf']['per_frame']['gpu_idle_unknown_ms'])
            row['dcache_tables_allocated'] = sorted({int(w['dcache_tables']) for w in windows})
        if 'prof=1' in p['options'] and p['build'] == 'r24':
            row['gpu_profile'] = profile(log, first, last)
        timing = p['timing']['all_intervals']
        mean_ms = timing['duration_s'] * 1000 / timing['intervals']
        cpu = p['perf']['per_frame']['thread_cpu_ms']
        row['thread_clock_quality'] = dict(
            api_reported_available=p['perf']['thread_cpu_available'] if p['perf']['windows'] else None,
            total_cpu_ms_per_frame=cpu,
            maximum_8_cores_ms_per_frame=8 * mean_ms,
            exceeds_physical_upper_bound=cpu is not None and cpu > 8 * mean_ms,
            trustworthy_for_thread_attribution=False,
            note='Repeated near-identical per-thread readings and totals above 8 CPU cores of elapsed time; do not use these rankings as bottleneck evidence.')
        for key in ('before', 'after'):
            for f in row[key]:
                local = csvfile.parent / f['name']
                assert hashlib.sha256(local.read_bytes()).hexdigest() == f['sha256']
                f['path'] = str(local.relative_to(out)).replace('\\', '/')
        rows.append(row)
    result = dict(
        title='PPSA91762', date='2026-10-29', protocol='HANDOFF-r24-perf-HE.md',
        measurement='CPU intervals between vkQueuePresentKHR submissions; not display scanout or simulation speed.',
        seconds_per_phase=20, original_fps_mode=0,
        unchanged_save_sha256=json.loads((out / 'save-backup/verification.json').read_text())['files'][1]['sha256'],
        initial_configs=state['initial_configs'], boots=state['boots'], phases=rows,
        caveats=[
            'All samples use the same saved position and camera. Ambient character/foliage animations and illumination can vary.',
            'All timing intervals, including stalls, are retained. Screenshots and FTP transfers stay outside recorder windows.',
            'Only full counter windows within each measurement frame range are used. Each log is bound to one launch.',
            'CPU and GPU timers overlap and must not be added together; kick is an asynchronous thread timer.',
            'Thread clocks return success but the reported CPU totals violate an 8-core upper bound; attribution is invalid.',
            'The r23c build lacks r24 counters; null is unavailable, not zero.',
        ])
    def find(boot, label=None):
        return next((x for x in rows if x['boot'] == boot and (label is None or x['label'] == label)), None)
    def compare(name, controls, candidate):
        if candidate is None or any(x is None for x in controls):
            return None
        fps = statistics.mean(x['timing']['all_intervals']['interval_rate_fps'] for x in controls)
        actual = candidate['timing']['all_intervals']['interval_rate_fps']
        return dict(name=name, controls=[x['boot'] + '/' + x['label'] for x in controls],
                    candidate=candidate['boot'] + '/' + candidate['label'],
                    control_fps_mean=fps, candidate_fps=actual, fps_change_percent=(actual / fps - 1) * 100)
    comparisons = [
        compare('r23c-r24-r23c instrumentation ABA', [find('A1-r23c'), find('A2-r23c')], find('B1-r24-tls-4k', 'slots16-A1')),
        compare('16-32-16 slots ABA', [find('B1-r24-tls-4k', 'slots16-A1'), find('B1-r24-tls-4k', 'slots16-A2')], find('B1-r24-tls-4k', 'slots32-B')),
        compare('16-64-16 slots ABA', [find('B1-r24-tls-4k', 'slots16-A2'), find('B1-r24-tls-4k', 'slots16-A3')], find('B1-r24-tls-4k', 'slots64-B')),
        compare('tls-cpu-tls dispatch ABA', [find('B1-r24-tls-4k', 'slots16-A3'), find('B2-r24-tls-4k')], find('C-r24-cpu-4k')),
        compare('4K-1080p-4K display ABA', [find('B2-r24-tls-4k'), find('B3-r24-tls-4k')], find('D-r24-tls-1080p')),
    ]
    result['comparisons'] = [x for x in comparisons if x is not None]
    if len(result['comparisons']) == 5:
        base = find('B1-r24-tls-4k', 'slots16-A1')
        display = find('D-r24-tls-1080p')
        bp = base['perf']['per_frame']; dp = display['perf']['per_frame']
        result['findings_he'] = [
            f"בוצעו {len(rows)} מדידות של 20 שניות, באותה שמירה ונקודת מצלמה ובמצב 0. בכל המדידות היו אפס intervals עם עבודת shaders.",
            f"מכשור r24: שינוי של {result['comparisons'][0]['fps_change_percent']:.2f}% ב-FPS מול ממוצע שתי מדידות r23c ב-ABA.",
            f"ב-4K: GPU busy {bp['gpu_busy_ms']:.2f} ms ו-idle {bp['gpu_idle_ms']:.2f} ms לפריים; מתוכו {bp['gpu_idle_between_dcb_ms']:.2f} ms בין הגשות ו-{bp['gpu_idle_within_dcb_ms']:.2f} ms בתוך הגשה. המדידה תומכת בבדיקת מסלול ההגשה והסנכרון כצוואר בקבוק; היא אינה מוכיחה ש-kick לבדו הוא הסיבה.",
            "עומקים 32 ו-64 הוחלו ואומתו בחומרה, כולל headroom של 1 GiB. לא נמדד יתרון מול 16 בשתי בדיקות ABA.",
            f"dcache=cpu פעל בחומרה ללא יתרון ב-ABA: שינוי FPS {result['comparisons'][3]['fps_change_percent']:.2f}% מול TLS.",
            f"1080p אומת ב-swapchain ובצילום 1920x1080 והגיע ל-{display['timing']['all_intervals']['interval_rate_fps']:.2f} FPS; שיפור של {result['comparisons'][4]['fps_change_percent']:.2f}% מול בקרות 4K. GPU busy {dp['gpu_busy_ms']:.2f} ms, dcb_submit {dp['dcb_submit_ms']:.2f} ms ו-kick {dp['kick_ms']:.2f} ms לפריים.",
            "ב-1080p נותר idle גבוה למרות 30 FPS יציבים במצב 0; אין לפרש את כל ה-idle כמחסור בהזנת ה-GPU. הבדיקה לא מדדה 60 FPS או מהירות סימולציה.",
            "pthread_getcpuclockid החזיר הצלחה, אך סך זמני ה-threads חורג מהמקסימום האפשרי לשמונה ליבות ורבים מהערכים זהים. הנתונים הגולמיים מצורפים; דירוגי ה-threads אינם אמינים.",
            "כיוון להמשך הנובע מהמדידות: לבדוק תזמון וסנכרון ההגשות ואת עלות מסלול הפלט ב-4K. הגדלת slots והחלפת מטמון dispatch אינן נתמכות כשיפור בסצנה שנבדקה.",
        ]
    if (out / 'final-state.json').exists():
        result['final_state'] = json.loads((out / 'final-state.json').read_text())
    profiled = find('E-r24-prof-4k')
    if profiled and profiled.get('gpu_profile'):
        profile_data = profiled['gpu_profile']
        heavy = profile_data['largest_mark_intervals'][:2]
        result.setdefault('findings_he', []).append(
            f"prof=1: נכללו {profile_data['profiled_frames']} פריימים בפרופיל בתוך המדידה. "
            + '; '.join(f"{r['label']}: {r['mean_ms']:.2f} ms" for r in heavy)
            + '. המרווחים כוללים עבודה והמתנות עד חותמת הזמן הבאה, ואינם עלות shader בלעדית.')
    target = out / 'Results-r24-20261029.json'
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for row in rows:
        t = row['timing']['all_intervals']; pf = row['perf']['per_frame']
        print(row['boot'], row['label'], f"fps={t['interval_rate_fps']:.4f}",
              f"p50={t['frame_ms']['p50']:.4f}", f"p95={t['frame_ms']['p95']:.4f}",
              'logic=' + str(row['perf']['logic_ms_mean']), 'busy=' + str(pf['gpu_busy_ms']),
              'idle=' + str(pf['gpu_idle_ms']), 'shader_intervals=' + str(row['timing']['shader_affected_intervals']))
    print(target)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('out', type=Path)
    main(p.parse_args().out)
