#!/usr/bin/env python3
"""Build the existing native-probe template with the isolated filesystem overlay.
Offline inputs only. No console access, game data, installation or title reservation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--source-manifest-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--title', type=int, default=91780)
    a = p.parse_args()
    repo, sources, out = (x.resolve() for x in (a.repo, a.sources, a.out))
    native = Path('/home/tomer/ps5-za-native')
    if out.exists() or native not in out.parents or a.title != 91780:
        raise ValueError('new native output and provisional side title 91780 required')
    def turn(minimum=30):
        if any(not os.environ.get('PC_TEST_' + k) for k in ('AGENT', 'TICKET', 'TOKEN')):
            raise ValueError('canonical PC lease environment required')
        r = subprocess.run([sys.executable, repo / 'workbench/zw.py', 'pc-queue', 'check',
                            '--agent', os.environ['PC_TEST_AGENT'], '--ticket', os.environ['PC_TEST_TICKET']],
                           capture_output=True, text=True, check=True)
        state = json.loads(r.stdout)
        if state.get('must_yield') or (state.get('seconds_to_yield') is not None and state['seconds_to_yield'] < minimum):
            raise RuntimeError('probe requires another bounded PC turn')
        return state
    turn(90)
    source_manifest = sources / 'SOURCE-SHA256.json'
    if sha(source_manifest) != a.source_manifest_sha256:
        raise ValueError('probe source manifest differs')
    source_pins = json.loads(source_manifest.read_text(encoding='utf-8-sig'))
    for name, pin in source_pins.items():
        if Path(name).name != name or sha(sources / name) != pin:
            raise ValueError('probe source differs: ' + name)
    template = repo / 'native-probe'
    sdk = native / 'PS5_Vulkan/.deps/native/ps5-payload-sdk'
    zlib = native / 'PS5_Vulkan/.deps/native/zlib/root'
    if (zlib / '.source-version').read_text().strip() != '1.3.2' or not (sdk / 'bin/prospero-lld').is_file():
        raise ValueError('cached pinned SDK/zlib unavailable; no download attempted')
    if sha(template / 'runtime/libc.prx') != 'e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036':
        raise ValueError('existing native-probe libc differs')
    out.mkdir()
    evidence = out / 'evidence'; evidence.mkdir()
    log = (evidence / 'build.log').open('x', encoding='utf-8')
    env = {**os.environ, 'PS5_CLANG': '/usr/bin/clang-21', 'CXX': '/usr/bin/clang++-21', 'BUILD_JOBS': '2'}
    for key in ('APP_INCLUDE_PATHS','APP_STATIC_ARCHIVES','APP_RUNTIME_MODULES','PACBREW_PACKAGES','PACBREW_INCLUDE_PATHS','PACBREW_STATIC_ARCHIVES'):
        env[key] = ''
    def run(command, target=None):
        state = turn()
        print('PROBE RUN', Path(str(command[0])).name, flush=True)
        stream = Path(target).open('wb') if target is not None else log
        try:
            with subprocess.Popen(list(map(str, command)), cwd=out, env=env, stdout=stream, stderr=log, start_new_session=True) as proc:
                try:
                    rc = proc.wait(timeout=max(1, state['seconds_to_yield'] - 25) if state.get('seconds_to_yield') is not None else None)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try: proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                    raise RuntimeError('owned probe build stopped for FIFO handoff')
                if rc:
                    raise RuntimeError('probe command failed: ' + str(rc) + ': ' + str(command[0]))
        finally:
            if target is not None: stream.close()
            log.flush()
    app = out / 'native-probe'
    app.mkdir()
    for folder in ('tools','tooling','runtime'):
        shutil.copytree(template / folder, app / folder)
    (app / 'sce_sys').mkdir(); (app / 'src').mkdir()
    for name in ('icon0.png','pic0.dds','pic1.dds','snd0.at9'):
        shutil.copy2(template / 'sce_sys' / name, app / 'sce_sys' / name)
    for name in ('demo_renderer.cpp','demo_renderer.hpp','probe.hpp'):
        shutil.copy2(template / 'src' / name, app / 'src' / name)
    for source, dest in [('native_main.cpp','main.cpp'),('fs_probe.cpp','probe.cpp'),('fs_probe.hpp','fs_probe.hpp')]:
        shutil.copy2(sources / source, app / 'src' / dest)
    shutil.copy2(source_manifest, evidence / 'SOURCE-SHA256.json')
    shutil.copy2(__file__, evidence / 'executed-builder.py')
    param = json.loads((template / 'sce_sys/param.json').read_text())
    param.update(titleId='PPSA91780', conceptId='91780', contentId='UP9000-PPSA91780_00-ZAFSPROBE0000000')
    param['localizedParameters']['en-US']['titleName'] = 'ZA Save FS Probe'
    (app / 'sce_sys/param.json').write_text(json.dumps(param, indent=2) + '\n')
    # Complete private dependency copies make the unchanged bootstrap a no-op.
    (app / '.deps/native').mkdir(parents=True)
    run(['cp','-a','--reflink=auto',sdk,app / '.deps/native/ps5-payload-sdk'])
    (app / '.deps/native/zlib').mkdir()
    run(['cp','-a','--reflink=auto',zlib,app / '.deps/native/zlib/root'])
    nm = sdk / 'bin/llvm-nm'
    providers = {}
    for library in sorted((sdk / 'target/lib').glob('*.so')):
        result = subprocess.run([nm,'-D','--defined-only',library], capture_output=True, text=True)
        if result.returncode: continue
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 3: providers.setdefault(fields[-1], []).append(library.name)
    ordinary = lambda name: [x for x in providers.get(name, []) if 'libkernel_sys' not in x]
    required = ['open','close','read','write','stat','fstat','mkdir','unlink','rmdir','fsync','clock_gettime','getpid']
    optional = {name: bool(ordinary(name)) for name in ('lstat','symlink','readlink','getdents')}
    audit = {'required': {x: providers.get(x, []) for x in required}, 'optional': {x: {'providers':providers.get(x, []),'enabled':flag} for x,flag in optional.items()}}
    (evidence / 'sdk-import-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    if any(not ordinary(x) for x in required):
        raise ValueError('required API missing from ordinary title SDK imports; no raw-syscall bypass')
    definitions = ['ZA_SAVE_FS_PROBE_TITLE_NUM=91780'] + ['ZA_PROBE_HAS_' + name.upper() + '=' + str(int(flag)) for name,flag in optional.items()]
    env['APP_DEFINITIONS'] = ' '.join(definitions)
    fixtures = out / 'host-fixtures'; fixtures.mkdir()
    harness = out / 'host-main.cpp'
    harness.write_text('#include "fs_probe.hpp"\nint main(int argc,char** argv){return argc==2?za::save_fs_probe::run_host(argv[1]):2;}\n')
    run(['/usr/bin/clang++-21','-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
         '-fsanitize=address,undefined','-fno-sanitize-recover=all','-DZA_SAVE_FS_PROBE_HOST_TEST=1',
         '-DZA_SAVE_FS_PROBE_TITLE_NUM=91780','-DZA_PROBE_HAS_LSTAT=1','-DZA_PROBE_HAS_SYMLINK=1',
         '-DZA_PROBE_HAS_READLINK=1','-DZA_PROBE_HAS_GETDENTS=0','-I'+str(app / 'src'),app / 'src/probe.cpp',harness,'-o',out / 'host-test'])
    run([out / 'host-test', fixtures])
    reports = list(fixtures.glob('*/report.json'))
    if len(reports) != 1: raise ValueError('host report missing')
    host = json.loads(reports[0].read_text())
    if host.get('sentinels_unchanged') is not True or any(x.get('result') == 'FOLLOWED_LINK_UNSAFE' for x in host['rows']):
        raise ValueError('host private fixture safety failed')
    shutil.copy2(reports[0], evidence / 'host-report.json')
    run(['bash',app / 'tools/build.sh','Folder'])
    package = app / 'dist/PPSA91780'
    run([nm,'-u',app / 'build/llvm-pie.elf'], evidence / 'final-undefined-symbols.txt')
    missing = []
    for line in (evidence / 'final-undefined-symbols.txt').read_text().splitlines():
        fields = line.split()
        if fields and not ordinary(fields[-1]): missing.append({'symbol':fields[-1],'providers':providers.get(fields[-1],[])})
    if missing: raise ValueError('unresolved or raw-sys-only imports: '+repr(missing))
    for name,pin in source_pins.items():
        if sha(sources / name) != pin: raise ValueError('probe source changed')
    manifest = {str(f.relative_to(package)):sha(f) for f in sorted(package.rglob('*')) if f.is_file()}
    result = {'status':'built-host-tested-not-run-on-PS5','title_id':'PPSA91780','known_free':False,'package':str(package),
              'eboot_sha256':sha(package / 'eboot.bin'),'package_manifest':manifest,'host_sentinels_unchanged':True,
              'source_manifest_sha256':a.source_manifest_sha256,'sdk_api_choices':optional,'console_access':False,
              'romfs_required':False,'game_data_access':False,'installed':False,'hardware_tested':False}
    (evidence / 'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    log.close()


if __name__ == '__main__': main()
