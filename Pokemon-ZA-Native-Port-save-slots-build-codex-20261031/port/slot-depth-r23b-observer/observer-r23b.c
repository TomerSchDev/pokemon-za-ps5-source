/* Development-only, opt-in visual observer and bounded frame recorder.
 * No network listener; the existing FTP service transports scoped text commands.
 * Measurements buffer samples in RAM. No command polling, image readback or
 * file writes occur inside a measurement window. Never subtract stutters.
 */
#include "observer.h"
#include "preparation-observer-api.h"
#include "immutable-control.h"
#include "slot-depth-control.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#ifndef ZA_OBSERVER_ROOT
#define ZA_OBSERVER_ROOT "/download0/zarecomp/observer"
#endif
#ifndef ZA_OBSERVER_ENABLE
#define ZA_OBSERVER_ENABLE "/app0/observer-enable.txt"
#endif
#ifdef ZA_OBSERVER_HOST_TEST
#define ZA_OBSERVER_COMMAND ZA_OBSERVER_ROOT "/command.txt"
#else
#define ZA_OBSERVER_COMMAND "/app0/observer-command.txt"
#endif
#define NS UINT64_C(1000000000)
#define CAP 32768
extern uint64_t plat_now_ns(void);
extern void za_performance_request(int);
extern int za_performance_status(void);
extern int za_submission_switch_profile(const char *, uint64_t);
extern int sceKernelDebugOutText(int, const char *);
typedef struct {
    uint64_t frame, now, dt, before, after, cost;
    int submitted, represented, mode;
} Sample;
typedef struct { char op[20], arg[80]; uint64_t seq; unsigned value; } Command;
static bool enabled, previous_ok, previous_represented;
static uint64_t session, sequence, poll_after, previous_frame, previous_time, previous_work;
static uint64_t settle_until, stop_at, measure_seq, input_until, input_start;
static unsigned measure_seconds, sample_count;
static int action = -1;
static pthread_mutex_t input_lock = PTHREAD_MUTEX_INITIALIZER;
static Sample *samples;
static char session_dir[256];
static const char *const actions[] = {"A","B","X","Y","LSTICK","RSTICK","L","R","ZL","ZR","PLUS",
    "MINUS","LEFT","UP","RIGHT","DOWN","STICK_UP","STICK_DOWN","STICK_LEFT","STICK_RIGHT",
    "RSTICK_UP","RSTICK_DOWN","RSTICK_LEFT","RSTICK_RIGHT","RELEASE"};
static bool directory(const char *path) {
    struct stat st;
    if (!mkdir(path, 0755)) return true;
    return errno == EEXIST && !stat(path, &st) && S_ISDIR(st.st_mode);
}
static bool write_text(const char *path, const char *text) {
    char temp[320]; snprintf(temp, sizeof temp, "%s.part", path);
    FILE *f = fopen(temp, "wb"); if (!f) return false;
    bool ok = fwrite(text, 1, strlen(text), f) == strlen(text);
    if (fclose(f)) ok = false;
    if (ok && !rename(temp, path)) return true;
    remove(temp); return false;
}
static void ack(const Command *c, const char *result, const char *file, uint64_t cost) {
    char path[320], text[800];
    snprintf(path, sizeof path, "%s/ack_%" PRIu64 ".json", session_dir, c->seq);
    snprintf(text, sizeof text,
        "{\"session\":\"%016" PRIx64 "\",\"seq\":%" PRIu64 ",\"op\":\"%s\",\"result\":\"%s\","
        "\"file\":\"%s\",\"cost_ns\":%" PRIu64 "}\n", session, c->seq, c->op, result, file, cost);
    if (!write_text(path, text)) sceKernelDebugOutText(0, "[za-observer] ack write failed\n");
}
/* Separate receipt: profile/list cap are applied, not just queued. */
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
static int preparation_flags(const char *profile) {
    if (!profile) return -1;
    if (!strcmp(profile,"baseline")) return 0;
    if (!strcmp(profile,"plan-only")) return ZA_PREPARATION_PLAN;
    if (!strcmp(profile,"lazy-only")) return ZA_PREPARATION_LAZY;
    if (!strcmp(profile,"optimized")) return ZA_PREPARATION_ALL;
    return -1;
}
/* Read back the actual applied profile. Never echo a queued request as success,
 * and never interpolate an unrecognized runtime string into the JSON receipt. */
