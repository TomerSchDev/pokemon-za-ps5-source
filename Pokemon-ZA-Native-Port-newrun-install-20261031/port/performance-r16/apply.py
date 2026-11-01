"""Build guarded r16 experiments in an isolated snapshot, never in r15."""
from pathlib import Path
import hashlib, json, shutil, sys, difflib

root = Path(__file__).resolve().parents[2]
work = Path(sys.argv[1])
assert work.name == 'perf-r16-20261028', 'Only the isolated r16 work directory is allowed'
source = work / 'source'
target = source / 'runtime/nvn/vulkan/exec.c'
backup = work / 'exec-r15-original.c'
if not backup.exists():
    assert hashlib.sha256(target.read_bytes()).hexdigest() == '1cfd51bcca8d2a2fd8419eb2e2752c19d4fb75eaeab3a1b1fc381a5fa7d6e72d'
    shutil.copyfile(target, backup)
old = backup.read_text()
s = old
changes = []
def replace(a, b, name):
    global s
    assert s.count(a) == 1, (name, s.count(a))
    s = s.replace(a, b)
    changes.append(name)

replace('#include "../../settings.h"', '#include "../../settings.h"\n#include "za_r16_cache_table.h"', 'bounded growing caches')
shutil.copyfile(root/'port/performance-r16/cache_table.h', target.parent/'za_r16_cache_table.h')
replace('    static VkDynamicState d[sizeof DYN / sizeof DYN[0]];\n    static uint32_t nd;',
        '    static _Thread_local VkDynamicState d[sizeof DYN / sizeof DYN[0]];\n    static _Thread_local uint32_t nd;', 'thread-private dynamic state initialization')
replace('#define PROG_TAB 4096\nstatic struct { uint64_t key; Prog *prog; } prog_tab[PROG_TAB];',
        'static ZaCacheTable prog_table;\nstatic uint64_t za_key_generation = 1;\nstatic uint64_t za_prog_memo_hits, za_pipe_memo_hits, za_pipe_memo_checks, za_lean_hits, za_lean_copies;\nstatic int za_memo_on(void) { static int v = -1; if (v < 0) v = ENV("ZA_R16_NO_KEY_MEMO") == NULL; return v; }', 'program table declaration')
replace('    uint32_t slot = (uint32_t)(h ^ (h >> 31)) & (PROG_TAB - 1);\n    while (prog_tab[slot].key && prog_tab[slot].key != h) slot = (slot + 1) & (PROG_TAB - 1);\n    if (prog_tab[slot].key) return prog_tab[slot].prog;\n    Prog *p = calloc(1, sizeof *p);\n    prog_tab[slot].key = h;\n    prog_tab[slot].prog = p;',
        '''    Prog *p = za_cache_get(&prog_table, h);
    if (p) return p;
    p = calloc(1, sizeof *p);
    if (!p || !za_cache_put(&prog_table, h, p)) {
        free(p); LOG("[za-r16] program cache allocation failed; draw skipped\\n"); return NULL;
    }''', 'bounded program lookup with OOM handling')
replace('#define PIPE_TAB 8192\nstatic struct { uint64_t key; Pipe *pipe; } pipe_tab[PIPE_TAB];',
        'static ZaCacheTable pipe_table;', 'pipeline table declaration')
replace('    uint32_t pslot = (uint32_t)(ph ^ (ph >> 29)) & (PIPE_TAB - 1);\n    while (pipe_tab[pslot].key && pipe_tab[pslot].key != ph) pslot = (pslot + 1) & (PIPE_TAB - 1);\n    Pipe *pp = pipe_tab[pslot].pipe;',
        '    Pipe *pp = za_cache_get(&pipe_table, ph);', 'bounded pipeline lookup')
replace('        pp->k = k;\n        pipe_tab[pslot].key = ph;\n        pipe_tab[pslot].pipe = pp;',
        '''        if (!pp || !za_cache_put(&pipe_table, ph, pp)) {
            free(pp); LOG("[za-r16] pipeline cache allocation failed; draw skipped\\n"); stat_skipped_here(); return;
        }
        pp->k = k;''', 'pipeline allocation failure handling')
