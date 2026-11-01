// Host test of runtime/services/save_slot.c (the slot.zrs writer that follows the game's save commits).
// Build + run: tools/save_slot/test.sh (Linux / WSL; ASan + UBSan). Optional real fixture: ZA_SLOT_FIXTURE_RUN=<a launcher-
// made run folder with save/save_0/main and slot.zrs> (copied into a scratch dir; never written).
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "../../runtime/services/save_slot.h"
// the test's own za_slot implementation under the plain names, as the launcher's unit is in the title: links next to
// save_slot.c's renamed copy (no duplicate symbols) and reads what the writer wrote independently of it
#define ZA_SLOT_IMPLEMENTATION
#include "../../runtime/services/za_slot.h"

// ---- what save_slot.c needs from the platform layer
int plat_open_file(const char *path, int flags) { return open(path, flags, 0644); }
uint64_t plat_now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000u + (uint64_t)ts.tv_nsec;
}

// ---- log capture (save_slot.c is built with -D'SAVE_SLOT_LOG(...)=test_log(__VA_ARGS__)')
static pthread_mutex_t log_lock = PTHREAD_MUTEX_INITIALIZER;
static char log_buf[1 << 16];
static size_t log_len;
void test_log(const char *fmt, ...) {
    char line[2048];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    fputs(line, stderr);
    pthread_mutex_lock(&log_lock);
    size_t n = strlen(line);
    if (log_len + n < sizeof log_buf) { memcpy(log_buf + log_len, line, n + 1); log_len += n; }
    pthread_mutex_unlock(&log_lock);
}
static void log_reset(void) { pthread_mutex_lock(&log_lock); log_len = 0; log_buf[0] = 0; pthread_mutex_unlock(&log_lock); }
static int log_has(const char *s) { pthread_mutex_lock(&log_lock); int r = strstr(log_buf, s) != NULL; pthread_mutex_unlock(&log_lock); return r; }

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

// ---- files
typedef struct { uint8_t *p; size_t n; } Buf;
static Buf slurp(const char *path) {
    Buf b = {0, 0};
    FILE *f = fopen(path, "rb");
    if (!f) return b;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    b.p = malloc(n ? (size_t)n : 1);
    b.n = fread(b.p, 1, (size_t)n, f);
    fclose(f);
    return b;
}
static void spit(const char *path, const void *p, size_t n) {
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); exit(2); }
    if (fwrite(p, 1, n, f) != n) exit(2);
    fclose(f);
}
static int exists(const char *p) { struct stat sb; return stat(p, &sb) == 0; }
static int same_file(const char *path, const Buf *b) {
    Buf c = slurp(path);
    int r = c.p && c.n == b->n && !memcmp(c.p, b->p, b->n);
    free(c.p);
    return r;
}

