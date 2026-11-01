/* Diagnostic game-DLL extension only, not part of the PS5 title.
 * Reads one explicitly named per-run mailbox. Never retains/writes guest pointers.
 * Command format: monotonic sequence, amount (0 = OFF, permitted additions only).
 * Only the production public money API is used; bounded to 10 minutes. */
#include "za_money.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
static DWORD WINAPI controller(void* unused) {
    (void)unused;
    const char* path=getenv("ZA_MONEY_PC_COMMAND");
    if(!path||!*path)return 0;
    unsigned last=0;
    for(unsigned tick=0;tick<6000;++tick) {
        unsigned seq=0,amount=0; FILE* f=fopen(path,"r");
        int n=f?fscanf(f,"%u %u",&seq,&amount):0; if(f)fclose(f);
        if(n==2&&seq>last) {
            int enabled=za_money_set_enabled(amount!=0);
            int accepted=amount&&enabled?za_money_request(amount):0;
            last=seq;
            f=fopen("r27money-control.log","a");
            if(f){fprintf(f,"seq=%u amount=%u ready=%d enabled=%d accepted=%d pending=%u applied=%u value=%u\n",
              seq,amount,za_money_ready(),za_money_enabled(),accepted,za_money_pending(),za_money_applied(),za_money_last_value());fclose(f);}
        }
        Sleep(100);
    }
    return 0;
}
void za_money_pc_start(void) {
    static int started=0;
    if(!started++&&getenv("ZA_MONEY_PC_COMMAND")) {
        HANDLE h=CreateThread(NULL,0,controller,NULL,0,NULL); if(h)CloseHandle(h);
    }
}
