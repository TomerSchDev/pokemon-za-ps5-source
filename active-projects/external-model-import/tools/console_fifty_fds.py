"""Inspect or adjust only the owned title process' open-file limit via the OS API."""
import json,subprocess,sys,time
from pathlib import Path
from console_fifty_live import OUT,LOCAL,STATE,api,guard
def linux(p):
 s=str(p.resolve());return '/mnt/'+s[0].lower()+s[2:].replace('\\','/')
def main():
 action=sys.argv[1];assert action in ('inspect','raise')
 state=json.loads(STATE.read_text());pid=state['pid'];c=api.Console()
 try:
  guard(c,state);name='fd-'+action+'-'+str(pid);log='/data/console-fifty-'+name+'.log'
  assert c.read(log,16384) is None,'Prior versioned diagnostic exists.'
  if action=='raise':
   before=(OUT/('fd-inspect-'+str(pid)+'.log')).read_text();assert 'target_rc=0' in before
  source=r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/sysctl.h>
#include <sys/resource.h>
static int contains(const char*p,const char*s){char b[4096];FILE*f=fopen(p,"rb");if(!f)return 0;size_t n=fread(b,1,sizeof b-1,f);fclose(f);b[n]=0;return strstr(b,s)!=0;}
int main(void){
 FILE*f=fopen(LOGPATH,"w");if(!f)return 1;setvbuf(f,NULL,_IONBF,0);
 if(!contains(SESSION_PATH,SESSION_ID)){fprintf(f,"REFUSED session changed\n");fclose(f);return 2;}
 struct rlimit self={0},old={0},after={0};int r=getrlimit(RLIMIT_NOFILE,&self);
 fprintf(f,"self_rc=%d soft=%llu hard=%llu errno=%d\n",r,(unsigned long long)self.rlim_cur,(unsigned long long)self.rlim_max,errno);
 int mib[5]={CTL_KERN,KERN_PROC,KERN_PROC_RLIMIT,TARGET_PID,RLIMIT_NOFILE};size_t n=sizeof old;errno=0;
 r=sysctl(mib,5,&old,&n,NULL,0);fprintf(f,"target_rc=%d pid=%d bytes=%zu soft=%llu hard=%llu errno=%d\n",r,TARGET_PID,n,(unsigned long long)old.rlim_cur,(unsigned long long)old.rlim_max,errno);
 if(r||n!=sizeof old){fprintf(f,"UNSUPPORTED read; no limits changed\n");fclose(f);return 2;}
#if APPLY
 if(old.rlim_cur<16384){struct rlimit wanted=old;wanted.rlim_cur=16384;if(wanted.rlim_max<wanted.rlim_cur)wanted.rlim_max=wanted.rlim_cur;errno=0;
  r=sysctl(mib,5,NULL,NULL,&wanted,sizeof wanted);fprintf(f,"set_rc=%d errno=%d\n",r,errno);if(r){fclose(f);return 2;}}
 n=sizeof after;errno=0;r=sysctl(mib,5,&after,&n,NULL,0);
 fprintf(f,"readback_rc=%d pid=%d soft=%llu hard=%llu errno=%d\n",r,TARGET_PID,(unsigned long long)after.rlim_cur,(unsigned long long)after.rlim_max,errno);
 if(r||after.rlim_cur<16384){fclose(f);return 2;}
 fprintf(f,"COMPLETE only this title process changed; executable and system-wide limits unchanged\n");
#else
 fprintf(f,"COMPLETE read-only; no limits changed\n");
#endif
 fclose(f);return 0;
}
'''
  definitions={'LOGPATH':log,'SESSION_PATH':state['data']+'/observer/session.json','SESSION_ID':state['session']}
  prefix=''.join('#define %s %s\n'%(k,json.dumps(v)) for k,v in definitions.items())
  prefix+='#define TARGET_PID %d\n#define APPLY %d\n'%(pid,int(action=='raise'))
  local=LOCAL/'compiler';local.mkdir(exist_ok=True);src=local/(name+'.c');src.write_text(prefix+source,encoding='utf-8');elf=src.with_suffix('.elf')
  sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
  subprocess.run(['wsl.exe','-e',sdk+'/bin/prospero-clang','-O2',linux(src),'-o',linux(elf)],check=True)
  remote='/data/pldmgr/payloads/za_console_fifty_20261031/'+elf.name
  raw=elf.read_bytes();c.store(remote,raw);c.chmod(remote,'755');assert c.read(remote,4<<20)==raw
  guard(c,state);print(api.http_text(api.PAYLOAD_MANAGER+'/loadpayload:'+remote),flush=True)
  deadline=time.monotonic()+20
  while True:
   raw=c.read(log,16384)
   if raw and any(w in raw for w in (b'COMPLETE',b'UNSUPPORTED',b'REFUSED',b'set_rc=-1')):break
   assert time.monotonic()<deadline;time.sleep(.2)
  (OUT/(name+'.log')).write_bytes(raw);print(raw.decode(),flush=True)
 finally:c.close()
if __name__=='__main__':main()
