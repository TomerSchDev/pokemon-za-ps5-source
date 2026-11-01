from pathlib import Path
import json,hashlib,statistics
from datetime import datetime,timezone
root=Path(__file__).resolve().parent;q=root/'quickstart';workspace=root.parents[1]
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
bench=[]
for name in ['45-city-totodile-30','46-city-totodile-60','49-city-stable-30']:
    run=root/'runs'/name;d=read(run/'benchmark.json');d.pop('samples',None)
    rows=[json.loads(s) for s in (run/'telemetry.jsonl').read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    d['telemetry_summary']=dict(samples=len(rows),cpu_core_equivalents_mean=round(statistics.mean(r['process_cpu_core_percent'] for r in rows)/100,2),
        process_working_set_peak_bytes=max(r['process_working_set_bytes'] for r in rows),
        gpu_utilization_mean_percent=round(statistics.mean(float(r['gpu'].split(',')[0]) for r in rows),1),
        note='Process CPU is summed across cores; GPU telemetry is whole-device. These counters do not establish a bottleneck.')
    d['slow_motion_when_forced60']=name=='46-city-totodile-60';bench.append(d)
manifest=read(q/'templates.json')
record=dict(schema=1,version='0.1.0',verified_utc=datetime.now(timezone.utc).isoformat(),
    hardware=dict(cpu='Intel Core i7-12700F',gpu='NVIDIA RTX 3050 8GB',ram_gb=32,os='Windows 11',nvidia_driver='610.88'),
    game_version='1.0.0',checkpoint=manifest['checkpoint'],
    checkpoint_acquired_through_actual_gameplay=True,all_tutorials_skipped=False,
    checkpoint_history='Totodile opening battles, first night/Hotel Z, morning Taunie battle lost, Rotom Phone and Pokemon Center; Mission 03 wild-zone visit pending.',
    templates=manifest['starters'],
    template_validation=dict(save_hash=True,roundtrip_identical=True,party_legality_at_pinned_pkhex=True,
        modified_blocks_allowlist=['3AA1A9AD','2D87BE5C','FADA7742'],only_modified_work_key='FD3EE7DF4BDD257C',story_flags_preserved=True),
    gui_validation=dict(unit_tests_passed=6,visual_controls_checked=True,profile_created_via_gui='chikorita-20261025-153630-366c10',
        profile_sha256_verified=True,stock_runtime_started_via_gui=True,isolated_path_confirmed=True,
        interrupted_run_recorded=True,
        stock_dll_city_reload_verified_separately=True,stock_dll_reload_run='50-quickstart-stock-dll',
        limitation='Desktop key presses did not advance the title screen during UI automation; the GUI-created profile was separately loaded with the stock runtime and stock game DLL using its existing scripted input hook. No claim of a manual controller test.'),
    binaries=dict(gui_sha256=digest(root/'quickstart-build/dist/ZA-Quick-Start.exe'),
        stable_runtime_sha256=digest(workspace/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024/runtime/lasrecomp.exe'),
        diagnostic_runtime_sha256=digest(root/'city-runtime/lasrecomp.exe'),
        diagnostic_game_library_sha256=digest(root/'lab-library/lasgame-lab.dll')),
    sources=dict(runtime='https://github.com/Hexveil404/PokeZ-ARecomp',runtime_commit='4d82d8998adb75036c27f476e8d8f7e737bed36a',
        save_library='https://github.com/kwsch/PKHeX',save_library_commit='9c3391d017d91ba407ef53075b15581f1bec8f0d'),
    benchmarks=bench,
    limitations=['No complete story playthrough with edited starters','Later tutorials and progression restrictions remain','Fixed trainer name and appearance',
        'Base 1.0.0 only; no DLC/update testing','About one minute per FPS mode on one street; not whole-game performance',
        'No individual frame-time percentiles or 1% low metric','Warm-cache timed routes; startup shader compilation is excluded',
        'Small differences between independent runs do not establish causality','Launcher contains no game assets or engine'],
    default_fps_setting=30,experimental_optimizations_shipped=False)
(q/'VALIDATION.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({k:record[k] for k in ['version','verified_utc','binaries']},indent=2))
