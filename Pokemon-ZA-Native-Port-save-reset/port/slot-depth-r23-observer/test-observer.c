#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <limits.h>
#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>
static int lstat_behavior,stat_calls,stat_fail_at,stat_empty_at,stat_changed_at;
static int read_calls,read_fail_at,read_short_at,read_extra_at;
static int test_retire_lstat(const char *path,struct stat *st) {
    if(lstat_behavior==1)return 0; /* Possible native success-without-output shim. */
    if(lstat_behavior==2){errno=EACCES;return -1;}
    return lstat(path,st);
}
static int test_retire_fstat(int fd,struct stat *st) {
    ++stat_calls;
    if(stat_calls==stat_fail_at){errno=EIO;return -1;}
    if(stat_calls==stat_empty_at)return 0;
    int rc=fstat(fd,st);
    if(!rc&&stat_calls==stat_changed_at)++st->st_ino;
    return rc;
}
static ssize_t test_retire_read(int fd,void *out,size_t n) {
    ++read_calls;
    if(read_calls==read_fail_at){errno=EIO;return -1;}
    if(read_calls==read_extra_at){assert(n);((char*)out)[0]='x';return 1;}
    ssize_t rc=read(fd,out,n);
    return read_calls==read_short_at && rc>0?rc-1:rc;
}
#define ZA_RETIRE_LSTAT test_retire_lstat
#define ZA_RETIRE_FSTAT test_retire_fstat
#define ZA_RETIRE_READ test_retire_read
#include "observer-r23.c"
static uint64_t clock_ns=NS;
static int requested_mode, capture_calls, submission_calls, applied_cap;
static uint64_t applied_frame;
static unsigned preparation_calls, preparation_current;
static int preparation_force = INT_MIN;
static bool preparation_bad_name;
uint64_t plat_now_ns(void){return clock_ns;}
int za_performance_status(void){return requested_mode;}
void za_performance_request(int value){requested_mode=value;}
int sceKernelDebugOutText(int channel,const char *text){(void)channel;(void)text;return 0;}
int za_submission_switch_profile(const char *profile, uint64_t frame) {
    ++submission_calls; applied_frame = frame;
    applied_cap = !strcmp(profile,"each") ? 1 : !strcmp(profile,"batch2") ? 2 : !strcmp(profile,"batch4") ? 4 : 8;
    return applied_cap;
}
int za_preparation_switch_profile(const char *profile,uint64_t at_frame) {
    assert(at_frame>0);
    ++preparation_calls;
    clock_ns+=NS/10;
    if(preparation_force!=INT_MIN)return preparation_force;
    int flags=preparation_flags(profile);assert(flags>=0);
    preparation_current=(unsigned)flags;
    return flags+1;
}
const char *za_preparation_profile_name(void) {
    static const char *const names[]={"baseline","plan-only","lazy-only","optimized"};
    return preparation_bad_name ? "bad\"name" : names[preparation_current];
}
uint32_t za_preparation_profile_flags(void){return preparation_current;}
#include "test-immutable-observer-stubs.inc"
#include "test-slot-depth-stubs.inc"

static void receipt_has(uint64_t seq,const char *part) {
    char path[320],buf[2400];snprintf(path,sizeof path,"%s/ack_%" PRIu64 ".json",session_dir,seq);
    FILE *f=fopen(path,"rb");assert(f);size_t n=fread(buf,1,sizeof buf-1,f);fclose(f);buf[n]=0;
    assert(strstr(buf,part));
}
static void capture(void *p,const char *path){assert(p==(void*)1);capture_calls++;clock_ns+=NS/4;assert(write_text(path,"........................................"));}
static void send(uint64_t seq,const char *request) {
    char text[256];snprintf(text,sizeof text,"%016" PRIx64 " %" PRIu64 " %s\n",session,seq,request);
    assert(write_text(ZA_OBSERVER_ROOT "/command.txt",text));clock_ns+=NS;
}
static void frame(uint64_t i,uint64_t work){za_observer_frame(i,true,false,work,(void*)1,capture);}
#include "test-retire.inc"
#include "test-immutable-observer.inc"
#include "test-slot-depth.inc"