// ---- a synthetic SwishCrypto save (the inverse of za_slot.h's reader)
static const uint8_t xorpad[0x7F] = {
    0xA0, 0x92, 0xD1, 0x06, 0x07, 0xDB, 0x32, 0xA1, 0xAE, 0x01, 0xF5, 0xC5, 0x1E, 0x84, 0x4F, 0xE3, 0x53, 0xCA, 0x37, 0xF4,
    0xA7, 0xB0, 0x4D, 0xA0, 0x18, 0xB7, 0xC2, 0x97, 0xDA, 0x5F, 0x53, 0x2B, 0x75, 0xFA, 0x48, 0x16, 0xF8, 0xD4, 0x8A, 0x6F,
    0x61, 0x05, 0xF4, 0xE2, 0xFD, 0x04, 0xB5, 0xA3, 0x0F, 0xFC, 0x44, 0x92, 0xCB, 0x32, 0xE6, 0x1B, 0xB9, 0xB1, 0x2E, 0x01,
    0xB0, 0x56, 0x53, 0x36, 0xD2, 0xD1, 0x50, 0x3D, 0xDE, 0x5B, 0x2E, 0x0E, 0x52, 0xFD, 0xDF, 0x2F, 0x7B, 0xCA, 0x63, 0x50,
    0xA4, 0x67, 0x5D, 0x23, 0x17, 0xC0, 0x52, 0xE1, 0xA6, 0x30, 0x7C, 0x2B, 0xB6, 0x70, 0x36, 0x5B, 0x2A, 0x27, 0x69, 0x33,
    0xF5, 0x63, 0x7B, 0x36, 0x3F, 0x26, 0x9B, 0xA3, 0xED, 0x7A, 0x53, 0x00, 0xA4, 0x48, 0xB3, 0x50, 0x9E, 0x14, 0xA0, 0x52,
    0xDE, 0x7E, 0x10, 0x2B, 0x1B, 0x77, 0x6E,
};
typedef struct { uint32_t state; int counter; } Xs;
static uint32_t xs_adv(uint32_t s) { s ^= s << 2; s ^= s >> 15; s ^= s << 13; return s; }
static void xs_init(Xs *x, uint32_t seed) { x->state = seed; x->counter = 0; for (int i = __builtin_popcount(seed); i > 0; i--) x->state = xs_adv(x->state); }
static uint8_t xs_next(Xs *x) {
    uint8_t r = (uint8_t)(x->state >> (x->counter << 3));
    if (x->counter == 3) { x->state = xs_adv(x->state); x->counter = 0; } else x->counter++;
    return r;
}
typedef struct { uint8_t *p; size_t n, cap; } Save;
static void put(Save *s, uint8_t plain) { s->p[s->n] = plain ^ xorpad[s->n % 0x7F]; s->n++; }
static void block(Save *s, uint32_t key, const uint8_t *data, uint32_t size) {
    for (int i = 0; i < 4; i++) put(s, (uint8_t)(key >> (8 * i)));
    Xs x;
    xs_init(&x, key);
    put(s, 4 ^ xs_next(&x));
    for (int i = 0; i < 4; i++) put(s, (uint8_t)(size >> (8 * i)) ^ xs_next(&x));
    for (uint32_t k = 0; k < size; k++) put(s, data[k] ^ xs_next(&x));
}
static void wr32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
static void wr64(uint8_t *p, uint64_t v) { memcpy(p, &v, 8); }
// caught = c, seen = c + extra_seen, location `map`, phase, research level / points; 0x18000+ bytes
static Buf make_save(uint32_t caught, uint32_t extra_seen, const char *map, uint32_t phase, uint32_t level, uint32_t points) {
    Save s = {calloc(1, 0x20000), 0, 0x20000};
    uint8_t coords[0x2C] = {0};
    snprintf((char *)coords, 32, "%s", map);
    float x = 1.5f, z = -2.25f, y = 3.0f;
    memcpy(coords + 0x20, &x, 4), memcpy(coords + 0x24, &y, 4), memcpy(coords + 0x28, &z, 4);  /* the game: x, height y, z */
    block(&s, 0x910D381Fu, coords, sizeof coords);
    const uint32_t entries = 1 + caught + extra_seen;
    uint8_t *dex = calloc(entries, 0x84);
    for (uint32_t i = 1; i < entries; i++) { wr32(dex + i * 0x84, i <= caught ? 1 : 0); wr32(dex + i * 0x84 + 4, 1); }
    block(&s, 0x2D87BE5Cu, dex, entries * 0x84);
    free(dex);
    uint8_t work[32];
    wr64(work, 0x1111ull), wr64(work + 8, 5);
    wr64(work + 16, 0x992FE2A6DEC12926ull), wr64(work + 24, phase);
    block(&s, 0xFADA7742u, work, sizeof work);
    uint8_t mable[12] = {0};
    wr32(mable, level), wr32(mable + 8, points);
    block(&s, 0x85DBDCE9u, mable, sizeof mable);
    static uint8_t filler[0x10000];
    for (size_t i = 0; i < sizeof filler; i++) filler[i] = (uint8_t)(i * 7 + phase);
    block(&s, 0x12345678u, filler, sizeof filler);
    uint8_t h[32];
    save_slot_swish_hash(s.p, s.n, h);
    memcpy(s.p + s.n, h, 32);
    s.n += 32;
    Buf b = {s.p, s.n};
    return b;
}

