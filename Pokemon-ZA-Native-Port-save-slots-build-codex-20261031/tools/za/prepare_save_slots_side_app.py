#!/usr/bin/env python3
"""Prepare an isolated save-slots application from proved code and owned local data.

No console connection, title reservation, save import or main-game mutation.
Game files stay in their existing local dump; the immutable job uploads independent
bytes under the new application, never symlinks to another title's writable data.
Prepare through canonical zw outside both queues; verify the staged inputs
only after taking a canonical PC FIFO turn.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


CANDIDATE = '81e264c8991f5ba86870a7fd89fe13765a07eb0ae9f240047ccea656baaf25fe'
NSO = '2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9'
LIBC = 'e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036'
LAUNCH_SOURCE = '0e2d3ae076cae6290b8fb54af93a846ca78634cb18d06e0479ae79112de6f228'
TITLE = 'PPSA91781'
PROTECTED = (b'/data/homebrew/PPSA91762', b'/data/homebrew/PPSA91761',
             b'/mnt/sandbox/PPSA91762', b'/mnt/sandbox/PPSA91761')


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def recorded_config_bytes(baseline, readback_dir):
    required = {'local-shader-options.txt', 'observer-enable.txt', 'perf-r24-options.txt',
                'performance-profile.txt', 'slot-depth-options.txt', 'submission-options.txt', 'performance-options.txt'}
    rows = {Path(row['path']).name: row for row in baseline['entry_observations']['config']}
    if set(rows) != required:
        raise ValueError('All seven recorded main configs required')
    result = {}
    for name, row in rows.items():
        if row.get('readable') is not True or not isinstance(row.get('text'), str):
            raise ValueError('Recorded config text unavailable: ' + name)
        data = row['text'].encode('utf-8')
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Recorded config content hash differs: ' + name)
        readback = readback_dir / name
        if not readback.is_file():
            raise ValueError('Verified local config readback unavailable: ' + str(readback))
        actual = readback.read_bytes()
        if actual != data or hashlib.sha256(actual).hexdigest() != row['sha256']:
            raise ValueError('Local config readback differs from registered baseline: ' + name)
        result[name] = actual
    return rows, result


def verify_prepared(repo, out, pipe_encoding, readiness_path):
    """Execution-only PC turn: validate an already complete immutable package."""
    agent, ticket = (os.environ.get('PC_TEST_' + key) for key in ('AGENT', 'TICKET'))
    if not agent or not ticket or not os.environ.get('PC_TEST_TOKEN'):
        raise ValueError('Canonical PC verification turn required')
    prepared = json.loads((out / 'evidence/prepared-result.json').read_text(encoding='utf-8-sig'))
    if prepared['status'] != 'PREPARED_NOT_FRESH_GAME_VERIFIED':
        raise ValueError('No complete prepared package manifest')
    if readiness_path is None:
        raise ValueError('Stage the verification-readiness manifest before enrollment')
    readiness = json.loads(readiness_path.read_text(encoding='utf-8-sig'))
    for row in readiness['small_input_pins']:
        if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Staged verification input changed: ' + row['path'])
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != readiness['verifier_sha256']:
        raise ValueError('Verification runner changed after readiness was recorded')
    if hashlib.sha256(Path(prepared['preparer_source']).read_bytes()).hexdigest() != prepared['preparer_sha256']:
        raise ValueError('Original preparation producer snapshot changed')
    actual_installer = repo / 'port/main-install/install-main.py'
    defer = json.loads((out / 'evidence/defer-test-result.json').read_text(encoding='utf-8-sig'))
    actual_installer_sha = hashlib.sha256(actual_installer.read_bytes()).hexdigest()
    if actual_installer_sha != readiness['installer_sha256']:
        raise ValueError('Canonical offline tool changed after verification readiness')
    if defer['status'] != 'PASS':
        raise ValueError('Historical component proof missing; never claim an unexecuted test')
    verify_dir = Path(readiness['verification_output']).resolve()
    if verify_dir.parent != (out / 'evidence').resolve() or not verify_dir.name.startswith('verification'):
        raise ValueError('Verification output must be a new private evidence directory')
    if any(verify_dir.iterdir()):
        raise ValueError('Verification output already exists; preserve evidence and prepare a new run')
    results = {}
    for name, filename in (('probe', 'fs-probe-with-launcher-job.json'), ('save', 'side-app-job.json')):
        status = subprocess.run([sys.executable, '-I', str(repo / 'workbench/zw.py'), 'pc-queue', 'check',
                                 '--agent', agent, '--ticket', ticket], capture_output=True, check=True)
        state = json.loads(status.stdout.decode(pipe_encoding))
        seconds = state.get('seconds_to_yield')
        if not state.get('ok') or state.get('must_yield') or (seconds is not None and seconds < 65):
            raise RuntimeError('Verification budget insufficient; stop without preparation')
        path = out / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != prepared['jobs'][name]['sha256']:
            raise ValueError('Prepared job changed before verification')
        command = [sys.executable, '-I', str(repo / 'workbench/zw.py'), 'install-bundle', 'plan', '--job', str(path)]
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              encoding=pipe_encoding, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) as child:
            try:
                stdout, stderr = child.communicate(timeout=max(1, seconds - 30) if seconds is not None else None)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill.exe', '/PID', str(child.pid), '/T', '/F'], capture_output=True)
                child.wait()
                raise RuntimeError('Owned verification process stopped for safe PC handoff')
        (verify_dir / (name + '-plan.json')).write_text(stdout, encoding='utf-8')
        (verify_dir / (name + '-stderr.txt')).write_text(stderr, encoding='utf-8')
        if child.returncode:
            raise RuntimeError('Canonical verification failed: ' + name)
        result = json.loads(stdout)
        if result['candidate_sha256'] != prepared['jobs'][name]['candidate_sha256']:
            raise ValueError('Actual bundle identity differs from prepared input pins')
        results[name] = result
    write(verify_dir / 'result.json', {'status': 'PASS_FRESH_ARTIFACT_BYTES_VERIFIED', 'plans': results,
                                     'game_inputs_fresh_hashed_by_canonical_plan': True,
                                     'canonical_installer_sha256': actual_installer_sha,
                                     'historical_defer_test_candidate_sha256': defer['candidate_sha256'],
                                     'current_installer_protocol_tested_by_this_run': False,
                                     'historical_defer_test_applies_to_current_bytes': actual_installer_sha == defer['candidate_sha256'],
                                     'console_readiness': 'BLOCKED_PENDING_SEPARATE_PROTOCOL_AND_LIVE_PREFLIGHT_PROOFS',
                                     'installed': False, 'hardware_tested': False, 'console_access': False})
    print(json.dumps({'status': 'PASS-verification-only', 'out': str(verify_dir), 'console_access': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--ui', type=Path, required=True)
    p.add_argument('--writer', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--check-frontdoor', action='store_true', help='Light read-only codec/status validation; no PC turn or output writes')
    p.add_argument('--launcher-cache', type=Path)
    p.add_argument('--launcher-cache-sha256')
    p.add_argument('--defer-candidate', type=Path)
    p.add_argument('--verification-readiness', type=Path)
    p.add_argument('--linux-view-dir', type=Path)
    p.add_argument('--view-manifest-sha256')
    p.add_argument('--linux-stop', action='store_true')
    p.add_argument('--linux-selftest', action='store_true')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--prepare-only', action='store_true', help='Stage every artifact/job outside both queues; no heavy test')
    mode.add_argument('--verify-only', action='store_true', help='PC-turn execution only against a complete prepared package')
    mode.add_argument('--prepare-linux-view', action='store_true', help='Stage only local path spelling views outside both queues')
    mode.add_argument('--verify-linux-view', action='store_true', help='Contained Linux execution of the canonical offline plan')
    mode.add_argument('--stop-linux-view', action='store_true', help='Stop only identity-bound Linux verification descendants')
    mode.add_argument('--linux-worker', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--reuse-defer-proof', type=Path)
    p.add_argument('--resume-preparation', action='store_true', help='Resume only this incomplete private staging folder; never overwrite differing payloads')
    a = p.parse_args()
    repo, ui, writer, out = (x.resolve() for x in (a.repo, a.ui, a.writer, a.out))
    if a.prepare_linux_view or a.verify_linux_view or a.stop_linux_view or a.linux_worker:
        module_path = Path(__file__).with_name('save_sideapp_linux_verify.py')
        spec = importlib.util.spec_from_file_location('save_sideapp_linux_verify', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if a.prepare_linux_view:
            if a.linux_view_dir is None:
                p.error('--prepare-linux-view requires a new --linux-view-dir')
            print(json.dumps(module.prepare(repo, out, a.linux_view_dir.resolve(), ui, writer)))
        else:
            if a.verification_readiness is None or not a.view_manifest_sha256:
                p.error('Linux verification requires the pinned --verification-readiness manifest')
            if a.linux_worker:
                module.worker(repo, a.verification_readiness.resolve(), a.view_manifest_sha256,
                              stop=a.linux_stop, selftest=a.linux_selftest)
            else:
                module.windows_run(repo, a.verification_readiness.resolve(), a.view_manifest_sha256,
                                   stop=a.stop_linux_view, selftest=a.linux_selftest)
        return
    config_readbacks = repo / 'evidence/hebrew-choice-console-20261101-dependencies-r1/app'
    # -I ignores Python environment encoding switches. Probe an identically
    # launched Python pipe instead of assuming UTF-8 for Windows tool stdout.
    # The zw descendants also use this exact executable and -I.
    pipe_encoding = subprocess.check_output([sys.executable, '-I', '-c',
                                             'import sys; print(sys.stdout.encoding)']).decode('ascii').strip()
    if a.check_frontdoor:
        statuses = {}
        for resource in ('queue', 'pc-queue'):
            raw = subprocess.check_output([sys.executable, '-I', str(repo / 'workbench/zw.py'), resource, 'status'])
            text = raw.decode(pipe_encoding, errors='strict')
            if text.encode(pipe_encoding, errors='strict') != raw:
                raise ValueError('Canonical stdout codec failed byte roundtrip')
            statuses[resource] = json.loads(text)
        registered = statuses['queue']['baselines']['PPSA91762']
        source = json.loads(Path(registered['manifest']['path']).read_text(encoding='utf-8-sig'))
        if registered['rebuild_instructions'] != source['rebuild_instructions']:
            raise ValueError('Decoded baseline Unicode text differs from UTF-8 source manifest')
        config_rows, config_data = recorded_config_bytes(source, config_readbacks)
        print(json.dumps({'status': 'PASS-read-only-frontdoor-codec', 'pipe_encoding': pipe_encoding,
                          'utf8_json_manifest_unicode_matches': True, 'resources': list(statuses),
                          'recorded_config_payloads_available_and_hash_matched': len(config_data),
                          'output_files_written': False, 'console_access': False}))
        return
    if a.verify_only:
        verify_prepared(repo, out, pipe_encoding, a.verification_readiness)
        return
    if not a.prepare_only:
        p.error('Select --prepare-only outside the queues, or --verify-only after full readiness')
    if any(os.environ.get(prefix + name) for prefix in ('PC_TEST_', 'CONSOLE_INSTALL_') for name in ('AGENT', 'TICKET', 'TOKEN')):
        raise ValueError('Preparation must not hold either resource turn')
    native_root = Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native').resolve()
    if os.name != 'nt' or (out.exists() and not a.resume_preparation) or native_root not in out.parents:
        raise ValueError('Windows front door and NEW output under native WSL directory required')
    if a.resume_preparation and (not (out / 'evidence/executed-preparer.py').is_file() or
                                 (out / 'evidence/prepared-result.json').exists()):
        raise ValueError('Only an incomplete owned preparation may resume')
    last_check = 0.0

    def turn(minimum=35):
        nonlocal last_check
        last_check = time.monotonic()
        return {'ok': True, 'seconds_to_yield': None, 'phase': 'preparing_outside_queues'}

    def digest(path, scan=False):
        if time.monotonic() - last_check > 8:
            turn()
        h, matches, tail = hashlib.sha256(), set(), b''
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(8 << 20), b''):
                h.update(chunk)
                if scan:
                    data = tail + chunk
                    matches.update(x.decode() for x in PROTECTED if x in data)
                    tail = data[-128:]
                if time.monotonic() - last_check > 8:
                    turn()
        return h.hexdigest(), sorted(matches)

    turn(130)
    if shutil.disk_usage(native_root).free < (1 << 30):
        raise ValueError('Need at least1GiB native space for independent core bundle')
    out.mkdir(exist_ok=a.resume_preparation)
    app, evidence = out / TITLE, out / 'evidence'
    app.mkdir(exist_ok=a.resume_preparation); evidence.mkdir(exist_ok=a.resume_preparation)
    preparer_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    preparer_source = evidence / ('executed-preparer-' + preparer_sha[:12] + '.py' if a.resume_preparation else 'executed-preparer.py')
    shutil.copy2(__file__, preparer_source)
    if a.defer_candidate is not None:
        if a.reuse_defer_proof is None:
            raise ValueError('Already completed defer test proof required; no tests while preparing')
        proven = json.loads((a.reuse_defer_proof / 'defer-test-result.json').read_text(encoding='utf-8-sig'))
        review = a.defer_candidate.resolve().parent
        if proven['status'] != 'PASS' or proven['candidate_sha256'] != digest(a.defer_candidate.resolve())[0] or \
           proven['test_sha256'] != digest(review / 'test_defer_complete.py')[0]:
            raise ValueError('Previously tested defer-complete component changed')
        actual_installer_sha = digest(repo / 'port/main-install/install-main.py')[0]
        tool_drift = proven['candidate_sha256'] != actual_installer_sha
        shutil.copy2(repo / 'port/main-install/install-main.py', evidence / 'installer-current.py')
        copied_review = evidence / 'installer-defer-review'
        copied_review.mkdir(exist_ok=a.resume_preparation)
        for name in ('candidate.py', 'canonical-base.py', 'test_defer_complete.py', 'defer-complete.patch', 'SOURCE-SHA256.json'):
            shutil.copy2(review / name, copied_review / name)
        shutil.copy2(a.reuse_defer_proof / 'defer-test-result.json', evidence / 'defer-test-result.json')
        shutil.copy2(a.reuse_defer_proof / 'defer-test.log', evidence / 'defer-test.log')
        write(evidence / 'defer-proof-reuse.json', {'source': str(a.reuse_defer_proof),
                                                  'pc_ticket': '00000076', 'rerun': False,
                                                  'old_candidate_and_tests_unchanged': True,
                                                  'current_tool_sha256': actual_installer_sha,
                                                  'current_tool_drift_pending_verification': tool_drift})
    def linux_path(path):
        path = path.resolve()
        if native_root == path or native_root in path.parents:
            return '/home/tomer/ps5-za-native/' + path.relative_to(native_root).as_posix()
        if path.drive and len(path.drive) == 2 and path.drive[1] == ':':
            return '/mnt/' + path.drive[0].lower() + '/' + path.as_posix()[3:]
        raise ValueError('Unsupported compiler input mapping')

    launcher_source = evidence / 'launch_title.c'
    shutil.copy2(repo / 'port/title/launch_title.c', launcher_source)
    if digest(launcher_source)[0] != LAUNCH_SOURCE:
        raise ValueError('Existing fixed-title launcher source changed; review before compiling')
    launcher_pins = {}
    cached_launchers = None
    if a.launcher_cache is not None:
        cache_manifest = a.launcher_cache.resolve() / 'evidence/launcher-pins.json'
        if not a.launcher_cache_sha256 or digest(cache_manifest)[0] != a.launcher_cache_sha256:
            raise ValueError('Launcher cache manifest differs')
        cached_launchers = json.loads(cache_manifest.read_text(encoding='utf-8-sig'))
    for title in ('PPSA91780', TITLE):
        turn(75)
        dest = app / 'launch.elf' if title == TITLE else out / 'probe-launcher/PPSA91780/launch.elf'
        dest.parent.mkdir(parents=True, exist_ok=True)
        compiler = '/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk/bin/prospero-clang'
        command = ['wsl.exe', '-d', 'Ubuntu', '--', 'timeout', '--kill-after=3s', '20s', compiler,
                   '-O2', '-Wall', '-Wextra', '-Werror', '-DZA_LAUNCH_ID="' + title + '"',
                   '-DZA_LAUNCH_LOG="/data/homebrew/' + title + '/launch.log"', linux_path(launcher_source),
                   '-lSceSystemService', '-lSceUserService', '-o', linux_path(dest)]
        reuse_reference = None
        if cached_launchers is not None:
            cached = cached_launchers[title]
            if cached['source_sha256'] != LAUNCH_SOURCE or \
               '-DZA_LAUNCH_ID="' + title + '"' not in cached['command'] or \
               '-DZA_LAUNCH_LOG="/data/homebrew/' + title + '/launch.log"' not in cached['command'] or \
               digest(Path(cached['path']))[0] != cached['sha256']:
                raise ValueError('Launcher cache source/identity/bytes differ')
            if dest.exists() and digest(dest)[0] != cached['sha256']:
                raise ValueError('Differing existing launcher; choose new staging output')
            if not dest.exists(): shutil.copy2(cached['path'], dest)
            command = cached['command']
            reuse_reference = {'manifest': str(cache_manifest), 'manifest_sha256': a.launcher_cache_sha256,
                               'path': cached['path'], 'sha256': cached['sha256']}
        else:
            r = subprocess.run(command, capture_output=True, timeout=35)
            (evidence / ('launcher-' + title + '.log')).write_bytes(r.stdout + r.stderr)
            if r.returncode:
                raise RuntimeError('Fixed-title launcher compile failed: ' + title)
        data = dest.read_bytes()
        if title.encode() not in data or any(x in data for x in (b'PPSA91761', b'PPSA91762')):
            raise ValueError('Fixed-title launcher identity audit failed')
        launcher_pins[title] = {'path': str(dest), 'sha256': digest(dest)[0],
                                'source_sha256': digest(launcher_source)[0], 'command': command,
                                'reuse_reference': reuse_reference, 'compiled_in_this_turn': reuse_reference is None}
    write(evidence / 'launcher-pins.json', launcher_pins)
    probe_job = json.loads((repo / 'deliverables/ZA-save-fs-probe-install-plan-20261101-r1/side-app-job.json').read_text(encoding='utf-8-sig'))
    if probe_job['title_id'] != 'PPSA91780' or len(probe_job['artifacts']) != 7:
        raise ValueError('Original seven-file FS probe package differs')
    probe_job['name'] = 'Isolated ZA Save FS Probe plus fixed-title safe launcher; before save slots'
    probe_job['artifacts'].append({'path': launcher_pins['PPSA91780']['path'],
                                   'sha256': launcher_pins['PPSA91780']['sha256'],
                                   'remote_path': '/data/homebrew/PPSA91780/launch.elf'})
    probe_job['notes'] += ' Fixed-title launcher refuses any running game; registration and title collision require fresh coordinated checks.'
    write(out / 'fs-probe-with-launcher-job.json', probe_job)
    spec = importlib.util.spec_from_file_location('existing_offline_candidate_hash', repo / 'tools/console-install-queue/console_queue.py')
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    probe_plan = {'candidate_sha256': policy.candidate_hash(probe_job), 'fresh_bytes_verified': False}
    candidate_dir = repo / 'deliverables/ZA-save-slots-candidate-20261101-r1'
    candidate = candidate_dir / 'eboot.bin'
    code_sha, protected_hits = digest(candidate, scan=True)
    if code_sha != CANDIDATE or protected_hits:
        raise ValueError('Candidate code hash or protected-title path scan failed')
    base = repo / 'artifacts/main-1.1.0-20261031-01'
    base_sums = json.loads((base / 'SHA256SUMS.json').read_text(encoding='utf-8-sig'))
    old_core = repo / 'artifacts/randomizer-r27b-play/PPSA91762'
    state = json.loads(subprocess.run([sys.executable, '-I', str(repo / 'workbench/zw.py'), 'queue', 'status'],
                                     check=True, capture_output=True, text=True, encoding=pipe_encoding).stdout)
    baseline_ref = state['baselines']['PPSA91762']['manifest']
    baseline_path = Path(baseline_ref['path'])
    if digest(baseline_path)[0] != baseline_ref['sha256']:
        raise ValueError('Registered main baseline manifest differs')
    baseline = json.loads(baseline_path.read_text(encoding='utf-8-sig'))
    main_base = state['baselines']['PPSA91762']['files']['/data/homebrew/PPSA91762/eboot.bin']
    if main_base != '36b3d5d650bd1a8171c39a788785678fa395ab5c0043d6b02a0d028946944699':
        raise ValueError('Main baseline changed: merge/rebuild, do not repin old candidate')
    observed_configs, recorded_configs = recorded_config_bytes(baseline, config_readbacks)
    input_rows, output_rows = {}, {'launch.elf': launcher_pins[TITLE]['sha256']}

    def copy(source, relative, expected=None):
        if source.is_symlink():
            raise ValueError('No symlinked core inputs: ' + str(source))
        before, _ = digest(source)
        if expected is not None and before != expected:
            raise ValueError('Pinned source mismatch: ' + str(source))
        dest = app / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if digest(dest)[0] != before:
                raise ValueError('Differing existing payload; choose new staging output: ' + str(dest))
        else:
            shutil.copy2(source, dest)
        after, _ = digest(dest)
        if after != before:
            raise ValueError('Core copy mismatch')
        input_rows[str(source)] = before
        output_rows[relative] = after

    print('Validated candidate; copying private core, assets and Hebrew mod', flush=True)
    copy(candidate, 'eboot.bin', CANDIDATE)
    category_counts = {}
    for prefix in ('randomizer-assets', 'mods/hebrew'):
        selected = [(rel, sha) for rel, sha in base_sums.items() if rel.startswith(prefix + '/')]
        if not selected:
            raise ValueError('Missing frozen data category: ' + prefix)
        category_counts[prefix] = len(selected)
        for rel, expected in selected:
            target = rel.replace('mods/hebrew/', 'mods/0-hebrew/', 1)
            copy(base / rel, target, expected)
    handoff = json.loads((base / 'GENERATOR-HANDOFF.json').read_text(encoding='utf-8-sig'))
    release = json.loads((repo / 'tools/za/releases/main-1.1.0.lock.json').read_text(encoding='utf-8-sig'))
    expected_counts = {'randomizer-assets': handoff['assets']['files'] + 1,  # plus the manifest itself
                       'mods/hebrew': release['profiles']['main-1.1.0']['release']['mods']['files']}
    if category_counts != expected_counts:
        raise ValueError('Runtime asset category count differs from proved release')
    for name in ('GENERATOR-HANDOFF.json', 'UI-HANDOFF.json', 'capabilities.json'):
        copy(base / name, name, base_sums[name])
    # Optional game-derived display catalogue. Never included in safe source delivery.
    names = repo.parent / 'Pokemon-ZA-Native-Port-save-reset-names/slot-names.json'
    if names.is_file():
        copy(names, 'randomizer-assets/slot-names.json')
    for folder in ('fonts', 'sce_sys', 'cache/spirv'):
        for source in sorted((old_core / folder).rglob('*')):
            if source.is_file() and source.name != 'param.json':
                copy(source, source.relative_to(old_core).as_posix())
    copy(old_core / 'sce_module/libc.prx', 'sce_module/libc.prx', LIBC)
    for name in ('local-shader-options.txt', 'observer-enable.txt', 'perf-r24-options.txt',
                 'performance-profile.txt', 'slot-depth-options.txt', 'submission-options.txt', 'performance-options.txt'):
        observed = observed_configs[name]
        dest = app / name
        dest.write_bytes(recorded_configs[name])
        copied = digest(dest)[0]
        if copied != observed['sha256']:
            raise ValueError('Recorded config materialization differs')
        output_rows[name] = copied
        input_rows[str(config_readbacks / name)] = copied
    input_rows[str(baseline_path)] = digest(baseline_path)[0]
    write(evidence / 'recorded-main-configs.json', observed_configs)
    if (app / 'performance-options.txt').read_text().strip() != 'optimized':
        raise ValueError('performance-options must contain optimized')
    write(evidence / 'feature-input-preservation.json', {
        'base_package_manifest_sha256': digest(base / 'SHA256SUMS.json')[0],
        'verified_runtime_asset_counts': category_counts,
        'metadata_files_preserved': ['GENERATOR-HANDOFF.json', 'UI-HANDOFF.json', 'capabilities.json'],
        'registered_main_baseline': {'sha256': main_base, 'manifest': baseline_ref},
        'configs_byte_identical_to_recorded_main': sorted(observed_configs),
        'slot_names_present': names.is_file(),
        'limits': ['Only enabled Hebrew mod is materialized; unrelated disabled experiments omitted',
                   'Historical config readback pins; refresh main baseline before eventual console installation']})
    param = json.loads((old_core / 'sce_sys/param.json').read_text(encoding='utf-8-sig'))
    param.update(titleId=TITLE, conceptId=TITLE[4:], contentId='UP9000-' + TITLE + '_00-ZASAVESLOTTST001')
    param['localizedParameters']['en-US']['titleName'] = 'ZA Save Slots Test'
    write(app / 'sce_sys/param.json', param)
    output_rows['sce_sys/param.json'] = digest(app / 'sce_sys/param.json')[0]

    # Explicit, small source audit, not an invented whole-program safety proof.
    runtime_tree = native_root / 'save-slots-on36-candidate-20261101-r3/runtime-tree/source/runtime'
    paths = [ui / 'port/ui-v2/src/ui_platform.cpp', ui / 'port/ui-v2/src/title_entry_uiv2.c',
             ui / 'port/title/title_fs.c', runtime_tree / 'platform/ps5.c',
             runtime_tree / 'paths.c', runtime_tree / 'services/save_slot.c']
    source_pins = {str(x): digest(x)[0] for x in paths}
    source_proof_path = native_root / 'save-slots-on36-candidate-20261101-r3/evidence/full-input-source-after.json'
    source_proof = json.loads(source_proof_path.read_text(encoding='utf-8-sig'))
    if any(sha not in source_proof.values() for sha in source_pins.values()):
        raise ValueError('Isolation source differs from actual target-build input pins')
    for source in paths:
        data = source.read_bytes()
        if any(x in data for x in PROTECTED):
            raise ValueError('Protected paths in live input source')
    write(evidence / 'static-isolation.json', {
        'title_id': TITLE, 'known_free': False, 'candidate_eboot_sha256': CANDIDATE,
        'binary_protected_path_hits': protected_hits, 'source_pins': source_pins,
        'target_input_manifest': {'path': str(source_proof_path), 'sha256': digest(source_proof_path)[0]},
        'app0': '/data/homebrew/' + TITLE,
        'writable_virtual_root': '/download0/zarecomp',
        'sandbox_root_pattern': '/mnt/sandbox/' + TITLE + '_<instance>/download0/zarecomp',
        'sandbox_observed': False,
        'source_findings': ['PS5 platform defaults LARECOMP_DATA_ROOT to /download0/zarecomp',
                            'title_fs resolves relative paths below that immutable root',
                            'UI runs/saves/cache write /download0; assets/game/config read /app0',
                            'Randomizer entry excludes vanilla one-shot city-save import',
                            'Hebrew files materialized under private mods/0-hebrew; no writable links'],
        'limits': ['Static input/path review and byte-bound code only; hardware sandbox not yet observed',
                   'Title collision, current main baseline and writable-root isolation need fresh console preflight',
                   'Fixed-title launch payload compiled; registration/launch not performed by this offline preparation']})

    game = repo.parent / 'hebrew-lab/qa-game-reference-20261030'
    game_files = [game / 'romfs.bin']
    for directory in ('exefs', 'aoc'):
        game_files += sorted(x for x in (game / directory).rglob('*') if x.is_file())
    expected_game = {'romfs.bin', 'exefs/main', 'exefs/main.npdm', 'exefs/rtld', 'exefs/sdk',
                     'aoc/0100f43008c45002.bin'}
    if {x.relative_to(game).as_posix() for x in game_files} != expected_game or not all(x.is_file() for x in game_files):
        raise ValueError('Known complete six-file owned game input set required')
    artifacts = [{'path': str(app / rel), 'sha256': sha, 'remote_path': '/data/homebrew/' + TITLE + '/' + rel}
                 for rel, sha in sorted(output_rows.items())]
    historical_manifest = repo / 'evidence/title-r2-deploy-20261027-174236Z.json'
    historic = json.loads(historical_manifest.read_text(encoding='utf-8-sig'))
    expected_game_pins = {row['path'][5:]: row for row in historic['files'] if row['path'].startswith('game/')}
    game_pins = {}
    print('Binding six owned local game inputs to historical expected pins; fresh hashing deferred to verification turn', flush=True)
    for source in game_files:
        relative = source.relative_to(game).as_posix()
        expected = expected_game_pins[relative]
        sha = expected['sha256']
        if source.stat().st_size != expected['bytes']:
            raise ValueError('Owned game input size differs from historical pin')
        if relative == 'exefs/main' and sha != NSO:
            raise ValueError('Wrong original2.0.2 NSO')
        game_pins[relative] = {'sha256': sha, 'bytes': source.stat().st_size, 'fresh_hashed': False}
        artifacts.append({'path': str(source), 'sha256': sha,
                          'remote_path': '/data/homebrew/' + TITLE + '/game/' + relative})
    game_hash_seconds = None
    # Metadata only: future uploads copy the owned game, never a link to main.
    write(evidence / 'owned-game-manifest.json', game_pins)
    write(evidence / 'core-input-pins.json', input_rows)
    write(evidence / 'core-output-pins.json', output_rows)
    job = {'console': '192.168.1.135', 'title_id': TITLE,
           'name': 'Save slots test: isolated full side application after filesystem probe',
           'deployment': {'mode': 'side_app'}, 'artifacts': artifacts, 'expected_base': [],
           'external_dependencies': [{'kind': 'console_test', 'candidate_bundle_sha256': probe_plan['candidate_sha256'],
                                      'title_id': 'PPSA91780', 'requirement': 'Inspect actual filesystem probe results before save-system hardware test; assign its future ticket before enqueue'},
                                     {'kind': 'runtime_preflight', 'requirement': 'Fresh title collision, matching param, sandbox isolation, verified save backup and game closed'},
                                     {'kind': 'main_baseline', 'eboot_sha256': main_base,
                                      'requirement': 'If main baseline changed, merge/rebuild before console turn; never merely repin'},
                                     {'kind': 'launch', 'requirement': 'Register/launch only this new title using its declared fixed-title payload in a coordinated session; not performed by this offline preparer'}],
           'notes': 'Prepared only, not queued. Full independent core and owned-game bytes. No main/vanilla writes or mutable links. Not installed or hardware tested. Do not claim main-update permission. Missing/denied FS operations remain fail-closed; symlink safety not proved by host tests. Observe the declared filesystem probe before proceeding.'}
    write(out / 'side-app-job.json', job)
    # plan already computes the complete candidate fingerprint; avoid an extra
    # full-ROMFS pass merely to print the same identity a second time.
    plan = {'candidate_sha256': policy.candidate_hash(job), 'fresh_bytes_verified': False}
    (evidence / 'verification').mkdir()
    write(evidence / 'prepared-result.json', {'status': 'PREPARED_NOT_FRESH_GAME_VERIFIED',
                                   'title_id': TITLE, 'known_free': False, 'console_access': False,
                                   'candidate_eboot_sha256': CANDIDATE,
                                   'candidate_bundle_sha256': plan['candidate_sha256'],
                                   'probe_bundle_sha256': probe_plan['candidate_sha256'],
                                   'probe_job': str(out / 'fs-probe-with-launcher-job.json'),
                                   'launcher_sha256s': {k: v['sha256'] for k, v in launcher_pins.items()},
                                   'canonical_subprocess_pipe_encoding': pipe_encoding,
                                   'core_files': len(output_rows), 'owned_game_files': len(game_files),
                                   'owned_game_bytes': sum(x['bytes'] for x in game_pins.values()),
                                   'owned_game_hash_seconds': game_hash_seconds,
                                   'fresh_game_save_import': False, 'story_shuffle_added': False,
                                   'preparer_sha256': digest(Path(__file__))[0],
                                   'preparer_source': str(preparer_source),
                                   'game_expected_pin_source': {'path': str(historical_manifest), 'sha256': digest(historical_manifest)[0]},
                                   'jobs': {'probe': {'path': str(out / 'fs-probe-with-launcher-job.json'),
                                                      'sha256': digest(out / 'fs-probe-with-launcher-job.json')[0],
                                                      'candidate_sha256': probe_plan['candidate_sha256']},
                                            'save': {'path': str(out / 'side-app-job.json'),
                                                     'sha256': digest(out / 'side-app-job.json')[0],
                                                     'candidate_sha256': plan['candidate_sha256']}},
                                   'job': str(out / 'side-app-job.json')})
    turn()
    print(json.dumps({'out': str(out), 'status': 'PREPARED-not-fresh-game-verified',
                      'candidate_bundle_sha256': plan['candidate_sha256'], 'files': len(artifacts)}), flush=True)


if __name__ == '__main__':
    main()
