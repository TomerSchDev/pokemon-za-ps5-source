#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
static const unsigned char *config_bytes;
static size_t config_size;
static unsigned config_opens,config_reads,config_closes,config_partial;
static int config_open_errno,config_read_error,config_close_error,config_read_fail_at,config_fd=-1;
static int startup_open(const char *path,int flags) {
    assert(!strcmp(path,ZA_SLOT_STARTUP_PATH) && flags==(O_RDONLY|O_NOFOLLOW|O_NONBLOCK));
    assert(errno==0);++config_opens;
    if(config_open_errno){errno=config_open_errno;return -1;}
    config_fd=open(path,flags);return config_fd;
}
static ssize_t startup_read(int fd,void *out,size_t count) {
    assert(fd==config_fd && count>0 && count<=4 && config_reads<4 && errno==0);++config_reads;
    if(config_read_fail_at==(int)config_reads){errno=config_read_error;return -1;}
    if(config_partial && count>config_partial)count=config_partial;
    return read(fd,out,count);
}
static int startup_close(int fd){assert(fd==config_fd && errno==0);++config_closes;int rc=close(fd);if(config_close_error){errno=config_close_error;return -1;}return rc;}
#define ZA_SLOT_STARTUP_OPEN startup_open
#define ZA_SLOT_STARTUP_READ startup_read
#define ZA_SLOT_STARTUP_CLOSE startup_close
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
    config_bytes=bytes;config_size=size;config_open_errno=config_read_error=config_close_error=config_read_fail_at=0;
    config_opens=config_reads=config_closes=config_partial=0;config_fd=-1;
    FILE *f=fopen(ZA_SLOT_STARTUP_PATH,"wb");assert(f);assert(fwrite(bytes,1,size,f)==size);assert(!fclose(f));
    slot_calls=slot_status_calls=0;slot_force=INT_MIN;slot_bad_status=0;slot_budget_unavailable=false;
    slot_status=(ZaSlotDepthStatus){.abi_version=1,.active_slots=8,.capacity_slots=ZA_SLOT_DEPTH_CAPACITY};logs[0]=0;
    sequence=poll_after=previous_time=0;clock_ns+=NS;
}
static void check_no_retry(void) {
    unsigned calls=slot_calls,gets=slot_status_calls,opens=config_opens;
    for(unsigned i=0;i<100;++i)frame(1000+i,0);
    za_observer_init();
    assert(calls==slot_calls && gets==slot_status_calls && opens==config_opens);
}
int main(void) {
    /* r24: 32 and 64 as well as r23c's 8 and 16 */
    static const char *const valid[]={"8","8\n","16","16\n","32","32\n","64","64\n"};
    static const unsigned depth[]={8,8,16,16,32,32,64,64};
    for(unsigned i=0;i<8;++i) {
        fresh((const unsigned char*)valid[i],strlen(valid[i]));za_observer_init();
        assert(!enabled && slot_startup_loaded && slot_startup_requested==depth[i]);
        assert(slot_startup_pending==(i>=2) && config_opens==1 && config_reads==2 && config_closes==1);
        assert(strstr(logs,"source=file ") && strstr(logs,"read_result=0 read_errno=0 read_calls=2") && strstr(logs,"eof=1 close_result=0 close_errno=0"));
        config_bytes=(const unsigned char*)"garbage";config_size=7;za_observer_init();assert(config_opens==1);
        if(i<2){frame(1,0);assert(!slot_calls && !slot_status_calls);check_no_retry();continue;}
        za_observer_frame(0,true,false,0,NULL,NULL);
        za_observer_frame(1,false,false,0,NULL,NULL);
        za_observer_frame(2,true,true,0,NULL,NULL);
        assert(slot_startup_pending && !slot_calls && !slot_status_calls);
        assert(!za_observer_menu("run") && !slot_calls);
        frame(3,0);assert(slot_calls==1 && slot_status_calls==1 && !slot_startup_pending && slot_status.active_slots==depth[i]);
        char applied[160];
        snprintf(applied,sizeof applied,"apply requested=%u result=%u confirmed=1 active=%u frame=3 status_frame=3 status_result=%u cost_ns=125000000",
                 depth[i],depth[i],depth[i],depth[i]);
        assert(strstr(logs,applied));
        check_no_retry();
    }
    static const char *const invalid[]={""," 16","16 ","16\r\n","16\r","16\n\n","016","8\nX","16X","1600","16\nmore","\n16","16\t","+16","-16"};
    for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];++i) {
        fresh((const unsigned char*)invalid[i],strlen(invalid[i]));za_observer_init();frame(1,0);
        assert(slot_startup_requested==8 && !slot_startup_pending && !slot_calls && !slot_status_calls);
        assert(strstr(logs,"config requested=8 source=invalid "));check_no_retry();
    }
    static const unsigned char embedded[]={ '1','6',0 };unsigned char huge[4096];memset(huge,'8',sizeof huge);
    const unsigned char *bad[]={embedded,huge};size_t bad_sizes[]={sizeof embedded,sizeof huge};
    for(unsigned i=0;i<2;++i){fresh(bad[i],bad_sizes[i]);za_observer_init();frame(1,0);assert(slot_startup_requested==8 && !slot_calls && config_reads<=2);}
    /* Partial reads remain bounded and a trailing byte is never accepted. */
    for(unsigned partial=1;partial<=2;++partial) {
        fresh((const unsigned char*)"16\n",3);config_partial=partial;za_observer_init();
        assert(slot_startup_requested==16 && config_reads==(partial==1?4u:3u) && config_closes==1);frame(1,0);check_no_retry();
        fresh((const unsigned char*)"16\nX",4);config_partial=partial;za_observer_init();frame(1,0);
        assert(slot_startup_requested==8 && !slot_calls && config_reads==(partial==1?4u:2u) && strstr(logs,"bytes=4 eof=0"));
    }
    for(unsigned fault=0;fault<7;++fault) {
        fresh((const unsigned char*)"16",2);
        if(fault<2)config_open_errno=fault?EACCES:ENOENT;
        if(fault>=2 && fault!=3){config_read_fail_at=fault==5?2:1;config_read_error=fault==4?EINTR:EIO;}
        if(fault==3 || fault==6)config_close_error=EBADF;
        za_observer_init();frame(1,0);assert(slot_startup_requested==8 && !slot_calls && !slot_status_calls);
        assert(strstr(logs,fault==0?"source=missing":fault==1?"source=open_error":fault==3?"source=close_error":"source=read_error"));
        if(fault<2)assert(!config_reads && !config_closes && strstr(logs,"read_result=-2 read_errno=0 read_calls=0 bytes=0 eof=0 close_result=-2 close_errno=0"));
        if(fault==4)assert(config_reads==1); /* No EINTR retry. */
        if(fault==6)assert(strstr(logs,"read_result=-1 read_errno=5") && strstr(logs,"close_result=-1 close_errno=9"));
        if(fault>=2)assert(config_closes==1);
        check_no_retry();
    }
    /* Real POSIX path errors, not only fault injection. */
    fresh((const unsigned char*)"16",2);assert(!unlink(ZA_SLOT_STARTUP_PATH));za_observer_init();assert(strstr(logs,"source=missing") && !slot_startup_pending);
    assert(!symlink("/dev/null",ZA_SLOT_STARTUP_PATH));
    /* Keep the configured symlink for this process-emulation fixture. */
    slot_startup_loaded=false;slot_startup_requested=8;config_opens=config_reads=config_closes=0;logs[0]=0;
    za_observer_init();assert(strstr(logs,"source=open_error") && !slot_startup_pending && !config_reads && !config_closes);assert(!unlink(ZA_SLOT_STARTUP_PATH));
    fresh((const unsigned char*)"16",2);assert(!unlink(ZA_SLOT_STARTUP_PATH));assert(!mkfifo(ZA_SLOT_STARTUP_PATH,0600));
    za_observer_init();assert(strstr(logs,"source=invalid") && !slot_startup_pending && config_reads==1 && config_closes==1);assert(!unlink(ZA_SLOT_STARTUP_PATH));
    fresh((const unsigned char*)"16",2);assert(!unlink(ZA_SLOT_STARTUP_PATH));assert(!mkdir(ZA_SLOT_STARTUP_PATH,0700));
    za_observer_init();assert(strstr(logs,"source=read_error") && !slot_startup_pending && config_reads==1 && config_closes==1);assert(!rmdir(ZA_SLOT_STARTUP_PATH));
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
    puts("r23c startup actual observer: strict bounded POSIX configuration, partial reads/EOF/errors/errno/close cleanup, process-once read, default8, disabled observer, safe boundary, menu, failed/mismatched receipt, no retry, measurement deferral and separate command frame passed");
}