static const char RandJson[] = "{\"schema\":\"za-slot-rand-1\",\"run_id\":\"rTEST\"}";
static const char SettJson[] = "{\"schema\":\"za-slot-settings-1\",\"seed\":\"1234abcd\"}";
static Buf make_slot(const Buf *save) {
    za_slot_summary s;
    memset(&s, 0, sizeof s);
    snprintf(s.run_id, sizeof s.run_id, "rTEST-0001");
    snprintf(s.seed, sizeof s.seed, "1234abcd");
    snprintf(s.algorithm, sizeof s.algorithm, "za202-v3-test");
    snprintf(s.build_id, sizeof s.build_id, "build-xyz");
    s.created_time = 1700000000;
    s.save_time = 1700000001;
    s.caught = 999;
    s.flags = ZA_SLOT_HAS_CAUGHT;
    size_t need = za_slot_build(NULL, 0, &s, RandJson, strlen(RandJson), SettJson, strlen(SettJson), save->p, save->n);
    Buf b = {malloc(need), need};
    za_slot_build(b.p, need, &s, RandJson, strlen(RandJson), SettJson, strlen(SettJson), save->p, save->n);
    return b;
}

static char root[512];
static void make_run(const char *name, char *dir, size_t cap, const Buf *save, const Buf *slot) {
    snprintf(dir, cap, "%s/%s", root, name);
    char p[1024];
    mkdir(dir, 0755);
    snprintf(p, sizeof p, "%s/save", dir); mkdir(p, 0755);
    snprintf(p, sizeof p, "%s/save/save_0", dir); mkdir(p, 0755);
    snprintf(p, sizeof p, "%s/save/save_0/main", dir);
    if (save) spit(p, save->p, save->n);
    snprintf(p, sizeof p, "%s/slot.zrs", dir);
    if (slot) spit(p, slot->p, slot->n);
}

// per-thread IO syscall counters (Linux task IO accounting)
typedef struct { long long syscr, syscw, wchar; } Io;
static Io thread_io(void) {
    Io io = {-1, -1, -1};
    char b[1024];
    int fd = open("/proc/thread-self/io", O_RDONLY);
    if (fd < 0) return io;
    ssize_t n = read(fd, b, sizeof b - 1);
    close(fd);
    if (n <= 0) return io;
    b[n] = 0;
    char *q;
    if ((q = strstr(b, "syscr:"))) io.syscr = atoll(q + 6);
    if ((q = strstr(b, "syscw:"))) io.syscw = atoll(q + 6);
    if ((q = strstr(b, "wchar:"))) io.wchar = atoll(q + 6);
    return io;
}

static void hexs(const uint8_t *h, size_t n, char *out) { for (size_t i = 0; i < n; i++) sprintf(out + 2 * i, "%02x", h[i]); }

