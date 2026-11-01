/* Host integration test: the kernel cwd stays untouched while relative and
 * absolute reads/writes, directory streams, and two-path renames agree. */
#define _GNU_SOURCE 1
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
int za_title_fs_set_root(const char *);
char *__real_getcwd(char *, size_t);
int main(void) {
    char kernel_cwd[1024], after[1024], path[1024];
    assert(__real_getcwd(kernel_cwd, sizeof kernel_cwd));
    char temp[] = "/tmp/za-title-fs-XXXXXX";
    assert(mkdtemp(temp));
    assert(za_title_fs_set_root("relative") == -1 && errno == EINVAL);
    assert(za_title_fs_set_root("/path/that/does/not/exist") == -1);
    assert(za_title_fs_set_root(temp) == 0);
    assert(za_title_fs_set_root(temp) == 0);
    assert(za_title_fs_set_root("/tmp") == -1 && errno == EPERM);
    assert(getcwd(path, sizeof path) && !strcmp(path, temp));
    assert(!getcwd(path, 1) && errno == ERANGE);
    assert(!getcwd(path, 0) && errno == EINVAL);
    char *allocated = getcwd(NULL, 0);
    assert(allocated && !strcmp(allocated, temp)); free(allocated);
    assert(mkdir("cache", 0700) == 0);
    FILE *f = fopen("cache/a", "wb"); assert(f);
    assert(fwrite("hello", 1, 5, f) == 5 && fclose(f) == 0);
    snprintf(path, sizeof path, "%s/cache/a", temp);
    int fd = open(path, O_RDONLY); assert(fd >= 0);
    char content[6] = {0}; assert(read(fd, content, 5) == 5); close(fd);
    assert(!strcmp(content, "hello"));
    assert(rename(path, "cache/b") == 0);
    struct stat st; assert(stat("cache/b", &st) == 0 && st.st_size == 5);
    assert(lstat("cache/b", &st) == 0 && S_ISREG(st.st_mode));
    assert(access("cache/b", F_OK) == 0);
    assert(chmod("cache/b", 0600) == 0);
    assert(realpath("cache/../cache/b", path));
    assert(strstr(path, "/cache/b"));
    DIR *d = opendir("cache"); assert(d);
    int found = 0; struct dirent *e;
    while ((e = readdir(d))) if (!strcmp(e->d_name, "b")) found++;
    assert(found == 1 && closedir(d) == 0);
    fd = open("cache/c", O_WRONLY | O_CREAT | O_EXCL, 0600); assert(fd >= 0); close(fd);
    assert(unlink("cache/c") == 0);
    f = fopen("cache/b", "r"); assert(f);
    assert(freopen("cache/c", "w", f) && fclose(f) == 0);
    assert(remove("cache/b") == 0 && remove("cache/c") == 0);
    assert(rmdir("cache") == 0);
    assert(!fopen("", "r") && errno == ENOENT);
    char too_long[1100]; memset(too_long, 'x', sizeof too_long - 1); too_long[1099] = 0;
    assert(!fopen(too_long, "r") && errno == ENAMETOOLONG);
    assert(__real_getcwd(after, sizeof after) && !strcmp(after, kernel_cwd));
    assert(rmdir(temp) == 0);
    puts("title_fs: all path integration checks passed; kernel cwd unchanged");
}
