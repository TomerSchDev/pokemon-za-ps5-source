/* Keep immutable Hebrew assets in this side application's app0, as the main
 * title already does. Verify source-pack/current/new bytes BEFORE removing any
 * old copied file. Never inspect, restore or write rando/save contents. */
#define main za_unused_seed_entry
#include "seed-side-data.c"
#undef main
#include <stdlib.h>
#include <sys/statvfs.h>
#ifndef SIDE_LINK_TARGET
#define SIDE_LINK_TARGET "/app0/hebrew-choice-mods"
#endif
struct old_file { char path[1400]; struct stat identity; };
int main(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    char meta[4096]={0}; FILE *p=fopen(SIDE_MOUNT "/sce_sys/param.json","rb");
    if(!p)return 2;size_t n=fread(meta,1,sizeof meta-1,p);fclose(p);
    if(n==sizeof meta-1||!strstr(meta,"\"titleId\": \"PPSA91990\""))return 3;
    const char *root=SIDE_DATA "/mods/0-hebrew", *backup=SIDE_DATA "/mods/_before-readonly-hebrew";
    struct stat root_stat;int linked=0, root_exists=lstat(root,&root_stat)==0;
    if(root_exists&&S_ISLNK(root_stat.st_mode)) {
        char link[1400];ssize_t length=readlink(root,link,sizeof link-1);
        if(length<0)return 10;link[length]=0;
        if(strcmp(link,SIDE_LINK_TARGET))return 11;linked=1;
    } else if(root_exists&&!S_ISDIR(root_stat.st_mode))return 12;
    FILE *in=fopen(SIDE_APP "/init-data.bin","rb");if(!in)return 4;
    char magic[8];uint64_t count,total=0;
    if(fread(magic,1,8,in)!=8||memcmp(magic,"ZASIDE01",8)||number(in,4,&count)||!count||count>10000){fclose(in);return 5;}
    struct old_file *old=calloc((size_t)count,sizeof *old);if(!old){fclose(in);return 6;}
    unsigned old_count=0,verified=0,removed=0;int result=7;
    for(uint64_t i=0;i<count;i++) {
        uint64_t length,size;char rel[1024],current[1400],readonly[1400];
        if(number(in,2,&length)||!length||length>=sizeof rel||number(in,8,&size)||size>(256ULL<<20))goto done;
        total+=size;if(total>(2ULL<<30)||fread(rel,1,length,in)!=length)goto done;rel[length]=0;
        if(strlen(rel)!=length||!valid(rel))goto done;
        if(!strncmp(rel,"rando/",6)){if(fseek(in,(long)size,SEEK_CUR))goto done;continue;}
        const char *prefix="mods/0-hebrew/";
        if(strncmp(rel,prefix,strlen(prefix)))goto done;
        if(snprintf(current,sizeof current,SIDE_DATA "/%s",rel)>=(int)sizeof current||
           snprintf(readonly,sizeof readonly,SIDE_APP "/hebrew-choice-mods/%s",rel+strlen(prefix))>=(int)sizeof readonly)goto done;
        int rd=open(readonly,O_RDONLY|O_NOFOLLOW),previous=-1;struct stat original,st;
        if(rd<0||fstat(rd,&st)||!S_ISREG(st.st_mode)||(uint64_t)st.st_size!=size){if(rd>=0)close(rd);goto done;}
        if(!linked) {
            if(dirs(current)){close(rd);goto done;}
            if(!lstat(current,&original)) {
                if(!S_ISREG(original.st_mode)||(uint64_t)original.st_size!=size){close(rd);goto done;}
                previous=open(current,O_RDONLY|O_NOFOLLOW);if(previous<0){close(rd);goto done;}
            } else if(errno!=ENOENT){close(rd);goto done;}
        }
        uint64_t remaining=size;int bad=0;unsigned char prior[65536];
        while(remaining) {
            size_t take=remaining>sizeof block?sizeof block:(size_t)remaining;
            if(fread(block,1,take,in)!=take||read(rd,check,take)!=(ssize_t)take||memcmp(block,check,take)||
               (previous>=0&&(read(previous,prior,take)!=(ssize_t)take||memcmp(block,prior,take)))){bad=1;break;}
            remaining-=take;
        }
        if(!bad&&(read(rd,check,1)!=0||(previous>=0&&read(previous,prior,1)!=0)))bad=1;
        close(rd);if(previous>=0)close(previous);if(bad)goto done;
        if(previous>=0){strcpy(old[old_count].path,current);old[old_count++].identity=original;}
        verified++;
    }
    if(fgetc(in)!=EOF||!verified)goto done;
    /* All immutable copies now match. Old data is also retained in the exact
     * verified app0 pack and app0 assets; remove only matching known copies. */
    for(unsigned i=0;i<old_count;i++) {
        struct stat now;struct stat *before=&old[i].identity;
        if(lstat(old[i].path,&now)||now.st_dev!=before->st_dev||now.st_ino!=before->st_ino||
           now.st_size!=before->st_size||now.st_mtime!=before->st_mtime||!S_ISREG(now.st_mode)||unlink(old[i].path))goto done;
        removed++;
    }
    if(restore_dirs()||writable_dir(SIDE_DATA "/mods",0))goto done;
    if(!linked) {
        struct stat existing;
        if(root_exists&&(!lstat(backup,&existing)||errno!=ENOENT||rename(root,backup)))goto done;
        if(symlink(SIDE_LINK_TARGET,root))goto done;
    }
    result=0;
done:
    if(restore_dirs())result=8;
    free(old);fclose(in);
    struct statvfs volume;unsigned long long available=0;
    if(!statvfs(SIDE_DATA,&volume))available=(unsigned long long)volume.f_bavail*volume.f_frsize;
    if(!result&&available<(128ULL<<20))result=9;
    printf("%s readonly_mods=%u removed_verified_copies=%u available_bytes=%llu; rando/save files untouched\n",
           result?"FAILED":"COMPLETE",verified,removed,available);
    return result;
}
