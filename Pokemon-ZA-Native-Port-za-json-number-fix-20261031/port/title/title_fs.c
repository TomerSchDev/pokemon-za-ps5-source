/* A native title cannot chdir (FW13.60: EPERM). Resolve relative file names
 * against one immutable data root before calling the real file APIs instead.
 * Link with --wrap for the entry points below; the SDK's *at implementations
 * eventually use these APIs too. No system permissions are changed. */
#define _GNU_SOURCE 1
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define PATH_BYTES 1024
static char data_root[PATH_BYTES] = "/app0";
static bool root_set;

static const char *absolute(const char *path, char out[PATH_BYTES]) {
    if (!path) { errno = EFAULT; return NULL; }
    if (!*path) { errno = ENOENT; return NULL; }
    if (path[0] == '/') return path;
    const int n = snprintf(out, PATH_BYTES, "%s/%s", data_root, path);
    if (n < 0 || n >= PATH_BYTES) { errno = ENAMETOOLONG; return NULL; }
    return out;
}

extern int __real_stat(const char *, struct stat *);
/* Called once on the main thread, before worker threads begin doing file I/O.
 * Validate the directory first: failure must not redirect subsequent writes. */
int za_title_fs_set_root(const char *path) {
    struct stat st;
    if (!path || path[0] != '/') { errno = EINVAL; return -1; }
    if (strlen(path) >= sizeof data_root) { errno = ENAMETOOLONG; return -1; }
    if (root_set) {
        if (!strcmp(path, data_root)) return 0;
        errno = EPERM; return -1;
    }
    if (__real_stat(path, &st)) return -1;
    if (!S_ISDIR(st.st_mode)) { errno = ENOTDIR; return -1; }
    strcpy(data_root, path);
    root_set = true;
    return 0;
}

char *__wrap_getcwd(char *buffer, size_t size) {
    const size_t needed = strlen(data_root) + 1;
    if (buffer && !size) { errno = EINVAL; return NULL; }
    if (size && size < needed) { errno = ERANGE; return NULL; }
    if (!buffer) {
        buffer = malloc(size ? size : needed);
        if (!buffer) return NULL;
    }
    memcpy(buffer, data_root, needed);
    return buffer;
}

extern FILE *__real_fopen(const char *, const char *);
FILE *__wrap_fopen(const char *path, const char *mode) {
    char full[PATH_BYTES]; const char *p = absolute(path, full);
    return p ? __real_fopen(p, mode) : NULL;
}
extern FILE *__real_freopen(const char *, const char *, FILE *);
FILE *__wrap_freopen(const char *path, const char *mode, FILE *stream) {
    if (!path) return __real_freopen(NULL, mode, stream);
    char full[PATH_BYTES]; const char *p = absolute(path, full);
    return p ? __real_freopen(p, mode, stream) : NULL;
}
extern int __real_open(const char *, int, ...);
int __wrap_open(const char *path, int flags, ...) {
    int mode = 0;
    if (flags & O_CREAT) {
        va_list ap; va_start(ap, flags); mode = va_arg(ap, int); va_end(ap);
    }
    char full[PATH_BYTES]; const char *p = absolute(path, full);
    return p ? __real_open(p, flags, mode) : -1;
}
extern DIR *__real_opendir(const char *);
DIR *__wrap_opendir(const char *path) {
    char full[PATH_BYTES]; const char *p = absolute(path, full);
    return p ? __real_opendir(p) : NULL;
}
extern char *__real_realpath(const char *, char *);
char *__wrap_realpath(const char *path, char *resolved) {
    char full[PATH_BYTES]; const char *p = absolute(path, full);
    return p ? __real_realpath(p, resolved) : NULL;
}

#define ONE_PATH(name) \
    extern int __real_##name(const char *); \
    int __wrap_##name(const char *path) { \
        char full[PATH_BYTES]; const char *p = absolute(path, full); \
        return p ? __real_##name(p) : -1; \
    }
ONE_PATH(unlink)
ONE_PATH(remove)
ONE_PATH(rmdir)

#define PATH_ARG(name, type) \
    extern int __real_##name(const char *, type); \
    int __wrap_##name(const char *path, type arg) { \
        char full[PATH_BYTES]; const char *p = absolute(path, full); \
        return p ? __real_##name(p, arg) : -1; \
    }
PATH_ARG(stat, struct stat *)
PATH_ARG(lstat, struct stat *)
PATH_ARG(mkdir, mode_t)
PATH_ARG(chmod, mode_t)
PATH_ARG(access, int)

extern int __real_rename(const char *, const char *);
int __wrap_rename(const char *from, const char *to) {
    char full_from[PATH_BYTES], full_to[PATH_BYTES];
    const char *a = absolute(from, full_from);
    if (!a) return -1;
    const char *b = absolute(to, full_to);
    return b ? __real_rename(a, b) : -1;
}
