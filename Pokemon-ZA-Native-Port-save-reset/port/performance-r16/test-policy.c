#include "frame_policy.h"
#include <assert.h>
#include <stdio.h>
static uint64_t now, present;
static void frames(ZaFramePolicy *s, unsigned count, uint64_t dt, uint64_t builds) {
    for(unsigned i=0;i<count;i++) { now+=dt; ++present; za_frame_step(s,1,now,present,builds); }
}
int main(void) {
    ZaFramePolicy s={0};
    assert(za_frame_step(&s,-2,0,0,0)==-2);
    frames(&s,1000,33333333,0); assert(s.mode==ZA_FPS_ORIGINAL && !s.started);
    za_frame_arm(&s,true);
    frames(&s,600,16666667,0); assert(s.mode==ZA_FPS_TRIAL && s.warm==5);
    frames(&s,1,3000000000,0); assert(s.mode==ZA_FPS_TRIAL && s.warm==0);
    frames(&s,300,22222222,1); assert(s.warm==0 && s.slow==0);
    frames(&s,1,16666667,UINT64_C(1)<<32); assert(s.warm==0);
    frames(&s,600,16666667,UINT64_C(1)<<32); assert(s.mode==ZA_FPS_TRIAL);
    /* A job that begins and ends between samples still invalidates the window. */
    frames(&s,1,16666667,UINT64_C(2)<<32); assert(s.warm==0 && s.slow==0);
    frames(&s,600,22222222,UINT64_C(2)<<32); assert(s.mode==ZA_FPS_FALLBACK);
    assert(za_frame_step(&s,1,now+1,present,UINT64_C(2)<<32)==1);
    za_frame_arm(&s,true); frames(&s,660,16666667,0); assert(s.mode==ZA_FPS_TRIAL);
    za_frame_step(&s,1,now-1,present,0); assert(s.warm==0 && s.mode==ZA_FPS_TRIAL);
    za_frame_step(&s,1,now+1,0,0); assert(s.warm==0 && s.mode==ZA_FPS_TRIAL);
    za_frame_arm(&s,false); assert(za_frame_step(&s,-2,now,present,0)==-2);
    puts("PASS frame policy: manual arm, cold startup, clean 60, load gaps, queued jobs, completed-job epoch, sustained 45 fallback, retry, rollback, original mode");
}
