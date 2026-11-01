// Host test of runtime/services/fs.c's loose-file overlay (mods/<name>/romfs/...): reads through romfs_read() of
// thousands of overlay files must return the files' bytes while the process keeps a bounded number of host file
// descriptors (the PS5 title has ~1024: one kept descriptor per mod file ever read ran it out and the game parsed
// zero-filled resources). Linux only (/proc/self/fd). Build and run: tools/test_fs_overlay_fds.sh
//
// The unit is #included, so the test drives its static overlay table directly; the services it would talk to are
// never called (the link ignores their unresolved symbols).
#include "../runtime/services/fs.c"

#include <dirent.h>
#include <pthread.h>
#include <stdio.h>
#include <sys/resource.h>

#ifndef ROMFS_OVERLAY_FD_LIMIT
#define TEST_FD_BOUND 1000000  // (the unfixed fs.c: no bound, the test reports the growth)
#else
#define TEST_FD_BOUND ROMFS_OVERLAY_FD_LIMIT
#endif

static int nfiles = 2500;
static char dir[256];
static int failures;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; fprintf(stdout, "FAIL: " __VA_ARGS__); fputc('\n', stdout); } } while (0)

static uint64_t file_size(int k) { return 1 + (uint64_t)k * 977 % 6000; }
static uint8_t file_byte(int k, uint64_t j) { return (uint8_t)(k * 131 + j * 7 + (j >> 8)); }

static int open_fds(void) {
    int n = 0;
    DIR *d = opendir("/proc/self/fd");
    for (struct dirent *e; d && (e = readdir(d));) n += e->d_name[0] != '.';
    if (d) closedir(d);
    return n - 1;  // (the DIR's own descriptor)
}

// ov[k] is file k, laid out as rom_index lays out loose files: 16-byte aligned, one after another.
static void build_overlay(const char *missing_path) {
    ov_n = 0;
    ov_cap = nfiles + 1;
    ov = calloc((size_t)ov_cap, sizeof *ov);
    uint64_t at = 0;
    for (int k = 0; k < nfiles; k++) {
        char p[512];
        snprintf(p, sizeof p, "%s/f%05d.bin", dir, k);
        ov[ov_n++] = (Overlay){at, file_size(k), strdup(p), -1, NULL};
        at += (file_size(k) + 0xF) & ~0xFull;
    }
    if (missing_path) ov[ov_n++] = (Overlay){at, 4096, strdup(missing_path), -1, NULL};
}

static void write_files(void) {
    uint8_t *buf = malloc(8192);
    for (int k = 0; k < nfiles; k++) {
        char p[512];
        snprintf(p, sizeof p, "%s/f%05d.bin", dir, k);
        for (uint64_t j = 0; j < file_size(k); j++) buf[j] = file_byte(k, j);
        FILE *f = fopen(p, "wb");
        if (!f || fwrite(buf, 1, file_size(k), f) != file_size(k)) { perror(p); exit(2); }
        fclose(f);
    }
    free(buf);
}

// Read [off, off+len) of the virtual image and check it against the files (zeros in the alignment padding).
static int read_and_check(uint64_t off, uint64_t len, uint8_t *buf) {
    if (romfs_read(-1, buf, len, off) != (ssize_t)len) return 0;
    int k = 0;
    while (k + 1 < nfiles && ov[k + 1].start <= off) k++;
    for (uint64_t j = 0; j < len; j++) {
        uint64_t o = off + j;
        while (k + 1 < nfiles && ov[k + 1].start <= o) k++;
        uint64_t in = o - ov[k].start;
        uint8_t want = in < ov[k].size ? file_byte(k, in) : 0;
        if (buf[j] != want) return 0;
    }
    return 1;
}

static int max_fds_seen, baseline;
static pthread_mutex_t seen_lock = PTHREAD_MUTEX_INITIALIZER;
static void note_fds(void) {
    pthread_mutex_lock(&seen_lock);  // (one counter at a time: each one's /proc/self/fd DIR is a descriptor too)
    int n = open_fds() - baseline;
    if (n > max_fds_seen) max_fds_seen = n;
    pthread_mutex_unlock(&seen_lock);
}

typedef struct { unsigned seed; int reads, bad; } Worker;
static void *worker(void *arg) {
    Worker *w = arg;
    uint8_t buf[20000];
    uint64_t end = ov[nfiles - 1].start + ov[nfiles - 1].size;
    for (int r = 0; r < w->reads; r++) {
        uint64_t off = (uint64_t)rand_r(&w->seed) * 7919 % end;
        uint64_t len = 1 + (uint64_t)rand_r(&w->seed) % 16000;  // often spans several files
        if (off + len > end) len = end - off;
        if (!read_and_check(off, len, buf)) w->bad++;
        if (!(r & 63)) note_fds();
    }
    return NULL;
}

static int count_log(const char *log, const char *needle) {
    FILE *f = fopen(log, "r");
    char line[2048];
    int n = 0;
    while (f && fgets(line, sizeof line, f)) n += strstr(line, needle) != NULL;
    if (f) fclose(f);
    return n;
}

