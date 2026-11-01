// SPDX-License-Identifier: GPL-3.0-or-later
// Bounded native-host capability checks. No game data and no Wine dependencies.
#include "probe.hpp"

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

// Public libkernel ABI, cross-checked against prospero-win's PS5 memory backend.
// Only these native APIs are used; no Wine code or runtime is linked.
extern "C" {
int sceKernelReserveVirtualRange(void **address, size_t bytes, int flags, size_t alignment);
int sceKernelAllocateMainDirectMemory(size_t bytes, size_t alignment, int type, int64_t *offset);
int sceKernelMapDirectMemory(void **address, size_t bytes, int protection, int flags,
                            int64_t offset, size_t alignment);
int sceKernelMprotect(const void *address, size_t bytes, int protection);
int sceKernelMunmap(void *address, size_t bytes);
int sceKernelReleaseDirectMemory(int64_t offset, size_t bytes);
}

namespace za::probe {
namespace {
constexpr char build_id[] = "za-native-probe-a0-20261026-r2";
// Keep a relocatable read-only manifest: the native title converter requires
// .data.rel.ro to begin its RELRO segment, even in this minimal program.
__attribute__((used, section(".data.rel.ro")))
const char *const build_manifest[] = {build_id, "PS5 native capability probe; no game content"};
constexpr char report_path[] = "/download0/za-native-probe.json";
constexpr unsigned short status_port = 18760;
constexpr std::uintptr_t guest_lo = UINT64_C(0x7000000000);
constexpr std::uintptr_t guest_hi = UINT64_C(0x7800000000);
constexpr std::size_t page_size = 0x4000;
int listener = -1;
int network_error = 0;
int storage_error = 0;
int asset_ok = 0;
int full_range_ok = 0;
int full_range_error = 0;
int code_page_ok = 0;
int heap_page_ok = 0;
int native_reserve_rc = -1;
int native_alloc_rc = -1;
int native_map_rc = -1;
int native_protect_rc = -1;
int native_cleanup_rc = -1;
bool native_exact = false;
bool native_rw = false;
int video_rc = 0;
bool video_ready = false;
const char *video_stage = "not_started";
unsigned long long boot_ns = 0;
unsigned long long heartbeat = 0;
char report[2400]{};

unsigned long long now_ns() noexcept {
    struct timespec time{};
    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0) return 0;
    return static_cast<unsigned long long>(time.tv_sec) * 1000000000ULL + time.tv_nsec;
}

std::size_t format_report() noexcept {
    const int n = snprintf(report, sizeof report,
        "{\"build\":\"%s\",\"pid\":%d,\"boot_monotonic_ns\":%llu,"
        "\"uptime_ms\":%llu,\"heartbeat\":%llu,\"port\":%u,"
        "\"network_errno\":%d,\"storage_errno\":%d,\"asset_read_ok\":%s,"
        "\"guest_lo\":\"0x7000000000\",\"guest_hi\":\"0x7800000000\","
        "\"reserve_32g_exact_ok\":%s,\"reserve_errno\":%d,"
        "\"main_page_rw_ok\":%s,\"heap_page_rw_ok\":%s,"
        "\"native_reserve_rc\":%d,\"native_reserve_exact\":%s,"
        "\"native_alloc_rc\":%d,\"native_map_rc\":%d,\"native_rw_ok\":%s,"
        "\"native_protect_rc\":%d,\"native_cleanup_rc\":%d,"
        "\"video_stage\":\"%s\",\"video_rc\":%d,\"video_api_ready\":%s,"
        "\"visual_verified\":false,\"vulkan_tested\":false,"
        "\"controller_tested\":false,\"audio_tested\":false,"
        "\"game_code_executed\":false,\"wine_used\":false}\n",
        build_id, getpid(), boot_ns, (now_ns() - boot_ns) / 1000000ULL, heartbeat,
        status_port, network_error, storage_error, asset_ok ? "true" : "false",
        full_range_ok ? "true" : "false", full_range_error,
        code_page_ok ? "true" : "false", heap_page_ok ? "true" : "false",
        native_reserve_rc, native_exact ? "true" : "false", native_alloc_rc,
        native_map_rc, native_rw ? "true" : "false", native_protect_rc, native_cleanup_rc,
        video_stage, video_rc, video_ready ? "true" : "false");
    return n > 0 && static_cast<std::size_t>(n) < sizeof report ? static_cast<std::size_t>(n) : 0;
}

void persist() noexcept {
    const std::size_t count = format_report();
    int fd = open(report_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) { storage_error = errno; return; }
    fchmod(fd, 0644); // Readable by the console's existing FTP diagnostic service.
    std::size_t done = 0;
    while (done < count) {
        const ssize_t n = write(fd, report + done, count - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { storage_error = n < 0 ? errno : EIO; break; }
        done += static_cast<std::size_t>(n);
    }
    if (done == count) storage_error = 0;
    close(fd);
}

int test_page(std::uintptr_t address) noexcept {
    void *wanted = reinterpret_cast<void *>(address);
    // Hint only: never replace an existing process mapping with MAP_FIXED.
    void *mapped = mmap(wanted, page_size, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mapped == MAP_FAILED) return 0;
    int ok = 0;
    if (mapped == wanted) {
        auto *words = static_cast<volatile std::uint64_t *>(mapped);
        words[0] = UINT64_C(0x5a415053354e4154);
        words[page_size / sizeof(*words) - 1] = UINT64_C(0x0102030405060708);
        ok = words[0] == UINT64_C(0x5a415053354e4154) &&
             words[page_size / sizeof(*words) - 1] == UINT64_C(0x0102030405060708);
    }
    munmap(mapped, page_size);
    return ok;
}

void test_memory() noexcept {
    constexpr std::size_t length = guest_hi - guest_lo;
    void *wanted = reinterpret_cast<void *>(guest_lo);
    // Reserve address space with no access and never touch it. This is not
    // a 32 GiB physical-memory allocation, nor proof of full guest commit support.
    errno = 0;
    void *mapped = mmap(wanted, length, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mapped == MAP_FAILED) full_range_error = errno;
    else {
        full_range_ok = mapped == wanted;
        if (!full_range_ok) full_range_error = EADDRNOTAVAIL;
        munmap(mapped, length);
    }
    code_page_ok = test_page(guest_lo);
    heap_page_ok = test_page(UINT64_C(0x7240000000));

    // Reserve without physical backing, refusing to overwrite any other mapping.
    // MAP_EXCL is deliberately not used: it is not reliable on PS5.
    constexpr int fixed = 0x10, no_overwrite = 0x80;
    void *native = wanted;
    native_reserve_rc = sceKernelReserveVirtualRange(&native, length, fixed | no_overwrite, page_size);
    if (native_reserve_rc != 0) return;
    native_exact = native == wanted;
    if (!native_exact) { native_cleanup_rc = sceKernelMunmap(native, length); return; }
    constexpr std::size_t backed = 0x10000; // 64 KiB, not the entire 32 GiB window.
    int64_t physical = 0;
    native_alloc_rc = sceKernelAllocateMainDirectMemory(backed, page_size, 0x0c, &physical);
    if (native_alloc_rc == 0) {
        void *page = native;
        native_map_rc = sceKernelMapDirectMemory(&page, backed, PROT_READ | PROT_WRITE,
                                               fixed, physical, page_size);
        if (native_map_rc == 0 && page == native) {
            auto *words = static_cast<volatile std::uint64_t *>(page);
            words[0] = UINT64_C(0x5a41505335444952);
            words[backed / sizeof(*words) - 1] = UINT64_C(0x1122334455667788);
            native_rw = words[0] == UINT64_C(0x5a41505335444952) &&
                        words[backed / sizeof(*words) - 1] == UINT64_C(0x1122334455667788);
            native_protect_rc = sceKernelMprotect(page, backed, PROT_READ);
            if (native_protect_rc == 0) {
                native_rw = native_rw && words[0] == UINT64_C(0x5a41505335444952);
                native_protect_rc = sceKernelMprotect(page, backed, PROT_READ | PROT_WRITE);
            }
        }
    }
    native_cleanup_rc = sceKernelMunmap(native, length);
    if (native_alloc_rc == 0 && native_cleanup_rc == 0)
        native_cleanup_rc = sceKernelReleaseDirectMemory(physical, backed);
}

void start_listener() noexcept {
    listener = socket(AF_INET, SOCK_STREAM, 0);
    if (listener < 0) { network_error = errno; return; }
    int enabled = 1;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof enabled);
    sockaddr_in address{};
    address.sin_len = sizeof address;
    address.sin_family = AF_INET;
    address.sin_port = htons(status_port);
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(listener, reinterpret_cast<const sockaddr *>(&address), sizeof address) < 0 ||
        listen(listener, 2) < 0 || fcntl(listener, F_SETFL, O_NONBLOCK) < 0) {
        network_error = errno;
        close(listener);
        listener = -1;
    }
}
} // namespace

