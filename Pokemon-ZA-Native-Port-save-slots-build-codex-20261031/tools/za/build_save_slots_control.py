#!/usr/bin/env python3
"""Isolated save-slot build on installed 36b3, in independently bounded PC turns.

Control replays the exact recorded JSON-fix link recipe and compares fresh PIE
and signed SELF byte for byte. Candidate keeps every other frozen input.
No installation, new release lock, MAIN update, game assets in sources or story shuffle.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
from collections import Counter
import signal

NATIVE = Path('/home/tomer/ps5-za-native')
PREVIOUS = NATIVE / 'main1.1-json-number-candidate-20261031-r2'
EXPECTED = {'eboot.bin': '36b3d5d650bd1a8171c39a788785678fa395ab5c0043d6b02a0d028946944699',
            'llvm-pie.elf': '58ce44d942b5c7ff78aa902cc0f9dfe37f5635011aa5265ac9158792df54b0ed'}
WRAPPER = '2dde618866a32d186cd730bff8f34fcb8dccab435b66fa5432f328f68135ae4c'
PRESERVE_UI_PUBLIC = {
    '_ZN2ui5model11pageIndexOfEPKc': 'ui_model.o',
    '_ZN2ui8launcher10Controller11dateOfRunIdERKNSt3__112basic_stringIcNS2_11char_traitsIcEENS2_9allocatorIcEEEE': 'launcher_core.o',
    '_ZN2ui8launcher13savedRunsPageEv': 'ui_launcher.o',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['control', 'candidate'])
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--ui', required=True, type=Path)
    parser.add_argument('--writer', required=True, type=Path)
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--control', type=Path)
    parser.add_argument('--resume-cache', type=Path)
    parser.add_argument('--checkpoint-sha256')
    args = parser.parse_args()
    repo, ui, writer, out = (p.resolve() for p in (args.repo, args.ui, args.writer, args.out))

    def budget(minimum=35):
        if any(not os.environ.get('PC_TEST_' + name) for name in ('AGENT', 'TICKET', 'TOKEN')):
            raise ValueError('canonical PC lease environment is required')
        result = subprocess.run([sys.executable, repo / 'workbench/zw.py', 'pc-queue', 'check',
                                 '--agent', os.environ['PC_TEST_AGENT'], '--ticket', os.environ['PC_TEST_TICKET']],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        state = json.loads(result.stdout)
        if not state.get('ok') or state.get('must_yield') or (state.get('seconds_to_yield') is not None and state['seconds_to_yield'] < minimum):
            raise RuntimeError('PC handoff budget insufficient; stop and requeue, preserving outputs')
        return state
    budget(150)
    if out.exists() or NATIVE not in out.parents:
        raise ValueError('--out must be a NEW native build folder')
    for protected in (repo, ui, writer, NATIVE / 'PS5_Vulkan', NATIVE / 'PS5_Mesa', PREVIOUS):
        if out == protected or out in protected.parents or protected in out.parents:
            raise ValueError('output overlaps protected inputs')
    freeze = ui / 'evidence/save-slots-continuation-01/source-freeze.json'
    if sha(freeze) != args.freeze_sha256:
        raise ValueError('UI source-freeze differs')
    pins = json.loads(freeze.read_text(encoding='utf-8-sig'))
    host = json.loads((freeze.parent / 'host-results.json').read_text(encoding='utf-8-sig'))
    if host.get('status') != 'PASS' or host.get('exit_code') != 0:
        raise ValueError('UI host tests did not pass')

    def check_sources():
        if sha(freeze) != args.freeze_sha256 or any(sha(ui / name) != digest for name, digest in pins.items()):
            raise ValueError('tested UI source changed')
    check_sources()
    spec = importlib.util.spec_from_file_location('base_za', repo / 'tools/za/za.py')
    za = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(za)
    lock = za.read_lock()
    profile = lock['profiles']['main-1.1.0']
    base_lock_sha = sha(za.lock_path(lock, 'main-1.1.0'))
    if base_lock_sha != '7ccc2d7674a5c3e618f267bf0aa5edffbbbc5c87148872ede83141aae39969b1':
        raise ValueError('main-1.1.0 lock differs')
    before = za.check_files(lock, ['main-1.1.0'])
    if not before['ok']:
        raise ValueError('frozen base differs')
    manifest = json.loads((repo / 'deliverables/ZA-new-run-json-fix-20261031-r2/candidate/SHA256SUMS.json').read_text())
    recipe_file = PREVIOUS / 'evidence/commands.json'
    if sha(recipe_file) != manifest['evidence/commands.json']:
        raise ValueError('recorded 36b3 link recipe differs')
    if sha(PREVIOUS / 'program/json_number_ps5.o') != WRAPPER:
        raise ValueError('JSON wrapper object differs')
    records = json.loads(recipe_file.read_text())
    selected = [c for c in records if Path(c[0]).name in ('prospero-lld', 'llvm-strip', 'ps5-native-tool')]
    if len(selected) != 5:
        raise ValueError('unexpected recorded link/conversion recipe')
    out.mkdir()
    evidence = out / 'evidence'
    evidence.mkdir()
    shutil.copy2(__file__, evidence / 'executed-builder.py')
    shutil.copy2(freeze, evidence / 'source-freeze.json')
    shutil.copy2(freeze.parent / 'host-results.json', evidence / 'host-results.json')
    dump(evidence / 'base-before.json', before)
    source_roots = [ui / 'port/ui-v2', Path(__file__).resolve().parents[2] / 'port/ui-v2',
                    writer / 'runtime/services', NATIVE / 'r28b-dlc-dex-fd-20261031-r1/source/runtime']
    source_roots += [ui / 'port' / name for name in ('rando-v3','randomizer','rando-v2','rando-music','cheats-r28','cheats-r27','perf-r28','perf-r26','title','observer-r17')]
    source_roots += [NATIVE / 'r29ui-codex-20261031-final-01/tree' / name for name in ('inc','port/sdl3-shim/include','port/shaderc-cache/include','source/third_party/ps5-stubs')]
    extensions = {'.c','.cpp','.h','.hpp','.inc','.sh','.py'}
    source_files = sorted({p.resolve() for root in source_roots for p in root.rglob('*')
                           if p.is_file() and p.suffix in extensions})
    source_files += [Path('/usr/bin/clang-21').resolve(), Path('/usr/lib/llvm-21/bin/llvm-nm'),
                     NATIVE / 'PS5_Vulkan/tooling/prospero-clang18',
                     NATIVE / 'PS5_Vulkan/.deps/native/ps5-payload-sdk/bin/prospero-lld']
    all_source_pins = {str(p): sha(p) for p in source_files}
    dump(evidence / 'full-input-source-before.json', all_source_pins)
    log = (evidence / 'build.log').open('x', encoding='utf-8')
    env = {**os.environ, 'PS5_CLANG': '/usr/bin/clang-21',
           'PS5_VULKAN': str(NATIVE / 'PS5_Vulkan'),
           'PS5_PAYLOAD_SDK': str(NATIVE / 'PS5_Vulkan/.deps/native/ps5-payload-sdk'),
           'ZA_UI_ASSETS': str(NATIVE / 'rando-v3-codex-m1-assets'), 'ZA_REQUIRE_HANDOFF': '1'}
    executed = []

    def run(command, target=None):
        turn = budget()
        command = list(map(str, command))
        executed.append(command)
        print('RUN', Path(command[0]).name, command[1][:90] if len(command) > 1 else '', flush=True)
        log.write('\n$ ' + shlex.join(command) + '\n')
        log.flush()
        stream = Path(target).open('wb') if target is not None else log
        limit = turn.get('seconds_to_yield')
        try:
            with subprocess.Popen(command, cwd=out, env=env, stdout=stream, stderr=log, start_new_session=True) as proc:
                try:
                    code = proc.wait(timeout=max(1, limit - 30) if limit is not None else None)
                except subprocess.TimeoutExpired:
                    # This process group was created above solely for this owned command.
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    raise RuntimeError('owned command stopped before handoff; checkpoint and requeue')
                if code:
                    raise RuntimeError('command failed: ' + str(code) + ': ' + command[0])
        finally:
            if target is not None:
                stream.close()
            log.flush()

    replacements = {}
    added = []
    retained_symbols = []
    old_object_symbols = {}
    global_diff = None
    runtime_sources = {}
    reused_objects = []
    if args.phase == 'candidate':
        if args.control is None:
            raise ValueError('candidate needs the passed installed-36 control folder')
        control = args.control.resolve()
        receipt = json.loads((control / 'evidence/result.json').read_text())
        if receipt.get('phase') != 'control' or receipt.get('status') != 'PASS':
            raise ValueError('control did not pass')
        for name, expected in EXPECTED.items():
            if sha(control / 'program' / name) != expected or not za.equal_bytes(control / 'program' / name, PREVIOUS / 'program' / name):
                raise ValueError('36b3 control is stale')
        if args.resume_cache:
            cache = args.resume_cache.resolve()
            checkpoint_path = cache / 'evidence/checkpoint.json'
            if sha(checkpoint_path) != args.checkpoint_sha256:
                raise ValueError('resume checkpoint differs')
            checkpoint = json.loads(checkpoint_path.read_text())
            if checkpoint.get('status') != 'stopped-for-resource-handoff' or checkpoint.get('source_freeze_sha256') != args.freeze_sha256 or checkpoint.get('owned_processes_after_stop') != []:
                raise ValueError('checkpoint not safely stopped or wrong sources')
            for name, pin in checkpoint['files'].items():
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts or relative.suffix not in ('.o', '.d'):
                    raise ValueError('invalid checkpoint filename')
                data = (cache / relative).read_bytes()
                if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
                    raise ValueError('checkpoint object differs: ' + name)
                target = out / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                if relative.suffix == '.o':
                    reused_objects.append(name)
            shutil.copy2(checkpoint_path, evidence / 'resume-checkpoint.json')
        tree = out / 'runtime-tree'
        ancillary = NATIVE / 'r29ui-codex-20261031-final-01/tree'
        fd_runtime = NATIVE / 'r28b-dlc-dex-fd-20261031-r1/source/runtime'
        for relative in ('inc', 'port/sdl3-shim/include', 'port/shaderc-cache/include', 'source/third_party/ps5-stubs'):
            shutil.copytree(ancillary / relative, tree / relative)
        shutil.copytree(fd_runtime, tree / 'source/runtime')
        compiler = ui / 'port/ui-v2/tools/compile-runtime-object.sh'
        if not (out / 'fs-control.o').is_file():
            run(['bash', compiler, tree, 'services/fs', out / 'fs-control.o'])
        fs_ref = next(f for f in profile['runtime'] if f.endswith('/services/fs.o'))
        if not za.equal_bytes(out / 'fs-control.o', za.expand(fs_ref)):
            raise ValueError('original FD-fix fs.o did not reproduce')
        prep = json.loads((Path(__file__).resolve().parents[2] / 'evidence/save-slots-build-prep-20261031-r1/PLAN.json').read_text(encoding='utf-8-sig'))
        for name in ('fs.c', 'save_slot.c', 'save_slot.h'):
            source = writer / 'runtime/services' / name
            expected = [value for key, value in prep['runtime']['sources_sha256'].items() if key.replace('\\', '/').endswith('/' + name)]
            if len(expected) != 1 or sha(source) != expected[0]:
                raise ValueError('runtime writer source differs from audited 17d9c6b: ' + name)
            runtime_sources[str(source)] = sha(source)
            shutil.copy2(source, tree / 'source/runtime/services' / name)
        shared_header = ui / 'port/ui-v2/src/za_slot.h'
        shutil.copy2(shared_header, tree / 'source/runtime/services/za_slot.h')
        dump(evidence / 'runtime-header-overlay.json', {'source': str(shared_header), 'sha256': sha(shared_header),
             'runtime_original_header_sha256': sha(writer / 'runtime/services/za_slot.h'), 'basis': 'tested UI header copied byte-for-byte; runtime original remains unchanged'})
        if not (out / 'fs.o').is_file():
            run(['bash', compiler, tree, 'services/fs', out / 'fs.o'])
        if not (out / 'save_slot.o').is_file():
            run(['bash', compiler, tree, 'services/save_slot', out / 'save_slot.o'])
        replacements[za.expand(fs_ref)] = str(out / 'fs.o')
        added.append(str(out / 'save_slot.o'))
        build_project = Path(__file__).resolve().parents[2]
        helper_text = (ui / 'port/ui-v2/tools/compile-title-objects.sh').read_text()
        marker = '-c "$root/src/$s.cpp"'
        if helper_text.count(marker) != 1:
            raise ValueError('unexpected title compile helper')
        helper_text = helper_text.replace(marker, '-MMD -MF "$out/$s.d" ' + marker)
        cc_marker = 'cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }'
        if helper_text.count(cc_marker) != 1:
            raise ValueError('unexpected compiler wrapper')
        cc_atomic = '''cc() {
    local args=("$@") index=-1
    for i in "${!args[@]}"; do [[ ${args[$i]} != -o ]] || index=$((i+1)); done
    [[ $index -ge 0 ]] || return 2
    local final=${args[$index]}
    if [[ -f $final ]]; then echo "reuse pinned $(basename "$final")"; return 0; fi
    args[$index]="$final.building"
    sh "$PS5_VULKAN/tooling/prospero-clang18" "${args[@]}" && mv -- "$final.building" "$final"
}'''
        helper_text = helper_text.replace(cc_marker, cc_atomic)

        def project_view(source, destination):
            tools = destination / 'port/ui-v2/tools'
            tools.mkdir(parents=True)
            extra_map = shlex.quote('-ffile-prefix-map=' + str(source) + '=' + str(repo))
            (tools / 'compile-title-objects.sh').write_text(helper_text.replace('cxx=(', 'flags+=(' + extra_map + ')\ncxx=(', 1))
            shutil.copy2(source / 'port/ui-v2/tools/verify-generator-handoff.py', tools / 'verify-generator-handoff.py')
            for name in ('src', 'third_party'):
                (tools.parent / name).symlink_to(source / 'port/ui-v2' / name, target_is_directory=True)
            for name in ('rando-v3', 'randomizer', 'rando-v2', 'rando-music', 'cheats-r28', 'cheats-r27', 'perf-r28', 'perf-r26', 'title', 'observer-r17'):
                (destination / 'port' / name).symlink_to(source / 'port' / name, target_is_directory=True)
            return destination

        old_project = project_view(build_project, out / 'source-view-old')
        new_project = project_view(ui, out / 'source-view-new')
        old_title, new_title = out / 'title-control', out / 'title-new'
        for project, folder in ((old_project, old_title), (new_project, new_title)):
            env['ZA_TITLE_PREFIX_MAP'] = str(project) + '=' + str(repo)
            run(['bash', project / 'port/ui-v2/tools/compile-title-objects.sh', tree, folder,
                 NATIVE / 'rando-v3-codex-m1-assets', 'r29-ui'])
        changed = {'launcher_core.o', 'ui_launcher.o', 'launcher_ps5.o'}
        title_controls = {}
        for item in old_title.glob('*.o'):
            matches = [f for f in profile['extra'] if Path(f).name.endswith('-' + item.name)]
            if len(matches) != 1 or not za.equal_bytes(item, za.expand(matches[0])):
                raise ValueError('old title object failed exact control: ' + item.name)
            mine = new_title / item.name
            affected_header = False
            depfile = new_title / (item.stem + '.d')
            if depfile.is_file():
                text = depfile.read_text()
                affected_header = any('/' + header in text for header in ('launcher_core.h', 'ui_launcher.h', 'za_slot.h', 'saves_fs.h'))
            if item.name in changed or (affected_header and not za.equal_bytes(item, mine)):
                replacements[za.expand(matches[0])] = str(mine)
                title_controls[item.name] = 'rebuilt ABI consumer'
            elif not za.equal_bytes(item, mine):
                raise ValueError('undeclared header/object change: ' + item.name)
            else:
                title_controls[item.name] = 'byte-identical control; original retained'
        dump(evidence / 'title-controls.json', title_controls)
        run(['/usr/lib/llvm-21/bin/llvm-nm', '--extern-only', '--defined-only', old_title / 'launcher_core.o'], evidence / 'old-controller-symbols.txt')
        retained_symbols = [line.split()[-1] for line in (evidence / 'old-controller-symbols.txt').read_text().splitlines()
                            if line.split()[-1].startswith('_ZN2ui8launcher10Controller9loadCardsE')]
        if len(retained_symbols) != 1:
            raise ValueError('old loadCards symbol was absent or ambiguous')
        for item in list(old_title.glob('*.o')) + [out / 'fs-control.o']:
            target = evidence / ('object-symbols-' + item.stem + '.txt')
            run(['/usr/lib/llvm-21/bin/llvm-nm', '--defined-only', item], target)
            old_object_symbols[item.name] = {line.split()[-1] for line in target.read_text().splitlines() if len(line.split()) >= 3}
        for name, owner in PRESERVE_UI_PUBLIC.items():
            if name not in old_object_symbols.get(owner, set()):
                raise ValueError('public retention source owner differs: ' + name)
            retained_symbols.append(name)
        dump(evidence / 'compiler-header-dependencies.json', {p.name: p.read_text() for p in new_title.glob('*.d')})
        dump(evidence / 'writer-source-sha256.json', runtime_sources)
    program = out / 'program'
    shutil.copytree(PREVIOUS / 'program/ps5-link', program / 'ps5-link')
    shutil.copy2(PREVIOUS / 'program/json_number_ps5.o', program / 'json_number_ps5.o')
    for original in selected:
        command = [value.replace(str(PREVIOUS / 'program'), str(program)) for value in original]
        if Path(command[0]).name == 'prospero-lld':
            counts = {value: command.count(value) for value in replacements}
            if any(count != 1 for count in counts.values()):
                raise ValueError('replacement token absent or ambiguous')
            command = [replacements.get(value, value) for value in command]
            # Normal object files; adding before the frozen game archive preserves the recipe's library order.
            index = command.index(za.expand(profile['archive']))
            command[index:index] = added
            command += ['--undefined=' + name for name in retained_symbols]
        run(command)
    nm = '/usr/lib/llvm-21/bin/llvm-nm'
    run([nm, '--defined-only', program / 'llvm-pie.elf'], evidence / 'defined-symbols.txt')
    run([nm, '--extern-only', '--defined-only', program / 'llvm-pie.elf'], evidence / 'global-symbols.txt')
    if args.phase == 'control':
        for name, expected in EXPECTED.items():
            if sha(program / name) != expected or not za.equal_bytes(program / name, PREVIOUS / 'program' / name):
                raise ValueError('installed 36b3 reproduction differs: ' + name)
    else:
        run(['python3', repo / 'port/local-shader-r19/verify-registration.py', PREVIOUS / 'program/llvm-pie.elf', program / 'llvm-pie.elf'], evidence / 'registration.json')
        run(['python3', repo / 'port/title/verify-image.py', program / 'title-stripped.elf', program / 'eboot.elf', evidence / 'defined-symbols.txt'], evidence / 'image-preservation.json')
        symbols = (evidence / 'defined-symbols.txt').read_text()
        for name in ('__wrap_localeconv', '__wrap_strtod', 'plat_strtod', 'save_slot_commit', 'save_slot_arm', 'rt_za_slot_rebuild', 'za_slot_read_summary_file'):
            if name not in symbols:
                raise ValueError('feature symbol missing: ' + name)
        if any(name not in symbols for name in retained_symbols):
            raise ValueError('old public loadCards symbol was lost')
        def symbol_table(path):
            return {f[-1]: f[-2] for line in Path(path).read_text().splitlines() if len(f := line.split()) >= 3}
        old_global = symbol_table(control / 'evidence/global-symbols.txt')
        new_global = symbol_table(evidence / 'global-symbols.txt')
        lost = []
        forbidden = []
        for name in sorted(old_global.keys() - new_global.keys()):
            kind = old_global[name]
            owners = sorted(owner for owner, names in old_object_symbols.items() if name in names)
            weak_cpp = kind.upper() in ('W', 'V') and name.startswith('_Z')
            category = 'weak_cpp_comdat' if weak_cpp else 'strong_or_C_runtime_public_loss'
            detail = {'symbol': name, 'nm_type': kind, 'old_object_definitions': owners,
                      'classification': category,
                      'reason': 'Weak C++ instantiation no longer rooted by the changed UI call graph; ABI consumers recompiled' if weak_cpp else 'Stable public/runtime C symbols must remain'}
            lost.append(detail)
            if not weak_cpp:
                forbidden.append(detail)
        global_diff = {'before_count': len(old_global), 'after_count': len(new_global), 'lost': lost,
                       'added': sorted(new_global.keys() - old_global.keys()), 'forbidden_public_losses': forbidden,
                       'weak_internal_loss_count': sum(item['classification'] == 'weak_cpp_comdat' for item in lost)}
        def full_inventory(path):
            return Counter((f[-1], f[-2]) for line in Path(path).read_text().splitlines() if len(f := line.split()) >= 3)
        full_before = full_inventory(control / 'evidence/defined-symbols.txt')
        full_after = full_inventory(evidence / 'defined-symbols.txt')
        global_diff['all_defined_symbol_losses'] = [
            {'symbol': name, 'nm_type': kind, 'lost_definitions': count,
             'old_object_definitions': sorted(owner for owner, names in old_object_symbols.items() if name in names),
             'classification': 'local_or_weak_symbol_change' if kind.islower() or kind.upper() in ('W', 'V') else 'global_definition_change',
             'reason': 'Changed UI/runtime source and header call graph; local string/registration counters may renumber. Global/public loss is checked separately above.'}
            for (name, kind), count in sorted((full_before - full_after).items())]
        global_diff['all_defined_symbol_additions'] = [
            {'symbol': name, 'nm_type': kind, 'added_definitions': count}
            for (name, kind), count in sorted((full_after - full_before).items())]
        dump(evidence / 'global-symbol-diff.json', global_diff)
        if forbidden:
            raise ValueError('public/runtime symbol loss requires review; see global-symbol-diff.json')
        parser_names = [line.split()[-1] for line in symbols.splitlines()
                        if len(line.split()) >= 3 and 'nlohmann' in line and any(term in line for term in ('lexer', 'parser', 'parse'))]
        run(['/usr/lib/llvm-21/bin/llvm-objdump', '--disassemble', '--disassemble-symbols=' + ','.join(parser_names), program / 'llvm-pie.elf'], evidence / 'json-call-disassembly.txt')
        assembly = (evidence / 'json-call-disassembly.txt').read_text()
        mapping = {name: [line for line in assembly.splitlines() if ('call' in line or 'jmp' in line) and '<__wrap_' + name in line]
                   for name in ('localeconv', 'strtod')}
        dump(evidence / 'json-call-targets.json', mapping)
        if any(not matches for matches in mapping.values()):
            raise ValueError('JSON wrapper call-target proof missing')
    check_sources()
    if any(sha(path) != digest for path, digest in all_source_pins.items()):
        raise ValueError('full build source/helper/toolchain input changed during reuse/link')
    dump(evidence / 'full-input-source-after.json', all_source_pins)
    if any(sha(path) != expected for path, expected in runtime_sources.items()):
        raise ValueError('runtime writer source changed during compilation')
    budget(65)
    after = za.check_files(lock, ['main-1.1.0'])
    if not after['ok']:
        raise ValueError('frozen base changed during build')
    dump(evidence / 'commands.json', executed)
    dump(evidence / 'base-after.json', after)
    result = {'phase': args.phase, 'status': 'PASS', 'base_eboot_sha256': EXPECTED['eboot.bin'],
              'base_lock_sha256': base_lock_sha, 'source_freeze_sha256': args.freeze_sha256,
              'eboot_sha256': sha(program / 'eboot.bin'), 'pie_sha256': sha(program / 'llvm-pie.elf'),
              'replacements': replacements, 'added': added, 'host_proof': host,
              'retained_public_symbols': retained_symbols,
              'global_symbol_diff': global_diff,
              'reused_checkpoint_objects': reused_objects, 'resume_checkpoint_sha256': args.checkpoint_sha256,
              'console_access': False, 'installed': False, 'hardware_tested': False,
              'release_locks_changed': False, 'story_shuffle_added': False}
    dump(evidence / 'result.json', result)
    log.close()
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