int main(int argc, char **argv) {
    if (argc > 1) nfiles = atoi(argv[1]);
    // the console's budget: ~1024 descriptors for the whole title
    struct rlimit rl = {1024, 1024};
    if (setrlimit(RLIMIT_NOFILE, &rl) != 0) perror("setrlimit 1024");
    snprintf(dir, sizeof dir, "/tmp/za-fs-overlay-fds-%d", (int)getpid());
    mkdir(dir, 0755);
    write_files();
    char log[300];
    snprintf(log, sizeof log, "%s/fs.log", dir);
    if (!freopen(log, "w", stderr)) { perror(log); return 2; }
    setvbuf(stderr, NULL, _IONBF, 0);
    char missing[300];
    snprintf(missing, sizeof missing, "%s/does-not-exist.bin", dir);
    build_overlay(missing);
    baseline = open_fds();
    printf("files %d, fd limit (RLIMIT_NOFILE) %d, overlay fd bound %d, baseline open fds %d\n", nfiles,
           (int)rl.rlim_cur, TEST_FD_BOUND, baseline);

    // 1. every file once, in order, each read alone
    uint8_t buf[20000];
    int bad = 0;
    for (int k = 0; k < nfiles; k++) {
        if (!read_and_check(ov[k].start, ov[k].size, buf)) bad++;
        note_fds();
    }
    printf("1. sequential: %d files read, %d wrong, max extra fds %d\n", nfiles, bad, max_fds_seen);
    CHECK(bad == 0, "sequential reads returned wrong bytes for %d files", bad);
    CHECK(max_fds_seen <= TEST_FD_BOUND, "sequential: %d extra fds open (bound %d)", max_fds_seen, TEST_FD_BOUND);

    // 2. 8 threads, random ranges across file boundaries
    enum { NT = 8 };
    pthread_t th[NT];
    Worker w[NT];
    for (int t = 0; t < NT; t++) {
        w[t] = (Worker){(unsigned)(t * 2654435761u + 1), 25000, 0};
        pthread_create(&th[t], NULL, worker, &w[t]);
    }
    bad = 0;
    for (int t = 0; t < NT; t++) pthread_join(th[t], NULL), bad += w[t].bad;
    printf("2. parallel: %d threads x %d random reads, %d wrong, max extra fds %d\n", NT, w[0].reads, bad, max_fds_seen);
    CHECK(bad == 0, "parallel reads returned wrong bytes %d times", bad);
    CHECK(max_fds_seen <= TEST_FD_BOUND, "parallel: %d extra fds open (bound %d)", max_fds_seen, TEST_FD_BOUND);

    // 3. the rest of the process holds almost every descriptor: the cache sheds its own and still reads
    int before = count_log(log, "overlay open failed");
#ifdef ROMFS_OVERLAY_FD_LIMIT
    overlay_cache_reset();  // (empty cache: the tight limit below leaves it 8 descriptors of its 64)
#endif
    struct rlimit tight = {(rlim_t)(open_fds() + 8), 1024};
    if (tight.rlim_cur > 1024) tight.rlim_cur = 1024;
    setrlimit(RLIMIT_NOFILE, &tight);
    bad = 0;
    for (int k = 0; k < nfiles; k += 3) bad += !read_and_check(ov[k].start, ov[k].size, buf);
    int failed_opens = count_log(log, "overlay open failed") - before;
    printf("3. limit = open fds + 8 (%d): %d files read, %d wrong, %d failed opens logged\n", (int)tight.rlim_cur,
           (nfiles + 2) / 3, bad, failed_opens);
    CHECK(bad == 0, "under a tight descriptor limit %d files read wrong", bad);
    CHECK(failed_opens == 0, "under a tight descriptor limit %d opens failed", failed_opens);
    setrlimit(RLIMIT_NOFILE, &rl);

    // 4. a mod file that vanished: zero-filled, and logged (never silent)
    before = count_log(log, "overlay open failed");
    memset(buf, 0xAA, 4096);
    ssize_t got = romfs_read(-1, buf, 4096, ov[nfiles].start);
    int zeros = 1;
    for (int j = 0; j < 4096; j++) zeros &= buf[j] == 0;
    int logged = count_log(log, "overlay open failed") - before;
    printf("4. missing file: read returned %zd, zero-filled %s, failure logged %d time(s)\n", got, zeros ? "yes" : "no",
           logged);
    CHECK(got == 4096 && zeros, "missing overlay file: not a zero-filled full read");
#ifdef ROMFS_OVERLAY_FD_LIMIT
    CHECK(logged == 1, "missing overlay file: open failure logged %d times (want 1)", logged);
#endif

    // 5. reboot (fs_reset): every overlay descriptor closed
    int open_before_reset = open_fds() - baseline;
    fs_reset();
    int after = open_fds() - baseline;
    printf("5. fs_reset: extra fds %d -> %d\n", open_before_reset, after);
    CHECK(after <= 0, "fs_reset left %d descriptors open", after);

    printf("max extra fds over the run: %d (bound %d)\n", max_fds_seen, TEST_FD_BOUND);
    printf(failures ? "FAILED (%d)\n" : "PASS\n", failures);
    if (!failures) {
        for (int k = 0; k < nfiles; k++) {
            char p[512];
            snprintf(p, sizeof p, "%s/f%05d.bin", dir, k);
            unlink(p);
        }
        unlink(log);
        rmdir(dir);
    } else {
        printf("log: %s\n", log);
    }
    return failures != 0;
}
