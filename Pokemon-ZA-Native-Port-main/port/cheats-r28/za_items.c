/* Requests cross threads; game calls run synchronously inside its item getter.
 * No retained guest object pointer. Inventory writes are exclusively in the
 * original add-item path f_700048963c -> f_700048994c -> f_7000a5a268.
 */
#include "za_items.h"
#include "cpu.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
static const ZaItem catalog[] = {
#include "items.inc"
};
enum { NOT_READY, READY, QUEUED, ADDED, FULL, BAD_TABLE, REJECTED };
static const char *messages[]={"OPEN THE BAG FIRST","READY","QUEUED - OPEN BAG","ADDED","ITEM / POCKET FULL","ITEM UNAVAILABLE IN GAME","REQUEST REJECTED"};
static atomic_uint_fast64_t mailbox;
static atomic_int ready, status;
static atomic_uint applied,last_count;
static atomic_flag consumer=ATOMIC_FLAG_INIT;
void f_70002bc8ec(Cpu*);
void f_70002bc9d0(Cpu*);
void f_700099e47c(Cpu*);
void f_7000a5a228(Cpu*);
void f_700048963c(Cpu*);
unsigned za_items_count(void){return sizeof(catalog)/sizeof(catalog[0]);}
const ZaItem *za_items_at(unsigned i){return i<za_items_count()?&catalog[i]:0;}
int za_items_ready(void){return atomic_load(&ready);}
int za_items_pending(void){return (atomic_load(&mailbox)&0xffffffffu)!=0;}
const char *za_items_status(void){unsigned s=atomic_load(&status);return s<7?messages[s]:messages[REJECTED];}
unsigned za_items_last_count(void){return atomic_load(&last_count);}
unsigned za_items_applied(void){return atomic_load(&applied);}
void za_items_reset(void){
    uint64_t old=atomic_load(&mailbox);
    while(!atomic_compare_exchange_weak(&mailbox,&old,(old+0x100000000ull)&0xffffffff00000000ull)){}
    atomic_store(&ready,0);atomic_store(&status,NOT_READY);
}
int za_items_request(unsigned index,unsigned amount){
    if(index>=za_items_count()||(amount!=1&&amount!=10&&amount!=99&&amount!=999)||!za_items_ready())return 0;
    uint64_t old=atomic_load(&mailbox);
    if(old&0xffffffffu)return 0;
    uint64_t command=((uint64_t)(index+1)<<16)|amount;
    if(!atomic_compare_exchange_strong(&mailbox,&old,old|command))return 0;
    atomic_store(&status,QUEUED);return 1;
}
static unsigned get_count(Cpu *c,unsigned id){c->x[0]=id;f_70002bc8ec(c);return (unsigned)(c->x[0]>>32);}
static int game_item(Cpu *c,const ZaItem *item){
    uint64_t table=LD64(0x7003ec3320ull);
    if(!table||table<0x10000)return 0;
    c->x[0]=table;c->x[1]=item->id;f_70002bc9d0(c);
    if(!c->x[0])return 0;
    c->x[0]=table;c->x[1]=item->id;f_7000a5a228(c);
    if(c->x[0]!=item->cap)return 0;
    c->x[0]=table;c->x[1]=item->id;f_700099e47c(c);
    return c->x[0]==item->pocket;
}
void za_items_pump(void *cpu){
    if(atomic_flag_test_and_set_explicit(&consumer,memory_order_acquire))return;
    /* These singleton readiness checks are the same guards used by the game's
     * add-item wrapper and its queued grant handler. Component lookup itself
     * remains in the original typed getter, on this guest thread and stack. */
    if(!LD32(0x700610d940ull)||!LD32(0x700610dec0ull))goto done;
    Cpu *c=cpu;Cpu saved;memcpy(&saved,c,sizeof(saved));
    if(!atomic_exchange(&ready,1)){
        atomic_store(&status,READY);
#ifdef ZA_ITEMS_TRACE
        fprintf(stderr,"[r28-items] ready\n");fflush(stderr);
        for(unsigned i=0;i<za_items_count();++i){
            int valid=game_item(c,&catalog[i]);
            fprintf(stderr,"[r28-catalog] id=%u pocket=%u cap=%u valid=%d\n",catalog[i].id,catalog[i].pocket,catalog[i].cap,valid);
        }
        fflush(stderr);
#endif
    }
    uint64_t old=atomic_load(&mailbox);
    unsigned command=(unsigned)old;
    if(command){
        unsigned index=(command>>16)-1,amount=command&0xffff;
        if(index>=za_items_count()||!game_item(c,&catalog[index])){
            if(atomic_compare_exchange_strong(&mailbox,&old,old&0xffffffff00000000ull))atomic_store(&status,BAD_TABLE);
        }else{
            const ZaItem *item=&catalog[index];
            unsigned before=get_count(c,item->id);
            if(atomic_compare_exchange_strong(&mailbox,&old,old&0xffffffff00000000ull)){
                if(before>item->cap){atomic_store(&status,REJECTED);}
                else if(before==item->cap){atomic_store(&status,FULL);atomic_store(&last_count,before);}
                else{
                    c->x[0]=0x700610d800ull;c->x[1]=item->id;c->x[2]=amount;c->x[3]=0;c->x[4]=0;
                    f_700048963c(c);
                    unsigned after=get_count(c,item->id);
                    atomic_store(&last_count,after);
                    if(after>before&&after<=item->cap){atomic_fetch_add(&applied,1);atomic_store(&status,ADDED);}
                    else atomic_store(&status,after==before?FULL:REJECTED);
#ifdef ZA_ITEMS_TRACE
                    fprintf(stderr,"[r28-items] id=%u before=%u request=%u after=%u status=%s applied=%u\n",item->id,before,amount,after,za_items_status(),za_items_applied());fflush(stderr);
#endif
                }
            }
        }
    }
    memcpy(c,&saved,sizeof(saved));
done:
    atomic_flag_clear_explicit(&consumer,memory_order_release);
}
