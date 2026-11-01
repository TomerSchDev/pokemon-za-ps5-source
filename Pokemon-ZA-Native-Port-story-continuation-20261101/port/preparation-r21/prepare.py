"""Reproducible isolated r21 preparation; never edits the installed r20b snapshot."""
from pathlib import Path
import difflib, hashlib, json, shutil
ROOT = Path(__file__).resolve().parents[2]
PORT = ROOT/'port/preparation-r21'
EVIDENCE = ROOT/'evidence/preparation-r21'
BASE = Path('/home/tomer/ps5-za-native/batch-r20b-20261028')
WORK = Path('/home/tomer/ps5-za-native/preparation-r21-20261028')
PINS = {
 'runtime/nvn/vulkan/exec.c':'9c51bba1327d9e2a3236d4e3874339e94a0d9551090b4eceddfac05173b5d165',
 'runtime/nvn/objects.c':'bcd9f6a95898b6bb39e97d283ce6b66e9e587a2ef1d9e0452489e0b66d821d25',
 'runtime/nvn/nvn.h':'503232b102f9405df18340736858a2cf28cce8b4f0dcac1d15e7a8d7c8ec1f5f'}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def once(text,old,new):
    assert text.count(old)==1,(text.count(old),old[:100])
    return text.replace(old,new)
def modify_exec(old):
    s=once(old,'#include "za_submission_r20.h"','#include "za_submission_r20.h"\n#include "za_preparation_r21.h"\n#include "za_preparation_counters_r21.inc"')
    s=once(s,'    za_submission_report();','    za_submission_report();\n    za_preparation_report();')
    s=once(s,'    int nbinds;\n    VkDescriptorSetLayout','    int nbinds;\n    ZaPrepRecipe prep;  // immutable, published before state becomes ready\n    VkDescriptorSetLayout')
    s=once(s,'    p->nbinds += vk_reflect(sf, nf, p->binds + p->nbinds, MAX_BIND - p->nbinds);',
        '    p->nbinds += vk_reflect(sf, nf, p->binds + p->nbinds, MAX_BIND - p->nbinds);\n'
        '    if (!za_prep_build(&p->prep, p->binds, p->nbinds)) { free(sv); free(sf); atomic_store(&p->state, 2); return; }')
    s=once(s,'    cp->p.nbinds = vk_reflect(spv, n, cp->p.binds, MAX_BIND);',
        '    cp->p.nbinds = vk_reflect(spv, n, cp->p.binds, MAX_BIND);\n'
        '    if (!za_prep_build(&cp->p.prep, cp->p.binds, cp->p.nbinds)) { free(spv); atomic_store(&cp->p.state, 2); return; }')
    start=s.index('static VkDescriptorSet stage_set(')
    end=s.index('\n// ================================================================== compute',start)
    original=s[start:end].rstrip()
    counted=once(original,'    if (n) vkUpdateDescriptorSets(g_vk.dev, (uint32_t)n, w, 0, NULL);',
        '    if (n) { ++cnt->updates; cnt->writes += (uint32_t)n; vkUpdateDescriptorSets(g_vk.dev, (uint32_t)n, w, 0, NULL); }')
    baseline=counted.replace('static VkDescriptorSet stage_set(', 'static VkDescriptorSet stage_set_original(',1)
    baseline=once(baseline,'const VkDescriptorImageInfo *pre_ii) {','const VkDescriptorImageInfo *pre_ii, ZaPrepCounters *cnt) {')
    prepared=counted.replace('static VkDescriptorSet stage_set(', 'static VkDescriptorSet stage_set_prepared(',1)
    prepared=once(prepared,'const VkDescriptorImageInfo *pre_ii) {',
        'const VkDescriptorImageInfo *pre_ii, unsigned flags, ZaPrepCounters *cnt) {\n'
        '    const ZaPrepStage *plan = &p->prep.stage[set];\n    bool planned = (flags & ZA_PREP_PLAN) != 0;')
    a=prepared.index('    float rs[70][4] =')
    b=prepared.index('    for (int i = 0; i < p->nbinds;',a)
    block=prepared[a:b]
    block=once(block,'    float rs[70][4] = {{1, 1, 0, 0}};  // ([65]: mirror mode, renderer.m; [66..69]: vertex transform feedback buffers)',
        '    memset(rs, 0, sizeof rs);\n    rs[0][0] = rs[0][1] = 1;')
    prepared=prepared[:a]+'    float rs[70][4];\n    if (!(flags & ZA_PREP_LAZY) || plan->has_rscale) {\n'+''.join('    '+line+'\n' for line in block.splitlines())+'    }\n'+prepared[b:]
    first='''    for (int i = 0; i < p->nbinds; i++) {
        VkBindingInfo *b = &p->binds[i];
        if (b->set != set) continue;'''
    prepared=once(prepared,first,'''    int ordinary_count = planned ? plan->nordinary : p->nbinds;
    for (int i = 0; i < ordinary_count; i++) {
        VkBindingInfo *b = &p->binds[planned ? plan->ordinary[i].source : i];
        if (!planned && b->set != set) continue;
        ZaPrepKind kind = planned ? (ZaPrepKind)plan->ordinary[i].kind : za_prep_kind(b);''')
    prepared=once(prepared,'if (b->type == VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER && b->binding >= 32) {','if (kind == ZA_PREP_TEXTURE) {')
    prepared=once(prepared,'} else if (b->type == VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER && b->binding < 17) {','} else if (kind == ZA_PREP_CBUF) {')
    prepared=once(prepared,'} else if (b->type == VK_DESCRIPTOR_TYPE_STORAGE_BUFFER) {','} else if (kind == ZA_PREP_STORAGE) {')
    second='''    for (int i = 0; i < p->nbinds; i++) {
        VkBindingInfo *b = &p->binds[i];
        if (b->set != set || b->type != VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER ||
            (b->binding != 18 && b->binding != 19 && b->binding != GMAP_BUFFER_INDEX)) continue;'''
    prepared=once(prepared,second,'''    int special_count = planned ? plan->nspecial : p->nbinds;
    for (int i = 0; i < special_count; i++) {
        VkBindingInfo *b = &p->binds[planned ? plan->special[i].source : i];
        if (!planned && (b->set != set || b->type != VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER ||
            (b->binding != 18 && b->binding != 19 && b->binding != GMAP_BUFFER_INDEX))) continue;''')
    wrapper='''static VkDescriptorSet stage_set(Prog *p, VkDescriptorSetLayout layout, uint32_t set, int stage, ShaderInfo *si, const float *rscale_row0,
                                 const float tint[8], uint32_t gx, uint32_t gy, uint32_t gz, const VkDescriptorImageInfo *pre_ii) {
    unsigned flags = za_preparation_profile_flags();
    ZaPrepCounters *cnt = &za_prep_counts[flags];
    const ZaPrepStage *plan = &p->prep.stage[set];
    ++cnt->calls; ++cnt->allocs;
    if (stage == 5) ++cnt->compute; else if (stage == 1) ++cnt->fragment; else ++cnt->vertex;
    cnt->ordinary_visits += (flags & ZA_PREP_PLAN) ? plan->nordinary : (unsigned)p->nbinds;
    cnt->special_visits += (flags & ZA_PREP_PLAN) ? plan->nspecial : (unsigned)p->nbinds;
    if (!(flags & ZA_PREP_LAZY) || plan->has_rscale) ++cnt->rscale_builds; else ++cnt->rscale_skips;
    if (!flags) return stage_set_original(p, layout, set, stage, si, rscale_row0, tint, gx, gy, gz, pre_ii, cnt);
    return stage_set_prepared(p, layout, set, stage, si, rscale_row0, tint, gx, gy, gz, pre_ii, flags, cnt);
}
'''
    s=s[:start]+baseline+'\n\n'+prepared+'\n\n'+wrapper+s[end:]
    s=once(s,'#include "za_submission_boundary_r20b.inc"','#include "za_submission_boundary_r20b.inc"\n#include "za_preparation_boundary_r21.inc"')
    return s
