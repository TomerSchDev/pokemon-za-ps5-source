/* Disable (or restore) side-branch mod links by renaming NAME <-> _NAME, so the console runs main only.
 * Runs as a payload while PPSA91762 is mounted at its menu. Renames only the names it was built with;
 * refuses if a target name already exists. Saves, runs and other mods are not touched. */
#define _DEFAULT_SOURCE 1
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#ifndef MOD_NAMES
#error "MOD_NAMES (comma-free list as a C array initializer) and RESTORE (0/1) are required"
#endif
#define DATA "/mnt/sandbox/PPSA91762_000/download0/zarecomp"
#define MODS DATA "/mods"
#define LOG "/data/main-isolate-mods.log"
static const char *names[] = MOD_NAMES;
int main(void){
 FILE*f=fopen(LOG,"w");if(!f)return 1;setvbuf(f,NULL,_IONBF,0);
 fprintf(f,"START %s side-branch mods\n",RESTORE?"restore":"disable");
 struct stat ms,s;int rc=2,count=(int)(sizeof names/sizeof names[0]);char renamed[64]={0};
 if(count>64){fprintf(f,"REFUSED too many names\n");goto end;}
 if(stat(MODS,&ms)){fprintf(f,"FAILED mods stat errno=%d\n",errno);goto end;}
 if(chmod(MODS,0777)){fprintf(f,"FAILED mods chmod errno=%d\n",errno);goto end;}
 for(int i=0;i<count;i++){char on[1024],off[1024];
  snprintf(on,sizeof on,MODS "/%s",names[i]);snprintf(off,sizeof off,MODS "/_%s",names[i]);
  const char*from=RESTORE?off:on,*to=RESTORE?on:off;
  if(lstat(from,&s)){if(!lstat(to,&s)){fprintf(f,"ALREADY %s\n",to);continue;}fprintf(f,"MISSING %s\n",from);goto undo;}
  if(!lstat(to,&s)){fprintf(f,"REFUSED target exists %s\n",to);goto undo;}
  if(rename(from,to)){fprintf(f,"FAILED rename %s errno=%d\n",from,errno);goto undo;}
  fprintf(f,"RENAMED %s -> %s\n",from,to);renamed[i]=1;}
 rc=0;goto restore;
undo:
 for(int i=count-1;i>=0;i--){if(!renamed[i])continue;char on[1024],off[1024];
  snprintf(on,sizeof on,MODS "/%s",names[i]);snprintf(off,sizeof off,MODS "/_%s",names[i]);
  if(RESTORE)rename(on,off);else rename(off,on);}
restore:
 chmod(MODS,ms.st_mode&0777);
end:
 fprintf(f,"%s; restart required\n",rc?"FAILED (all renames undone)":"COMPLETE");
 fclose(f);return rc;
}
