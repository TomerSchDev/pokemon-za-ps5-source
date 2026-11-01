/* ui-v2 PC proof: the Windows side of pc_compat.h. */
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <direct.h>
#include <errno.h>
#include <io.h>
#include <stdio.h>

int za_pc_rename(const char *from, const char *to) {
    if (MoveFileExA(from, to, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) return 0;
    errno = GetLastError() == ERROR_FILE_NOT_FOUND ? ENOENT : EACCES;
    return -1;
}
int za_pc_mkdir(const char *path) { return _mkdir(path); }
int za_pc_fsync(int fd) { return _commit(fd); }
#endif
