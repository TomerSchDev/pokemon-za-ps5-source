#include "za_items.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
static atomic_uint batch_amount;
/* Diagnostic only: replay independent public requests on the same synchronous
 * game callback. This avoids hundreds of menu transitions during inventory QA.
 * The production PS5 helper has no batch entry and no file/controller access. */
void za_items_pc_batch(void *cpu){
 unsigned amount=atomic_exchange(&batch_amount,0);if(!amount)return;
 FILE *f=fopen("r28items-batch.log","a");
 for(unsigned i=0;i<za_items_count();++i){
  int accepted=za_items_request(i,amount);za_items_pump(cpu);
  if(f)fprintf(f,"id=%u accepted=%d status=%s count=%u pending=%d\n",za_items_at(i)->id,accepted,za_items_status(),za_items_last_count(),za_items_pending());
 }
 if(f)fclose(f);
}
static DWORD WINAPI controller(void *unused){
 (void)unused;const char *path=getenv("ZA_MONEY_PC_COMMAND");if(!path)return 0;
 unsigned last=0,waiting=0;
 for(unsigned tick=0;tick<6000;++tick){
  unsigned seq=0,id=0,amount=0;FILE *f=fopen(path,"r");
  int n=f?fscanf(f,"%u %u %u",&seq,&id,&amount):0;if(f)fclose(f);
  if(waiting&&!za_items_pending()){
   f=fopen("r28items-control.log","a");if(f){fprintf(f,"done=%u status=%s value=%u applied=%u\n",waiting,za_items_status(),za_items_last_count(),za_items_applied());fclose(f);}waiting=0;
  }
  if(n==3&&seq>last&&!waiting){
   if(id==50000){atomic_store(&batch_amount,amount);last=seq;continue;}
   unsigned i=0;while(i<za_items_count()&&za_items_at(i)->id!=id)++i;
   int accepted=za_items_request(i,amount);
   if(!accepted){Sleep(100);continue;}last=seq;waiting=seq;
   f=fopen("r28items-control.log","a");
   if(f){fprintf(f,"seq=%u id=%u amount=%u ready=%d accepted=%d status=%s applied=%u\n",seq,id,amount,za_items_ready(),accepted,za_items_status(),za_items_applied());fclose(f);}
  }
  Sleep(100);
 }return 0;
}
void za_money_pc_start(void){static int started=0;if(!started++&&getenv("ZA_MONEY_PC_COMMAND")){HANDLE h=CreateThread(NULL,0,controller,NULL,0,NULL);if(h)CloseHandle(h);}}
