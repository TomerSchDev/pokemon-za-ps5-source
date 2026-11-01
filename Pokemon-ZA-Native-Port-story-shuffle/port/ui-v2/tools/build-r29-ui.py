#!/usr/bin/env python3
"""Build an isolated r29-ui candidate on the pinned r28b DLC Dex + Music base; never accesses a console.

Run in WSL Ubuntu: python3 port/ui-v2/tools/build-r29-ui.py --out /home/tomer/ps5-za-native/r29ui-NEW
Optional --tree is the prepared, immutable merge tree; --assets is the verified rando-v3 asset set.
The output must not exist. --package optionally copies the final program/assets/evidence to a NEW directory.
No installation, save migration, git commit, or overwrite of an earlier package occurs here.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
UI = HERE.parent
PROJECT = UI.parents[1]
BASE_META = json.loads((HERE / 'R29UI-TREE.json').read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(path, expected):
    if sha(path) != expected:
        raise ValueError('SHA-256 mismatch: ' + str(path))


def source_hashes():
    files = []
    for folder in (UI / 'src', UI / 'test', UI / 'tools', UI / 'fonts', UI / 'pc',
                   PROJECT / 'port/rando-v3/core', PROJECT / 'port/rando-v3/src', PROJECT / 'port/rando-v3/tools'):
        files.extend(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.extend(PROJECT / 'port/randomizer' / name for name in ('import_repair.cpp', 'import_repair.hpp', 'run_store.hpp'))
    files.extend((PROJECT / 'port/rando-v3/capabilities.json', PROJECT / 'port/rando-v3/HANDOFF.json',
                  UI / 'mockups/SHA256SUMS.txt'))
    return {str(p.relative_to(PROJECT)): sha(p) for p in sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--tree', type=Path, default=Path(BASE_META['tree']['path']))
    parser.add_argument('--assets', type=Path, default=PROJECT.parent / 'rando-v3-lab/assets')
    parser.add_argument('--package', type=Path)
    args = parser.parse_args()
    out, base, assets = args.out.resolve(), args.tree.resolve(), args.assets.resolve()
    if out.exists() or base == out or base in out.parents or out in base.parents:
        raise ValueError('--out must be a NEW directory outside the base tree')
    for protected in (assets, PROJECT, Path('/home/tomer/ps5-za-native/PS5_Vulkan'), Path('/home/tomer/ps5-za-native/PS5_Mesa')):
        if out == protected or out in protected.parents or protected in out.parents:
            raise ValueError('--out must not overlap assets, source repository, or the SDK trees')
    if any(c.isspace() for c in str(out) + str(base)):
        raise ValueError('--out and --tree cannot contain whitespace: the historical link recipe splits extra inputs on spaces')
    if args.package and args.package.resolve().exists():
        raise ValueError('--package must be a NEW directory')
    if args.package:
        package = args.package.resolve()
        for protected in (base, assets, out):
            if package == protected or package in protected.parents or protected in package.parents:
                raise ValueError('--package must not overlap base/assets/build inputs')
        if PROJECT in package.parents and PROJECT / 'artifacts' not in package.parents:
            raise ValueError('packages inside the repository belong under artifacts/')
    # No output directories or build mutations until the verified generator contract is available.
    spec = importlib.util.spec_from_file_location('generator_gate', HERE / 'verify-generator-handoff.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    receipt = gate.verify(PROJECT / 'port/rando-v3/HANDOFF.json', assets)
    plan = Path(os.environ.get('ZA_MUSIC_PLAN', '/home/tomer/ps5-za-native/r29-music-plan-v2.json')).resolve()
    plan_sha = 'fcef0023680e21a305b962d9962bcdafe518d0c9c899d50f841692f9d6471c70'
    pin(plan, plan_sha)  # this digest is embedded in the pinned base za_music_plan.o
    def verify_base():
        pin(base / 'r28b/control/llvm-pie.elf', BASE_META['control']['sha256'])
        pin(base / 'r28b/base/liblasgame-base.a', BASE_META['base_archive_copy']['sha256'])
        for item in BASE_META['link_inputs']['runtime_objects']:
            pin(base / 'source' / item['path'], item['sha256'])
        for item in BASE_META['link_inputs']['extra_inputs']:
            pin(base / 'r28b/inputs' / item['index'] / item['name'], item['sha256'])
    verify_base()
    out.mkdir(parents=True)
    evidence = out / 'evidence'
    evidence.mkdir()
    (evidence / 'generator-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    env = os.environ.copy()
    env.update(ZA_UI_ASSETS=str(assets), ZA_REQUIRE_HANDOFF='1', ZA_MUSIC_PLAN=str(plan), PIN_GOLDENS='0', PS5_CHECK='0')
    log = (evidence / 'build.log').open('w', encoding='utf-8')

    def run(command, cwd=PROJECT, stdout=None):
        line = shlex.join(map(str, command))
        print(line, flush=True)
        log.write('\n$ ' + line + '\n')
        log.flush()
        with subprocess.Popen(list(map(str, command)), cwd=cwd, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
            collected = []
            for part in proc.stdout:
                log.write(part)
                log.flush()
                if stdout is None:
                    print(part, end='', flush=True)
                else:
                    collected.append(part)
            if proc.wait():
                raise RuntimeError('build command failed: ' + line)
        if stdout is not None:
            Path(stdout).write_text(''.join(collected), encoding='utf-8')

    run([sys.executable, HERE / 'gen-capabilities.py', PROJECT / 'port/rando-v3/capabilities.json',
         UI / 'src/capabilities_generated.inc'])
    run([sys.executable, HERE / 'embed-font.py', UI / 'fonts', UI / 'src/fonts_embedded.inc'])
    sources_before = source_hashes()
    run(['bash', HERE / 'build-host.sh', out / 'host'])
    if sources_before != source_hashes():
        raise ValueError('generator/UI sources changed during host validation')
    (evidence / 'source-hashes.json').write_text(json.dumps(sources_before, indent=2) + '\n')
    # Only the new copied tree is mutated; the prepared tree and all reference objects remain read-only.
    work = out / 'tree'
    run(['cp', '-a', '--reflink=auto', base, work])
    controls = out / 'controls'
    controls.mkdir()
    for unit in ('main', 'nvn/vulkan/device'):
        target = controls / (Path(unit).name + '.o')
        run(['bash', HERE / 'compile-runtime-object.sh', work, unit, target])
        pin(target, BASE_META['compile']['reproduced'][unit]['sha256'])
    run([sys.executable, HERE / 'apply-runtime-launcher.py', work / 'source/runtime'])
    run(['bash', HERE / 'compile-runtime-object.sh', work, 'main', work / 'source/build/ps5/rt/main.o'])
    title = out / 'title'
    run(['bash', HERE / 'compile-title-objects.sh', work, title, assets, 'r29-ui'])
    v3 = out / 'v3'
    env['RANDO_V3_RUNTIME'] = str(work / 'source/runtime')
    run(['bash', PROJECT / 'port/rando-v3/tools/build-ps5-check.sh', v3])
    replacements = {'cheats.o': title / 'overlay_ps5.o', 'native_menu.o': title / 'launcher_ps5.o',
                    'menu_display.o': None, 'randomizer.o': v3 / 'randomizer.o',
                    'progression.o': v3 / 'legacy_progression.o', 'research_rewards.o': v3 / 'legacy_research_rewards.o',
                    'run_store.o': v3 / 'run_store_v3.o', 'title_entry.o': title / 'title_entry.o'}
    extra = []
    replaced = []
    recorded_tree = BASE_META['tree']['path']
    for token in BASE_META['link_inputs']['control_link_inputs_tokens']:
        name = Path(token).name
        if name in replacements and token.startswith(recorded_tree + '/'):
            replaced.append(name)
            if replacements[name] is not None:
                extra.append(str(replacements[name]))
        else:
            extra.append(token.replace(recorded_tree + '/', str(work) + '/'))
    if set(replaced) != set(replacements):
        raise ValueError('base link inputs do not contain exactly the expected replacement objects')
    for stem in ('ui_canvas', 'ui_widgets', 'ui_model', 'settings_codes', 'items_picker', 'ui_launcher', 'ui_overlay', 'ui_pad',
                 'fonts_embedded', 'ui_platform', 'launcher_core', 'ui_quad'):
        extra.append(str(title / (stem + '.o')))
    extra.append(str(v3 / 'rando_v3.o'))
    env['ZA_PS5_EXTRA_INPUTS'] = shlex.join(extra)
    real_vulkan = Path('/home/tomer/ps5-za-native/PS5_Vulkan')
    facade = out / 'vulkan-facade'
    facade.mkdir()
    for sub in ('tooling', '.deps', 'vendor'):
        (facade / sub).symlink_to(real_vulkan / sub, target_is_directory=True)
    (facade / 'tools').mkdir()
    shutil.copy2(real_vulkan / 'tools/radv-link.sh', facade / 'tools/radv-link.sh')
    env.update(PS5_VULKAN=str(facade),
               PS5_PAYLOAD_SDK='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk',
               PS5_CLANG='/usr/bin/clang-21')
    (evidence / 'link-inputs.txt').write_text(env['ZA_PS5_EXTRA_INPUTS'] + '\n')
    runtime = [work / 'source' / obj['path'] for obj in BASE_META['link_inputs']['runtime_objects']]
    program = out / 'program'
    program.mkdir()
    pie = program / 'llvm-pie.elf'
    run(['bash', work / 'source/tools/ps5/link-title.sh', pie, *runtime,
         work / 'r28b/base/liblasgame-base.a'], cwd=work / 'source')
    run([sys.executable, PROJECT / 'port/local-shader-r19/verify-registration.py',
         base / 'r28b/control/llvm-pie.elf', pie], stdout=evidence / 'registration.json')
    nm = '/usr/lib/llvm-21/bin/llvm-nm'
    run([nm, '--defined-only', pie], stdout=evidence / 'defined-symbols.txt')
    symbols = (evidence / 'defined-symbols.txt').read_text()
    for symbol in ('launcher_run', 'menu_render', 'za_items_pump', 'randomizeMusic', 'za_dlc_dex_unlock_pump'):
        if symbol not in symbols:
            raise ValueError('required runtime feature missing from linked image: ' + symbol)
    sdk = Path(env['PS5_PAYLOAD_SDK'])
    run([sdk / 'bin/llvm-strip', '--strip-debug', '-o', program / 'title-stripped.elf', pie])
    tool = real_vulkan / 'build/host/ps5-native-tool'
    stubs = program / 'ps5-link/stubs'
    run([tool, 'link', '--in', program / 'title-stripped.elf', '--out', program / 'eboot.elf',
         '--stub-dir', sdk / 'target/lib', '--stub', stubs / 'libSceAgc.so', '--stub', stubs / 'libSceAgcDriver.so',
         '--module-sdk', '0x02000009', '--companion-sdk', '0x08050001', '--file-name', 'eboot.elf'])
    run([sys.executable, PROJECT / 'port/title/verify-image.py', program / 'title-stripped.elf',
         program / 'eboot.elf', evidence / 'defined-symbols.txt'], stdout=evidence / 'image-preservation.json')
    run([tool, 'self', '--sign', '--in', program / 'eboot.elf', '--out', program / 'eboot.bin', '--magic', '0x1D3D154F'])
    run([tool, 'self', '--inspect', '--file', program / 'eboot.bin'], stdout=evidence / 'self-inspection.txt')
    if sources_before != source_hashes():
        raise ValueError('generator/UI sources changed during the build; candidate not packaged')
    # Recheck every base input and generator asset after compiling/linking.
    gate.verify(PROJECT / 'port/rando-v3/HANDOFF.json', assets)
    verify_base()
    report = {'package': 'r29-ui', 'status': 'candidate-built-no-hardware-test',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'base': BASE_META['base'],
              'generator': receipt, 'controls_byte_identical': ['main.o', 'device.o'],
              'music_plan_sha256': plan_sha,
              'runtime_objects_changed': ['main.o'], 'replaced_extra_objects': replaced,
              'eboot_sha256': sha(program / 'eboot.bin'), 'pie_sha256': sha(pie),
              'host_tests': ['ui ASan+UBSan', 'launcher flow, settings codes and emitted wild bytes', 'overlay glue ASan+UBSan',
                             '22 approved PNG goldens', 'deterministic second render'],
              'hardware_tested': False, 'console_access': False, 'installation_performed': False}
    (evidence / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.package:
        package = args.package.resolve()
        package.mkdir(parents=True)
        shutil.copy2(program / 'eboot.bin', package / 'eboot.bin')
        packaged_assets = package / 'randomizer-assets'
        packaged_assets.mkdir()
        manifest_name = json.loads((PROJECT / 'port/rando-v3/HANDOFF.json').read_text())['assets']['manifest_file']
        manifest = json.loads((assets / manifest_name).read_text())
        for name in (*manifest.keys(), manifest_name):
            shutil.copy2(assets / name, packaged_assets / name)
        shutil.copytree(evidence, package / 'evidence')
        for name in ('test_ui.log', 'test_settings_codes.log', 'test_launcher_flow.log', 'test_overlay_glue.log', 'goldens.log'):
            shutil.copy2(out / 'host' / name, package / 'evidence' / name)
        shutil.copy2(PROJECT / 'port/rando-v3/HANDOFF.json', package / 'GENERATOR-HANDOFF.json')
        shutil.copy2(PROJECT / 'port/rando-v3/capabilities.json', package / 'capabilities.json')
        (package / 'README-HE.txt').write_text('r29-ui — חבילת מועמד לבדיקת PS5. טרם הותקנה או נבדקה בקונסולה.\n'
            'בסיס: r28b DLC Dex + Music. תפריט UI v2 + rando-v3, רמות בר ו-Alpha.\n'
            'נדרשים גיבוי שמירה עדכני ובדיקת התקנה מתואמת; אין לשחזר שמירה ישנה מעל התקדמות חדשה.\n'
            'להעביר גם randomizer-assets בשלמותה: הבינארי דורש את נכסי v3 ומסרב לנכסים ישנים.\n', encoding='utf-8')
        sums = {str(p.relative_to(package)): sha(p) for p in sorted(package.rglob('*')) if p.is_file()}
        (package / 'SHA256SUMS.json').write_text(json.dumps(sums, indent=2) + '\n')
    log.close()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