replace('    memset(prog_tab, 0, sizeof prog_tab);\n    memset(pipe_tab, 0, sizeof pipe_tab);',
        '    za_cache_reset(&prog_table);\n    za_cache_reset(&pipe_table);\n    ++za_key_generation;', 'cache reset and memo invalidation')

# Retain the original hash bytes and lookup semantics; skip only repeated input
# hashing. Do not add an address-only program-result memo or bypass invalidation.
start=s.index('    uint64_t h = 0xcbf29ce484222325ull;', s.index('static Prog *get_program('))
end=s.index('    Prog *p = za_cache_get', start)
hashcode=s[start:end]
memo='''    struct ZaProgramInput {
        uint64_t code[2], generation;
        ShaderKey vertex;
        uint8_t rt_kind[8];
        uint32_t stencil, sint;
    } input;
    memset(&input, 0, sizeof input);
    input.code[0] = np->stages[0].code_addr; input.code[1] = np->stages[1].code_addr;
    input.generation = za_key_generation; memcpy(&input.vertex, vkey, sizeof *vkey);
    memcpy(input.rt_kind, fkey->rt_kind, sizeof input.rt_kind);
    input.stencil = fkey->stencil_slots; input.sint = fkey->sint_slots;
    static struct { bool valid; struct ZaProgramInput input; uint64_t hash; } last;
    uint64_t h;
    if (za_memo_on() && last.valid && !memcmp(&last.input, &input, sizeof input)) {
        h = last.hash; ++za_prog_memo_hits;
    } else {
HASHCODE
        last.valid = true; memcpy(&last.input, &input, sizeof input); last.hash = h;
    }
'''.replace('HASHCODE', hashcode.replace('    uint64_t h =', '    h =', 1))
s=s[:start]+memo+s[end:]; changes.append('exact-input program hash memo')

# Track queued as well as executing work. The single packed atomic snapshot
# cannot observe a completed job with an old completion epoch and pending=0.
activity='''static _Atomic uint64_t za_build_activity;
uint64_t za_renderer_build_activity(void) { return atomic_load(&za_build_activity); }
static void za_build_begin(void) { atomic_fetch_add(&za_build_activity, 1); }
static void za_build_end(void) { atomic_fetch_add(&za_build_activity, UINT64_C(0xffffffff)); }
'''
replace('typedef struct Job {', activity+'\ntypedef struct Job {', 'shader queue activity telemetry')
assert s.count('        j->fn(j->arg);')==2
s=s.replace('        j->fn(j->arg);', '        j->fn(j->arg);\n        za_build_end();')
replace('    if (sync_shaders()) { fn(arg); return; }\n    static bool started;\n    if (!started) { started = true; pthread_t t; pthread_create(&t, NULL, translator, NULL); }',
        '''    za_build_begin();
    if (sync_shaders()) { fn(arg); za_build_end(); return; }
    static bool started;
    if (!started) {
        pthread_t t;
        if (pthread_create(&t, NULL, translator, NULL)) { fn(arg); za_build_end(); return; }
        pthread_detach(t); started = true;
    }''', 'translation activity and thread failure fallback')
start=s.index('static void run_job(void (*fn)(void *), void *arg) {')
end=s.index('\n// ================================================================== state',start)
replace(s[start:end], '''static pthread_once_t za_workers_once = PTHREAD_ONCE_INIT;
static void za_start_workers(void) {
    int n = SDL_GetNumLogicalCPUCores() - 4;
    if (n < 4) n = 4;
    if (n > MAX_WORKERS) n = MAX_WORKERS;
    int made = 0;
    for (int i = 0; i < n; ++i) {
        pthread_t t;
        if (!pthread_create(&t, NULL, worker, (void *)(intptr_t)made)) { pthread_detach(t); ++made; }
    }
    atomic_store(&nworkers, made);
}
static void run_job(void (*fn)(void *), void *arg) {
    za_build_begin();
    if (sync_shaders()) { fn(arg); za_build_end(); return; }
    pthread_once(&za_workers_once, za_start_workers);
    if (!atomic_load(&nworkers)) { fn(arg); za_build_end(); return; }
    Job *j = malloc(sizeof *j);
    if (!j) { fn(arg); za_build_end(); return; }
    j->fn = fn; j->arg = arg; j->next = NULL;
    pthread_mutex_lock(&jobs_lock);
    if (jobs_tail) jobs_tail->next = j; else jobs_head = j;
    jobs_tail = j;
    pthread_cond_signal(&jobs_cond);
    pthread_mutex_unlock(&jobs_lock);
}
''', 'synchronized worker startup and tracked synchronous fallback')
replace('    Job *j = malloc(sizeof *j);\n    j->fn = fn;',
        '    Job *j = malloc(sizeof *j);\n    if (!j) { fn(arg); za_build_end(); return; }\n    j->fn = fn;', 'translation allocation fallback')

