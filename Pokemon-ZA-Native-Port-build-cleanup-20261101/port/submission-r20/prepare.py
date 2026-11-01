"""Create r20 in a new WSL tree. Baseline and generated game archive are inputs."""
import difflib
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORT = ROOT / 'port/submission-r20'
EVIDENCE = ROOT / 'evidence/submission-r20'
BASE = Path('/home/tomer/ps5-za-native/compiler-r19-20261028')
WORK = Path('/home/tomer/ps5-za-native/batch-r20-20261028')
PIN = {
    'runtime/nvn/vulkan/exec.c': 'c946497e728a57389d5d2bed8b7904548aafe74dabb9b92b38b37109752dcee4',
    'runtime/nvn/objects.c': '42f556e32637dc673012ce0495cf718e208642256754b2dc508ffa6127c60da3',
    'runtime/nvn/nvn.h': '58ec91a28415d5e1140f816838c60ad56c5b7c9b8bf00d246c51f935f5325515',
}

def replace_once(text, old, new):
    assert text.count(old) == 1, (text.count(old), old[:120])
    return text.replace(old, new)

def main():
    assert not WORK.exists(), 'Never overwrite another prepared build.'
    for name, want in PIN.items():
        assert hashlib.sha256((BASE/'source'/name).read_bytes()).hexdigest() == want, name
    WORK.mkdir()
    for name in ('source', 'port', 'inc', 'shaders', 'evidence'):
        shutil.copytree(BASE/name, WORK/name, symlinks=True,
            ignore=shutil.ignore_patterns('build', '.git') if name == 'source' else None)
    for name in ('rt', 'inc'):
        shutil.copytree(BASE/'source/build/ps5'/name, WORK/'source/build/ps5'/name, symlinks=True)
    shutil.copytree(BASE/'objects-r19', WORK/'objects-r20')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    patches = []
    for rel in PIN:
        path = WORK/'source'/rel
        old = path.read_text()
        text = old
        if rel.endswith('objects.c'):
            text = replace_once(text, 'for (int i = 0; i < n; i++) backend_execute(handles[i]);',
                'backend_execute_batch(handles, n);  // r20: preserve the NVN call boundary')
        elif rel.endswith('nvn.h'):
            text = replace_once(text, 'void backend_execute(uint64_t handle);',
                'void backend_execute(uint64_t handle);\nvoid backend_execute_batch(const uint64_t *handles, int n);')
        else:
            text = replace_once(text, '#include "za_r16_cache_table.h"',
                '#include "za_r16_cache_table.h"\n#include "za_submission_r20.h"')
            text = replace_once(text, 'if (!seq) { wait_why = NULL; return; }',
                'if (!seq) { wait_why = NULL; return; }\n    za_submission_flush_to(seq, ZA_SUB_WAIT);  // never wait for work still held on the CPU')
            text = replace_once(text, '// Submit the pending work (if any). wait/signal: binary semaphores for presentation (may be null).',
                '#include "za_submission_queue_r20.inc"\n\n// Submit the pending work (if any). wait/signal: binary semaphores for presentation (may be null).')
            block = '''    {
        PROF_T0();
        dl_note("submit %llu", (unsigned long long)submit_seq + 1);
        VkResult sr = vkQueueSubmit2(g_vk.queue, 1, &si, VK_NULL_HANDLE);
        if (sr == VK_ERROR_DEVICE_LOST) vk_devlost_dump();
        VK_CHECK(sr);
        PROF_ADD(prof_submit);
    }'''
            text = replace_once(text, block, '''    dl_note("logical submit %llu", (unsigned long long)submit_seq + 1);
    za_submission_accept(&si);  // r20: ordered closed CBs, one final timeline signal''')
            text = replace_once(text, 'const char *renderer_stats(void) {',
                'const char *renderer_stats(void) {\n    za_submission_report();')
            text = replace_once(text, 'if (r->op < CMD_COUNT) op_counts[r->op]++;',
                'if (r->op < CMD_COUNT) op_counts[r->op]++;\n        za_command_count++;')
            text = replace_once(text, 'if (r->x[1]) nvn_sync_set_seq(r->x[1], renderer_fence_seq());',
                'if (r->x[1]) nvn_sync_set_seq(r->x[1], renderer_fence_seq());\n            za_list_fenced = true;  // including nested CMD_CALL lists')
            start = text.index('void backend_execute(uint64_t handle) {')
            assert text[start:].count('{') == text[start:].count('}') == 1
            text = text[:start] + '#include "za_submission_executor_r20.inc"\n'
        path.write_text(text)
        patches += list(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
            fromfile='r19a/'+rel, tofile='r20/'+rel))
    for src, dst in [('submission.h', 'za_submission_r20.h'), ('queue.inc', 'za_submission_queue_r20.inc'),
                     ('executor.inc', 'za_submission_executor_r20.inc')]:
        shutil.copy2(PORT/src, WORK/'source/runtime/nvn/vulkan'/dst)
    (EVIDENCE/'runtime-r20.patch').write_text(''.join(patches))
    receipt = {'base': str(BASE), 'work': str(WORK), 'base_sources': PIN,
        'base_eboot_sha256': '1f8d448a9d6a89f3abc2d94e36db23bef008d3dc8e1d30e9f3ea7c5fea557918',
        'runtime_sources': {r: hashlib.sha256((WORK/'source'/r).read_bytes()).hexdigest() for r in PIN}}
    (EVIDENCE/'preparation.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    main()
