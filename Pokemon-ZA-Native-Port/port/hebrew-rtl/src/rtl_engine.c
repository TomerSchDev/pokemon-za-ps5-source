/* Hebrew RTL at TextBox layout time. Logical message buffers stay logical.
 * Candidate for the audited 2.0.2 TextBox ABI only. */
#include "cpu.h"
#include <fribidi.h>
#include <stdlib.h>
#include <stdio.h>
#ifdef RTL_PROXY
GuestFn original_700264efe4;
#else
extern void original_700264efe4(Cpu *);
#endif
typedef struct {int start,len,color;FriBidiChar cp;} Unit;
static int transform_line(const uint16_t *s,int n,uint16_t *out,int *color) {
    Unit *u=calloc(n+1,sizeof *u);FriBidiChar *cp=calloc(n+1,sizeof *cp),*vis=calloc(n+1,sizeof *vis);
    FriBidiStrIndex *v2l=calloc(n+1,sizeof *v2l);uint16_t *raw=calloc(n+1,sizeof *raw);int k=0,o=0,i=0,pending=0,rlen=0;
    if(!u||!cp||!vis||!v2l||!raw){free(u);free(cp);free(vis);free(v2l);free(raw);return -1;}
    while(i<n){
        if(s[i]==0x10){
            if(i+2>=n || s[i+1]<1 || i+2+s[i+1]>n){o=-1;goto done;}
            int size=2+s[i+1],code=s[i+2];
            if(code==0xff00 && size==4){
                *color=s[i+3];i+=size;continue;
            }
            if(code==0xbd0a && size==4){
                int count=s[i+3];if(i+size+count>n){o=-1;goto done;}
                memcpy(raw+rlen,s+i,(size+count)*2);rlen+=size+count;i+=size+count;
                u[k]=(Unit){pending,rlen-pending,*color,0xfffc};cp[k++]=0xfffc;pending=rlen;continue;
            }
            memcpy(raw+rlen,s+i,size*2);rlen+=size;i+=size;continue;
        }
        FriBidiChar ch=s[i++];raw[rlen++]=ch;
        if(ch>=0xd800 && ch<=0xdbff && i<n && s[i]>=0xdc00 && s[i]<=0xdfff){raw[rlen++]=s[i];ch=0x10000+((ch-0xd800)<<10)+(s[i++]-0xdc00);}
        u[k]=(Unit){pending,rlen-pending,*color,ch};cp[k++]=ch;pending=rlen;
    }
    FriBidiParType dir=FRIBIDI_PAR_RTL;
    if(k && !fribidi_log2vis(cp,k,&dir,vis,NULL,v2l,NULL)){o=-1;goto done;}
    int emitted_color=0;
    for(int j=0;j<k;j++){
        Unit a=u[v2l[j]];
        if(a.color!=emitted_color){out[o++]=0x10;out[o++]=2;out[o++]=0xff00;out[o++]=a.color;emitted_color=a.color;}
        if(a.cp==vis[j]){memcpy(out+o,raw+a.start,a.len*2);o+=a.len;}
        else { /* Mirrored bracket; preserve any control prefix. */
            int chars=a.cp>0xffff?2:1;
            memcpy(out+o,raw+a.start,(a.len-chars)*2);o+=a.len-chars;
            if(vis[j]<=0xffff)out[o++]=vis[j];else{uint32_t c=vis[j]-0x10000;out[o++]=0xd800+(c>>10);out[o++]=0xdc00+(c&1023);}
        }
    }
    if(emitted_color){out[o++]=0x10;out[o++]=2;out[o++]=0xff00;out[o++]=0;}
    if(pending<rlen){memcpy(out+o,raw+pending,(rlen-pending)*2);o+=rlen-pending;}
done:free(u);free(cp);free(vis);free(v2l);free(raw);return o;
}
#ifdef RTL_ENGINE_TEST
__declspec(dllexport)
#endif
int rtl_transform(const uint16_t *s,int n,uint16_t *out) {
    int o=0,start=0,color=0;
    for(int i=0;i<=n;i++){
        /* A zero in a control payload is data, never a string terminator. */
        if(i<n && s[i]==0x10){if(i+2>=n || i+2+s[i+1]>n)return -1;i+=1+s[i+1];continue;}
        if(i==n || s[i]==10){int size=transform_line(s+start,i-start,out+o,&color);if(size<0)return -1;o+=size;if(i<n)out[o++]=10;start=i+1;}
    }
    out[o]=0;return o;
}
#ifndef RTL_ENGINE_TEST
void f_700264efe4(Cpu *c) {
    uintptr_t box=c->x[0];const uint16_t *s=(void *)(uintptr_t)LD64(box+0xd8);int n=LD16(box+0x112),he=0;
    /* 0 is UTF-16; 1 is UTF-8, which this hook leaves untouched. */
    if(s && !LD8(box+0x117) && n>0 && n<16384){for(int i=0;i<n;i++){
        if(s[i]==0x10 && i+2<n && i+2+s[i+1]<=n){i+=1+s[i+1];continue;}
        if(s[i]>=0x590&&s[i]<=0x5ff){he=1;break;}
    }}
    if(!he){original_700264efe4(c);return;}
    uint16_t *visual=calloc((size_t)n*6+8,sizeof *visual);
    int size=visual?rtl_transform(s,n,visual):-1;
    if(size<0 || size>65535){free(visual);original_700264efe4(c);return;}
    if(getenv("LARECOMP_RTL_LAYOUT_TRACE")) {
        static uintptr_t seen[2048];static int count;int found=0;
        for(int i=0;i<count;i++)if(seen[i]==box)found=1;
        if(!found && count<2048){seen[count++]=box;
            fprintf(stderr,"[rtl-pane] %llx %d %x %x ",(unsigned long long)box,n,LD16(box+0x114),LD8(box+0x116));
            for(int i=0;i<0xd8;i++)fprintf(stderr,"%02x",LD8(box+i));
            fprintf(stderr," text=");for(int i=0;i<n;i++)fprintf(stderr,"%04x,",s[i]);fputc('\n',stderr);
        }

    }
    /* Native TextBox horizontal=2 (right), explicit line alignment=3 (right).
       Keep vertical origin, sizing and all other bits exact. */
    uint8_t old_horizontal=LD8(box+0x116)&3;uint16_t old_lines=LD16(box+0x114)&3;
    char pane[25];memcpy(pane,(const void *)(box+0xb0),24);pane[24]=0;
    /* Button legends are laid out by their measured width next to a separate
       icon. Moving their text inside the template's 270px box overlaps the
       next legend. Preserve those native anchors; bidi still applies. */
    /* Auto-sized map quest chips and headers already derive
       their pane origin from measured text. Keep that origin, and road labels
       attached to their map coordinates. Multiline prose still aligns right. */
    int anchored=!strcmp(pane,"T_option_00") || !strcmp(pane,"T_quest_00") || !strcmp(pane,"T_fly_00")
        /* Shared context choices (cmn_context_{small_,}item_00): the frame
           shrinks to measured text but T_00 retains its template width.
           Right-aligning inside that width pushes choices past the frame.
           Match both audited sizes; dialogue also uses T_00 and must retain RTL. */
        || (!strcmp(pane,"T_00") &&
            ((LD32(box+0x50)==0x44070000 && LD32(box+0x54)==0x42380000)
             || (LD32(box+0x50)==0x43f30000 && LD32(box+0x54)==0x42200000)))
        || (!strcmp(pane,"T_title_00") && LD32(box+0x50)==0x43f30000 && LD32(box+0x54)==0x42200000)
        || strstr(pane,"_num_")!=NULL
        /* Menu quest counter row (main_menu_quest_parts_00, 312x40): the game places
           T_item_num_00 ("5/5") after the label's measured width; a right-aligned
           label would run under the number. */
        || (!strcmp(pane,"T_item_00") && LD32(box+0x50)==0x439c0000 && LD32(box+0x54)==0x42200000)
        || (pane[0]=='T' && pane[1]=='_' && (pane[2]=='a'||pane[2]=='r') && pane[3]>='0' && pane[3]<='9');
    if(!anchored){
        ST8(box+0x116,(LD8(box+0x116)&~3u)|2u);
        ST16(box+0x114,(LD16(box+0x114)&~3u)|3u);
    }
    /* Map summary auto-sizing sits exactly on the wrap boundary. Reserve a
       small advance margin for reordered glyph bearings, within this audited
       468x160 pane only; retain the game's original font size after layout. */
    uint32_t old_font_width=LD32(box+0xf8);
    int map_summary=!strcmp(pane,"T_detail_00") && LD32(box+0x50)==0x43ea0000 && LD32(box+0x54)==0x43200000;
    if(map_summary){float width;memcpy(&width,&old_font_width,4);width*=0.97f;uint32_t adjusted;memcpy(&adjusted,&width,4);ST32(box+0xf8,adjusted);}
    ST64(box+0xd8,(uintptr_t)visual);ST16(box+0x112,size);
    original_700264efe4(c);
    ST64(box+0xd8,(uintptr_t)s);ST16(box+0x112,n);
    if(map_summary)ST32(box+0xf8,old_font_width);
    ST8(box+0x116,(LD8(box+0x116)&~3u)|old_horizontal);
    ST16(box+0x114,(LD16(box+0x114)&~3u)|old_lines);free(visual);
}
#endif
