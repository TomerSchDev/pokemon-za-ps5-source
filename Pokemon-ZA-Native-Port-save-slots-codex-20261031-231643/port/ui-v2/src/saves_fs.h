// Read-only run-directory classification. Some PS5 title paths reject lstat
// even when opening the directory succeeds. The fallback never follows the
// final component and is intentionally NOT used to authorize deletion.
#pragma once
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace ui::launcher::saves::fs_detail {
inline bool isDirectoryNoFollow(const char* path) {
    struct stat st {};
    if (!lstat(path, &st)) return S_ISDIR(st.st_mode);
    if (errno != EPERM && errno != ENOSYS && errno != ENOTSUP) return false;
#if defined(O_NOFOLLOW) && defined(O_DIRECTORY)
    const int fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (fd < 0) return false;
    const bool directory = !fstat(fd, &st) && S_ISDIR(st.st_mode);
    const int saved = errno;
    const bool closed = !close(fd);
    errno = saved;
    return directory && closed;
#else
    errno = ENOTSUP;
    return false;
#endif
}
}  // namespace ui::launcher::saves::fs_detail
