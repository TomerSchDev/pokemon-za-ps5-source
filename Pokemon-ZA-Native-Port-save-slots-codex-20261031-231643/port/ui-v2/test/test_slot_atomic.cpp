// Only synthetic files in a required new root. No real saves are consumed.
#define ZA_SLOT_IMPLEMENTATION
#include "za_slot.h"
#include <cstdarg>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <sys/stat.h>

extern "C" int __real_open(const char*, int, ...);
extern "C" int __real_unlink(const char*);
extern "C" int __real_fsync(int);
static std::string raceTemp, raceTarget, denyUnlink;
static bool denySync;
static int opens, checks, failures;
#define CHECK(x) do { ++checks; if (!(x)) { ++failures; std::fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); } } while (0)
extern "C" int __wrap_open(const char* path, int flags, ...) {
    ++opens;
    if ((flags & O_CREAT) && !(flags & O_EXCL)) std::abort();
    if (raceTemp == path) {
        if (symlink(raceTarget.c_str(), path)) std::abort();
        raceTemp.clear();
    }
    return __real_open(path, flags, 0644);
}
extern "C" int __wrap_unlink(const char* path) {
    if (denyUnlink == path) { errno = EPERM; return -1; }
    return __real_unlink(path);
}
extern "C" int __wrap_fsync(int fd) {
    if (denySync) { errno = EIO; return -1; }
    return __real_fsync(fd);
}
static std::string read(const std::string& p) {
    std::ifstream f(p, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(f), {});
}
static void write(const std::string& p, const char* s) { std::ofstream(p, std::ios::binary) << s; }
static int atomic(const std::string& p, const char* s) {
    return za_slot_write_atomic(p.c_str(), reinterpret_cast<const uint8_t*>(s), std::strlen(s));
}
int main(int argc, char** argv) {
    if (argc != 2 || mkdir(argv[1], 0700)) return 2;
    const std::string root = argv[1], slot = root + "/slot.zrs", temp = slot + ".new", outside = root + "/outside";
    write(outside, "keep outside");
    CHECK(!atomic(slot, "v0") && read(slot) == "v0");
    write(temp, "partial stale");
    CHECK(!atomic(slot, "v1") && read(slot) == "v1");
    CHECK(!symlink(outside.c_str(), temp.c_str()));
    CHECK(!atomic(slot, "v2") && read(slot) == "v2" && read(outside) == "keep outside");
    const std::string missing = root + "/missing-target";
    CHECK(!symlink(missing.c_str(), temp.c_str()));
    CHECK(!atomic(slot, "v3") && read(slot) == "v3");
    struct stat st {};
    CHECK(stat(missing.c_str(), &st) && errno == ENOENT);
    raceTemp = temp; raceTarget = outside;
    CHECK(atomic(slot, "must not replace") == -1);
    CHECK(read(slot) == "v3" && read(outside) == "keep outside");
    CHECK(!__real_unlink(temp.c_str()));
    denyUnlink = temp;
    const int before = opens;
    CHECK(atomic(slot, "must not open") == -1 && opens == before && read(slot) == "v3");
    denyUnlink.clear();
    denySync = true;
    CHECK(atomic(slot, "must not publish") == -1 && read(slot) == "v3");
    denySync = false;
    CHECK(lstat(temp.c_str(), &st) && errno == ENOENT);
    CHECK(read(outside) == "keep outside");
    std::printf("%s: slot atomic writer (%d synthetic checks)\n", failures ? "FAIL" : "PASS", checks);
    return failures ? 1 : 0;
}
