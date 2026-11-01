/* Scope only this trial's mod; keep all previous saves and mods unchanged. */
#define _DEFAULT_SOURCE 1
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#include "scope_fifty.h"
#define FULL "../../../app0/console-fifty-20261031-r1-models"
#define MODS DATA "/mods"
#define ORIGINAL MODS "/00-console-fifty-20261031-r1"
#define DISABLED MODS "/_00-console-fifty-20261031-r1"
#define SCOPED MODS "/00-console-fifty-scoped-models"
#define REGISTRY MODS "/00-00-console-fifty-batch-metadata"
static int contains(const char*p,const char*t){char s[16384];FILE*f=fopen(p,"rb");if(!f)return 0;size_t n=fread(s,1,sizeof s-1,f);fclose(f);s[n]=0;return strstr(s,t)!=NULL;}
static int target(const char*p,const char*t){char s[1400];ssize_t n=readlink(p,s,sizeof s-1);if(n<0)return 0;s[n]=0;return !strcmp(s,t);}
static int parent(const char*path){char p[1400];if(strlen(path)>=sizeof p)return -1;strcpy(p,path);for(size_t i=strlen(SCOPE);p[i];i++)if(p[i]=='/'){p[i]=0;struct stat s;if(stat(p,&s)){if(errno!=ENOENT||mkdir(p,0777)||chmod(p,0777))return -1;}else if(!S_ISDIR(s.st_mode))return -1;p[i]='/';}return 0;}
int main(void){
 FILE*f=fopen("/data/console-fifty-scope.log","w");if(!f)return 1;setvbuf(f,NULL,_IONBF,0);int rc=2,data_changed=0;struct stat ms,ds,s;
 fprintf(f,"START %s\n",SCOPE);
 if(!contains(DATA "/observer/session.json",SID)||!contains("/data/homebrew/PPSA91762/console-fifty-20261031-r1-models/installation.json",ARCHIVE_SHA)){fprintf(f,"REFUSED session/staging changed\n");goto end;}
 if(stat(MODS,&ms)||stat(DATA,&ds)||chmod(DATA,0777))goto end;data_changed=1;
 if(stat(SCOPE,&s)){if(errno!=ENOENT||mkdir(SCOPE,0777)||chmod(SCOPE,0777)){fprintf(f,"FAILED scope directory errno=%d\n",errno);goto end;}}else if(!S_ISDIR(s.st_mode))goto end;
 for(unsigned i=0;i<N_LINKS;i++){
  if(parent(links[i][0])){fprintf(f,"FAILED parents %s errno=%d\n",links[i][0],errno);goto end;}
  if(lstat(links[i][0],&s)){if(errno!=ENOENT||symlink(links[i][1],links[i][0])){fprintf(f,"FAILED symlink %s errno=%d\n",links[i][0],errno);goto end;}}
  else if(!target(links[i][0],links[i][1])){fprintf(f,"REFUSED different existing link %s\n",links[i][0]);goto end;}
  if(stat(links[i][0],&s)){fprintf(f,"FAILED broken scoped source %s errno=%d\n",links[i][0],errno);goto end;}
  fprintf(f,"LINK %s\n",links[i][0]);
 }
 if(chmod(MODS,0777))goto end;
 if(!lstat(ORIGINAL,&s)){
  if(!target(ORIGINAL,FULL)||!lstat(DISABLED,&s)||errno!=ENOENT||rename(ORIGINAL,DISABLED))goto restore;
 }else if(errno!=ENOENT||!target(DISABLED,FULL))goto restore;
 if(!lstat(SCOPED,&s)){
  if(!target(SCOPED,LINK_TARGET)){
   char old[1400];ssize_t n=readlink(SCOPED,old,sizeof old-1);if(n<0)goto restore;old[n]=0;
   if(strncmp(old,"../console-fifty-scope-b",23))goto restore;
   if(symlink(LINK_TARGET,SCOPED ".pending")||rename(SCOPED ".pending",SCOPED))goto restore;
  }
 }else if(errno!=ENOENT||symlink(LINK_TARGET,SCOPED))goto restore;
 if(!target(SCOPED,LINK_TARGET))goto restore;
 if(!lstat(REGISTRY,&s)){
  if(!target(REGISTRY,REG_TARGET)){
   char old[1400];ssize_t n=readlink(REGISTRY,old,sizeof old-1);if(n<0)goto restore;old[n]=0;
   const char*prefix="../../../app0/console-fifty-registration-b";
   if(strncmp(old,prefix,strlen(prefix)))goto restore;
   if(symlink(REG_TARGET,REGISTRY ".pending")||rename(REGISTRY ".pending",REGISTRY))goto restore;
  }
 }else if(errno!=ENOENT||symlink(REG_TARGET,REGISTRY))goto restore;
 if(!target(REGISTRY,REG_TARGET))goto restore;
 rc=0;
restore:chmod(MODS,ms.st_mode&0777);
end:if(data_changed)chmod(DATA,ds.st_mode&0777);fprintf(f,"%s scope=%s links=%d errno=%d; restart required\n",rc?"FAILED":"COMPLETE",SCOPE,N_LINKS,errno);fclose(f);return rc;
}
