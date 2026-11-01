// Synthetic-only regression: unsupported lstat must not hide genuine runs,
// follow run symlinks, or accept a directory swapped for a link before open.
#include "saves_fs.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

extern "C" int __real_lstat(const char*, struct stat*);
extern "C" int __real_open(const char*, int, ...);
static bool denyLstat;
static std::string swapPath, swapTarget;
static int fallbackOpens;
static int checks, failures;
#define CHECK(x) do { ++checks; if (!(x)) { ++failures; std::fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); } } while (0)

extern "C" int __wrap_lstat(const char* path, struct stat* st) {
    if (denyLstat) { errno = EPERM; return -1; }
    return __real_lstat(path, st);
}
extern "C" int __wrap_open(const char* path, int flags, ...) {
    ++fallbackOpens;
    if (!(flags & O_NOFOLLOW) || !(flags & O_DIRECTORY)) std::abort();
    if (swapPath == path) {
        if (rmdir(path) || symlink(swapTarget.c_str(), path)) std::abort();
        swapPath.clear();
    }
    return __real_open(path, flags);
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const std::string root = argv[1];
    if (mkdir(root.c_str(), 0700)) return 2;  // must be new; never consume existing data
    const std::string run = root + "/run", outside = root + "/outside", link = root + "/link";
    CHECK(!mkdir(run.c_str(), 0700));
    CHECK(!mkdir(outside.c_str(), 0700));
    CHECK(!symlink(outside.c_str(), link.c_str()));
    using ui::launcher::saves::fs_detail::isDirectoryNoFollow;
    CHECK(isDirectoryNoFollow(run.c_str()));
    CHECK(!isDirectoryNoFollow(link.c_str()));
    CHECK(fallbackOpens == 0);
    denyLstat = true;
    CHECK(isDirectoryNoFollow(run.c_str()));
    CHECK(!isDirectoryNoFollow(link.c_str()));
    CHECK(!isDirectoryNoFollow((root + "/missing").c_str()));
    const std::string file = root + "/file";
    FILE* f = std::fopen(file.c_str(), "wb");
    CHECK(f && std::fputs("keep", f) >= 0 && !std::fclose(f));
    CHECK(!isDirectoryNoFollow(file.c_str()));
    // The type changes AFTER lstat failed and immediately BEFORE the actual
    // fallback open. O_NOFOLLOW must reject the replacement, not inspect its target.
    swapPath = run; swapTarget = outside;
    CHECK(!isDirectoryNoFollow(run.c_str()));
    struct stat st {};
    CHECK(!stat(outside.c_str(), &st) && S_ISDIR(st.st_mode));
    CHECK(fallbackOpens == 5);
    std::printf("%s: save directory no-follow (%d synthetic checks)\n", failures ? "FAIL" : "PASS", checks);
    return failures ? 1 : 0;
}