# Pipeline memo key captures every input used by the unchanged builder,
# including all eight pass formats, NULL attachments and fixed-function state.
# No pointers into mutable arrays are retained.
pipeinput='''typedef struct {
    Prog *prog;
    uint64_t generation;
    VkFormat color[8], depth, stencil;
    uint32_t ncolor, samples, attrib[16], stream[16][2], rt_format[8], channel_mask;
    int nattrib, nstream;
    uint8_t rt_present[8], blend[8][8], blend_enable, a2c, cls, poly_fill, depth_clamp, restart;
    FixedState fx;
} ZaPipeInput;
static void za_pipe_input(ZaPipeInput *in, Prog *pr, uint8_t cls, bool native, uint32_t mode, const FixedState *fx) {
    memset(in, 0, sizeof *in);
    in->prog = pr; in->generation = za_key_generation;
    memcpy(in->color, pass_color, sizeof in->color);
    in->depth = pass_depth; in->stencil = pass_stencil; in->ncolor = pass_ncolor; in->samples = pass_samples;
    memcpy(in->attrib, st.attrib, sizeof in->attrib); memcpy(in->stream, st.stream, sizeof in->stream);
    in->nattrib = st.nattrib; in->nstream = st.nstream;
    for (int i = 0; i < 8; ++i) if (st.rt.color[i]) { in->rt_present[i] = 1; in->rt_format[i] = st.rt.color[i]->format; }
    memcpy(in->blend, st.blend, sizeof in->blend);
    in->channel_mask = st.channel_mask; in->blend_enable = st.color_state[0]; in->a2c = st.ms[0xC] != 0;
    in->cls = cls; in->poly_fill = st.poly[2] != 1;
    static int noclamp = -1;
    if (noclamp < 0) noclamp = ENV("LARECOMP_VK_NO_DEPTH_CLAMP") != NULL;
    in->depth_clamp = st.depth_clamp && !noclamp;
    in->restart = g_vkc.no_eds2 && st.prim_restart && native && (mode == 3 || mode == 5);
    if (g_vkc.no_eds1) in->fx = *fx;
}
'''
replace('static ZaCacheTable pipe_table;', 'static ZaCacheTable pipe_table;\n'+pipeinput, 'by-value pipeline memo dependencies')
start=s.index('    // ---- pipeline\n    PipeKey k;')
end=s.index('    if (!wait_built(&pp->state, r))',start)
original=s[start:end]
builder=original.replace('    PipeKey k;\n','',1)
builder=builder.replace('    FixedState fx;\n    fixed_state(&fx, vkey.flip_x, vkey.flip_y, native, topo);\n','')
builder=builder.replace('    Pipe *pp = za_cache_get', '    pp = za_cache_get',1)
new='''    FixedState fx;
    fixed_state(&fx, vkey.flip_x, vkey.flip_y, native, topo);
    ZaPipeInput memo_input;
    za_pipe_input(&memo_input, pr, cls, native, mode, &fx);
    static struct { bool valid; ZaPipeInput input; PipeKey key; Pipe *pipe; } last_pipe;
    bool memo_hit = za_memo_on() && last_pipe.valid && !memcmp(&last_pipe.input, &memo_input, sizeof memo_input);
    static int shadow = -1;
    if (shadow < 0) shadow = ENV("ZA_R16_MEMO_SHADOW") != NULL;
    PipeKey k;
    Pipe *pp;
    if (memo_hit && !shadow) { k = last_pipe.key; pp = last_pipe.pipe; ++za_pipe_memo_hits; }
    else {
BUILDER
        if (memo_hit) {
            ++za_pipe_memo_checks;
            if (pp != last_pipe.pipe || memcmp(&k, &last_pipe.key, sizeof k)) {
                LOG("[za-r16] pipeline memo mismatch; refusing incorrect draw\\n"); abort();
            }
        }
        last_pipe.valid = true; memcpy(&last_pipe.input, &memo_input, sizeof memo_input);
        memcpy(&last_pipe.key, &k, sizeof k); last_pipe.pipe = pp;
    }
'''.replace('BUILDER', builder)
s=s[:start]+new+s[end:]; changes.append('pipeline memo with exact shadow comparison')

