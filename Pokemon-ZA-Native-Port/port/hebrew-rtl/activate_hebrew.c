/* Link mods/hebrew to the verified app0 copy of the Hebrew package (the Rowlet / console-fifty pattern).
 * Runs as a payload while PPSA91762 is mounted at its menu. Never touches saves, runs or other mods.
 * Refuses when the old Hebrew Trial is ON (its visual-order files would shadow the logical text). */
#define _DEFAULT_SOURCE 1
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#ifndef PACKAGE_DIR
#error "PACKAGE_DIR (app0 folder name) and PACKAGE_SHA (its manifest digest) are required"
#endif
#define APP "/data/homebrew/PPSA91762"
#define DATA "/mnt/sandbox/PPSA91762_000/download0/zarecomp"
#define MODS DATA "/mods"
#define LINK MODS "/hebrew"
#define LINK_TARGET "../../../app0/" PACKAGE_DIR "/hebrew"
#define LOG "/data/hebrew-rtl-activate.log"
extern int getdents(int,char*,int);
static int contains(const char*path,const char*text){char s[16384];FILE*f=fopen(path,"rb");if(!f)return 0;size_t n=fread(s,1,sizeof s-1,f);fclose(f);s[n]=0;return strstr(s,text)!=NULL;}
int main(void){
 FILE*f=fopen(LOG,"w");if(!f)return 1;setvbuf(f,NULL,_IONBF,0);
 fprintf(f,"START hebrew mods link; saves, runs, executable and other mods untouched\n");
 struct stat ms,s;int rc=2,linked=0;
 if(!contains(APP "/" PACKAGE_DIR "/installation.json",PACKAGE_SHA)){fprintf(f,"REFUSED package not verified on app0\n");goto end;}
 if(stat(MODS,&ms)){fprintf(f,"FAILED mods stat errno=%d\n",errno);goto end;}
 /* A payload cannot read the mods folder until it is opened up (console-fifty pattern); restored at the end. */
 if(chmod(MODS,0777)){fprintf(f,"FAILED mods chmod errno=%d\n",errno);goto end;}
 if(!lstat(MODS "/000-hebrew-trial",&s)){fprintf(f,"REFUSED Hebrew Trial is ON; set HEBREW TRIAL OFF first\n");goto restore;}
 /* The listing is evidence only; the link needs search + write on the folder, not read (open gave EACCES on PS5). */
 int fd=open(MODS,O_RDONLY|O_DIRECTORY);char buf[16384];int n=0;
 if(fd<0)fprintf(f,"NOTE mods listing unavailable errno=%d; other mods are not touched\n",errno);
 else while((n=getdents(fd,buf,sizeof buf))>0){for(int p=0;p<n;){struct dirent*e=(struct dirent*)(buf+p);if(!e->d_reclen)break;
  if(strcmp(e->d_name,".")&&strcmp(e->d_name,"..")){char path[1400],target[1400];snprintf(path,sizeof path,MODS "/%s",e->d_name);
   ssize_t k=readlink(path,target,sizeof target-1);if(k>=0)target[k]=0;else strcpy(target,"(directory or regular file)");
   fprintf(f,"PRESERVED_MOD %s -> %s\n",e->d_name,target);}
  p+=e->d_reclen;}}
 if(fd>=0)close(fd);
 if(!lstat(LINK,&s)){char target[1400];ssize_t k=readlink(LINK,target,sizeof target-1);
  if(k>=0){target[k]=0;if(!strcmp(target,LINK_TARGET)){fprintf(f,"ALREADY linked %s\n",target);rc=0;goto restore;}}
  fprintf(f,"REFUSED existing mods/hebrew (%s); inspect before replacing\n",k>=0?target:"not a link");goto restore;}
 if(errno!=ENOENT){fprintf(f,"FAILED link lstat errno=%d\n",errno);goto restore;}
 if(symlink(LINK_TARGET,LINK)){fprintf(f,"FAILED symlink errno=%d\n",errno);goto restore;}linked=1;
 if(stat(LINK "/romfs/ik_message/dat/English/common/main_menu.dat",&s)||stat(LINK "/romfs/ui/font/bin/FOT-UDKakugoC80Pro-DB.bfotf",&s)){
  fprintf(f,"FAILED link does not resolve errno=%d\n",errno);goto restore;}
 rc=0;
restore:
 if(rc&&linked)unlink(LINK);
 chmod(MODS,ms.st_mode&0777);
end:
 fprintf(f,"%s link=%s -> %s; restart required\n",rc?"FAILED":"COMPLETE",LINK,LINK_TARGET);
 fclose(f);return rc;
}
