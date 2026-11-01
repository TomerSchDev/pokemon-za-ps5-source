#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
static const unsigned char *config_bytes;
static size_t config_size;
static unsigned config_opens,config_reads,config_errors,config_closes;
static int config_open_errno,config_read_error,config_close_error;
static FILE *startup_open(const char *path,const char *mode) {
    assert(!strcmp(path,ZA_SLOT_STARTUP_PATH) && !strcmp(mode,"rb"));++config_opens;
    if(config_open_errno){errno=config_open_errno;return NULL;}
    FILE *f=tmpfile();assert(f);
    assert(fwrite(config_bytes,1,config_size,f)==config_size);rewind(f);return f;
}
static size_t startup_read(void *out,size_t size,size_t count,FILE *f) {
    assert(size==1 && count==(config_reads?1u:4u));++config_reads;return fread(out,size,count,f);
}
static int startup_error(FILE *f){++config_errors;return config_read_error || ferror(f);}
static int startup_close(FILE *f){++config_closes;int rc=fclose(f);return config_close_error ? EOF : rc;}
#define ZA_SLOT_STARTUP_FOPEN startup_open
#define ZA_SLOT_STARTUP_FREAD startup_read
#define ZA_SLOT_STARTUP_FERROR startup_error
#define ZA_SLOT_STARTUP_FCLOSE startup_close
#define ZA_TEST_DEBUG_OUT 1
#define main regression_main
#include "test-observer.c"
#undef main
static char logs[32768];
int sceKernelDebugOutText(int channel,const char *text) {
    (void)channel;assert(strlen(logs)+strlen(text)<sizeof logs);strcat(logs,text);return 0;
}
/* Fresh-process emulation only. No production reset path touches these flags. */
static void fresh(const unsigned char *bytes,size_t size) {
    assert(!samples);enabled=false;remove(ZA_OBSERVER_ENABLE);
    slot_startup_loaded=false;slot_startup_pending=false;slot_startup_requested=8;
    config_bytes=bytes;config_size=size;config_open_errno=config_read_error=config_close_error=0;
    config_opens=config_reads=config_errors=config_closes=0;
    slot_calls=slot_status_calls=0;slot_force=INT_MIN;slot_bad_status=0;slot_budget_unavailable=false;
    slot_status=(ZaSlotDepthStatus){.abi_version=1,.active_slots=8,.capacity_slots=16};logs[0]=0;
    sequence=poll_after=previous_time=0;clock_ns+=NS;
}
static void check_no_retry(void) {
    unsigned calls=slot_calls,gets=slot_status_calls,opens=config_opens;
    for(unsigned i=0;i<100;++i)frame(1000+i,0);
    za_observer_init();
    assert(calls==slot_calls && gets==slot_status_calls && opens==config_opens);
}
int main(void) {
    static const char *const valid[]={"8","8\n","16","16\n"};
    for(unsigned i=0;i<4;++i) {
        fresh((const unsigned char*)valid[i],strlen(valid[i]));za_observer_init();
        assert(!enabled && slot_startup_loaded && slot_startup_requested==(i<2?8u:16u));
        assert(slot_startup_pending==(i>=2) && config_opens==1 && config_reads==2 && config_errors==1 && config_closes==1);
        assert(strstr(logs,"source=file\n"));
        config_bytes=(const unsigned char*)"garbage";config_size=7;za_observer_init();assert(config_opens==1);
        if(i<2){frame(1,0);assert(!slot_calls && !slot_status_calls);check_no_retry();continue;}
        za_observer_frame(0,true,false,0,NULL,NULL);
        za_observer_frame(1,false,false,0,NULL,NULL);
        za_observer_frame(2,true,true,0,NULL,NULL);
        assert(slot_startup_pending && !slot_calls && !slot_status_calls);
        assert(!za_observer_menu("run") && !slot_calls);
        frame(3,0);assert(slot_calls==1 && slot_status_calls==1 && !slot_startup_pending && slot_status.active_slots==16);
        assert(strstr(logs,"apply requested=16 result=16 confirmed=1 active=16 frame=3 status_frame=3 status_result=16 cost_ns=125000000"));
        check_no_retry();
    }
    static const char *const invalid[]={""," 16","16 ","16\r\n","16\r","16\n\n","016","8\nX","16X","1600","16\nmore","\n16","16\t","+16","-16"};
    for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];++i) {
        fresh((const unsigned char*)invalid[i],strlen(invalid[i]));za_observer_init();frame(1,0);
        assert(slot_startup_requested==8 && !slot_startup_pending && !slot_calls && !slot_status_calls);
        assert(strstr(logs,"config requested=8 source=invalid\n"));check_no_retry();
    }
    static const unsigned char embedded[]={ '1','6',0 };unsigned char huge[4096];memset(huge,'8',sizeof huge);
    const unsigned char *bad[]={embedded,huge};size_t bad_sizes[]={sizeof embedded,sizeof huge};
    for(unsigned i=0;i<2;++i){fresh(bad[i],bad_sizes[i]);za_observer_init();frame(1,0);assert(slot_startup_requested==8 && !slot_calls && config_reads==2);}
    for(unsigned fault=0;fault<4;++fault) {
        fresh((const unsigned char*)"16",2);
        if(fault<2)config_open_errno=fault?EACCES:ENOENT;
        if(fault==2)config_read_error=1;if(fault==3)config_close_error=1;
        za_observer_init();frame(1,0);assert(slot_startup_requested==8 && !slot_calls && !slot_status_calls);
        assert(strstr(logs,fault?"source=read_error":"source=missing"));
        if(fault>=2)assert(config_closes==1);
        check_no_retry();
    }
    const int rejected[]={-1,-3,-4,-5,-6,0,8,16};
    for(unsigned i=0;i<sizeof rejected/sizeof rejected[0];++i) {
        fresh((const unsigned char*)"16",2);slot_force=rejected[i];za_observer_init();frame(5,0);
        assert(slot_calls==1 && slot_status_calls==1 && slot_status.active_slots==8 && !slot_startup_pending);
        assert(strstr(logs,"confirmed=0 active=8"));check_no_retry();
    }
    for(int mismatch=1;mismatch<=14;++mismatch) {
        fresh((const unsigned char*)"16",2);slot_bad_status=mismatch;za_observer_init();frame(6,0);
        assert(slot_calls==1 && slot_status_calls==1 && strstr(logs,"confirmed=0"));check_no_retry();
    }
    /* Actual observer measurement path. Startup must remain pending through
     * settling, collection and the completion frame, without status polling. */
    fresh((const unsigned char*)"16\n",3);za_observer_init();assert(!enabled);
    assert(write_text(ZA_OBSERVER_ENABLE,"observe-r17\n"));za_observer_init();assert(enabled && config_opens==1);
    send(1,"measure 1");za_observer_frame(0,false,false,0,NULL,NULL);assert(samples && !stop_at);
    uint64_t old_poll=poll_after,old_sequence=sequence;
    send(2,"snapshot");frame(1,0);assert(samples && !stop_at && !slot_calls && !slot_status_calls);
    assert(!za_observer_menu("run"));clock_ns+=NS;frame(2,0);assert(stop_at && !slot_calls);
    unsigned f=3;
    while(samples){clock_ns+=NS/30;frame(f++,0);assert(!slot_calls && !slot_status_calls && old_poll==poll_after && old_sequence==sequence);}
    int captures=capture_calls;frame(f++,0);
    assert(slot_calls==1 && slot_status_calls==1 && old_sequence==sequence && captures==capture_calls);
    frame(f++,0);assert(capture_calls==captures+1 && sequence==2);
    /* Startup frame cannot arm a queued new measurement. */
    fresh((const unsigned char*)"16",2);assert(write_text(ZA_OBSERVER_ENABLE,"observe-r17\n"));za_observer_init();assert(enabled);
    send(1,"measure 1");frame(20,0);assert(!samples && sequence==0 && slot_calls==1);
    frame(21,0);assert(samples && sequence==1 && slot_calls==1);
    clock_ns+=2*NS;frame(22,0);clock_ns+=NS;frame(23,0);assert(!samples && slot_calls==1);
    puts("r23b startup actual observer: strict bounded configuration, process-once read, default8, disabled observer, safe boundary, menu, failed/mismatched receipt, no retry, measurement deferral and separate command frame passed");
}