# Selective upstream lean graphics-driver constants. Preserve full compute
# path and r15's transform-feedback scale table; do not change descriptor ABI.
lean='''static int za_lean_on(void) { static int v = -1; if (v < 0) v = ENV("ZA_R16_NO_CBUF_LEAN") == NULL; return v; }
static VkSpan za_driver_constants(int stage, uint64_t size) {
    static struct { uint64_t seq, size, generation; int stage; Range sb[16]; VkSpan span; } last[2];
    int slot = stage == 1;
    uint32_t base = 0x110 + 0x400 * slot;
    int ne = size > base ? (int)((size - base + 15) / 16) : 0;
    if (ne > 16) ne = 16;
    uint64_t seq = vk_pending_seq();
    const Range *sb = st.sbuf[stage];
    if (last[slot].generation == za_key_generation && last[slot].seq == seq && last[slot].size == size &&
        last[slot].stage == stage && !memcmp(last[slot].sb, sb, (size_t)ne * sizeof(Range))) {
        ++za_lean_hits; return last[slot].span;
    }
    uint32_t drv[0x800 / 4];
    memset(drv, 0, size);
    for (int i = 0; i < ne; ++i) {
        uint32_t *e = &drv[(base + 16 * i) / 4];
        e[0] = (uint32_t)sb[i].addr; e[1] = (uint32_t)(sb[i].addr >> 32); e[2] = (uint32_t)sb[i].size;
    }
    VkSpan sp = vk_transient_copy(drv, size, 256);
    last[slot].seq = seq; last[slot].size = size; last[slot].stage = stage; last[slot].span = sp;
    last[slot].generation = za_key_generation; memcpy(last[slot].sb, sb, (size_t)ne * sizeof(Range));
    ++za_lean_copies;
    return sp;
}
'''
replace('// Constant buffer k of a stage (renderer.m bind_cbufs), copied into transient memory.',
        lean+'\n// Constant buffer k of a stage (renderer.m bind_cbufs), copied into transient memory.', 'lean active graphics constant blocks')
replace('        if (size < 0x500 && stage == 5) size = 0x500;',
        '        if (stage != 5 && za_lean_on()) return ubo_span(za_driver_constants(stage, size), size);\n        if (size < 0x500 && stage == 5) size = 0x500;', 'lean path opt-out')

# Log cumulative counters with the existing periodic statistics.
pos=s.index('void vk_pace_frame(') if 'void vk_pace_frame(' in s else -1
# Insert after stats LOG call via an unambiguous following statement below.
needle='             atomic_exchange(&stat_compiles, 0),'
assert needle in s
start=s.index(needle)
end=s.index(';',start)+1
s=s[:end]+'''
        LOG("[za-r16] memo program=%llu pipeline=%llu shadow=%llu constants reused=%llu copied=%llu tables=%zu/%zu entries=%zu/%zu\\n",
            (unsigned long long)za_prog_memo_hits, (unsigned long long)za_pipe_memo_hits,
            (unsigned long long)za_pipe_memo_checks, (unsigned long long)za_lean_hits, (unsigned long long)za_lean_copies,
            prog_table.capacity, pipe_table.capacity, prog_table.count, pipe_table.count);
'''+s[end:]
# These globals are used by the early statistics function.
decl='static ZaCacheTable prog_table;\nstatic uint64_t za_key_generation = 1;\nstatic uint64_t za_prog_memo_hits, za_pipe_memo_hits, za_pipe_memo_checks, za_lean_hits, za_lean_copies;'
s=s.replace(decl,'')
s=s.replace('static ZaCacheTable pipe_table;','')
s=s.replace('#include "za_r16_cache_table.h"','#include "za_r16_cache_table.h"\n'+decl+'\nstatic ZaCacheTable pipe_table;')

