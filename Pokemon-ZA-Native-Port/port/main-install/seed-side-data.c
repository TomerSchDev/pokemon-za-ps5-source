/* Initialize a NEW, explicitly isolated test title from its verified application
 * pack. Never reads or writes another title, and never replaces differing data.
 * Pack: ZASIDE01, u32 count, repeated u16 path length, u64 size, path, bytes (LE).
 * Every new file is read back against the exact source bytes before proceeding.
 */
#define _DEFAULT_SOURCE 1
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#ifndef SIDE_APP
#define SIDE_APP "/data/homebrew/PPSA91990"
#endif
#ifndef SIDE_DATA
#define SIDE_DATA "/mnt/sandbox/PPSA91990_000/download0/zarecomp"
#endif
#ifndef SIDE_MOUNT
#define SIDE_MOUNT "/mnt/sandbox/PPSA91990_000/app0"
#endif
static unsigned char block[65536], check[65536];
static struct { char path[1400]; mode_t mode; } permissions[256];
static unsigned permission_count;
static int writable_dir(const char *path,int create) {
    struct stat s;
    if(lstat(path,&s)) {
        if(!create||errno!=ENOENT||mkdir(path,0777)||chmod(path,0777))return -1;
        return 0;
    }
    if(!S_ISDIR(s.st_mode))return -1;
    if((s.st_mode&0777)==0777)return 0;
    if(permission_count>=256||strlen(path)>=sizeof permissions[0].path)return -1;
    strcpy(permissions[permission_count].path,path);
    permissions[permission_count++].mode=s.st_mode&0777;
    return chmod(path,0777);
}
static int restore_dirs(void) {
    int bad=0;
    while(permission_count) { permission_count--;if(chmod(permissions[permission_count].path,permissions[permission_count].mode))bad=1; }
    return bad;
}
static int number(FILE *f, unsigned n, uint64_t *v) {
    *v = 0;
    for (unsigned i=0; i<n; i++) { int c=fgetc(f); if(c==EOF)return -1; *v|=(uint64_t)c<<(8*i); }
    return 0;
}
static int dirs(const char *path) {
    char p[1400]; if(strlen(path)>=sizeof p)return -1; strcpy(p,path);
    for(size_t i=strlen(SIDE_DATA);p[i];i++) if(p[i]=='/') {
        p[i]=0;
        if(writable_dir(p,1))return -1;
        p[i]='/';
    }
    return 0;
}
static int valid(const char *p) {
    if(strncmp(p,"mods/",5)&&strncmp(p,"rando/",6))return 0;
    if(strstr(p,"..")||strchr(p,'\\')||strchr(p,':')||strstr(p,"//"))return 0;
    for(const unsigned char *q=(const unsigned char*)p;*q;q++)if(*q<32||*q>=127)return 0;
    return p[strlen(p)-1]!='/';
}
int main(void) {
    char meta[4096]={0}; FILE *p=fopen(SIDE_MOUNT "/sce_sys/param.json","rb");
    if(!p)return 2; size_t n=fread(meta,1,sizeof meta-1,p); fclose(p);
    if(n==sizeof meta-1||!strstr(meta,"\"titleId\": \"PPSA91990\""))return 3;
    FILE *in=fopen(SIDE_APP "/init-data.bin","rb"); if(!in)return 4;
    char magic[8]; uint64_t count, total=0;
    if(fread(magic,1,8,in)!=8||memcmp(magic,"ZASIDE01",8)||number(in,4,&count)||count>10000){fclose(in);return 5;}
    if(writable_dir(SIDE_DATA,0)){restore_dirs();fclose(in);return 6;}
    FILE *log=fopen(SIDE_DATA "/side-seed.log","a"); if(!log){restore_dirs();fclose(in);return 6;}
    int result=7; unsigned completed=0;
    for(uint64_t i=0;i<count;i++) {
        uint64_t len,size; char rel[1024],dst[1400];
        if(number(in,2,&len)||!len||len>=sizeof rel||number(in,8,&size)||size>(256ULL<<20))goto done;
        total+=size; if(total>(2ULL<<30))goto done;
        if(fread(rel,1,len,in)!=len)goto done; rel[len]=0;
        if(strlen(rel)!=len||!valid(rel)||snprintf(dst,sizeof dst,SIDE_DATA "/%s",rel)>=(int)sizeof dst||dirs(dst))goto done;
        long start=ftell(in); if(start<0)goto done;
        struct stat s; int exists=lstat(dst,&s)==0;
        if(exists&&!S_ISREG(s.st_mode))goto done;
        if(!exists&&errno!=ENOENT)goto done;
        if(!exists) {
            int fd=open(dst,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0666); if(fd<0)goto done;
            uint64_t remain=size; int bad=0;
            while(remain) { size_t take=remain>sizeof block?sizeof block:(size_t)remain;
                if(fread(block,1,take,in)!=take||write(fd,block,take)!=(ssize_t)take){bad=1;break;} remain-=take;
            }
            if(fsync(fd))bad=1; if(close(fd))bad=1; if(chmod(dst,0666))bad=1; if(bad)goto done;
        }
        if(fseek(in,start,SEEK_SET))goto done;
        int rd=open(dst,O_RDONLY|O_NOFOLLOW); if(rd<0)goto done;
        uint64_t remain=size; int bad=0;
        while(remain) { size_t take=remain>sizeof block?sizeof block:(size_t)remain;
            if(fread(block,1,take,in)!=take||read(rd,check,take)!=(ssize_t)take||memcmp(block,check,take)){bad=1;break;} remain-=take;
        }
        if(!bad&&read(rd,check,1)!=0)bad=1; close(rd); if(bad)goto done;
        fprintf(log,"VERIFIED %s %llu\n",rel,(unsigned long long)size); fflush(log); completed++;
    }
    if(fgetc(in)!=EOF)goto done;
    result=0;
done:
    if(restore_dirs())result=8;
    fprintf(log,"%s %u/%llu; differing existing files never overwritten\n",result?"FAILED":"COMPLETE",completed,(unsigned long long)count);
    fflush(log); fsync(fileno(log)); fclose(log); fclose(in); return result;
}