void start() noexcept {
    boot_ns = now_ns();
    video_stage = "starting";
    int fd = open("/app0/assets/banner.txt", O_RDONLY);
    if (fd >= 0) {
        char content[32]{};
        asset_ok = read(fd, content, sizeof content) > 0;
        close(fd);
    }
    start_listener();
    persist();
    video_stage = "memory_probe";
    persist();
    test_memory();
    video_stage = "before_video";
    persist();
}

void video_result(const char *stage, int result, bool ready) noexcept {
    video_stage = stage;
    video_rc = result;
    video_ready = ready;
    persist();
}

void tick() noexcept {
    ++heartbeat;
    if (heartbeat == 1 || heartbeat % 10 == 0) persist();
    if (listener < 0) return;
    const int client = accept(listener, nullptr, nullptr);
    if (client < 0) return;
    // Read-only one-record TCP endpoint. No command parsing or remote actions.
    struct timeval timeout{0, 100000};
    setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
    const std::size_t count = format_report();
    std::size_t done = 0;
    while (done < count) {
        const ssize_t n = send(client, report + done, count - done, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        done += static_cast<std::size_t>(n);
    }
    close(client);
}

const char *memory_summary() noexcept {
    return native_exact && native_rw && native_cleanup_rc == 0 ? "NATIVE MEMORY TEST PASS" : "MEMORY TEST NEEDS WORK";
}
const char *storage_summary() noexcept {
    return storage_error == 0 && asset_ok ? "ASSET AND LOG FILE OK" : "FILE ACCESS NEEDS WORK";
}
}