static void ack_preparation(const Command *c, const char *result, int applied,
                            uint64_t frame, uint64_t cost) {
    const char *actual = za_preparation_profile_name();
    uint32_t flags = za_preparation_profile_flags();
    int actual_flags = preparation_flags(actual);
    bool coherent = actual_flags >= 0 && flags == (uint32_t)actual_flags;
    if (!coherent || (!strcmp(result,"applied") &&
        (applied != actual_flags + 1 || actual_flags != preparation_flags(c->arg))))
        result = "receipt_mismatch";
    char path[320], text[800];
    snprintf(path,sizeof path,"%s/ack_%" PRIu64 ".json",session_dir,c->seq);
    snprintf(text,sizeof text,
        "{\"session\":\"%016" PRIx64 "\",\"seq\":%" PRIu64 ",\"op\":\"preparation\",\"result\":\"%s\","
        "\"file\":\"\",\"cost_ns\":%" PRIu64 ",\"requested_profile\":\"%s\",\"profile\":\"%s\",\"flags\":%d,\"frame\":%" PRIu64 ",\"runtime_result\":%d}\n",
        session,c->seq,result,cost,c->arg,coherent ? actual : "",coherent ? actual_flags : -1,frame,applied);
    if (!write_text(path,text)) sceKernelDebugOutText(0,"[za-observer] preparation ack write failed\n");
}
#include "immutable-observer.inc"
#include "slot-depth-observer.inc"
#include "slot-startup.inc"

static bool decimal(const char *text, uint64_t *out) {
    uint64_t n = 0;
    if (!*text) return false;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9' || n > (UINT64_MAX - (unsigned)(*text-'0'))/10) return false;
        n = n*10 + (unsigned)(*text-'0');
    }
    *out = n; return true;
}
#include "retire-capture.inc"

