"""Describe measured log intervals; these are not per-frame percentiles/1% lows."""
import argparse
import json
from pathlib import Path
import re
import statistics

p = argparse.ArgumentParser()
p.add_argument('run', type=Path)
p.add_argument('--start', type=float, required=True)
p.add_argument('--end', type=float, required=True)
a = p.parse_args()
raw = (a.run / 'stderr.log').read_text(encoding='utf-8', errors='replace')
rows = []
captured = False
for line in raw.splitlines():
    if '[vk] saved ' in line:
        captured = True
    m = re.search(r'\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps max ([\d.]+)ms', line)
    if not m:
        continue
    row = dict(seconds=float(m[1]), frame=int(m[2]), fps=float(m[3]), max_gap_ms=float(m[4]), capture_in_interval=captured)
    captured = False
    if a.start <= row['seconds'] <= a.end:
        rows.append(row)
clean = [r for r in rows if not r['capture_in_interval']]
if not clean:
    raise SystemExit('No measured intervals in range')
fps = [r['fps'] for r in clean]
result = dict(run=a.run.name, range_seconds=[a.start, a.end], intervals=len(clean),
              excluded_capture_intervals=len(rows)-len(clean),
              fps_interval_mean=round(statistics.mean(fps), 2),
              fps_interval_median=statistics.median(fps),
              fps_interval_min=min(fps), fps_interval_max=max(fps),
              largest_reported_gap_ms=max(r['max_gap_ms'] for r in clean),
              caveat='Approximately two-second log intervals, not individual frame-time percentiles; no 1% low claim.',
              samples=clean)
(a.run / 'benchmark.json').write_text(json.dumps(result, indent=2))
print(json.dumps({k:v for k,v in result.items() if k != 'samples'}, indent=2))
