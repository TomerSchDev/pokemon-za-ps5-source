"""Read-only source/object preservation audit of the isolated candidate."""
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = Path('/home/tomer/ps5-za-native/batch-r20b-20261028')
WORK = Path('/home/tomer/ps5-za-native/preparation-r21-20261028')
EVIDENCE = ROOT/'evidence/preparation-r21'
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while data := f.read(1024*1024): h.update(data)
    return h.hexdigest()
def allocated_sections(path):
    b = path.read_bytes()
    off = struct.unpack_from('<Q', b, 40)[0]
    size, count, names_idx = struct.unpack_from('<HHH', b, 58)
    headers = [struct.unpack_from('<IIQQQQIIQQ', b, off+i*size) for i in range(count)]
    ns = headers[names_idx]
    names = b[ns[4]:ns[4]+ns[5]]
    out = {}
    for s in headers:
        if not s[2] & 2: continue
        name = names[s[0]:].split(b'\0', 1)[0].decode()
        data = b[s[4]:s[4]+s[5]] if s[1] != 8 else bytes(s[5])
        # Actual old object's only remaining path string: VMA assertion __FILE__.
        for prefix in (b'/home/tomer/ps5-za-native/batch-r20b-20261028',
                       b'/home/tomer/ps5-za-native/preparation-r21-20261028'):
            data = data.replace(prefix, b'@WORK@')
        out[name] = hashlib.sha256(data).hexdigest()
    return out
