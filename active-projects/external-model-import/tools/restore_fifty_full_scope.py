"""Restore this QA cohort's full model registration; preserve other mods."""
import json, subprocess, time
from pathlib import Path
from console_fifty_live import OUT, LOCAL, STATE, APP, api, guard

def main():
    state = json.loads(STATE.read_text())
    c = api.Console()
    try:
        guard(c, state)
        for name in c.listing(state['data']+'/observer/session_'+state['session']):
            if name.startswith('ack_'):
                assert json.loads(c.read(state['data']+'/observer/session_'+state['session']+'/'+name,4096)).get('op') != 'continue'
        source = r'''
#define _DEFAULT_SOURCE 1
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#define MODS DATA "/mods"
static int target(const char*p,const char*t){char s[1400];ssize_t n=readlink(p,s,sizeof s-1);if(n<0)return 0;s[n]=0;return !strcmp(s,t);}
int main(void){
 FILE*f=fopen("/data/console-fifty-restore-full-r4.log","wx");if(!f)return 1;setvbuf(f,NULL,_IONBF,0);
 char sid[4096];FILE*i=fopen(DATA "/observer/session.json","r");if(!i){fclose(f);return 2;}size_t n=fread(sid,1,sizeof sid-1,i);sid[n]=0;fclose(i);
 if(!strstr(sid,SID)){fprintf(f,"REFUSED session changed\n");fclose(f);return 2;}
 struct stat s,ms;const char*full="../../../app0/console-fifty-20261031-r1-models";
 const char*original=MODS "/00-console-fifty-20261031-r1";const char*disabled=MODS "/_00-console-fifty-20261031-r1";
 const char*scope=MODS "/00-console-fifty-scoped-models";const char*scopeoff=MODS "/_00-console-fifty-scoped-models-r2";
 const char*reg=MODS "/00-00-console-fifty-batch-metadata";const char*regoff=MODS "/_00-00-console-fifty-batch-metadata-r2";
 int sr=stat(MODS,&ms);fprintf(f,"MODS stat=%d mode=%o\n",sr,ms.st_mode);if(sr){fclose(f);return 2;}int cr=chmod(MODS,0777);fprintf(f,"MODS chmod=%d\n",cr);if(cr){fclose(f);return 2;}
 const char*inspect[]={disabled,original,scope,reg};for(int j=0;j<4;j++){char p[1400];errno=0;ssize_t k=readlink(inspect[j],p,sizeof p-1);if(k>=0)p[k]=0;else strcpy(p,"(missing/not-link)");fprintf(f,"LINK %s => %s rc=%d errno=%d\n",inspect[j],p,(int)k,errno);}
 if(!target(disabled,full)||!lstat(original,&s)||errno!=ENOENT||!target(scope,"../console-fifty-scope-b01")||!target(reg,"../../../app0/console-fifty-registration-b01")){
  fprintf(f,"REFUSED unexpected existing QA links\n");chmod(MODS,ms.st_mode&0777);fclose(f);return 2;}
 if(!lstat(scopeoff,&s)||errno!=ENOENT||!lstat(regoff,&s)||errno!=ENOENT){fprintf(f,"REFUSED destinations/permissions\n");chmod(MODS,ms.st_mode&0777);fclose(f);return 2;}
 int rc=2;
 if(rename(scope,scopeoff))goto done;
 if(rename(reg,regoff)){rename(scopeoff,scope);goto done;}
 if(rename(disabled,original)){rename(regoff,reg);rename(scopeoff,scope);goto done;}
 if(target(original,full)&&target(scopeoff,"../console-fifty-scope-b01")&&target(regoff,"../../../app0/console-fifty-registration-b01"))rc=0;
done:chmod(MODS,ms.st_mode&0777);
 fprintf(f,"%s full cohort restored; all other mod links preserved; restart required\n",rc?"FAILED":"COMPLETE");fclose(f);return rc;
}
'''
        prefix = '#define DATA '+json.dumps(state['data'])+'\n#define SID '+json.dumps(state['session'])+'\n'
        directory = LOCAL/'compiler'
        src = directory/'restore-full-r2.c'; elf=src.with_suffix('.elf')
        src.write_text(prefix+source,encoding='utf-8')
        def linux(p):
            s=str(p.resolve());return '/mnt/'+s[0].lower()+s[2:].replace('\\','/')
        sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
        subprocess.run(['wsl.exe','-e',sdk+'/bin/prospero-clang','-O2',linux(src),'-o',linux(elf)],check=True)
        remote='/data/pldmgr/payloads/za_console_fifty_20261031/'+elf.name
        raw=elf.read_bytes();c.store(remote,raw);c.chmod(remote,'755');assert c.read(remote,4<<20)==raw
        guard(c,state);print(api.http_text(api.PAYLOAD_MANAGER+'/loadpayload:'+remote),flush=True)
        deadline=time.monotonic()+20
        while True:
            raw=c.read('/data/console-fifty-restore-full-r4.log',16384)
            if raw and any(word in raw for word in (b'COMPLETE',b'FAILED',b'REFUSED')):break
            assert time.monotonic()<deadline;time.sleep(.2)
        dest=OUT/'resume-20261031-r2/full-cohort-restore-r4.log';assert not dest.exists();dest.write_bytes(raw)
        print(raw.decode(),flush=True);assert b'COMPLETE' in raw
    finally:c.close()
if __name__=='__main__':main()