int main(void) {
    za_observer_init();assert(!enabled);
    assert(write_text(ZA_OBSERVER_ENABLE,"observe-r17\n"));za_observer_init();assert(enabled&&session);
    send(1,"continue wrong_run");assert(!za_observer_menu("r123"));
    send(2,"continue r123");assert(za_observer_menu("r123"));
    send(3,"measure -1");frame(1,0);assert(!samples);
    send(4,"measure 18446744073709551616");frame(2,0);assert(!samples);
    send(5,"input ../../x 2");frame(3,0);assert(action<0);
    send(6,"input A 3");frame(10,0);
    {uint64_t b=0;int32_t x=0,y=0,r=0,s=0;za_observer_input(10,&b,&x,&y,&r,&s);assert(!b&&action>=0);}
    for(unsigned f=11;f<=14;++f) {uint64_t b=0;int32_t x=0,y=0,r=0,s=0;za_observer_input(f,&b,&x,&y,&r,&s);assert(b==(f<14?1u:0u));}
    send(7,"input RSTICK_LEFT 2");frame(20,0);
    {uint64_t b=0;int32_t x=0,y=0,r=0,s=0;za_observer_input(21,&b,&x,&y,&r,&s);assert(r==-32767&&!b);za_observer_input(23,&b,&x,&y,&r,&s);assert(action<0);}
    send(8,"fps 1");frame(30,0);assert(requested_mode==1);
    send(8,"fps 0");frame(31,0);assert(requested_mode==1); /* no replay */
    assert(write_text(ZA_OBSERVER_ROOT "/command.txt","0000000000000000 99 fps 0\n"));clock_ns+=NS;frame(32,0);assert(requested_mode==1);
    send(9,"snapshot");frame(40,0);assert(capture_calls==1);
    send(10,"measure 1");frame(41,0);assert(samples&&sample_count==0);
    /* A pending capture must never be polled/encoded during the window. */
    send(11,"snapshot");frame(42,0);assert(samples&&capture_calls==1&&sample_count==0);
    clock_ns+=NS;frame(43,0);assert(stop_at&&sample_count==0);
    uint64_t i=44;
    while(samples){clock_ns+=NS/30;frame(i,i==50?UINT64_C(1)<<32:0);++i;assert(capture_calls==1);}
    clock_ns+=NS;frame(i++,0);assert(capture_calls==2);
    send(12,"measure 1");frame(i++,0);clock_ns+=2*NS;frame(i++,0);clock_ns-=1;frame(i++,0);assert(!samples);
    send(13,"measure 120");frame(i++,0);clock_ns+=2*NS;frame(i++,0);
    for(unsigned j=0;j<CAP;++j){clock_ns+=1;frame(i++,0);}
    assert(!samples); /* bounded memory even at unrealistic presentation rates */
    send(14,"submission batch4"); frame(i++,0);
    assert(submission_calls==1 && applied_cap==4 && applied_frame==i-1);
    { char path[320], buf[800]; snprintf(path,sizeof path,"%s/ack_14.json",session_dir);
      FILE *f=fopen(path,"rb"); assert(f); size_t n=fread(buf,1,sizeof buf-1,f);fclose(f);buf[n]=0;
      assert(strstr(buf,"\"result\":\"applied\"") && strstr(buf,"\"max_lists\":4") && strstr(buf,"\"profile\":\"batch4\"")); }
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
    /* New command uses the real parser, post-present branch and receipt writer. */
    assert(preparation_current==0 && preparation_calls==0);
    uint64_t serial=21;
    send(serial,"preparation optimized");assert(!za_observer_menu("r123"));
    assert(!preparation_calls);receipt_has(serial,"\"result\":\"rejected_in_menu\"");
    receipt_has(serial,"\"profile\":\"baseline\"");receipt_has(serial,"\"flags\":0");
    receipt_has(serial,"\"frame\":0");receipt_has(serial++,"\"runtime_result\":0");
    const char *bad[]={"preparation", "preparation plan", "preparation OPTIMIZED", "preparation optimized extra", "preparation ../baseline"};
    for(unsigned j=0;j<sizeof bad/sizeof bad[0];++j) {
        send(serial,bad[j]);frame(i++,0);assert(!preparation_calls);
        receipt_has(serial++,"\"op\":\"invalid\"");
    }
    const char *profiles[]={"baseline","plan-only","lazy-only","optimized"};
    for(unsigned j=0;j<4;++j) {
        char request[80],want[100];snprintf(request,sizeof request,"preparation %s",profiles[j]);
        send(serial,request);frame(i++,0);assert(preparation_current==j && preparation_calls==j+1);
        receipt_has(serial,"\"result\":\"applied\"");
        snprintf(want,sizeof want,"\"profile\":\"%s\",\"flags\":%u",profiles[j],j);receipt_has(serial,want);
        snprintf(want,sizeof want,"\"frame\":%" PRIu64,i-1);receipt_has(serial,want);
        snprintf(want,sizeof want,"\"runtime_result\":%u",j+1);receipt_has(serial,want);
        receipt_has(serial++,"\"cost_ns\":100000000");
    }
    send(serial-1,"preparation baseline");frame(i++,0);assert(preparation_calls==4 && preparation_current==3);
    send(serial,"preparation baseline");za_observer_frame(i++,true,true,0,(void*)1,capture);
    assert(preparation_calls==4);receipt_has(serial,"\"result\":\"rejected_boundary\"");
    receipt_has(serial++,"\"profile\":\"optimized\",\"flags\":3");
    send(serial,"preparation baseline");za_observer_frame(i++,false,false,0,(void*)1,capture);
    assert(preparation_calls==4);receipt_has(serial++,"\"result\":\"rejected_boundary\"");
    send(serial,"preparation baseline");za_observer_frame(0,true,false,0,(void*)1,capture);
    assert(preparation_calls==4);receipt_has(serial++,"\"result\":\"rejected_boundary\"");
    send(serial++,"measure 1");frame(i++,0);assert(samples && !stop_at);
    uint64_t consumed=sequence,old_poll=poll_after;
    send(serial,"preparation baseline");frame(i++,0);
    assert(samples && !stop_at && preparation_calls==4 && sequence==consumed && poll_after==old_poll);
    assert(!za_observer_menu("r123"));assert(sequence==consumed && poll_after==old_poll);
    clock_ns+=NS;frame(i++,0);assert(stop_at && preparation_calls==4 && sequence==consumed);
    while(samples) {clock_ns+=NS/30;frame(i++,0);assert(preparation_calls==4 && sequence==consumed && poll_after==old_poll);}
    clock_ns+=NS;frame(i++,0);assert(preparation_calls==5 && preparation_current==0);
    receipt_has(serial++,"\"result\":\"applied\"");
    const int failures[]={-1,-3,0,4};
    for(unsigned j=0;j<sizeof failures/sizeof failures[0];++j) {
        preparation_force=failures[j];send(serial,"preparation optimized");frame(i++,0);
        assert(preparation_current==0);
        receipt_has(serial,j==0?"\"result\":\"rejected_profile\"":j==1?"\"result\":\"drain_failed\"":"\"result\":\"receipt_mismatch\"");
        receipt_has(serial++,"\"profile\":\"baseline\",\"flags\":0");
    }
    preparation_force=INT_MIN;preparation_bad_name=true;
    send(serial,"preparation optimized");frame(i++,0);
    receipt_has(serial,"\"result\":\"receipt_mismatch\"");receipt_has(serial++,"\"profile\":\"\",\"flags\":-1");
    preparation_bad_name=false;
    unsigned no_commands=preparation_calls;
    for(unsigned j=0;j<100;++j){clock_ns+=NS;frame(i++,0);}
    assert(preparation_calls==no_commands);
    test_retirement(&serial,&i);
    test_immutable_observer(&serial,&i);
    test_slot_depth(&serial,&i);
    puts("observer preparation profiles/readback/cost, menu/boundary/parser rejection, replay protection, failed/mismatched runtime receipt and settling/measurement mailbox deferral passed");
    puts("observer legacy submission/fps/input/continue/capture/measurement/reset/capacity behaviors passed");
}