target.write_text(s)
entry=(root/'port/title/title_entry.c').read_text()
assert entry.count('    setenv("LARECOMP_NO_LAUNCHER"')==1
entry=entry.replace('    setenv("LARECOMP_NO_LAUNCHER"', '    extern void za_performance_init(void);\n    za_performance_init();\n    setenv("LARECOMP_NO_LAUNCHER"',1)
(work/'title_entry-r16.c').write_text(entry)

cheats=(root/'port/randomizer/cheats.cpp').read_text()
cheats=cheats.replace('namespace {', 'extern "C" void za_performance_request(int);\nextern "C" int za_performance_status(void);\nnamespace {',1)
cheats=cheats.replace('row=(row.load()+2)%3','row=(row.load()+3)%4').replace('row=(row.load()+1)%3','row=(row.load()+1)%4')
cheats=cheats.replace('        if(row==2){shiny=0;capture=0;}', '        if(row==3){za_performance_request(za_performance_status()!=1);return true;}\n        if(row==2){shiny=0;capture=0;}')
cheats=cheats.replace('"RESET BOTH TO NORMAL"};','"RESET BOTH TO NORMAL",std::string("FPS TRIAL  ")+(za_performance_status()==1?"60 AUTO":za_performance_status()==2?"30 FALLBACK - X RETRY":"30 - X START 60")};')
cheats=cheats.replace('for(int i=0;i<3;i++){','for(int i=0;i<4;i++){').replace('211+i*68','207+i*55').replace('225+i*68','220+i*55')
cheats=cheats.replace('"SHINY APPLIES TO NEWLY GENERATED POKEMON"','"FPS TRIAL: START AFTER LOADING - SESSION ONLY"')
(work/'cheats-r16.cpp').write_text(cheats)

build=(root/'port/randomizer/build-randomizer.sh').read_text()
build=build.replace('root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)', 'root='+repr(str(root)))
build=build.replace('work=/home/tomer/ps5-za-native/title-r1-20261027','work='+str(work)+'\nexport TITLE_WORK="$work"')
build=build.replace('revision=${RANDO_REV:-r1}', 'revision=r16')
build=build.replace('dist=$root/artifacts/randomizer-$revision', 'dist=$root/artifacts/randomizer-r16-validated')
build=build.replace('$work/fps-r13/liblasgame-r13.a','/home/tomer/ps5-za-native/title-r1-20261027/fps-r13/liblasgame-r13.a')
build=build.replace('$work/cheats-r12/liblasgame-r12.a','/home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a')
build=build.replace('${RANDO_CHEATS:-0}', '${RANDO_CHEATS:-1}')
build=build.replace('"$root/port/randomizer/cheats.cpp"','"$work/cheats-r16.cpp"')
build=build.replace('"$root/port/title/title_entry.c"','"$work/title_entry-r16.c"')
build=build.replace('export ZA_PS5_EXTRA_INPUTS=', 'cc -std=c11 "${flags[@]}" -I"$root/port/performance-r16" -c "$root/port/performance-r16/performance.c" -o "$obj/title_performance.o"\nexport ZA_PS5_EXTRA_INPUTS=')
build=build.replace('cp "$root/evidence/title-r14-repeat-pipeline-cache.bin" "$dist/PPSA91762/cache/vk_pipelines.bin"','# The existing console pipeline cache must be retained.')
build=build.replace("printf '30\\n' >", "printf 'optimized\\n' > \"$dist/PPSA91762/performance-options.txt\"\nprintf '30\\n' >")
(work/'build-r16.sh').write_text(build)
evidence=root/'evidence/performance-r16'; evidence.mkdir(exist_ok=True)
(evidence/'renderer-r16.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='r15/runtime/nvn/vulkan/exec.c',tofile='r16/runtime/nvn/vulkan/exec.c')))
manifest={'baseline_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'patched_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'changes':changes,'console_changed':False}
(evidence/'patch-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
