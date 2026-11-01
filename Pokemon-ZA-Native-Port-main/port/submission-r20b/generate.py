"""Generate private r20b sources; never edit the r20/r19 inputs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OLD = ROOT/'port/submission-r20'
def once(s, a, b):
    assert s.count(a) == 1, (s.count(a), a[:100])
    return s.replace(a, b)
def write(name, text):
    p = HERE/name
    assert not p.exists(), f'Preserve prepared file: {p}'
    p.write_text(text, newline='\n')

def main():
    h = (OLD/'submission.h').read_text().replace('ZA_SUBMISSION_R20_H', 'ZA_SUBMISSION_R20B_H')
    h = h.replace(' * sequence. Only their queue submission is batched. Keep below the 8-slot\n * renderer ring so a batch never needs its own completion to allocate a slot. */',
        ' * sequence. Storage holds 8 lists; selected caps 2/4 leave ring overlap.\n * The 8-list profile fills the renderer ring and is a diagnostic comparator. */')
    h = h.replace('ZA_SUB_PRESENT, ZA_SUB_CAPACITY, ZA_SUB_REASONS', 'ZA_SUB_PRESENT, ZA_SUB_CAPACITY, ZA_SUB_SWITCH, ZA_SUB_REASONS')
    h = h.replace('"internal", "present", "capacity"', '"internal", "present", "capacity", "switch"')
    start = h.index('/* Strict startup profile:')
    end = h.index('static void za_submission_flush_to', start)
    h = h[:start] + '''/* 0 rejects malformed input; startup chooses baseline 1 on rejection. */
static inline unsigned za_submission_parse_profile(const char *text) {
    if (!text) return 0;
    while (*text == ' ' || *text == '\\t' || *text == '\\r' || *text == '\\n') ++text;
    unsigned limit = 0, len = 0;
    if (!strncmp(text, "each", 4)) { limit = 1; len = 4; }
    else if (!strncmp(text, "batch2", 6)) { limit = 2; len = 6; }
    else if (!strncmp(text, "batch4", 6)) { limit = 4; len = 6; }
    else if (!strncmp(text, "batch8", 6)) { limit = 8; len = 6; }
    else return 0;
    text += len;
    while (*text == ' ' || *text == '\\t' || *text == '\\r' || *text == '\\n') ++text;
    return *text ? 0 : limit;
}
static inline const char *za_submission_profile_name(unsigned limit) {
    return limit == 2 ? "batch2" : limit == 4 ? "batch4" : limit == 8 ? "batch8" : "each";
}
''' + h[end:]
    write('submission.h', h)

    q = (OLD/'queue.inc').read_text().replace('[za-r20-submit]', '[za-r20b-submit]')
    q = once(q, 'static bool za_batch_on, za_submit_defer;', 'static bool za_batch_on, za_submit_defer;\nstatic unsigned za_batch_limit = 1;')
    q = once(q, 'za_sq.lists + 1 >= ZA_BATCH_LISTS', 'za_sq.lists + 1 >= za_batch_limit')
    q = q.replace('za_batch_on ? "batch" : "each"', 'za_submission_profile_name(za_batch_limit)')
    q = once(q, 'za_batch_on = za_submission_profile_batch(profile) && !ENV("LARECOMP_VK_SUBMIT_EACH");',
        '''za_batch_limit = za_submission_parse_profile(profile);
    if (!za_batch_limit || ENV("LARECOMP_VK_SUBMIT_EACH") || ENV("LARECOMP_SYNC_SUBMIT")) za_batch_limit = 1;
    za_batch_on = za_batch_limit > 1;''')
    q = once(q, 'za_submission_profile_name(za_batch_limit), ZA_BATCH_LISTS,',
        'za_submission_profile_name(za_batch_limit), za_batch_limit,')
    write('queue.inc', q)
    write('executor.inc', (OLD/'executor.inc').read_text())

    o = (ROOT/'port/local-shader-r19/observer-r19.c').read_text()
    o = once(o, 'extern int za_performance_status(void);',
        'extern int za_performance_status(void);\nextern int za_submission_switch_profile(const char *, uint64_t);')
    marker = 'static bool decimal(const char *text, uint64_t *out) {'
    acknowledgement = r'''/* Separate receipt: profile/list cap are applied, not just queued. */
static void ack_submission(const Command *c, const char *result, unsigned cap, uint64_t frame, uint64_t cost) {
    const char *actual = cap == 1 ? "each" : cap == 2 ? "batch2" : cap == 4 ? "batch4" : cap == 8 ? "batch8" : "";
    char path[320], text[800];
    snprintf(path, sizeof path, "%s/ack_%" PRIu64 ".json", session_dir, c->seq);
    snprintf(text, sizeof text,
        "{\"session\":\"%016" PRIx64 "\",\"seq\":%" PRIu64 ",\"op\":\"submission\",\"result\":\"%s\","
        "\"file\":\"\",\"cost_ns\":%" PRIu64 ",\"requested_profile\":\"%s\",\"profile\":\"%s\",\"max_lists\":%u,\"frame\":%" PRIu64 "}\n",
        session, c->seq, result, cost, c->arg, actual, cap, frame);
    if (!write_text(path, text)) sceKernelDebugOutText(0, "[za-observer] submission ack write failed\n");
}
'''
    o = once(o, marker, acknowledgement + marker)
    o = once(o, '    sequence = serial; /* Consume malformed new commands;',
        '''    if (!strcmp(op,"submission") && count == 4 &&
        (!strcmp(arg,"each") || !strcmp(arg,"batch2") || !strcmp(arg,"batch4") || !strcmp(arg,"batch8"))) valid = true;
    sequence = serial; /* Consume malformed new commands;''')
    o = once(o, '    } else if(!strcmp(c.op,"fps")) {', r'''    } else if(!strcmp(c.op,"submission")) {
        if (!submitted || represented) { ack_submission(&c,"rejected_boundary",0,frame,0); return; }
        uint64_t before = plat_now_ns();
        int applied = za_submission_switch_profile(c.arg, frame);
        const char *result = applied > 0 ? "applied" : applied == -2 ? "rejected_override" : "drain_failed";
        ack_submission(&c,result,applied > 0 ? (unsigned)applied : 0,frame,plat_now_ns()-before);
    } else if(!strcmp(c.op,"fps")) {''')
    write('observer-r20b.c', o)

    test = (OLD/'test-executor.c').read_text()
    test = once(test, '    za_batch_on = batch;', '    za_batch_on = batch; za_batch_limit = batch ? 8 : 1;')
    test = once(test, '    assert(za_submission_profile_batch("batch\\n"));',
        '    assert(za_submission_parse_profile("batch4\\n") == 4);')
    test = once(test, '    assert(za_submission_profile_batch(" \\tbatch\\r\\n"));',
        '    assert(za_submission_parse_profile(" \\tbatch2\\r\\n") == 2);\n    assert(za_submission_parse_profile("batch8") == 8);')
    test = test.replace('za_submission_profile_batch(', 'za_submission_parse_profile(')
    test = once(test, '    assert(!za_submission_parse_profile("each\\n"));',
        '    assert(za_submission_parse_profile("each\\n") == 1);\n    assert(!za_submission_parse_profile("batch"));')
    test = once(test, '#include "executor.inc"', '''#include "executor.inc"
static uint64_t renderer_fence_seq(void) { return logical_seq; }
static bool force_incomplete;
static uint64_t vk_completed_seq(void) { return force_incomplete ? 0 : signaled; }
#include "boundary.inc"''')
    test = once(test, '    za_submission_report();', '''    reset(true); normal(8); za_batch_limit = 4; run(8);
    assert(captured_n == 2 && za_sq.batch_hist[3] == 2);
    reset(true); normal(8); za_batch_limit = 2; run(8);
    assert(captured_n == 4 && za_sq.batch_hist[1] == 4);
    reset(true); scripts[0] = NORMAL; za_execute_one(0, false);
    assert(za_sq.ncbs && !signaled);
    assert(backend_submission_switch_profile("batch4", 99) == 4);
    assert(!za_sq.ncbs && signaled == logical_seq && za_batch_limit == 4);
    assert(backend_submission_switch_profile("batch2", 100) == 2);
    assert(backend_submission_switch_profile("each", 101) == 1 && !za_batch_on);
    assert(backend_submission_switch_profile("batch", 102) == -1 && za_batch_limit == 1);
    assert(!setenv("LARECOMP_VK_SUBMIT_EACH", "1", 1));
    assert(backend_submission_switch_profile("batch4", 103) == -2 && za_batch_limit == 1);
    assert(!unsetenv("LARECOMP_VK_SUBMIT_EACH"));
    assert(!setenv("LARECOMP_SYNC_SUBMIT", "1", 1));
    assert(backend_submission_switch_profile("batch2", 104) == -2 && za_batch_limit == 1);
    assert(!unsetenv("LARECOMP_SYNC_SUBMIT"));
    force_incomplete = true;
    assert(backend_submission_switch_profile("batch4", 105) == -3 && za_batch_limit == 1);
    force_incomplete = false;
    za_submission_report();''')
    test = '#define _POSIX_C_SOURCE 200809L\n' + test
    test = test.replace('#define LOG(...) ((void)0)', 'static char log_line[2048];\n#define LOG(...) ((void)snprintf(log_line,sizeof log_line,__VA_ARGS__))')
    write('test-executor.c', test)
    obs_test = (ROOT/'port/local-shader-r19/test-observer-r19.c').read_text().replace('"observer-r19.c"', '"observer-r20b.c"')
    obs_test = once(obs_test, 'static int requested_mode, capture_calls;',
        'static int requested_mode, capture_calls, submission_calls, applied_cap;\nstatic uint64_t applied_frame;')
    obs_test = once(obs_test, 'static void capture(void *p,const char *path)', '''int za_submission_switch_profile(const char *profile, uint64_t frame) {
    ++submission_calls; applied_frame = frame;
    applied_cap = !strcmp(profile,"each") ? 1 : !strcmp(profile,"batch2") ? 2 : !strcmp(profile,"batch4") ? 4 : 8;
    return applied_cap;
}
static void capture(void *p,const char *path)''')
    obs_test = once(obs_test, '    puts("observer protocol,', '''    send(14,"submission batch4"); frame(i++,0);
    assert(submission_calls==1 && applied_cap==4 && applied_frame==i-1);
    { char path[320], buf[800]; snprintf(path,sizeof path,"%s/ack_14.json",session_dir);
      FILE *f=fopen(path,"rb"); assert(f); size_t n=fread(buf,1,sizeof buf-1,f);fclose(f);buf[n]=0;
      assert(strstr(buf,"\\\"result\\\":\\\"applied\\\"") && strstr(buf,"\\\"max_lists\\\":4") && strstr(buf,"\\\"profile\\\":\\\"batch4\\\"")); }
    send(15,"submission batch2"); za_observer_frame(i++,true,true,0,(void*)1,capture);
    assert(submission_calls==1);
    send(16,"submission batch2"); za_observer_frame(i++,false,false,0,(void*)1,capture);
    assert(submission_calls==1);
    send(17,"submission batch"); frame(i++,0); assert(submission_calls==1);
    send(18,"measure 1"); frame(i++,0); assert(samples);
    send(19,"submission batch2"); frame(i++,0); assert(samples && submission_calls==1);
    clock_ns+=NS; frame(i++,0);
    while(samples) {clock_ns+=NS/30;frame(i++,0);assert(submission_calls==1);}
    clock_ns+=NS;frame(i++,0);assert(submission_calls==2 && applied_cap==2);
    send(20,"submission each"); frame(i++,0); assert(submission_calls==3 && applied_cap==1);
    puts("observer live submission receipts, represented/missing-present rejection, measurement exclusion; observer protocol,''')
    write('test-observer.c', obs_test)
    b = (OLD/'build.sh').read_text()
    b = b.replace('batch-r20-20261028', 'batch-r20b-20261028').replace('compiler-r19-20261028', 'batch-r20-20261028')
    b = b.replace('objects-r20', 'objects-r20b').replace('submission-r20', 'submission-r20b').replace('randomizer-r20-batch', 'randomizer-r20b-batch')
    b = b.replace('local-r20.mk','local-r20b.mk').replace('local-title-r20','local-title-r20b')
    b = once(b, "'executor.inc za_submission_executor_r20.inc'; do", "'executor.inc za_submission_executor_r20.inc' 'boundary.inc za_submission_boundary_r20b.inc'; do")
    b = once(b, 'libs=("$glsl', '''sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \\
    -I"$project/port/observer-r17" -c "$root/observer-r20b.c" -o "$obj/observer.o"
libs=("$glsl''')
    b = once(b, "printf 'batch\\n'", "printf 'each\\n'")
    write('build.sh', b)
    print('Generated private r20b canonical sources and tests.')

if __name__ == '__main__': main()
