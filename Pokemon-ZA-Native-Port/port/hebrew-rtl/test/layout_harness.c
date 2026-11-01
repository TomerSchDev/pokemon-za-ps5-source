/* Exercise the actual layout hook with a recording native-layout callback. */
#include "cpu.h"
#include <stdlib.h>
extern GuestFn original_700264efe4;
extern void f_700264efe4(Cpu *);
static uint16_t captured[65536];
static int calls, horizontal, lines, length, pointer_changed;
static const uint16_t *input;
static void record_layout(Cpu *c) {
    uintptr_t box=c->x[0];calls++;
    horizontal=LD8(box+0x116);lines=LD16(box+0x114);length=LD16(box+0x112);
    pointer_changed=LD64(box+0xd8)!=(uintptr_t)input;
    memcpy(captured,(const void *)(uintptr_t)LD64(box+0xd8),length*2);
    /* Preserve changes made by native layout outside the overridden low bits. */
    ST16(box+0x114,LD16(box+0x114)^0x40);
    c->x[0]=0xabcdef;
}
__declspec(dllexport) int exercise_layout(const char *name,float width,float height,
    const uint16_t *text,int n,int utf8,uint16_t *result,uint16_t *visual) {
    _Alignas(16) uint8_t box[0x180]={0};Cpu c={0};
    input=text;calls=0;memset(captured,0,sizeof captured);
    strncpy((char *)box+0xb0,name,24);memcpy(box+0x50,&width,4);memcpy(box+0x54,&height,4);
    ST64(box+0xd8,(uintptr_t)text);ST16(box+0x112,n);ST8(box+0x117,utf8);
    ST8(box+0x116,0xa1);ST16(box+0x114,0x120);c.x[0]=(uintptr_t)box;
    original_700264efe4=record_layout;f_700264efe4(&c);
    result[0]=calls;result[1]=horizontal;result[2]=lines;result[3]=length;
    result[4]=pointer_changed;result[5]=LD8(box+0x116);result[6]=LD16(box+0x114);
    result[7]=LD64(box+0xd8)==(uintptr_t)text;result[8]=LD16(box+0x112);
    result[9]=c.x[0]==0xabcdef;memcpy(visual,captured,length*2);return 0;
}
