"""Offline verification of the bounded PS5 compiler test; run under WSL."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('evidence', type=Path)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root/'evidence/randomizer-shaders-20261028-041124Z/manifest.json').read_text())
    hardware = json.loads((a.evidence/'hardware.json').read_text())
    rows = [json.loads(line) for line in (a.evidence/'results.jsonl').read_text().splitlines()]
    assert rows[0]['build'] == 'r18b'
    assert rows[-1] == dict(type='complete', passed=41, total=41, exit_code=0)
    compiles = [r for r in rows if r['type'] == 'compile']
    assert len(compiles) == 41 and all(r['passed'] == 1 for r in compiles)
    hashes = []
    for iteration in range(3):
        for entry in manifest:
            path = a.evidence/f'{iteration:02d}-{entry["source"]}.spv'
            value = digest(path)
            assert value == entry['spv_sha256'], path
            hashes.append(dict(name=path.name, sha256=value, matches_host=True))
    assert digest(a.evidence/'00-smoke.comp.spv') == digest(a.evidence/'00-recovery.comp.spv')
    spv = sorted(a.evidence.glob('*.spv'))
    assert len(spv) == 38
    validations = []
    for path in spv:
        proc = subprocess.run(['spirv-val', '--target-env', 'vulkan1.3', str(path)],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, (path, proc.stderr)
        validations.append(dict(name=path.name, passed=True))
    names = {entry['source'] for entry in manifest}
    graphics = [r for r in compiles if r['name'] in names]
    cold = [r['compile_ms'] for r in graphics if r['iteration'] == 0]
    warm = [r['compile_ms'] for r in graphics if r['iteration'] > 0]
    heaps = [r for r in rows if r['type'] == 'heap']
    klog = (a.evidence/'console.klog.log').read_text(errors='replace')
    result = dict(
        run=hardware['run'], pid=rows[0]['pid'], api_cases_passed=41,
        captured_shader_hash_matches=hashes, spirv_validations=validations,
        validator=subprocess.check_output(['spirv-val', '--version'], text=True).strip(),
        first_pass_ms=dict(total=sum(cold), minimum=min(cold), maximum=max(cold)),
        repeat_pass_ms=dict(minimum=min(warm), maximum=max(warm), median=statistics.median(warm)),
        heap=dict(peak_mapped_bytes=max(h['peak_mapped_bytes'] for h in heaps),
                  libc_fallbacks=max(h['libc_fallbacks'] for h in heaps),
                  after_graphics_iterations=[h['mapped_bytes'] for h in heaps if h['phase']=='iteration_complete']),
        controlled_close=hardware['controlled_close'], original_probe_restored=hardware['restored'],
        capture_contains_fatal_signal='A user thread receives a fatal signal' in klog,
        capture_contains_sigsys='SIGSYS' in klog,
        game_integration=False, gpu_pipeline_performance_measured=False,
        caveats=['Small captured shader sample, not full game coverage.',
                 'Heap mapped bytes are not total RSS or live allocations.',
                 'Controlled host termination; native title exit path remains unverified.',
                 'Compile timing excludes file I/O, GPU pipeline creation and the running game.'])
    assert result['original_probe_restored']
    (a.evidence/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in
          ('captured_shader_hash_matches','spirv_validations','validator')}, indent=2))

if __name__ == '__main__':
    main()