def main():
    baseline_manifest=json.loads((EVIDENCE/'preparation.json').read_text())['all_baseline_runtime_sources']
    for rel,digest in baseline_manifest.items():
        assert sha(BASE/'source/runtime'/rel)==digest, 'baseline changed: '+rel
    expected = {'nvn/objects.c', 'nvn/nvn.h', 'nvn/vulkan/exec.c'}
    changed = []
    preserved = 0
    for p in sorted((BASE/'source/runtime').rglob('*')):
        if not p.is_file(): continue
        r = p.relative_to(BASE/'source/runtime')
        assert (WORK/'source/runtime'/r).is_file(), str(r)
        if sha(p) == sha(WORK/'source/runtime'/r): preserved += 1
        else: changed.append(r.as_posix())
    assert set(changed) == expected, changed
    added = {p.relative_to(WORK/'source/runtime').as_posix() for p in (WORK/'source/runtime').rglob('*') if p.is_file() and not (BASE/'source/runtime'/p.relative_to(WORK/'source/runtime')).exists()}
    assert added == {'nvn/vulkan/za_preparation_r21.h', 'nvn/vulkan/za_preparation_counters_r21.inc', 'nvn/vulkan/za_preparation_boundary_r21.inc'}, added
    a = (BASE/'source/runtime/nvn/vulkan/exec.c').read_text()
    b = (WORK/'source/runtime/nvn/vulkan/exec.c').read_text()
    functions = {}
    for name in ('sub', 'vk_cmd', 'vk_upload_cmd', 'vk_transient', 'guest_copy',
                 'vc_flush', 'xm_copy_back', 'renderer_fence_seq', 'renderer_wait_seq',
                 'dispatch_compute', 'draw', 'vk_exec_reset', 'vk_pace_frame'):
        pattern = rf'(?m)^(?:static )?[\w *]+\b{name}\([^;]*?\)\s*\{{[\s\S]*?^\}}'
        old, new = re.search(pattern, a), re.search(pattern, b)
        assert old and new and old[0] == new[0], name
        functions[name] = hashlib.sha256(new[0].encode()).hexdigest()
    extra = {}
    for p in sorted((BASE/'objects-r20b').glob('*.o')):
        if p.name in ('title_entry.o','observer.o'): continue
        digest = sha(WORK/'objects-r21'/p.name)
        assert digest == sha(p), p.name
        extra[p.name] = digest
    runtime_diffs = []
    runtime_equal = 0
    stripped_diffs = []
    stripped_equal = {}
    scratch = WORK/'audit'
    scratch.mkdir(exist_ok=True)
    for p in sorted((BASE/'source/build/ps5/rt').rglob('*.o')):
        r = p.relative_to(BASE/'source/build/ps5/rt')
        if sha(p) == sha(WORK/'source/build/ps5/rt'/r): runtime_equal += 1
        else: runtime_diffs.append(r.as_posix())
        for src, output in ((p, scratch/'base.o'), (WORK/'source/build/ps5/rt'/r, scratch/'candidate.o')):
            subprocess.run(['/usr/lib/llvm-21/bin/llvm-strip', '--strip-debug', '-o', str(output), str(src)], check=True)
        if sha(scratch/'base.o') == sha(scratch/'candidate.o'):
            stripped_equal[r.as_posix()] = sha(scratch/'candidate.o')
        else: stripped_diffs.append(r.as_posix())
    assert set(stripped_diffs) == {'nvn/objects.o', 'nvn/vulkan/exec.o', 'nvn/vulkan/vma.o'}, stripped_diffs
    vma_paths = [tree/'source/build/ps5/rt/nvn/vulkan/vma.o' for tree in (BASE, WORK)]
    vma_sections = [allocated_sections(p) for p in vma_paths]
    assert vma_sections[0] == vma_sections[1], 'VMA changed beyond assertion source path'
    vma_disassembly = [subprocess.check_output(['/usr/lib/llvm-21/bin/llvm-objdump', '-dr', str(p)], text=True)
                       for p in vma_paths]
    vma_disassembly = [re.sub(r'(?m)^.*:\s+file format elf64-x86-64$', '@OBJECT@', text)
                       for text in vma_disassembly]
    assert vma_disassembly[0] == vma_disassembly[1], 'VMA instructions/relocations changed'
    nm = '/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk/bin/llvm-nm'
    imports = []
    for tree in (BASE, WORK):
        out = subprocess.check_output([nm, '--dynamic', '--undefined-only', str(tree/'source/build/ps5/title/llvm-pie.elf')], text=True)
        imports.append(sorted(line.split()[-1] for line in out.splitlines() if line.split()))
    assert imports[0] == imports[1], 'unexpected dynamic imports'
    game = Path('/home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a')
    driver = Path('/home/tomer/ps5-za-native/PS5_Vulkan/build/ps5/libvulkan_radeon.ps5.a')
    if not driver.is_file():
        matches = list(Path('/home/tomer/ps5-za-native/PS5_Vulkan').rglob('libvulkan_radeon.ps5.a'))
        assert len(matches) == 1, matches
        driver = matches[0]
    historical = json.loads((ROOT/'evidence/submission-r20b/preservation-audit.json').read_text())
    assert sha(game) == historical['game_archive']['sha256'], 'game archive changed'
    assert sha(driver) == historical['driver']['sha256'], 'driver archive changed'
    result = {'added_runtime_sources': sorted(added), 'changed_runtime_sources': changed, 'unchanged_runtime_source_files': preserved,
        'unchanged_functions_sha256': functions, 'unchanged_extra_objects': extra,
        'unchanged_runtime_objects': runtime_equal, 'changed_runtime_objects': runtime_diffs,
        'unchanged_stripped_runtime_objects': stripped_equal,
        'changed_stripped_runtime_objects': stripped_diffs,
        'runtime_object_note': 'All runtime objects were rebuilt after the shared nvn.h declaration changed. 61/64 expected to match byte-for-byte after stripping debug metadata. VMA instruction/relocation disassembly is identical and all allocated sections match after normalizing its assertion __FILE__ directory. Only objects.o and exec.o have intended code changes.',
        'vma_allocated_sections_equal_after_assertion_path_normalization': len(vma_sections[0]),
        'vma_instruction_and_relocation_disassembly_equal': True,
        'vma_disassembly_sha256': hashlib.sha256(vma_disassembly[0].encode()).hexdigest(),
        'same_dynamic_imports': True, 'dynamic_import_count': len(imports[0]),
        'game_archive': {'path': str(game), 'sha256': sha(game), 'size': game.stat().st_size,
                         'mtime_ns': game.stat().st_mtime_ns},
        'driver': {'path': str(driver), 'sha256': sha(driver), 'size': driver.stat().st_size,
                   'mtime_ns': driver.stat().st_mtime_ns,
                   'note': 'Hash equals the recorded r20b preservation audit; no driver code changes in r21.'},
        'note': 'Only immutable descriptor binding recipes/lazy rscale, counters/profile boundary API, observer handling and title revision changed. No allocation/update/bind or submission policy semantics intentionally changed; hardware testing pending.'}
    (EVIDENCE/'preservation-audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('changed_runtime_sources', 'unchanged_runtime_source_files',
        'unchanged_runtime_objects', 'changed_stripped_runtime_objects', 'same_dynamic_imports', 'dynamic_import_count')}, indent=2))

if __name__ == '__main__': main()
