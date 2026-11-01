"""Create private r20b audit/client from pinned project tools; no console access."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

def once(text, old, new):
    assert text.count(old) == 1, (text.count(old), old[:80])
    return text.replace(old, new)

def write(name, text):
    path = HERE/name
    assert not path.exists(), path
    path.write_text(text, newline='\n')

client = (ROOT/'port/observer-r17/client.py').read_text()
client = once(client, 'from analyze import analyze',
    "import sys\nsys.path.insert(0,str(Path(__file__).resolve().parents[1]/'observer-r17'))\nfrom analyze import analyze")
client = once(client, "TITLE='PPSA91762'", "PROFILES={'each':1,'batch2':2,'batch4':4,'batch8':8}\nTITLE='PPSA91762'")
client = once(client, "    elif op=='input':assert arg in ACTIONS", "    elif op=='submission':assert arg in PROFILES and frames is None\n    elif op=='input':assert arg in ACTIONS")
client = once(client, 'def collect(ftp,session,seq,out):', '''def validate_submission_ack(ack):
    if ack.get('op') != 'submission': return
    result = ack.get('result')
    if result == 'rejected_in_menu': return
    if result not in ('applied','rejected_boundary','rejected_override','drain_failed'):
        raise ValueError('Unknown submission result')
    if ack.get('requested_profile') not in PROFILES:
        raise ValueError('Invalid requested submission profile')
    if type(ack.get('frame')) is not int or ack['frame'] < 1:
        raise ValueError('Missing successful-frame context')
    if result == 'applied':
        profile = ack.get('profile')
        if profile != ack['requested_profile'] or type(ack.get('max_lists')) is not int or ack['max_lists'] != PROFILES[profile]:
            raise ValueError('Applied submission profile/cap receipt mismatch')
    elif ack.get('profile') != '' or ack.get('max_lists') != 0:
        raise ValueError('Rejected submission falsely reports an applied profile')

def collect(ftp,session,seq,out):''')
client = once(client, "    if ack.get('result')=='settling':return ack", "    validate_submission_ack(ack)\n    if ack.get('result')=='settling':return ack")
client = once(client, "('snapshot','measure','fps','input','continue','collect')", "('snapshot','measure','fps','input','continue','submission','collect')")
client = once(client, "        if op=='fps':s.add_argument('value',type=int,choices=(0,1))", "        if op=='fps':s.add_argument('value',type=int,choices=(0,1))\n        if op=='submission':s.add_argument('value',choices=tuple(PROFILES))")
write('client.py',client)

audit = (ROOT/'port/submission-r20/audit.py').read_text()
audit = audit.replace("compiler-r19-20261028", "batch-r20-20261028")
audit = once(audit, "WORK = Path('/home/tomer/ps5-za-native/batch-r20-20261028')", "WORK = Path('/home/tomer/ps5-za-native/batch-r20b-20261028')")
audit = once(audit, "EVIDENCE = ROOT/'evidence/submission-r20'", "EVIDENCE = ROOT/'evidence/submission-r20b'")
audit = once(audit, "b'/home/tomer/ps5-za-native/perf-r16-20261028'", "b'/home/tomer/ps5-za-native/batch-r20b-20261028'")
audit = once(audit, "expected = {'nvn/objects.c', 'nvn/nvn.h', 'nvn/vulkan/exec.c'}", "expected = {'nvn/objects.c', 'nvn/nvn.h', 'nvn/vulkan/exec.c', 'nvn/vulkan/za_submission_r20.h', 'nvn/vulkan/za_submission_queue_r20.inc'}")
audit = once(audit, "    assert set(changed) == expected, changed", "    assert set(changed) == expected, changed\n    added = {p.relative_to(WORK/'source/runtime').as_posix() for p in (WORK/'source/runtime').rglob('*') if p.is_file() and not (BASE/'source/runtime'/p.relative_to(WORK/'source/runtime')).exists()}\n    assert added == {'nvn/vulkan/za_submission_boundary_r20b.inc'}, added")
audit = once(audit, "(BASE/'objects-r19')", "(BASE/'objects-r20')")
audit = once(audit, "if p.name == 'title_entry.o': continue", "if p.name in ('title_entry.o','observer.o'): continue")
audit = once(audit, "sha(WORK/'objects-r20'/p.name)", "sha(WORK/'objects-r20b'/p.name)")
audit = once(audit, "    result = {'changed_runtime_sources': changed", "    historical = json.loads((ROOT/'evidence/submission-r20/preservation-audit.json').read_text())\n    assert sha(game) == historical['game_archive']['sha256'], 'game archive changed'\n    assert sha(driver) == historical['driver']['sha256'], 'driver archive changed'\n    result = {'added_runtime_sources': sorted(added), 'changed_runtime_sources': changed")
audit = once(audit, "Read-only current fingerprint. No historical baseline hash was available, so this is not proof of byte identity to the historical driver.", "Hash equals the recorded r20 preservation audit; no driver code changes in r20b.")
audit = once(audit, "Only source/list submission code and title revision changed. Scheduling tests are a host mock; hardware behavior is pending.", "Only submission profile/cap/switch code, observer command handling and title revision changed. Scheduling tests are a host mock; r20b hardware behavior is pending.")
write('audit.py',audit)

build = HERE/'build.sh'
text = build.read_text()
text = text.replace('Rebuild title_entry only', 'Rebuild title_entry and the private observer')
build.write_text(text,newline='\n')
generator = HERE/'generate.py'
text = generator.read_text()
text = text.replace("    write('test-executor.c', t)", "    t = t.replace('#define LOG(...) ((void)0)', 'static char log_line[2048];\\n#define LOG(...) ((void)snprintf(log_line,sizeof log_line,__VA_ARGS__))')\n    write('test-executor.c', t)")
generator.write_text(text,newline='\n')
