/* Fixed six-file copy of this user's already-installed game data into a NEW
 * unpublished randomizer staging folder. No arbitrary source/destination input,
 * no links, no overwrite, source and destination SHA-256 verified. */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/mount.h>
#include <unistd.h>
#include <mbedtls/sha256.h>
static const char* source="/data/homebrew/PPSA91761/game";
static const char* target="/data/.za-native-randomizer-r1/PPSA91762/game";
static const struct {const char* name;const char* hash;} files[]={
 {"exefs/main","2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9"},
 {"exefs/sdk","0449487b457490afae879c08d6a90dd28295eaaa5c55677089a46b13991afbab"},
 {"exefs/rtld","714ead44bbd81ccba54509399a5dca59c1a24e068b384292f6755829f1e9d523"},
 {"exefs/main.npdm","9960d4579cb8f8aedfac6e51d8452e31c5acdd0e39308cfc0d4a42955d956058"},
 {"romfs.bin","0ad824b860ebbd8dc512000a5789917241ef047f1ecea223344c3022a2377e90"},
 {"aoc/0100f43008c45002.bin","f3810c027bef4e7e8709ca1f1b5c7e7713ff499900269cd12df8a88064db0d1a"}
};
static unsigned char buffer[1<<20];
static FILE* logf;
static void hex(const unsigned char* b,char* out){for(int i=0;i<32;i++)sprintf(out+i*2,"%02x",b[i]);}
static int digest(const char* path,char* out){
    FILE* f=fopen(path,"rb");if(!f)return -1;
    mbedtls_sha256_context ctx;mbedtls_sha256_init(&ctx);mbedtls_sha256_starts(&ctx,0);
    size_t n;while((n=fread(buffer,1,sizeof buffer,f)))if(mbedtls_sha256_update(&ctx,buffer,n)){fclose(f);mbedtls_sha256_free(&ctx);return -1;}
    int failed=ferror(f);fclose(f);unsigned char bytes[32];mbedtls_sha256_finish(&ctx,bytes);mbedtls_sha256_free(&ctx);hex(bytes,out);return failed?-1:0;
}
static int mkdir_checked(const char* path){struct stat st;if(mkdir(path,0755)&&errno!=EEXIST)return -1;return lstat(path,&st)||!S_ISDIR(st.st_mode)?-1:0;}
int main(void){
    logf=fopen("/data/za-randomizer-copy.log","w");if(!logf)return 1;setvbuf(logf,NULL,_IONBF,0);
    struct stat st;uint64_t total=0;
    for(size_t i=0;i<sizeof files/sizeof files[0];i++){char p[256];snprintf(p,sizeof p,"%s/%s",source,files[i].name);if(lstat(p,&st)||!S_ISREG(st.st_mode)){fprintf(logf,"FAILED source type %s\n",p);return 1;}total+=(uint64_t)st.st_size;}
    struct statfs disk;
    if(statfs("/data",&disk)||((uint64_t)disk.f_bavail*disk.f_bsize)<total+(256u<<20)){fprintf(logf,"FAILED free-space preflight errno=%d required=%llu\n",errno,(unsigned long long)total);return 1;}
    const char* dirs[]={"/data/.za-native-randomizer-r1","/data/.za-native-randomizer-r1/PPSA91762",target,"/data/.za-native-randomizer-r1/PPSA91762/game/exefs","/data/.za-native-randomizer-r1/PPSA91762/game/aoc"};
    for(size_t i=0;i<sizeof dirs/sizeof dirs[0];i++)if(mkdir_checked(dirs[i])){fprintf(logf,"FAILED directory %s\n",dirs[i]);return 1;}
    fprintf(logf,"START bytes=%llu free=%llu\n",(unsigned long long)total,(unsigned long long)((uint64_t)disk.f_bavail*disk.f_bsize));
    for(size_t i=0;i<sizeof files/sizeof files[0];i++){
        char src[256],dst[256],tmp[280],hash[65]={0};
        snprintf(src,sizeof src,"%s/%s",source,files[i].name);snprintf(dst,sizeof dst,"%s/%s",target,files[i].name);snprintf(tmp,sizeof tmp,"%s.copying",dst);
        if(!lstat(dst,&st)) {if(!S_ISREG(st.st_mode)||digest(dst,hash)||strcmp(hash,files[i].hash)){fprintf(logf,"FAILED existing destination %s\n",dst);return 1;}fprintf(logf,"REUSED %s sha256=%s\n",files[i].name,hash);continue;}
        if(errno!=ENOENT)return 1;
        FILE* in=fopen(src,"rb");int fd=open(tmp,O_CREAT|O_EXCL|O_WRONLY,0644);FILE* out=fd>=0?fdopen(fd,"wb"):NULL;
        if(!in||!out){if(in)fclose(in);if(fd>=0)close(fd);fprintf(logf,"FAILED staging %s errno=%d\n",files[i].name,errno);return 1;}
        mbedtls_sha256_context ctx;mbedtls_sha256_init(&ctx);mbedtls_sha256_starts(&ctx,0);
        size_t n;uint64_t count=0,next=256u<<20;int failed=0;
        while((n=fread(buffer,1,sizeof buffer,in))) {
            if(fwrite(buffer,1,n,out)!=n||mbedtls_sha256_update(&ctx,buffer,n)){failed=1;break;}
            count+=n;if(count>=next){fprintf(logf,"PROGRESS %s bytes=%llu\n",files[i].name,(unsigned long long)count);next+=256u<<20;}
        }
        failed|=ferror(in)!=0;if(fclose(in))failed=1;if(fflush(out))failed=1;if(fsync(fileno(out)))failed=1;if(fclose(out))failed=1;
        unsigned char bytes[32];mbedtls_sha256_finish(&ctx,bytes);mbedtls_sha256_free(&ctx);hex(bytes,hash);
        if(failed||strcmp(hash,files[i].hash)||digest(tmp,hash)||strcmp(hash,files[i].hash)||rename(tmp,dst)){fprintf(logf,"FAILED verification %s errno=%d\n",files[i].name,errno);return 1;}
        fprintf(logf,"VERIFIED %s bytes=%llu sha256=%s\n",files[i].name,(unsigned long long)count,hash);
    }
    fprintf(logf,"COMPLETE all six files verified; new title remains unpublished\n");fclose(logf);return 0;
}