static bool command(uint64_t now, Command *out) {
    if (!enabled || now < poll_after) return false;
    poll_after = now + NS/2;
    FILE *f = fopen(ZA_OBSERVER_COMMAND, "rb"); if (!f) return false;
    char buf[256] = {0}; size_t n = fread(buf, 1, sizeof buf-1, f);
    bool ok = !ferror(f) && n < sizeof buf-1; fclose(f);
    if (!ok || !n || n >= sizeof buf-1 || memchr(buf, 0, n)) return false;
    char sid[40], seq[32], op[20], arg[80] = "", val[32] = "", extra[2];
    int count = sscanf(buf, "%39s %31s %19s %79s %31s %1s", sid, seq, op, arg, val, extra);
    char expected[20]; snprintf(expected, sizeof expected, "%016" PRIx64, session);
    uint64_t serial, number = 0;
    if (count < 3 || count > 5 || strcmp(sid, expected) || !decimal(seq, &serial) || !serial || serial <= sequence) return false;
    *out = (Command){.seq=serial};
    snprintf(out->op, sizeof out->op, "%s", op); snprintf(out->arg, sizeof out->arg, "%s", arg);
    bool valid = (!strcmp(op,"snapshot") && count == 3) ||
                 (!strcmp(op,"continue") && count == 4 && strspn(arg,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_") == strlen(arg));
    if ((!strcmp(op,"measure") || !strcmp(op,"fps")) && count == 4 && decimal(arg, &number)) {
        valid = !strcmp(op,"measure") ? number >= 1 && number <= 120 : number <= 1;
    }
    if (!strcmp(op,"input") && count == 5 && decimal(val, &number) && number >= 1 && number <= 120) {
        for (unsigned i=0; i<sizeof actions/sizeof actions[0]; ++i) if (!strcmp(arg, actions[i])) valid = true;
    }
    if (!strcmp(op,"submission") && count == 4 &&
        (!strcmp(arg,"each") || !strcmp(arg,"batch2") || !strcmp(arg,"batch4") || !strcmp(arg,"batch8"))) valid = true;
    if (!strcmp(op,"preparation") && count == 4 && preparation_flags(arg) >= 0) valid = true;
    if (!strcmp(op,"immutable_spans") && count == 4 && immutable_mode(arg) >= 0) valid = true;
    if (!strcmp(op,"slot_depth") && count == 4 && slot_depth_value(arg)) valid = true;
    if (!strcmp(op,"retire_capture") && count == 4) { char target_sid[17]; uint64_t target_seq; valid = retire_target(arg,target_sid,&target_seq); }
    sequence = serial; /* Consume malformed new commands; do not repeatedly parse/ack them. */
    if (!valid) { strcpy(out->op,"invalid"); ack(out,"rejected","",0); return false; }
    out->value = (unsigned)number; return true;
}
void za_observer_init(void) {
    slot_startup_init();
    FILE *f = fopen(ZA_OBSERVER_ENABLE,"rb"); if (!f) return;
    char text[32] = {0}; size_t n=fread(text,1,sizeof text-1,f); fclose(f);
    if (n != strlen("observe-r17\n") || strcmp(text,"observe-r17\n")) return;
#ifndef ZA_OBSERVER_HOST_TEST
    if (!directory("/download0/zarecomp")) return;
#endif
    if (!directory(ZA_OBSERVER_ROOT)) return;
    session = plat_now_ns();
    for (unsigned attempt=0; attempt<16; ++attempt,++session) {
        snprintf(session_dir,sizeof session_dir,ZA_OBSERVER_ROOT "/session_%016" PRIx64,session);
        if (!mkdir(session_dir,0755)) { enabled=true; break; }
        if (errno != EEXIST) return;
    }
    if (!enabled) return;
    char text_out[220];
    snprintf(text_out,sizeof text_out,"{\"protocol\":17,\"title\":\"PPSA91762\",\"session\":\"%016" PRIx64 "\"}\n",session);
    if (!write_text(ZA_OBSERVER_ROOT "/session.json",text_out)) { enabled=false; return; }
    sceKernelDebugOutText(0,"[za-observer-r17] opt-in capture/measurement enabled; waiting for scoped command\n");
}
bool za_observer_enabled(void) { return enabled; }
bool za_observer_menu(const char *active_run) {
    if (samples) return false; /* No mailbox I/O during settling/measurement. */
    Command c; if (!command(plat_now_ns(),&c)) return false;
    if (!strcmp(c.op,"retire_capture")) { retire_capture(&c); return false; }
    if (!strcmp(c.op,"preparation")) { ack_preparation(&c,"rejected_in_menu",0,0,0); return false; }
    if (!strcmp(c.op,"immutable_spans")) { ack_immutable(&c,"rejected_in_menu",0,0,0); return false; }
    if (!strcmp(c.op,"slot_depth")) { ack_slot_depth(&c,"rejected_in_menu",0,0,0); return false; }
    bool accepted = !strcmp(c.op,"continue") && *active_run && !strcmp(c.arg,active_run);
    ack(&c,accepted?"continue_requested":"rejected_in_menu","",0);
    return accepted;
}
void za_observer_input(uint64_t frame,uint64_t *buttons,int32_t *lx,int32_t *ly,int32_t *rx,int32_t *ry) {
    if (!enabled) return;
    pthread_mutex_lock(&input_lock);
    if (action < 0 || frame < input_start) { pthread_mutex_unlock(&input_lock); return; }
    if (frame >= input_until) { action=-1; pthread_mutex_unlock(&input_lock); return; }
    if (action < 16) *buttons |= UINT64_C(1) << action;
    else switch (action) {
    case 16:*ly=32767;break; case 17:*ly=-32767;break;case 18:*lx=-32767;break;case 19:*lx=32767;break;
    case 20:*ry=32767;break;case 21:*ry=-32767;break;case 22:*rx=-32767;break;case 23:*rx=32767;break;
    default:break;
    }
    pthread_mutex_unlock(&input_lock);
}
static void finish_measure(const char *result) {
    char name[100],path[320],temp[340];
    snprintf(name,sizeof name,"measure_%" PRIu64 ".csv",measure_seq);
    snprintf(path,sizeof path,"%s/%s",session_dir,name);snprintf(temp,sizeof temp,"%s.part",path);
    FILE *f=fopen(temp,"wb");bool ok=f!=NULL;
    if(f) {
        ok=fprintf(f,"frame,now_ns,dt_ns,submitted_interval,represented_interval,shader_before,shader_after,mode,observer_ns\n")>0;
        for(unsigned i=0;ok && i<sample_count;++i) {
            Sample *s=&samples[i];
            ok=fprintf(f,"%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%d,%d,%" PRIu64 ",%" PRIu64 ",%d,%" PRIu64 "\n",
                s->frame,s->now,s->dt,s->submitted,s->represented,s->before,s->after,s->mode,s->cost)>0;
        }
        if(fclose(f))ok=false;
        if(ok && rename(temp,path))ok=false;
    }
    if(!ok)remove(temp);
    Command c={.seq=measure_seq};strcpy(c.op,"measure");ack(&c,ok?result:"write_failed",ok?name:"",0);
    free(samples);samples=NULL;sample_count=0;settle_until=stop_at=0;previous_time=0;
}
void za_observer_frame(uint64_t frame,bool submitted,bool represented,uint64_t work,void *texture,
                       void (*save_texture)(void *,const char *)) {
    if(slot_startup_frame(frame,submitted,represented,samples!=NULL))return;
    if(!enabled)return;
    uint64_t now=plat_now_ns();
    if(samples) {
        if(previous_time && (now<=previous_time || frame<=previous_frame)) { finish_measure("clock_or_frame_reset");return; }
        if(!stop_at && now>=settle_until) { stop_at=now+(uint64_t)measure_seconds*NS;previous_time=0; }
        if(stop_at && previous_time) {
            Sample *s=&samples[sample_count++];
            *s=(Sample){.frame=frame,.now=now,.dt=now-previous_time,.before=previous_work,.after=work,
                .submitted=submitted&&previous_ok,.represented=represented||previous_represented,.mode=za_performance_status()};
            s->cost=plat_now_ns()-now;
        }
        previous_time=now;previous_frame=frame;previous_work=work;previous_ok=submitted;previous_represented=represented;
        if(stop_at && (now>=stop_at || sample_count==CAP))finish_measure(sample_count==CAP?"buffer_full":"complete");
        return;
    }
    Command c;if(!command(now,&c))return;
    if(!strcmp(c.op,"retire_capture")) {
        retire_capture(&c);
    } else if(!strcmp(c.op,"snapshot")) {
        char name[100],path[320];snprintf(name,sizeof name,"frame_%" PRIu64 "_%" PRIu64 ".png",frame,c.seq);
        snprintf(path,sizeof path,"%s/%s",session_dir,name);
        uint64_t before=plat_now_ns();save_texture(texture,path);uint64_t cost=plat_now_ns()-before;
        struct stat st;bool ok=!stat(path,&st)&&st.st_size>32;
        ack(&c,ok?"saved":"capture_failed",ok?name:"",cost);
    } else if(!strcmp(c.op,"measure")) {
        samples=calloc(CAP,sizeof *samples);
        if(!samples){ack(&c,"allocation_failed","",0);return;}
        measure_seq=c.seq;measure_seconds=c.value;settle_until=now+2*NS;stop_at=0;sample_count=0;previous_time=0;
        ack(&c,"settling","",0);
    } else if(!strcmp(c.op,"submission")) {
        if (!submitted || represented) { ack_submission(&c,"rejected_boundary",0,frame,0); return; }
        uint64_t before = plat_now_ns();
        int applied = za_submission_switch_profile(c.arg, frame);
        const char *result = applied > 0 ? "applied" : applied == -2 ? "rejected_override" : "drain_failed";
        ack_submission(&c,result,applied > 0 ? (unsigned)applied : 0,frame,plat_now_ns()-before);
    } else if(!strcmp(c.op,"preparation")) {
        if (!frame || !submitted || represented) { ack_preparation(&c,"rejected_boundary",0,frame,0); return; }
        uint64_t before = plat_now_ns();
        int applied = za_preparation_switch_profile(c.arg,frame);
        const char *result = applied > 0 ? "applied" : applied == -1 ? "rejected_profile" : applied == -3 ? "drain_failed" : "receipt_mismatch";
        ack_preparation(&c,result,applied,frame,plat_now_ns()-before);
    } else if(!strcmp(c.op,"immutable_spans")) {
        if (!frame || !submitted || represented) { ack_immutable(&c,"rejected_boundary",0,frame,0); return; }
        uint64_t before = plat_now_ns();
        int applied = za_immutable_spans_switch(c.arg,frame);
        const char *result = applied > 0 ? "applied" : applied == -1 ? "rejected_mode" : applied == -3 ? "drain_failed" : "receipt_mismatch";
        ack_immutable(&c,result,applied,frame,plat_now_ns()-before);
    } else if(!strcmp(c.op,"slot_depth")) {
        if (!frame || !submitted || represented) { ack_slot_depth(&c,"rejected_boundary",0,frame,0); return; }
        uint64_t before=plat_now_ns();
        int applied=za_slot_depth_switch(c.arg,frame);
        ack_slot_depth(&c,slot_depth_result(applied),applied,frame,plat_now_ns()-before);
    } else if(!strcmp(c.op,"fps")) {
        za_performance_request((int)c.value);ack(&c,"requested","",0);
    } else if(!strcmp(c.op,"input")) {
        pthread_mutex_lock(&input_lock);
        action=-1;
        for(unsigned i=0;i<sizeof actions/sizeof actions[0];++i)if(!strcmp(c.arg,actions[i]))action=(int)i;
        input_start=frame+1;input_until=input_start+c.value;
        if(action==24)action=-1;
        pthread_mutex_unlock(&input_lock);
        ack(&c,"input_armed","",0);
    } else ack(&c,"rejected_in_game","",0);
}
