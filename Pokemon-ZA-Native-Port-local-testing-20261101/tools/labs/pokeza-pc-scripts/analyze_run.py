"""Summarize measured ZA Recomp logs and rendered images, without inferring playability."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
from PIL import Image, ImageStat

p = argparse.ArgumentParser()
p.add_argument('run', type=Path)
a = p.parse_args()
root = a.run.resolve()
text = (root / 'stderr.log').read_text(encoding='utf-8', errors='replace')
samples = []
for line in text.splitlines():
    m = re.search(r'\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps max ([\d.]+)ms', line)
    if m:
        samples.append(dict(time_seconds=float(m[1]), frame=int(m[2]),
                            fps=float(m[3]), max_gap_ms=float(m[4])))
images = []
for path in sorted((root / 'build').glob('frame_*.png')):
    item = dict(file=path.name, bytes=path.stat().st_size)
    try:
        with Image.open(path) as im:
            im.load()
            item.update(size=list(im.size), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            stats = ImageStat.Stat(im.convert('RGB').resize((64, 36)))
            item.update(mean_rgb=[round(v, 2) for v in stats.mean],
                        stddev_rgb=[round(v, 2) for v in stats.stddev])
    except Exception as e:
        item['error'] = str(e)
    images.append(item)
summary = dict(run=root.name, fps_samples=samples, frames=images,
               interpretation='FPS samples include rendering and capture overhead. Images require visual review; a nonblack frame does not establish gameplay.',
               diagnostic_lines=[l for l in text.splitlines() if any(t in l.lower() for t in
                   ('fatal', 'exception', 'access violation', 'unimplemented', 'timed out', 'skip:', 'failed', 'unknown svc'))][-100:])
if samples:
    fps = [s['fps'] for s in samples]
    summary['fps_statistics'] = dict(sample_count=len(fps), min=min(fps), max=max(fps),
                                     median=statistics.median(fps), mean=round(statistics.mean(fps), 2))
(root / 'analysis.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k not in ('frames', 'fps_samples')}, indent=2))
print('Captured images:', len(images))
