// Native-probe module: bounded synthetic filesystem observations, no game data.
#include "fs_probe.hpp"
#include <cerrno>
#include <cstdarg>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <initializer_list>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

// Enable optional APIs only after the exact linked SDK stubs are audited.
#ifndef ZA_SAVE_FS_PROBE_TITLE_NUM
#define ZA_SAVE_FS_PROBE_TITLE_NUM 0
#endif
#ifndef ZA_PROBE_HAS_LSTAT
#define ZA_PROBE_HAS_LSTAT 0
#endif
#ifndef ZA_PROBE_HAS_SYMLINK
#define ZA_PROBE_HAS_SYMLINK 0
#endif
#ifndef ZA_PROBE_HAS_READLINK
#define ZA_PROBE_HAS_READLINK 0
#endif
#ifndef ZA_PROBE_HAS_GETDENTS
#define ZA_PROBE_HAS_GETDENTS 0
#endif

namespace za::save_fs_probe {
namespace {
constexpr int Title = ZA_SAVE_FS_PROBE_TITLE_NUM;
char brief[160] = "NOT RUN";
char scratch[640];
int report_fd = -1;
bool first_row = true, report_ok = true;
struct Entry { const char* name; char path[800]; bool made; bool link; };

bool write_all(int fd, const char* data, size_t size) {
    size_t at = 0;
    while (at < size) {
        ssize_t n = write(fd, data + at, size - at);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        at += size_t(n);
    }
    return true;
}
void emit(const char* format, ...) {
    if (!report_ok) return;
    char line[2048];
    va_list args; va_start(args, format);
    const int n = std::vsnprintf(line, sizeof line, format, args);
    va_end(args);
    if (n < 0 || size_t(n) >= sizeof line || !write_all(report_fd, line, size_t(n))) report_ok = false;
}
const char* type_of(mode_t mode) {
    return S_ISREG(mode) ? "regular" : S_ISDIR(mode) ? "directory" : S_ISLNK(mode) ? "symlink" : "other";
}
const char* result_of(long long rc, int error) {
    if (rc >= 0) return "OBSERVED";
    return error == EPERM || error == ENOSYS || error == ENOTSUP ? "UNSUPPORTED_OR_DENIED" : "ERROR";
}
void row(const char* api, const char* entry, long long rc, int error, const struct stat* st = nullptr,
         int flags = 0, int dtype = -1, const char* result = nullptr) {
    emit("%s{\"api\":\"%s\",\"entry\":\"%s\",\"rc\":%lld,\"errno\":%d,\"flags\":%d,"
         "\"mode\":%u,\"type\":\"%s\",\"dev\":%llu,\"ino\":%llu,\"size\":%lld,\"d_type\":%d,\"result\":\"%s\"}\n",
         first_row ? "" : ",", api, entry, rc, error, flags, st ? unsigned(st->st_mode) : 0,
         st ? type_of(st->st_mode) : "unknown", st ? (unsigned long long)st->st_dev : 0,
         st ? (unsigned long long)st->st_ino : 0, st ? (long long)st->st_size : 0,
         dtype, result ? result : result_of(rc, error));
    first_row = false;
}
bool owned_path(const char* path) {
    const size_t n = std::strlen(scratch);
    return n && !std::strncmp(path, scratch, n) && path[n] == '/' && !std::strstr(path, "/../");
}
bool new_file(const char* path, const char* content) {
    if (!owned_path(path)) return false;
    errno = 0;
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0644);
    if (fd < 0) return false;
    const bool written = write_all(fd, content, std::strlen(content));
    const bool closed = !close(fd);
    return written && closed;
}
bool content_is(const char* path, const char* expected) {
    char text[128];
    int fd = open(path, O_RDONLY);
    if (fd < 0) return false;
    const ssize_t n = read(fd, text, sizeof text);
    const bool closed = !close(fd);
    return closed && n == ssize_t(std::strlen(expected)) && !std::memcmp(text, expected, size_t(n));
}
bool side_identity() {
    if (Title < 10000 || Title > 99999 || (Title >= 91760 && Title <= 91763)) return false;
    char expected[16]; std::snprintf(expected, sizeof expected, "PPSA%05d", Title);
    char param[32769];
    int fd = open("/app0/sce_sys/param.json", O_RDONLY);
    if (fd < 0) return false;
    const ssize_t n = read(fd, param, sizeof param - 1);
    const bool closed = !close(fd);
    if (!closed || n < 0 || size_t(n) >= sizeof param - 1) return false;
    param[n] = 0;
    const char* p = std::strstr(param, "\"titleId\"");
    if (!p || !(p = std::strchr(p + 9, ':'))) return false;
    ++p;
    while (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t') ++p;
    return *p++ == '"' && !std::strncmp(p, expected, 9) && p[9] == '"';
}
void inspect(const Entry& entry) {
    if (!entry.made) { row("fixture", entry.name, -1, ENOTSUP, nullptr, 0, -1, "UNSUPPORTED_FIXTURE"); return; }
    struct stat st {};
    errno = 0; int rc = stat(entry.path, &st); int error = errno;
    row("stat", entry.name, rc, error, rc ? nullptr : &st);
#if ZA_PROBE_HAS_LSTAT
    errno = 0; rc = lstat(entry.path, &st); error = errno;
    row("lstat", entry.name, rc, error, rc ? nullptr : &st);
#else
    row("lstat", entry.name, -1, ENOSYS, nullptr, 0, -1, "UNSUPPORTED_IMPORT");
#endif
#if ZA_PROBE_HAS_READLINK
    char target[800];
    errno = 0; ssize_t count = readlink(entry.path, target, sizeof target); error = errno;
    row("readlink", entry.name, count, error);
#else
    row("readlink", entry.name, -1, ENOSYS, nullptr, 0, -1, "UNSUPPORTED_IMPORT");
#endif
#if defined(O_NOFOLLOW) && defined(O_DIRECTORY)
    const int options[] = {O_RDONLY | O_NOFOLLOW, O_RDONLY | O_NOFOLLOW | O_DIRECTORY};
    for (int flags : options) {
        errno = 0; int fd = open(entry.path, flags); error = errno;
        row("open", entry.name, fd, error, nullptr, flags, -1, entry.link && fd >= 0 ? "FOLLOWED_LINK_UNSAFE" : nullptr);
        if (fd >= 0) {
            errno = 0; rc = fstat(fd, &st); error = errno;
            row("fstat", entry.name, rc, error, rc ? nullptr : &st, flags);
            errno = 0; rc = close(fd); row("close", entry.name, rc, errno);
        }
    }
#else
    row("open_nofollow", entry.name, -1, ENOTSUP, nullptr, 0, -1, "UNSUPPORTED_FLAGS");
#endif
}
void directory_types(const char* path) {
#if ZA_PROBE_HAS_GETDENTS
    errno = 0; int fd = open(path, O_RDONLY | O_DIRECTORY); int error = errno;
    row("open_for_getdents", "objects", fd, error);
    if (fd < 0) return;
    alignas(std::max_align_t) char buffer[8192];
    for (int batches = 0; batches < 8; ++batches) {
        errno = 0; const int n = getdents(fd, buffer, sizeof buffer); error = errno;
        row("getdents", "objects", n, error);
        if (n <= 0) break;
        size_t at = 0;
        while (at + offsetof(struct dirent, d_name) < size_t(n)) {
            const auto* e = reinterpret_cast<const struct dirent*>(buffer + at);
            if (e->d_reclen <= offsetof(struct dirent, d_name) || at + e->d_reclen > size_t(n)) {
                row("getdents_record", "objects", -1, EIO, nullptr, 0, -1, "MALFORMED_RECORD"); break;
            }
            // Only log the five fixed names we created, never arbitrary raw strings.
            for (const char* name : {"regular", "directory", "file-link", "directory-link", "dangling-link"})
                if (!std::strncmp(e->d_name, name, e->d_reclen - offsetof(struct dirent, d_name)) &&
                    std::strlen(name) < e->d_reclen - offsetof(struct dirent, d_name))
                    row("getdents_type", name, 0, 0, nullptr, 0, e->d_type);
            at += e->d_reclen;
        }
    }
    errno = 0; int rc = close(fd); row("close_getdents", "objects", rc, errno);
#else
    (void)path;
    row("getdents", "objects", -1, ENOSYS, nullptr, 0, -1, "UNSUPPORTED_IMPORT");
#endif
}
int run_at(const char* parent, bool host) {
    // The side title always uses /download0. The host harness must supply its
    // own pre-created private parent and gets the same exclusive new subtree.
    if (!parent || parent[0] != '/' || std::strstr(parent, "..")) return 2;
    struct timespec t {};
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return 2;
    const int count = std::snprintf(scratch, sizeof scratch, "%s/za-save-fs-probe-%05d-%d-%lld-%ld",
                                    parent, Title, int(getpid()), (long long)t.tv_sec, t.tv_nsec);
    if (count < 0 || size_t(count) >= sizeof scratch || mkdir(scratch, 0755)) return 2;
    char path[800]; std::snprintf(path, sizeof path, "%s/report.json", scratch);
    report_fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0644);
    if (report_fd < 0) return 2;
    first_row = true; report_ok = true;
    emit("{\"schema\":\"za-save-fs-probe-1\",\"title\":\"PPSA%05d\",\"mode\":\"%s\","
         "\"game_access\":false,\"recursive_cleanup\":false,\"rows\":[\n", Title, host ? "host-synthetic" : "native-side-title");
    char objects[800], sentinel[800], sentinel_dir[800], sentinel_guard[900];
    std::snprintf(objects, sizeof objects, "%s/objects", scratch);
    std::snprintf(sentinel, sizeof sentinel, "%s/sentinel.txt", scratch);
    std::snprintf(sentinel_dir, sizeof sentinel_dir, "%s/sentinel-directory", scratch);
    std::snprintf(sentinel_guard, sizeof sentinel_guard, "%s/guard.txt", sentinel_dir);
    const bool sentinel_file = new_file(sentinel, "KEEP SENTINEL FILE");
    errno = 0; int rc = mkdir(sentinel_dir, 0755); row("mkdir", "sentinel-directory", rc, errno);
    const bool sentinel_directory = !rc && new_file(sentinel_guard, "KEEP SENTINEL DIRECTORY");
    errno = 0; rc = mkdir(objects, 0755); row("mkdir", "objects", rc, errno);
    if (rc || !sentinel_file || !sentinel_directory || !report_ok) { close(report_fd); return 2; }
    Entry entries[] = {{"regular", {}, false, false}, {"directory", {}, false, false},
                       {"file-link", {}, false, true}, {"directory-link", {}, false, true}, {"dangling-link", {}, false, true}};
    for (auto& e : entries) {
        std::snprintf(e.path, sizeof e.path, "%s/%s", objects, e.name);
        if (!std::strcmp(e.name, "regular")) { e.made = new_file(e.path, "OWNED TEST FILE"); row("create_file", e.name, e.made ? 0 : -1, e.made ? 0 : errno); }
        else if (!std::strcmp(e.name, "directory")) { errno = 0; rc = mkdir(e.path, 0755); e.made = !rc; row("mkdir", e.name, rc, errno); }
        else {
#if ZA_PROBE_HAS_SYMLINK
            const char* target = !std::strcmp(e.name, "file-link") ? "../sentinel.txt" :
                                 !std::strcmp(e.name, "directory-link") ? "../sentinel-directory" : "../missing-target";
            errno = 0; rc = symlink(target, e.path); e.made = !rc; row("symlink", e.name, rc, errno);
#else
            row("symlink", e.name, -1, ENOSYS, nullptr, 0, -1, "UNSUPPORTED_IMPORT");
#endif
        }
    }
    for (const auto& e : entries) inspect(e);
    directory_types(objects);
    // Fixed explicit paths only. No recursion, no directory contents traversal,
    // and no deletion of a sentinel or a name not created successfully above.
    for (const auto& e : entries) if (e.made && owned_path(e.path) && report_ok) {
        errno = 0;
        rc = !std::strcmp(e.name, "directory") ? rmdir(e.path) : unlink(e.path);
        row(!std::strcmp(e.name, "directory") ? "rmdir" : "unlink", e.name, rc, errno);
    }
    errno = 0; rc = rmdir(objects); row("rmdir", "objects", rc, errno);
    const bool sentinels_ok = content_is(sentinel, "KEEP SENTINEL FILE") && content_is(sentinel_guard, "KEEP SENTINEL DIRECTORY");
    row("sentinels", "outside-objects", sentinels_ok ? 0 : -1, sentinels_ok ? 0 : EIO,
        nullptr, 0, -1, sentinels_ok ? "UNCHANGED" : "CHANGED_UNSAFE");
    emit("],\"sentinels_unchanged\":%s,\"hardware_safety_verdict\":\"NOT_INFERRED_FROM_HOST_OR_SUCCESS_ALONE\"}\n", sentinels_ok ? "true" : "false");
    const bool saved = report_ok && !fsync(report_fd);
    const bool closed = !close(report_fd); report_fd = -1;
    std::snprintf(brief, sizeof brief, "%s - see private report.json", saved && closed && sentinels_ok ? "OBSERVATIONS SAVED" : "PROBE INCOMPLETE");
    return saved && closed && sentinels_ok ? 0 : 1;
}
}  // namespace
int run() noexcept {
    if (!side_identity()) { std::snprintf(brief, sizeof brief, "REFUSED: side-title identity not verified"); return 2; }
    const int rc = run_at("/download0", false);
    if (rc == 2) std::snprintf(brief, sizeof brief, "INCOMPLETE: private scratch/report/fixture setup");
    return rc;
}
const char* summary() noexcept { return brief; }
#ifdef ZA_SAVE_FS_PROBE_HOST_TEST
int run_host(const char* private_parent) noexcept {
    const int rc = run_at(private_parent, true);
    if (rc == 2) std::snprintf(brief, sizeof brief, "INCOMPLETE: private host scratch setup");
    return rc;
}
#endif
}  // namespace za::save_fs_probe

// Existing native-probe renderer callbacks. This overlay intentionally does
// not execute A0's memory/network checks or access its old report/data paths.
namespace za::probe {
void video_result(const char*, int, bool) noexcept {}
void tick() noexcept {}
}
