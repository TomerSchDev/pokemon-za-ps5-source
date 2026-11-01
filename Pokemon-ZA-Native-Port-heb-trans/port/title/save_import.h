/* One-shot import before guest startup. The caller provides fixed trusted paths
 * and the pinned size/FNV; deployment separately verifies the source SHA-256.
 * A journal blocks automatic retries after interruption. A valid completion
 * marker prevents reimporting over subsequent gameplay. All old data is retained.
 * Header-local implementation lets the host integration test use identical code. */
#ifndef ZA_SAVE_IMPORT_H
#define ZA_SAVE_IMPORT_H
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int za_save_path(char out[1024], const char *dir, const char *name) {
    int n = snprintf(out, 1024, "%s/%s", dir, name);
    return n < 0 || n >= 1024 ? -1 : 0;
}
static int za_save_exists(const char *path) {
    struct stat st;
    if (stat(path, &st) == 0) return 1;
    return errno == ENOENT ? 0 : -1;
}
static int za_save_dirs(const char *path) {
    char tmp[1024];
    if (!path || path[0] != '/' || strlen(path) >= sizeof tmp) return -1;
    strcpy(tmp, path);
    for (char *p = tmp + 1;; ++p) {
        if (*p && *p != '/') continue;
        char saved = *p; *p = 0;
        struct stat st;
        if ((mkdir(tmp, 0700) && errno != EEXIST) || stat(tmp, &st) || !S_ISDIR(st.st_mode)) return -1;
        *p = saved;
        if (!saved) return 0;
    }
}
static int za_save_write_new(const char *path, const unsigned char *data, size_t size) {
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return -1;
    size_t pos = 0;
    while (pos < size) {
        ssize_t n = write(fd, data + pos, size - pos);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); return -1; }
        pos += (size_t)n;
    }
    return close(fd);
}
static int za_save_matches(const char *path, const unsigned char *data, size_t size) {
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    unsigned char block[16384]; size_t pos = 0;
    while (pos < size) {
        size_t want = size - pos < sizeof block ? size - pos : sizeof block;
        if (fread(block, 1, want, f) != want || memcmp(block, data + pos, want)) { fclose(f); return 0; }
        pos += want;
    }
    int ok = fgetc(f) == EOF && !ferror(f);
    if (fclose(f)) ok = 0;
    return ok;
}

/* 0 = no request/already applied; 1 = imported; -1 = stop boot, preserve evidence. */
static int za_import_save_once(const char *source, const char *dir, const char *id,
                               size_t expected_size, uint64_t expected_hash) {
    char main_path[1024], backup[1024], pending[1024], done[1024], journal[1024], name[128];
    if (!source || source[0] != '/' || !id || !*id || strlen(id) > 64 || !expected_size) return -1;
    for (const char *p = id; *p; p++) if (!((*p >= 'a' && *p <= 'z') || (*p >= '0' && *p <= '9') || *p == '-')) return -1;
    if (za_save_path(main_path, dir, "main")) return -1;
    snprintf(name, sizeof name, "main.before-%s", id);
    if (za_save_path(backup, dir, name)) return -1;
    snprintf(name, sizeof name, "main.import-%s.tmp", id);
    if (za_save_path(pending, dir, name)) return -1;
    snprintf(name, sizeof name, ".import-%s.done", id);
    if (za_save_path(done, dir, name)) return -1;
    snprintf(name, sizeof name, ".import-%s.in-progress", id);
    if (za_save_path(journal, dir, name)) return -1;
    const size_t marker_size = strlen(id);
    int exists = za_save_exists(done);
    if (exists) return exists > 0 && za_save_matches(done, (const unsigned char *)id, marker_size) ? 0 : -1;
    exists = za_save_exists(source);
    if (exists <= 0) return exists; /* No staged request: ordinary boot. */
    if (za_save_exists(journal) || za_save_exists(backup) || za_save_exists(pending)) return -1;
    unsigned char *data = malloc(expected_size);
    if (!data) return -1;
    FILE *f = fopen(source, "rb");
    if (!f) { free(data); return -1; }
    int valid = fread(data, 1, expected_size, f) == expected_size && fgetc(f) == EOF && !ferror(f);
    if (fclose(f)) valid = 0;
    uint64_t hash = UINT64_C(0xcbf29ce484222325);
    if (valid) for (size_t i = 0; i < expected_size; i++) hash = (hash ^ data[i]) * UINT64_C(0x100000001b3);
    if (!valid || hash != expected_hash || za_save_dirs(dir)) { free(data); return -1; }
    if (za_save_write_new(journal, (const unsigned char *)id, marker_size) ||
        za_save_write_new(pending, data, expected_size) || !za_save_matches(pending, data, expected_size)) {
        free(data); return -1;
    }
    int had_main = za_save_exists(main_path);
    if (had_main < 0 || (had_main && rename(main_path, backup))) { free(data); return -1; }
    if (rename(pending, main_path)) {
        if (had_main) (void)rename(backup, main_path);
        free(data); return -1;
    }
    if (!za_save_matches(main_path, data, expected_size) ||
        za_save_write_new(done, (const unsigned char *)id, marker_size) ||
        !za_save_matches(done, (const unsigned char *)id, marker_size)) { free(data); return -1; }
    free(data);
    (void)unlink(journal); /* A valid done marker wins if journal cleanup fails. */
    return 1;
}
#endif
