#include <assert.h>
#include "observer.c"
static uint64_t clock_ns=NS;
static int requested_mode, capture_calls;
uint64_t plat_now_ns(void){return clock_ns;}
int za_performance_status(void){return requested_mode;}
void za_performance_request(int value){requested_mode=value;}
int sceKernelDebugOutText(int channel,const char *text){(void)channel;(void)text;return 0;}
static void capture(void *p,const char *path){assert(p==(void*)1);capture_calls++;clock_ns+=NS/4;assert(write_text(path,"........................................"));}
static void send(uint64_t seq,const char *request) {
    char text[256];snprintf(text,sizeof text,"%016" PRIx64 " %" PRIu64 " %s\n",session,seq,request);
    assert(write_text(ZA_OBSERVER_ROOT "/command.txt",text));clock_ns+=NS;
}
static void frame(uint64_t i,uint64_t work){za_observer_frame(i,true,false,work,(void*)1,capture);}
int main(void) {
    za_observer_init();assert(!enabled);
    assert(write_text(ZA_OBSERVER_ENABLE,"observe-r17\n"));za_observer_init();assert(enabled&&session);
    send(1,"continue wrong_run");assert(!za_observer_menu("r123"));
    send(2,"continue r123");assert(za_observer_menu("r123"));
    send(3,"measure -1");frame(1,0);assert(!samples);
    send(4,"measure 18446744073709551616");frame(2,0);assert(!samples);
    send(5,"input ../../x 2");frame(3,0);assert(action<0);
    send(6,"input A 3");frame(10,0);
    for(unsigned f=11;f<=14;++f) {uint64_t b=0;int32_t x=0,y=0,r=0,s=0;za_observer_input(f,&b,&x,&y,&r,&s);assert(b==(f<14?1u:0u));}
    send(7,"input RSTICK_LEFT 2");frame(20,0);
    {uint64_t b=0;int32_t x=0,y=0,r=0,s=0;za_observer_input(21,&b,&x,&y,&r,&s);assert(r==-32767&&!b);za_observer_input(19,&b,&x,&y,&r,&s);assert(action<0);}
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
    puts("observer protocol, scoped sessions, input expiry, capture separation, rollback and buffer bound passed");
}
