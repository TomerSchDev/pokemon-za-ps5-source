/* Scoped additive trial activation. Never overwrites an existing run or mod. */
#define _DEFAULT_SOURCE 1
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#include "console_fifty_activation.h"
extern int getdents(int,char*,int);
#define APP "/data/homebrew/PPSA91762"
#define RANDO DATA "/rando"
#define MODS DATA "/mods"
#define MODEL_LINK MODS "/00-console-fifty-20261031-r1"
#define TRIAL_LINK MODS "/00-0-console-fifty-20261031-r1"
#define SETUP APP "/console-fifty-20261031-r1-trial-setup"
#define MODEL_TARGET "../../../app0/console-fifty-20261031-r1-models"
#define TRIAL_TARGET "../../../app0/console-fifty-20261031-r1-trial-setup"
#define STAGE RANDO "/.pending-fifty-" RUN_ID
#define FINAL RANDO "/" RUN_ID
static unsigned char a[262144],b[262144];
static int equal(const char*x,const char*y){
 FILE*p=fopen(x,"rb"),*q=fopen(y,"rb");if(!p||!q){if(p)fclose(p);if(q)fclose(q);return 0;}
 int good=1;for(;;){size_t n=fread(a,1,sizeof a,p),m=fread(b,1,sizeof b,q);if(n!=m||memcmp(a,b,n)){good=0;break;}if(n<sizeof a){if(ferror(p)||ferror(q))good=0;break;}}
 fclose(p);fclose(q);return good;
}
static int contains(const char*path,const char*text){char s[16384];FILE*f=fopen(path,"rb");if(!f)return 0;size_t n=fread(s,1,sizeof s-1,f);fclose(f);s[n]=0;return strstr(s,text)!=NULL;}
static int copy_new(const char*src,const char*dst){
 FILE*in=fopen(src,"rb");if(!in)return -1;int fd=open(dst,O_CREAT|O_EXCL|O_WRONLY,0666);if(fd<0){fclose(in);return -1;}
 FILE*out=fdopen(fd,"wb");if(!out){close(fd);fclose(in);return -1;}int bad=0;size_t n;
 while((n=fread(a,1,sizeof a,in)))if(fwrite(a,1,n,out)!=n){bad=1;break;}
 bad|=ferror(in);fclose(in);if(fflush(out)||fsync(fd)||fclose(out)||chmod(dst,0666))bad=1;
 return bad||!equal(src,dst)?-1:0;
}
static int parents(const char*path){char p[1400];if(strlen(path)>=sizeof p)return -1;strcpy(p,path);
 for(size_t i=strlen(STAGE)+1;p[i];i++)if(p[i]=='/'){char c=p[i];p[i]=0;struct stat s;if(stat(p,&s)){if(errno!=ENOENT||mkdir(p,0777)||chmod(p,0777))return -1;}else if(!S_ISDIR(s.st_mode))return -1;p[i]=c;}return 0;
}
int main(void){
 FILE*f=fopen("/data/console-fifty-20261031-r1-activate.log","w");if(!f)return 1;setvbuf(f,NULL,_IONBF,0);
 fprintf(f,"START additive test run, models and native-encounter overlay; original saves and executable untouched\n");
 struct stat ms,rs,s;int rc=2,model_linked=0,trial_linked=0,published=0;
 if(!contains(DATA "/observer/session.json",SESSION_ID)||!contains(RANDO "/active.json",PREVIOUS_RUN)){fprintf(f,"REFUSED session/active-run changed\n");goto end;}
 if(!contains(APP "/console-fifty-20261031-r1-models/installation.json",MODEL_ARCHIVE_SHA)||!contains(SETUP "/setup-ready.json",RUN_ID)){fprintf(f,"REFUSED incomplete or wrong staging\n");goto end;}
 if(stat(MODS,&ms)||stat(RANDO,&rs)){fprintf(f,"FAILED directory stat\n");goto end;}
 if(chmod(MODS,0777)||chmod(RANDO,0777))goto restore;
 if(!lstat(MODEL_LINK,&s)||errno!=ENOENT||!lstat(TRIAL_LINK,&s)||errno!=ENOENT||!stat(FINAL,&s)||errno!=ENOENT){fprintf(f,"REFUSED existing trial or mod identity\n");goto restore;}
 int fd=open(MODS,O_RDONLY|O_DIRECTORY);if(fd<0)goto restore;char buf[16384];int n;
 while((n=getdents(fd,buf,sizeof buf))>0){for(int p=0;p<n;){struct dirent*e=(struct dirent*)(buf+p);if(!e->d_reclen){close(fd);goto restore;}if(strcmp(e->d_name,".")&&strcmp(e->d_name,"..")){char path[1400],target[1400];snprintf(path,sizeof path,MODS "/%s",e->d_name);ssize_t k=readlink(path,target,sizeof target-1);if(k>=0)target[k]=0;else strcpy(target,"(directory or regular file)");fprintf(f,"PRESERVED_MOD %s -> %s\n",e->d_name,target);}p+=e->d_reclen;}}
 close(fd);if(n<0)goto restore;
 if(mkdir(STAGE,0777)||chmod(STAGE,0777))goto restore;
 for(unsigned i=0;i<RUN_FILES;i++){char src[1400],dst[1400];snprintf(src,sizeof src,SETUP "/run/%s",run_files[i]);snprintf(dst,sizeof dst,STAGE "/%s",run_files[i]);if(parents(dst)||copy_new(src,dst)){fprintf(f,"FAILED run copy %s errno=%d\n",run_files[i],errno);goto restore;}fprintf(f,"COPIED %s\n",run_files[i]);}
 if(symlink(MODEL_TARGET,MODEL_LINK))goto restore;model_linked=1;
 if(symlink(TRIAL_TARGET,TRIAL_LINK))goto restore;trial_linked=1;
 if(stat(MODEL_LINK "/installation.json",&s)||stat(TRIAL_LINK "/setup-ready.json",&s))goto restore;
 if(rename(STAGE,FINAL))goto restore;published=1;
 if(!contains(RANDO "/active.json",PREVIOUS_RUN)||copy_new(RANDO "/active.json",RANDO "/active.before-console-fifty-20261031-r1.json")||copy_new(SETUP "/active-target.json",RANDO "/active.console-fifty-20261031-r1.new"))goto restore;
 if(rename(RANDO "/active.console-fifty-20261031-r1.new",RANDO "/active.json")||!equal(SETUP "/active-target.json",RANDO "/active.json"))goto restore;
 rc=0;
restore:
 if(rc){if(model_linked)unlink(MODEL_LINK);if(trial_linked)unlink(TRIAL_LINK);if(published)rename(FINAL,STAGE);}
 chmod(MODS,ms.st_mode&0777);chmod(RANDO,rs.st_mode&0777);
 fprintf(f,"%s run=%s; all prior mod links retained; restart required\n",rc?"FAILED":"COMPLETE",RUN_ID);
end:fclose(f);return rc;
}
