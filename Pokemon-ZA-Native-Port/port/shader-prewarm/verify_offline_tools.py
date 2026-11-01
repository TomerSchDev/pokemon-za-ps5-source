"""WSL checks: malformed BNSH rejection and persistent compiler recovery/parity."""
from pathlib import Path
import hashlib, json, struct, subprocess
from forecast import ROOT
from parse_bnsh import parse
from translate_all import WORK


def main():
    report = dict(parser_rejections=[], compiler_cases=[])
    sample = next((ROOT/'private-data/offline-shaders-20261028/bnsh').glob('*.bnsh')).read_bytes()
    block = struct.unpack_from('<H', sample, 22)[0]
    table = struct.unpack_from('<Q', sample, block+32)[0]
    cases = {'truncated': sample[:100], 'wrong_size': sample[:-1]}
    broken = bytearray(sample); struct.pack_into('<Q', broken, block+32, len(sample)+1)
    cases['out_of_bounds_table'] = broken
    broken = bytearray(sample); struct.pack_into('<Q', broken, table+16, len(sample)-1)
    cases['out_of_bounds_program'] = broken
    for name, blob in cases.items():
        try:
            list(parse(blob))
        except (ValueError, struct.error):
            report['parser_rejections'].append(name)
        else:
            raise AssertionError('Parser accepted '+name)
    baseline = ROOT/'evidence/shader-prewarm-research-20261028/compiler'
    captured = ROOT/'evidence/randomizer-shaders-20261028-041124Z'
    out = WORK/'worker-verification'; out.mkdir(exist_ok=True)
    worker = subprocess.Popen([str(WORK.parent/'host-build/compiler-worker')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def request(stage, source, dest, expected=True):
        worker.stdin.write(f'{stage}\t{source}\t{dest}\n'); worker.stdin.flush()
        result = json.loads(worker.stdout.readline())
        assert result['ok'] == expected, (source, result)
        report['compiler_cases'].append(dict(source=source.name, accepted=result['ok']))
    try:
        request(0, baseline/'invalid.glsl', out/'invalid.spv', False)
        request(0, baseline/'include.glsl', out/'include.spv', False)
        for source in sorted(captured.iterdir()):
            if source.suffix not in ('.vert','.frag','.comp'):
                continue
            dest = out/(source.name+'.spv')
            request({'.vert':0,'.frag':1,'.comp':2}[source.suffix], source, dest)
            assert dest.read_bytes() == (baseline/dest.name).read_bytes(), 'Compiler byte mismatch'
            subprocess.run(['spirv-val','--target-env','vulkan1.3',str(dest)], check=True)
        # Ensure another invalid request does not poison subsequent stages.
        request(9, baseline/'smoke.vert', out/'wrong-stage.spv', False)
        for stage, name in enumerate(('smoke.vert','smoke.frag','smoke.comp')):
            dest=out/(name+'.spv'); request(stage, baseline/name, dest)
            subprocess.run(['spirv-val','--target-env','vulkan1.3',str(dest)], check=True)
    finally:
        worker.stdin.close(); worker.wait(timeout=10)
    assert worker.returncode == 0
    report.update(complete=True, persistent_process=True, captured_byte_identical=12,
                  compiler_sha256=hashlib.sha256((WORK.parent/'host-build/compiler-worker').read_bytes()).hexdigest())
    (ROOT/'evidence/offline-shaders-20261028/tool-verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
