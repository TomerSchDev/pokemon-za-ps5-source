static uint32_t seed=0x21;
static uint32_t rnd(void) {seed=seed*1664525u+1013904223u;return seed;}
static void reset_state(unsigned variant) {
    memset(&record,0,sizeof record);
    for(int s=0;s<2;s++) for(int i=0;i<64;i++) {
        tex_sc[s][i][0]=(float)(s+i+1)/3;tex_sc[s][i][1]=(float)(s+i+2)/5;
        tex_wh[s][i][0]=(uint32_t)(101+s+i);tex_wh[s][i][1]=(uint32_t)(203+s+i);
    }
    gwin_base=0x100000;gwin_max=0x10000;gmem_lo=0x100;xm_lo=0x100800;
    xfb_on=(variant&1)!=0;xm_draw=(variant&2)!=0;
    g_mirror_w=(variant&4)?1280.0f:0.0f;xm_buf=(VkBuffer)(uintptr_t)73;
    xfb_addr[0]=0x101000;xfb_size[0]=0x100;
    xfb_addr[1]=(variant&8)?0x101003:0x100400;xfb_size[1]=0x80;
    xfb_addr[2]=(variant&16)?0x110000:0;xfb_size[2]=0x8000;
    xfb_addr[3]=0x101800;xfb_size[3]=0x800;
    for(unsigned i=0;i<65;i++)for(unsigned j=0;j<4;j++)gmap_tab[i][j]=i*19+j+variant;
}
static void finish_record(void) {memcpy(record.scales,tex_sc,sizeof tex_sc);memcpy(record.wh,tex_wh,sizeof tex_wh);}
static void test_case(Prog *p,unsigned variant,unsigned *cases) {
    assert(za_prep_build(&p->prep,p->binds,p->nbinds));
    ShaderInfo si={(int)(variant%81)};
    float rs0[4]={1.5f,0.75f,-0.0f,25.0f},tint[8]={1,0.5f,0,1,0,0,-0.0f,2};
    VkDescriptorImageInfo images[64];
    for(int i=0;i<64;i++)images[i]=(VkDescriptorImageInfo){(VkSampler)(uintptr_t)(3000+i),(VkImageView)(uintptr_t)(4000+i),VK_IMAGE_LAYOUT_GENERAL};
    for(int st=0;st<3;st++) {
        int stage=st==2?5:st;unsigned set=st==1?1:0;
        const float *row=(variant&32)?rs0:NULL,*t=(variant&64)?tint:NULL;
        const VkDescriptorImageInfo *ii=(variant&128)?images:NULL;
        reset_state(variant);
        VkDescriptorSet old=stage_set_r20b_reference(p,(VkDescriptorSetLayout)(uintptr_t)(11+set),set,stage,&si,row,t,3,5,7,ii);
        finish_record();Record reference=record;
        for(unsigned flags=0;flags<4;flags++) {
            reset_state(variant);memset(za_prep_counts,0,sizeof za_prep_counts);atomic_store(&za_prep_flags,flags);
            VkDescriptorSet newset=stage_set(p,(VkDescriptorSetLayout)(uintptr_t)(11+set),set,stage,&si,row,t,3,5,7,ii);
            finish_record();
            if(old!=newset || memcmp(&reference,&record,sizeof record)) {
                fprintf(stderr,"DIFF case=%u stage=%d flags=%u n=%d variant=%u\n",*cases,stage,flags,p->nbinds,variant);abort();
            }
            ZaPrepCounters *c=&za_prep_counts[flags];
            assert(c->calls==1&&c->allocs==record.allocs&&c->updates==record.updates&&c->writes==record.n);
            bool build=!(flags&ZA_PREP_LAZY)||p->prep.stage[set].has_rscale;
            assert(c->rscale_builds==(uint64_t)build&&c->rscale_skips==(uint64_t)!build);
            assert(c->ordinary_visits==((flags&ZA_PREP_PLAN)?p->prep.stage[set].nordinary:(unsigned)p->nbinds));
            assert(c->special_visits==((flags&ZA_PREP_PLAN)?p->prep.stage[set].nspecial:(unsigned)p->nbinds));
            ++*cases;
        }
    }
}
/* Extracted live boundary tested against controlled drain state. */
typedef enum { ZA_SUB_END, ZA_SUB_SWITCH } ZaSubmitReason;
static int za_submit_defer;
static bool in_pass;
static ZaSubmitReason za_submit_reason;
static pthread_mutex_t za_sq_lock=PTHREAD_MUTEX_INITIALIZER;
static struct {unsigned ncbs,lists;} za_sq;
static uint64_t fence=7,completed=7;
static unsigned drains,flushes,configured;
static void za_submission_configure(void) {++configured;}
static void renderer_flush(void) {++drains;}
static void za_submission_flush_to(uint64_t n,ZaSubmitReason why) {assert(n==UINT64_MAX&&why==ZA_SUB_SWITCH);++flushes;}
static uint64_t renderer_fence_seq(void) {return fence;}
static uint64_t vk_completed_seq(void) {return completed;}
#include "boundary.inc"
static void test_boundary(void) {
    atomic_store(&za_prep_flags,0);assert(!strcmp(za_preparation_profile_name(),"baseline"));
    assert(backend_preparation_switch_profile("bad",1)==-1&&drains==0);
    za_submit_defer=1;assert(backend_preparation_switch_profile("optimized",2)==-3&&drains==0);za_submit_defer=0;
    in_pass=true;assert(backend_preparation_switch_profile("optimized",3)==-3&&drains==0);in_pass=false;
    completed=6;assert(backend_preparation_switch_profile("optimized",4)==-3&&za_preparation_profile_flags()==0);completed=7;
    za_sq.ncbs=1;assert(backend_preparation_switch_profile("optimized",5)==-3&&za_preparation_profile_flags()==0);za_sq.ncbs=0;
    za_sq.lists=1;assert(backend_preparation_switch_profile("optimized",6)==-3&&za_preparation_profile_flags()==0);za_sq.lists=0;
    for(unsigned i=0;i<4;i++) {
        assert(backend_preparation_switch_profile(za_prep_name(i),7+i)==(int)i+1);
        assert(za_preparation_profile_flags()==i&&!strcmp(za_preparation_profile_name(),za_prep_name(i)));
    }
    assert(backend_preparation_switch_profile("bad",12)==-1&&za_preparation_profile_flags()==3);
    assert(za_submit_reason==ZA_SUB_END&&drains==flushes&&configured==drains);
    assert(backend_preparation_switch_profile("baseline",13)==1);
}
int main(void) {
    ZaPrepRecipe p;
    assert(!za_prep_build(&p,NULL,-1));assert(!za_prep_build(&p,NULL,97));assert(!za_prep_build(&p,NULL,1));assert(za_prep_build(&p,NULL,0));
    assert(za_prep_parse(NULL)==-1&&za_prep_parse("BASELINE")==-1&&za_prep_parse("baseline ")==-1);
    for(unsigned i=0;i<4;i++)assert(za_prep_parse(za_prep_name(i))==(int)i);
    unsigned cases=0;Prog prog={0};
    test_case(&prog,0,&cases); /* empty set still allocates, never updates */
    const uint32_t bindings[]={0,1,16,17,18,19,20,21,22,31,32,33,95,96,127};
    const VkDescriptorType types[]={VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,VK_DESCRIPTOR_TYPE_SAMPLER,VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE};
    for(unsigned v=0;v<256;v++) {
        memset(&prog,0,sizeof prog);prog.nbinds=(int)(v%97);
        for(int i=0;i<prog.nbinds;i++)prog.binds[i]=(VkBindingInfo){rnd()%3,bindings[rnd()%15],types[rnd()%5]};
        test_case(&prog,v,&cases);
    }
    /* Max ordinary, max special, duplicate/mixed-order reflection and both sets. */
    for(unsigned mode=0;mode<6;mode++) {
        memset(&prog,0,sizeof prog);prog.nbinds=96;
        for(int i=0;i<96;i++)prog.binds[i]=(VkBindingInfo){mode%2,mode<2?0u:mode<4?18u:(uint32_t)(18+i%3),VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER};
        test_case(&prog,255,&cases);
    }
    /* Exhaust each descriptor-kind/binding/set combination, including no rscale. */
    for(unsigned t=0;t<5;t++)for(unsigned b=0;b<15;b++)for(unsigned set=0;set<3;set++) {
        memset(&prog,0,sizeof prog);prog.nbinds=1;prog.binds[0]=(VkBindingInfo){set,bindings[b],types[t]};
        test_case(&prog,255,&cases);
    }
    test_boundary();za_preparation_report();
    printf("PASS: %u extracted stage_set differential executions; recipe limits/types/order; exact descriptors/copies/callbacks; counters; profile drain failure/success.\n",cases);
    return 0;
}
