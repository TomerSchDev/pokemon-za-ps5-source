#ifndef ZA_HEBREW_IO_H
#define ZA_HEBREW_IO_H
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

/* FW13.60 hardware: lstat is EPERM even in our own app/data directories,
 * while stat, O_NOFOLLOW opens and fstat work. Retain no-follow semantics:
 * stat is only a preliminary type check; accept metadata only from an opened
 * no-follow descriptor with the same identity. Missing paths keep stat errno.
 */
static inline int za_hebrew_metadata(const char *path,struct stat *out) {
    if(!lstat(path,out))return 0;
    if(errno!=EPERM&&errno!=ENOSYS)return -1;
    struct stat before{},after{};
    if(stat(path,&before))return -1;
    if(!S_ISREG(before.st_mode)&&!S_ISDIR(before.st_mode)){errno=EINVAL;return -1;}
    int flags=O_RDONLY|O_NOFOLLOW;
    if(S_ISDIR(before.st_mode))flags|=O_DIRECTORY;
    int fd=open(path,flags);if(fd<0)return -1;
    bool ok=!fstat(fd,&after);
    int error=errno;
    if(ok&&(before.st_dev!=after.st_dev||before.st_ino!=after.st_ino||
            (before.st_mode&S_IFMT)!=(after.st_mode&S_IFMT))) {ok=false;error=ESTALE;}
    if(close(fd)){if(ok)error=errno;ok=false;}
    if(!ok){errno=error;return -1;}
    *out=after;errno=0;return 0;
}
#endif
