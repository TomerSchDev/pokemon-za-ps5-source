"""Bounded local tests using ZA Recomp's own documented test hooks.

Does not send keyboard/mouse input to Windows or modify existing saves.
Each run has a separate data root. Game files are passed by absolute path.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['launcher', 'build', 'play'])
    p.add_argument('--release', required=True, type=Path)
    p.add_argument('--data-root', required=True, type=Path)
    p.add_argument('--game', type=Path)
    p.add_argument('--seconds', type=int, default=120)
    p.add_argument('--input', default='')
    p.add_argument('--capture-every', type=int, default=300)
    p.add_argument('--save', type=Path)
    p.add_argument('--test-library', type=Path)
    p.add_argument('--control', type=Path)
    p.add_argument('--fps', choices=['30', '60'], default='60')
    p.add_argument('--force-fps', action='store_true', help='Disable upstream automatic 60-to-30 fallback for a measured test')
    p.add_argument('--resolution', choices=['1x', '1.5x', '2x'], default='1x')
    p.add_argument('--profile', default='')
    p.add_argument('--vk-profile', action='store_true', help='Record upstream render-thread categories; instrumented timing only')
    p.add_argument('--gpu-profile-at', default='', help='Comma-separated present frame numbers for upstream GPU timestamp profiling')
    p.add_argument('--state-filter', choices=['on','off'], help='Diagnostic toggle for the existing upstream redundant-state filter')
    p.add_argument('--key-reuse', choices=['off','on','audit'], help='Experimental exact-input render key reuse')
    p.add_argument('--empty-submit', choices=['off','on'], help='Avoid waiting on a retired ring slot when there is no pending work')
    p.add_argument('--validation', action='store_true')
    p.add_argument('--log-files', action='store_true', help='Log actual first reads through the runtime filesystem')
    p.add_argument('--allow-user-input', action='store_true', help='Allow normal window input after or alongside the scripted test')
    p.add_argument('--submission-slots', choices=['8','16'])
    p.add_argument('--shot-at', default='', help='Optional comma separated frame numbers; excluded from timed intervals')
    a = p.parse_args()
    if a.seconds < 1 or a.seconds > 7200:
        p.error('seconds must be between 1 and 7200')
    if a.mode == 'play' and not a.game:
        p.error('play requires --game')
    if a.gpu_profile_at and not all(x.isdecimal() and int(x) > 0 for x in a.gpu_profile_at.split(',')):
        p.error('gpu-profile-at must contain positive comma-separated frame numbers')
    root = a.data_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / 'build').mkdir(exist_ok=True)
    log = root / ('probe-' + a.mode + '.json')
    if log.exists():
        p.error('this run already exists; choose a new data root')
    exe = a.release.resolve() / 'lasrecomp.exe'
    if not exe.is_file():
        p.error('release executable missing')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'POKELAB_'))}
    # main.c:reserve_guest_space() normally re-execs on an address collision.
    # On Windows this exits the parent and leaves a new child, outside Popen's
    # bounded wait. Fail closed on a collision in this diagnostic harness;
    # a fresh run can retry explicitly. This does not alter a successful boot.
    env.update(LARECOMP_DATA_ROOT=str(root), LARECOMP_NO_UPDATE_CHECK='1',
               LARECOMP_REEXEC='20')
    if a.test_library:
        env['LARECOMP_GAME_LIB'] = str(a.test_library.resolve())
    if a.control:
        env['POKELAB_CONTROL'] = str(a.control.resolve())
    if a.profile:
        env['LARECOMP_SAMPLE'] = a.profile
    if a.vk_profile:
        env['LARECOMP_VK_PROF'] = '1'
    if a.gpu_profile_at:
        env['LARECOMP_GPUPROF_AT'] = a.gpu_profile_at
    if a.state_filter:
        env['LARECOMP_VK_STATE_FILTER'] = '1' if a.state_filter == 'on' else '0'
    if a.key_reuse:
        env['LARECOMP_KEY_REUSE'] = str({'off':0, 'on':1, 'audit':2}[a.key_reuse])
    if a.empty_submit:
        env['LARECOMP_EMPTY_SUBMIT'] = '1' if a.empty_submit == 'on' else '0'
    if a.validation:
        env['LARECOMP_VK_VALIDATION'] = '1'
    if a.log_files:
        env['LARECOMP_LOG_FILES'] = '1'
    if a.submission_slots:
        env['LARECOMP_SUBMISSION_SLOTS'] = a.submission_slots
    if a.force_fps:
        env['LARECOMP_FPS'] = a.fps
    if a.shot_at:
        env['LARECOMP_SHOT_AT'] = a.shot_at
    args = [str(exe)]
    if a.mode == 'launcher':
        env.update(LARECOMP_LAUNCHER_SHOT='30:setup',
                   LARECOMP_SHOT_PATH=str(root / 'launcher.png'))
    elif a.mode == 'build':
        if not (root / 'extracted/exefs/main').is_file():
            p.error('build requires imported files in data-root/extracted')
        # Empty source asks the upstream launcher to build already imported files.
        env['LARECOMP_LAUNCHER_EXTRACT'] = ''
    else:
        args += [str(a.game.resolve()), '--play']
        save = a.save.resolve() if a.save else root / 'save'
        save.mkdir(parents=True, exist_ok=True)
        env.update(LARECOMP_SAVE_DIR=str(save),
                   LARECOMP_SETTINGS=str(root / 'larecomp.ini'),
                   LARECOMP_SCREENSHOT_EVERY=str(a.capture_every),
                   LARECOMP_WAIT_DUMP='10', LARECOMP_SKIP_WHY='1',
                   LARECOMP_KBD_AUTO='Test')
        if not a.allow_user_input:
            env['LARECOMP_NO_USER_INPUT'] = '1'
        if a.input:
            env['LARECOMP_INPUT'] = a.input
        (root / 'larecomp.ini').write_text(
            'aspect = original\nfullscreen = 0\nvolume = 0.3\n'
            'show_fps = 1\nfps60 = ' + str(int(a.fps == '60')) + '\nresolution = ' + a.resolution + '\n'
            'dynamic_res = off\ntex_hd = 0\nantialias = smaa\n'
            'upscaler = fsr1\nlanguage = en-US\nmouse_camera = off\n', encoding='utf-8')
    record = dict(mode=a.mode, started_utc=datetime.now(timezone.utc).isoformat(),
                  budget_seconds=a.seconds, game_execution_verified=False,
                  input_script=a.input, capture_every=a.capture_every,
                  test_library=str(a.test_library) if a.test_library else None,
                  fps_setting=a.fps, force_fps=a.force_fps, resolution=a.resolution,
                  shot_at=a.shot_at, sampling_profile=a.profile,
                  vk_profile=a.vk_profile, gpu_profile_at=a.gpu_profile_at,
                  state_filter=a.state_filter, startup_reexec_policy='fail_on_guest_address_collision')
    record.update(key_reuse=a.key_reuse, empty_submit=a.empty_submit, validation=a.validation)
    record['submission_slots'] = a.submission_slots
    record['log_files'] = a.log_files
    record['allow_user_input'] = a.allow_user_input
    start = time.monotonic()
    with (root / 'stdout.log').open('wb') as out, (root / 'stderr.log').open('wb') as err:
        proc = subprocess.Popen(args, cwd=root, env=env, stdout=out, stderr=err)
        record['pid'] = proc.pid
        log.write_text(json.dumps(record, indent=2))
        print(json.dumps(record), flush=True)
        try:
            record['exit_code'] = proc.wait(timeout=a.seconds)
            record['terminated_by_harness'] = False
        except subprocess.TimeoutExpired:
            proc.terminate()  # this specific child only, never all game instances
            record['exit_code'] = proc.wait(timeout=15)
            record['terminated_by_harness'] = True
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    record['elapsed_seconds'] = round(time.monotonic() - start, 3)
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    record['captured_files'] = [str(f.relative_to(root)) for f in root.rglob('*.png') if f.stat().st_size]
    log.write_text(json.dumps(record, indent=2))
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
