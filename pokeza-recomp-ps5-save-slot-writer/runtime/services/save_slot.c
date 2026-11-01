// slot.zrs follows the game's save commits (see save_slot.h). One background thread; the IPC path only signals it.
//
// Why a SHA-256 of its own: the runtime links none (the title's mbedtls_sha256.o is a launcher link extra of the PS5
// eboot; the PC exe and the runtime's own builds have no mbedtls), so a small FIPS 180-4 one lives here (checked against
// the NIST vectors and sha256sum by the host test).
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "../platform.h"
#include "save_slot.h"
// The launcher defines za_slot.h's implementation in its own unit and is linked into the same title: this copy's
// functions get names of their own, so both can be linked together whatever their versions.
#define za_slot_result_name rt_za_slot_result_name
#define za_slot_crc32 rt_za_slot_crc32
#define za_slot_build rt_za_slot_build
#define za_slot_parse_summary rt_za_slot_parse_summary
#define za_slot_verify rt_za_slot_verify
#define za_slot_section rt_za_slot_section
#define za_slot_read_summary_file rt_za_slot_read_summary_file
#define za_slot_write_atomic rt_za_slot_write_atomic
#define za_slot_save_progress rt_za_slot_save_progress
#define za_slot_save_read rt_za_slot_save_read
#define za_slot_rebuild rt_za_slot_rebuild
#define ZA_SLOT_IMPLEMENTATION
#include "za_slot.h"

#ifndef SAVE_SLOT_LOG
#define SAVE_SLOT_LOG(...) fprintf(stderr, __VA_ARGS__)
#endif
#define SLOG(...) SAVE_SLOT_LOG("[slot] " __VA_ARGS__)

enum { SaveMax = 32u << 20, SlotMax = 48u << 20, DirMax = 512 };