static void test_sha256(void) {
    uint8_t h[32];
    char x[65];
    save_slot_sha256((const uint8_t *)"", 0, h); hexs(h, 32, x);
    CHECK(!strcmp(x, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
    save_slot_sha256((const uint8_t *)"abc", 3, h); hexs(h, 32, x);
    CHECK(!strcmp(x, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
    const char *m = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    save_slot_sha256((const uint8_t *)m, strlen(m), h); hexs(h, 32, x);
    CHECK(!strcmp(x, "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"));
    uint8_t *a = malloc(1000000);
    memset(a, 'a', 1000000);
    save_slot_sha256(a, 1000000, h); hexs(h, 32, x);
    CHECK(!strcmp(x, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"));
    free(a);
}

static void test_update(void) {
    Buf old_save = make_save(3, 2, "t001_old_town", 100, 1, 10), new_save = make_save(7, 4, "t002_wild_zone", 21110, 5, 777);
    Buf slot = make_slot(&old_save);
    char dir[700], p[800];
    make_run("update", dir, sizeof dir, &new_save, &slot);
    snprintf(p, sizeof p, "%s/save/save_0/main", dir);
    struct stat before;
    stat(p, &before);
    log_reset();
    const uint64_t t_before = (uint64_t)time(NULL);
    SaveSlotStats s0 = save_slot_test_stats();
    save_slot_commit(dir);
    CHECK(save_slot_test_wait_idle(5000));
    SaveSlotStats s1 = save_slot_test_stats();
    CHECK(s1.writes == s0.writes + 1);
    CHECK(log_has("rewritten"));
    // the game save: byte-identical, not touched
    CHECK(same_file(p, &new_save));
    struct stat after;
    stat(p, &after);
    CHECK(before.st_mtim.tv_sec == after.st_mtim.tv_sec && before.st_mtim.tv_nsec == after.st_mtim.tv_nsec && before.st_ino == after.st_ino);
    // the container
    snprintf(p, sizeof p, "%s/slot.zrs", dir);
    Buf c = slurp(p);
    CHECK(za_slot_verify(c.p, c.n) == ZA_SLOT_OK);
    za_slot_summary m;
    CHECK(za_slot_parse_summary(c.p, c.n, &m) == ZA_SLOT_OK);
    CHECK(!strcmp(m.run_id, "rTEST-0001") && !strcmp(m.seed, "1234abcd") && !strcmp(m.algorithm, "za202-v3-test") && !strcmp(m.build_id, "build-xyz"));
    CHECK(m.created_time == 1700000000);
    CHECK(m.save_time >= t_before && m.save_time <= (uint64_t)time(NULL));
    CHECK(m.caught == 7 && m.seen == 11);
    CHECK(!strcmp(m.location, "t002_wild_zone"));
    CHECK(m.story_phase == 21110 && m.research_level == 5 && m.research_points == 777);
    CHECK(m.x == 1.5f && m.z == -2.25f && m.y == 3.0f);
    const uint32_t want = ZA_SLOT_HAS_CAUGHT | ZA_SLOT_HAS_SEEN | ZA_SLOT_HAS_LOCATION | ZA_SLOT_HAS_SAVE_HASH | ZA_SLOT_HAS_PHASE |
                          ZA_SLOT_HAS_RESEARCH | ZA_SLOT_HAS_POSITION;
    CHECK(m.flags == want);
    CHECK(m.save_size == new_save.n);
    uint8_t h[32];
    save_slot_sha256(new_save.p, new_save.n, h);
    CHECK(!memcmp(m.save_sha256, h, 32));
    const uint8_t *sec;
    size_t len;
    CHECK(za_slot_section(c.p, c.n, ZA_SLOT_SAVE, &sec, &len) == ZA_SLOT_OK && len == new_save.n && !memcmp(sec, new_save.p, len));
    CHECK(za_slot_section(c.p, c.n, ZA_SLOT_RAND, &sec, &len) == ZA_SLOT_OK && len == strlen(RandJson) && !memcmp(sec, RandJson, len));
    CHECK(za_slot_section(c.p, c.n, ZA_SLOT_SETT, &sec, &len) == ZA_SLOT_OK && len == strlen(SettJson) && !memcmp(sec, SettJson, len));
    snprintf(p, sizeof p, "%s/slot.zrs.new", dir);
    CHECK(!exists(p));
    free(c.p), free(slot.p), free(old_save.p), free(new_save.p);
}

static void test_missing_and_corrupt(void) {
    Buf save = make_save(2, 1, "t003", 5, 1, 1);
    char dir[700], p[800];
    // missing slot.zrs: skipped, nothing created
    make_run("missing", dir, sizeof dir, &save, NULL);
    log_reset();
    SaveSlotStats s0 = save_slot_test_stats();
    save_slot_commit(dir);
    CHECK(save_slot_test_wait_idle(5000));
    SaveSlotStats s1 = save_slot_test_stats();
    CHECK(s1.writes == s0.writes && s1.skips == s0.skips + 1);
    CHECK(log_has("slot.zrs - skipped (the launcher writes the first one)"));
    snprintf(p, sizeof p, "%s/slot.zrs", dir); CHECK(!exists(p));
    snprintf(p, sizeof p, "%s/slot.zrs.new", dir); CHECK(!exists(p));
    snprintf(p, sizeof p, "%s/save/save_0/main", dir); CHECK(same_file(p, &save));
    // corrupt slot.zrs (a byte of SETT flipped): skipped, left as it is
    Buf slot = make_slot(&save);
    const uint8_t *sec;
    size_t len;
    za_slot_section(slot.p, slot.n, ZA_SLOT_SETT, &sec, &len);
    slot.p[(size_t)(sec - slot.p) + 3] ^= 0x40;
    make_run("corrupt", dir, sizeof dir, &save, &slot);
    log_reset();
    s0 = save_slot_test_stats();
    save_slot_commit(dir);
    CHECK(save_slot_test_wait_idle(5000));
    s1 = save_slot_test_stats();
    CHECK(s1.writes == s0.writes && s1.skips == s0.skips + 1);
    CHECK(log_has("fails its check (checksum mismatch) - skipped"));
    snprintf(p, sizeof p, "%s/slot.zrs", dir); CHECK(same_file(p, &slot));
    // a truncated slot.zrs
    make_run("truncated", dir, sizeof dir, &save, NULL);
    snprintf(p, sizeof p, "%s/slot.zrs", dir);
    spit(p, slot.p, 100);
    log_reset();
    save_slot_commit(dir);
    CHECK(save_slot_test_wait_idle(5000));
    CHECK(log_has("fails its check"));
    Buf head = {slot.p, 100};
    CHECK(same_file(p, &head));
    free(slot.p), free(save.p);
}

static void test_bad_hash(void) {
    Buf save = make_save(4, 0, "t004", 7, 2, 2);
    Buf slot = make_slot(&save);
    Buf bad = {malloc(save.n), save.n};
    memcpy(bad.p, save.p, save.n);
    bad.p[0x200] ^= 1;  // payload byte: the trailing hash no longer matches (a save caught mid-write)
    char dir[700], p[800];
    make_run("badhash", dir, sizeof dir, &bad, &slot);
    log_reset();
    SaveSlotStats s0 = save_slot_test_stats();
    save_slot_commit(dir);
    CHECK(save_slot_test_wait_idle(5000));
    SaveSlotStats s1 = save_slot_test_stats();
    CHECK(s1.writes == s0.writes && s1.skips == s0.skips + 1);
    CHECK(log_has("fails its save hash"));
    snprintf(p, sizeof p, "%s/slot.zrs", dir); CHECK(same_file(p, &slot));
    snprintf(p, sizeof p, "%s/save/save_0/main", dir); CHECK(same_file(p, &bad));
    // a save that is missing / too small
    make_run("nosave", dir, sizeof dir, NULL, &slot);
    log_reset();
    save_slot_commit(dir);
    CHECK(save_slot_test_wait_idle(5000));
    CHECK(log_has("main unreadable (No such file or directory) - skipped"));
    snprintf(p, sizeof p, "%s/slot.zrs", dir); CHECK(same_file(p, &slot));
    free(bad.p), free(slot.p), free(save.p);
}

static void test_burst(void) {
    Buf save = make_save(5, 5, "t005", 9, 3, 3);
    Buf slot = make_slot(&save);
    char dir[700];
    make_run("burst", dir, sizeof dir, &save, &slot);
    save_slot_test_set_debounce_ms(300);
    SaveSlotStats s0 = save_slot_test_stats();
    for (int i = 0; i < 40; i++) {  // 40 commits over ~200 ms (an autosave burst)
        save_slot_commit(dir);
        usleep(5000);
    }
    CHECK(save_slot_test_wait_idle(5000));
    SaveSlotStats s1 = save_slot_test_stats();
    fprintf(stderr, "burst: %llu commits -> %llu runs, %llu writes\n", (unsigned long long)(s1.signals - s0.signals),
            (unsigned long long)(s1.runs - s0.runs), (unsigned long long)(s1.writes - s0.writes));
    CHECK(s1.signals - s0.signals == 40);
    CHECK(s1.writes - s0.writes == 1);
    CHECK(s1.runs - s0.runs == 1);
    save_slot_test_set_debounce_ms(50);
    free(slot.p), free(save.p);
}

static void test_ipc_path_no_io(void) {
    Buf save = make_save(1, 1, "t006", 1, 1, 1);
    Buf slot = make_slot(&save);
    char dir[700], p[800];
    make_run("noio", dir, sizeof dir, &save, &slot);
    save_slot_test_pause(1);  // the writer is held: whatever IO happens now is the caller's own
    Io a = thread_io(), b = thread_io();
    const uint64_t t0 = plat_now_ns();
    for (int i = 0; i < 1000; i++) save_slot_commit(dir);
    const uint64_t dt = plat_now_ns() - t0;
    Io c = thread_io();
    fprintf(stderr, "ipc path: 1000 commits in %.3f ms; thread io syscr %lld/%lld syscw %lld/%lld wchar %lld/%lld (calibration/commits)\n",
            (double)dt / 1e6, b.syscr - a.syscr, c.syscr - b.syscr, b.syscw - a.syscw, c.syscw - b.syscw, b.wchar - a.wchar, c.wchar - b.wchar);
    CHECK(a.syscr >= 0);
    CHECK(c.syscr - b.syscr == b.syscr - a.syscr);  // only the counter file's own read
    CHECK(c.syscw - b.syscw == b.syscw - a.syscw);
    CHECK(c.wchar - b.wchar == b.wchar - a.wchar);
    CHECK(dt < 50000000ull);  // well under 50 us per commit
    snprintf(p, sizeof p, "%s/slot.zrs", dir);
    CHECK(same_file(p, &slot));  // nothing written while the writer is held
    save_slot_test_pause(0);
    CHECK(save_slot_test_wait_idle(5000));
    Buf after = slurp(p);
    za_slot_summary m;
    CHECK(za_slot_parse_summary(after.p, after.n, &m) == ZA_SLOT_OK && m.save_time > 1700000001);
    free(after.p), free(slot.p), free(save.p);
}

// the real launcher-made run (game save + the launcher's slot.zrs): the writer's SUMM must agree with the launcher's
static void test_fixture(const char *src) {
    char sp[1024], lp[1024], dir[700], p[800];
    snprintf(sp, sizeof sp, "%s/save/save_0/main", src);
    snprintf(lp, sizeof lp, "%s/slot.zrs", src);
    Buf save = slurp(sp), slot = slurp(lp);
    if (!save.p || !slot.p) { fprintf(stderr, "fixture %s: unreadable\n", src); fails++; return; }
    uint8_t h[32];
    save_slot_swish_hash(save.p, save.n - 32, h);
    CHECK(!memcmp(h, save.p + save.n - 32, 32));  // the SwishCrypto hash agrees with the game's own trailer
    za_slot_summary l, m;
    CHECK(za_slot_parse_summary(slot.p, slot.n, &l) == ZA_SLOT_OK);
    make_run("fixture", dir, sizeof dir, &save, &slot);
    log_reset();
    save_slot_commit(dir);
    CHECK(save_slot_test_wait_idle(10000));
    CHECK(log_has("rewritten"));
    snprintf(p, sizeof p, "%s/slot.zrs", dir);
    Buf c = slurp(p);
    CHECK(za_slot_verify(c.p, c.n) == ZA_SLOT_OK);
    CHECK(za_slot_parse_summary(c.p, c.n, &m) == ZA_SLOT_OK);
    CHECK(!strcmp(m.run_id, l.run_id) && !strcmp(m.seed, l.seed) && !strcmp(m.algorithm, l.algorithm) && !strcmp(m.build_id, l.build_id));
    CHECK(m.created_time == l.created_time);
    CHECK(m.caught == l.caught && m.seen == l.seen && !strcmp(m.location, l.location));
    // a 1.0 container (256-byte SUMM) has no phase / research / position: compare those only where the launcher's has them
    const uint32_t v2 = ZA_SLOT_HAS_PHASE | ZA_SLOT_HAS_RESEARCH | ZA_SLOT_HAS_POSITION;
    fprintf(stderr, "fixture: the launcher's SUMM flags 0x%x (v2 fields %s)\n", l.flags, l.flags & v2 ? "present" : "absent: a 1.0 container");
    CHECK((m.flags & ~v2) == (l.flags & ~v2));
    CHECK((m.flags & v2) == v2);  // the writer always fills them from the save (1.1)
    if (l.flags & ZA_SLOT_HAS_PHASE) CHECK(m.story_phase == l.story_phase && m.dlc_phase == l.dlc_phase);
    if (l.flags & ZA_SLOT_HAS_RESEARCH) CHECK(m.research_level == l.research_level && m.research_points == l.research_points);
    if (l.flags & ZA_SLOT_HAS_POSITION) CHECK(m.x == l.x && m.y == l.y && m.z == l.z);
    CHECK(!memcmp(m.save_sha256, l.save_sha256, 32));
    const uint8_t *a, *b;
    size_t an, bn;
    CHECK(za_slot_section(c.p, c.n, ZA_SLOT_RAND, &a, &an) == ZA_SLOT_OK && za_slot_section(slot.p, slot.n, ZA_SLOT_RAND, &b, &bn) == ZA_SLOT_OK && an == bn && !memcmp(a, b, an));
    CHECK(za_slot_section(c.p, c.n, ZA_SLOT_SETT, &a, &an) == ZA_SLOT_OK && za_slot_section(slot.p, slot.n, ZA_SLOT_SETT, &b, &bn) == ZA_SLOT_OK && an == bn && !memcmp(a, b, an));
    CHECK(za_slot_section(c.p, c.n, ZA_SLOT_SAVE, &a, &an) == ZA_SLOT_OK && an == save.n && !memcmp(a, save.p, an));
    snprintf(p, sizeof p, "%s/save/save_0/main", dir);
    CHECK(same_file(p, &save));
    char x[65];
    hexs(m.save_sha256, 32, x);
    fprintf(stderr, "fixture: caught %u seen %u location %s phase %u research %u/%u flags 0x%x save sha256 %s\n", m.caught, m.seen,
            m.location, m.story_phase, m.research_level, m.research_points, m.flags, x);
    free(c.p), free(save.p), free(slot.p);
}

int main(void) {
    snprintf(root, sizeof root, "%s/save-slot-test-XXXXXX", getenv("TMPDIR") ? getenv("TMPDIR") : "/tmp");
    if (!mkdtemp(root)) { perror("mkdtemp"); return 2; }
    test_sha256();
    save_slot_commit("rando/never");  // before arm: ignored (no thread yet)
    CHECK(save_slot_test_stats().signals == 0);
    save_slot_test_set_debounce_ms(50);
    log_reset();
    save_slot_arm();
    save_slot_arm();  // once only
    CHECK(log_has("writer ready"));
    test_update();
    test_missing_and_corrupt();
    test_bad_hash();
    test_burst();
    test_ipc_path_no_io();
    const char *fx = getenv("ZA_SLOT_FIXTURE_RUN");
    if (fx && fx[0]) test_fixture(fx);
    else fprintf(stderr, "fixture: skipped (ZA_SLOT_FIXTURE_RUN not set)\n");
    printf("save_slot: %d checks, %d failed%s\n", checks, fails, fx && fx[0] ? " (with the real fixture)" : "");
    return fails ? 1 : 0;
}