def main():
    for rel,h in PINS.items(): assert sha(BASE/'source'/rel)==h,rel
    assert not WORK.exists(),'Do not overwrite a build; use apply.py for deliberate source regeneration.'
    WORK.mkdir()
    for name in ('source','port','inc','shaders','evidence'):
        shutil.copytree(BASE/name,WORK/name,symlinks=True,ignore=shutil.ignore_patterns('build','.git') if name=='source' else None)
    for name in ('rt','inc'): shutil.copytree(BASE/'source/build/ps5'/name,WORK/'source/build/ps5'/name,symlinks=True)
    shutil.copytree(BASE/'objects-r20b',WORK/'objects-r21')
    apply()
def apply():
    assert WORK.exists()
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    changes=[]
    for rel,h in PINS.items():
        assert sha(BASE/'source'/rel)==h,rel
        old=(BASE/'source'/rel).read_text(); new=old
        if rel.endswith('exec.c'): new=modify_exec(old)
        elif rel.endswith('nvn.h'):
            new=once(old,'int backend_submission_switch_profile(const char *profile, uint64_t frame);',
                'int backend_preparation_switch_profile(const char *profile, uint64_t frame);\nint backend_submission_switch_profile(const char *profile, uint64_t frame);')
        else:
            new=once(old,'NVN(nvnQueueSubmitCommands) {', '''/* Observer only, after a successful present: same serialization as submission switching. */
int za_preparation_switch_profile(const char *profile, uint64_t frame) {
    exec_lock_take();
    int applied = backend_preparation_switch_profile(profile, frame);
    exec_lock_give();
    return applied;
}

NVN(nvnQueueSubmitCommands) {''')
        (WORK/'source'/rel).write_text(new)
        changes.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='r20b/'+rel,tofile='r21/'+rel))
    for src,dst in [('preparation.h','za_preparation_r21.h'),('counters.inc','za_preparation_counters_r21.inc'),('boundary.inc','za_preparation_boundary_r21.inc')]:
        text=(PORT/src).read_text(); (WORK/'source/runtime/nvn/vulkan'/dst).write_text(text)
        changes.extend(difflib.unified_diff([],text.splitlines(True),fromfile='/dev/null',tofile='r21/runtime/nvn/vulkan/'+dst))
    (EVIDENCE/'runtime-r21.patch').write_text(''.join(changes))
    baseline={str(p.relative_to(BASE/'source/runtime')):sha(p) for p in (BASE/'source/runtime').rglob('*') if p.is_file()}
    (EVIDENCE/'preparation.json').write_text(json.dumps({'base':str(BASE),'work':str(WORK),'base_sources':PINS,'all_baseline_runtime_sources':baseline,'baseline_eboot_sha256':'9ee7737bb542eae1b804e644733898dce8808a9b85da3c4929c7031f83268852','profiles':{'baseline':0,'plan-only':1,'lazy-only':2,'optimized':3}},indent=2)+'\n')
    print('Prepared r21 sources',WORK)
if __name__=='__main__': main()