// ------------------------------------------------------------------ SHA-256 (FIPS 180-4)
typedef struct { uint32_t h[8]; uint64_t len; uint8_t buf[64]; size_t fill; } Sha256;
static const uint32_t K256[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
    0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
    0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
static uint32_t ror32(uint32_t x, int n) { return x >> n | x << (32 - n); }
static void sha256_block(Sha256 *c, const uint8_t *p) {
    uint32_t w[64], a, b, d, e, f, g, h, cc;
    for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ror32(w[i - 15], 7) ^ ror32(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = ror32(w[i - 2], 17) ^ ror32(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    a = c->h[0], b = c->h[1], cc = c->h[2], d = c->h[3], e = c->h[4], f = c->h[5], g = c->h[6], h = c->h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t t1 = h + (ror32(e, 6) ^ ror32(e, 11) ^ ror32(e, 25)) + ((e & f) ^ (~e & g)) + K256[i] + w[i];
        uint32_t t2 = (ror32(a, 2) ^ ror32(a, 13) ^ ror32(a, 22)) + ((a & b) ^ (a & cc) ^ (b & cc));
        h = g, g = f, f = e, e = d + t1, d = cc, cc = b, b = a, a = t1 + t2;
    }
    c->h[0] += a, c->h[1] += b, c->h[2] += cc, c->h[3] += d, c->h[4] += e, c->h[5] += f, c->h[6] += g, c->h[7] += h;
}
static void sha256_init(Sha256 *c) {
    static const uint32_t iv[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memcpy(c->h, iv, sizeof iv);
    c->len = 0, c->fill = 0;
}
static void sha256_update(Sha256 *c, const uint8_t *p, size_t n) {
    c->len += n;
    if (c->fill) {
        size_t k = 64 - c->fill < n ? 64 - c->fill : n;
        memcpy(c->buf + c->fill, p, k);
        c->fill += k, p += k, n -= k;
        if (c->fill < 64) return;
        sha256_block(c, c->buf);
        c->fill = 0;
    }
    for (; n >= 64; p += 64, n -= 64) sha256_block(c, p);
    memcpy(c->buf, p, n);
    c->fill = n;
}
static void sha256_final(Sha256 *c, uint8_t out[32]) {
    const uint64_t bits = c->len * 8;
    const uint8_t one = 0x80, zero = 0;
    sha256_update(c, &one, 1);
    while (c->fill != 56) sha256_update(c, &zero, 1);
    uint8_t l[8];
    for (int i = 0; i < 8; i++) l[i] = (uint8_t)(bits >> (56 - 8 * i));
    sha256_update(c, l, 8);
    for (int i = 0; i < 8; i++) {
        out[4 * i] = (uint8_t)(c->h[i] >> 24), out[4 * i + 1] = (uint8_t)(c->h[i] >> 16);
        out[4 * i + 2] = (uint8_t)(c->h[i] >> 8), out[4 * i + 3] = (uint8_t)c->h[i];
    }
}

#ifndef SAVE_SLOT_TEST
static
#endif
int save_slot_sha256(const uint8_t *data, size_t n, uint8_t out[32]) {
    Sha256 c;
    sha256_init(&c);
    sha256_update(&c, data, n);
    sha256_final(&c, out);
    return 0;
}

// SwishCrypto's save hash: SHA-256(intro salt + payload + outro salt) (PKHeX SwishCrypto; the launcher's
// saves::swishHash in port/ui-v2/src/launcher_core.cpp, port/rando-v2/za_player_name.cpp IntroHash / OutroHash)
static const uint8_t IntroHash[64] = {
    0x9E, 0xC9, 0x9C, 0xD7, 0x0E, 0xD3, 0x3C, 0x44, 0xFB, 0x93, 0x03, 0xDC, 0xEB, 0x39, 0xB4, 0x2A,
    0x19, 0x47, 0xE9, 0x63, 0x4B, 0xA2, 0x33, 0x44, 0x16, 0xBF, 0x82, 0xA2, 0xBA, 0x63, 0x55, 0xB6,
    0x3D, 0x9D, 0xF2, 0x4B, 0x5F, 0x7B, 0x6A, 0xB2, 0x62, 0x1D, 0xC2, 0x1B, 0x68, 0xE5, 0xC8, 0xB5,
    0x3A, 0x05, 0x90, 0x00, 0xE8, 0xA8, 0x10, 0x3D, 0xE2, 0xEC, 0xF0, 0x0C, 0xB2, 0xED, 0x4F, 0x6D,
};
static const uint8_t OutroHash[64] = {
    0xD6, 0xC0, 0x1C, 0x59, 0x8B, 0xC8, 0xB8, 0xCB, 0x46, 0xE1, 0x53, 0xFC, 0x82, 0x8C, 0x75, 0x75,
    0x13, 0xE0, 0x45, 0xDF, 0x32, 0x69, 0x3C, 0x75, 0xF0, 0x59, 0xF8, 0xD9, 0xA2, 0x5F, 0xB2, 0x17,
    0xE0, 0x80, 0x52, 0xDB, 0xEA, 0x89, 0x73, 0x99, 0x75, 0x79, 0xAF, 0xCB, 0x2E, 0x80, 0x07, 0xE6,
    0xF1, 0x26, 0xE0, 0x03, 0x0A, 0xE6, 0x6F, 0xF6, 0x41, 0xBF, 0x7E, 0x59, 0xC2, 0xAE, 0x55, 0xFD,
};
#ifndef SAVE_SLOT_TEST
static
#endif
int save_slot_swish_hash(const uint8_t *payload, size_t n, uint8_t out[32]) {
    Sha256 c;
    sha256_init(&c);
    sha256_update(&c, IntroHash, sizeof IntroHash);
    sha256_update(&c, payload, n);
    sha256_update(&c, OutroHash, sizeof OutroHash);
    sha256_final(&c, out);
    return 0;
}

// ------------------------------------------------------------------ one rewrite
// The whole file, read-only (plat_open_file: on Windows the game may still rename / delete it while it is open here).
// NULL with *err = errno (EFBIG: over `max`).
static uint8_t *read_all(const char *path, size_t max, size_t *n, int *err) {
    int fd = plat_open_file(path, O_RDONLY);
    if (fd < 0) { *err = errno; return NULL; }
    struct stat sb;
    if (fstat(fd, &sb) || sb.st_size < 0) { *err = errno ? errno : EIO; close(fd); return NULL; }
    if ((uint64_t)sb.st_size > max) { *err = EFBIG; close(fd); return NULL; }
    const size_t size = (size_t)sb.st_size;
    uint8_t *p = malloc(size ? size : 1);
    if (!p) { *err = ENOMEM; close(fd); return NULL; }
    size_t got = 0;
    while (got < size) {
        ssize_t r = pread(fd, p + got, size - got, (off_t)got);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;
        got += (size_t)r;
    }
    close(fd);
    if (got != size) { *err = EIO; free(p); return NULL; }
    *n = size;
    return p;
}

static void hex16(const uint8_t *h, char out[17]) {
    for (int i = 0; i < 8; i++) snprintf(out + 2 * i, 3, "%02x", h[i]);
}

// 1 = slot.zrs rewritten, 0 = skipped (logged)
static int rewrite(const char *dir, uint64_t gen) {
    char slot_path[DirMax + 32], save_path[DirMax + 32];
    snprintf(slot_path, sizeof slot_path, "%s/slot.zrs", dir);
    snprintf(save_path, sizeof save_path, "%s/save/save_0/main", dir);
    const uint64_t t0 = plat_now_ns();
    int err = 0, rc = 0;
    size_t old_n = 0, save_n = 0;
    uint8_t *old = NULL, *save = NULL, *out = NULL;
    za_slot_summary prev, s;
    uint8_t h[32];
    if (!(old = read_all(slot_path, SlotMax, &old_n, &err))) {
        if (err == ENOENT) SLOG("commit %llu: no %s - skipped (the launcher writes the first one)\n", (unsigned long long)gen, slot_path);
        else SLOG("commit %llu: %s unreadable (%s) - skipped\n", (unsigned long long)gen, slot_path, strerror(err));
        goto done;
    }
    int v = za_slot_verify(old, old_n);
    if (v == ZA_SLOT_OK) v = za_slot_parse_summary(old, old_n, &prev);
    if (v != ZA_SLOT_OK) {
        SLOG("commit %llu: %s fails its check (%s) - skipped, left as it is\n", (unsigned long long)gen, slot_path, za_slot_result_name(v));
        goto done;
    }
    if (!(save = read_all(save_path, SaveMax, &save_n, &err))) {
        SLOG("commit %llu: %s unreadable (%s) - skipped\n", (unsigned long long)gen, save_path, strerror(err));
        goto done;
    }
    if (save_n < 0x10000 || save_slot_swish_hash(save, save_n - 32, h) || memcmp(h, save + save_n - 32, 32)) {
        SLOG("commit %llu: %s (%zu bytes) fails its save hash (the game may be writing it) - skipped\n", (unsigned long long)gen,
             save_path, save_n);
        goto done;
    }
    memset(&s, 0, sizeof s);
    s.flags = za_slot_save_read(save, save_n, save_slot_swish_hash, &s);
    memcpy(s.run_id, prev.run_id, sizeof s.run_id);
    memcpy(s.seed, prev.seed, sizeof s.seed);
    memcpy(s.algorithm, prev.algorithm, sizeof s.algorithm);
    memcpy(s.build_id, prev.build_id, sizeof s.build_id);
    s.created_time = prev.created_time;
    s.save_time = (uint64_t)time(NULL);
    s.save_size = (uint32_t)save_n;
    save_slot_sha256(save, save_n, s.save_sha256);
    s.flags |= ZA_SLOT_HAS_SAVE_HASH;
    const size_t need = za_slot_rebuild(NULL, 0, old, old_n, &s, save, save_n);
    if (!need || !(out = malloc(need)) || za_slot_rebuild(out, need, old, old_n, &s, save, save_n) != need) {
        SLOG("commit %llu: container rebuild failed (%zu bytes) - skipped\n", (unsigned long long)gen, need);
        goto done;
    }
    if (za_slot_write_atomic(slot_path, out, need)) {
        SLOG("commit %llu: writing %s failed (%s) - the previous file stays\n", (unsigned long long)gen, slot_path, strerror(errno));
        goto done;
    }
    char hx[17];
    hex16(s.save_sha256, hx);
    SLOG("commit %llu: %s rewritten (%zu bytes): save %zu bytes sha256 %s..., save_time %llu, caught %u seen %u, %s, phase %u, "
         "flags 0x%x, %.1f ms\n",
         (unsigned long long)gen, slot_path, need, save_n, hx, (unsigned long long)s.save_time, s.caught, s.seen,
         s.location[0] ? s.location : "-", s.story_phase, s.flags, (double)(plat_now_ns() - t0) / 1e6);
    rc = 1;
done:
    free(out);
    free(save);
    free(old);
    return rc;
}

// ------------------------------------------------------------------ the writer thread
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_cv = PTHREAD_COND_INITIALIZER;       // signals / pause changes -> writer
static pthread_cond_t g_idle_cv = PTHREAD_COND_INITIALIZER;  // writer done -> test waiters
static int g_started;                                        // 1 running, -1 could not start
static uint64_t g_signals, g_handled, g_last_ns, g_writes, g_skips, g_runs;
static char g_dir[DirMax];
static int g_running, g_paused;
static uint64_t g_debounce_ns = 500000000ull;  // autosave bursts (several commits in a row) become one rewrite

static void realtime_in(struct timespec *ts, uint64_t ns) {
    clock_gettime(CLOCK_REALTIME, ts);
    ts->tv_sec += (time_t)(ns / 1000000000u);
    ts->tv_nsec += (long)(ns % 1000000000u);
    if (ts->tv_nsec >= 1000000000L) { ts->tv_sec++; ts->tv_nsec -= 1000000000L; }
}

static void *writer_main(void *arg) {
    (void)arg;
    char dir[DirMax];
    pthread_mutex_lock(&g_lock);
    for (;;) {
        while (g_handled == g_signals || g_paused) pthread_cond_wait(&g_cv, &g_lock);
        // quiet for the debounce time since the latest commit
        for (;;) {
            const uint64_t now = plat_now_ns(), due = g_last_ns + g_debounce_ns;
            if (now >= due || g_paused) break;
            struct timespec ts;
            realtime_in(&ts, due - now);
            pthread_cond_timedwait(&g_cv, &g_lock, &ts);
        }
        if (g_paused) continue;
        const uint64_t gen = g_signals;
        memcpy(dir, g_dir, sizeof dir);
        g_running = 1;
        pthread_mutex_unlock(&g_lock);
        const int wrote = rewrite(dir, gen);
        pthread_mutex_lock(&g_lock);
        g_running = 0;
        g_handled = gen;
        g_runs++;
        if (wrote) g_writes++; else g_skips++;
        pthread_cond_broadcast(&g_idle_cv);
    }
    return NULL;
}

void save_slot_arm(void) {
    pthread_mutex_lock(&g_lock);
    if (!g_started) {
        pthread_t t;
        g_started = pthread_create(&t, NULL, writer_main, NULL) == 0 ? 1 : -1;
        if (g_started == 1) pthread_detach(t);
        pthread_mutex_unlock(&g_lock);
        if (g_started == 1) SLOG("writer ready: slot.zrs follows each save commit (debounce %llu ms)\n", (unsigned long long)(g_debounce_ns / 1000000u));
        else SLOG("writer thread could not start: slot.zrs will not follow the saves\n");
        return;
    }
    pthread_mutex_unlock(&g_lock);
}

void save_slot_commit(const char *run_dir) {
    pthread_mutex_lock(&g_lock);
    if (g_started == 1 && run_dir && run_dir[0]) {
        size_t n = strlen(run_dir);
        if (n < sizeof g_dir) {
            memcpy(g_dir, run_dir, n + 1);
            g_signals++;
            g_last_ns = plat_now_ns();
            pthread_cond_signal(&g_cv);
        }
    }
    pthread_mutex_unlock(&g_lock);
}

#ifdef SAVE_SLOT_TEST
void save_slot_test_set_debounce_ms(unsigned ms) {
    pthread_mutex_lock(&g_lock);
    g_debounce_ns = (uint64_t)ms * 1000000u;
    pthread_mutex_unlock(&g_lock);
}
SaveSlotStats save_slot_test_stats(void) {
    pthread_mutex_lock(&g_lock);
    SaveSlotStats s = {g_signals, g_writes, g_skips, g_runs};
    pthread_mutex_unlock(&g_lock);
    return s;
}
int save_slot_test_wait_idle(unsigned timeout_ms) {
    struct timespec ts;
    realtime_in(&ts, (uint64_t)timeout_ms * 1000000u);
    pthread_mutex_lock(&g_lock);
    int r = 0;
    while (!(r = g_handled == g_signals && !g_running))
        if (pthread_cond_timedwait(&g_idle_cv, &g_lock, &ts)) { r = g_handled == g_signals && !g_running; break; }
    pthread_mutex_unlock(&g_lock);
    return r;
}
void save_slot_test_pause(int on) {
    pthread_mutex_lock(&g_lock);
    g_paused = on;
    pthread_cond_broadcast(&g_cv);
    pthread_mutex_unlock(&g_lock);
}
#endif
