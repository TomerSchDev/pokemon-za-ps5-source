/* Publish a run generated off-console (same generator, same assets) and make it the active run.
 * Copies /data/homebrew/PPSA91762/<SRC_DIR>/<files> into rando/.pending-<RUN_ID>, verifies every byte, renames it to
 * rando/<RUN_ID>, keeps active.json as active.before-<RUN_ID>.json and writes the new active.json. Never overwrites a
 * run; existing runs and saves are untouched. Runs as a payload while PPSA91762 is mounted at its menu. */
#define _DEFAULT_SOURCE 1
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#if !defined(RUN_ID) || !defined(SRC_DIR) || !defined(RUN_FILES)
#error "RUN_ID, SRC_DIR and RUN_FILES (C array initializer of relative paths) are required"
#endif
#define APP "/data/homebrew/PPSA91762"
#define DATA "/mnt/sandbox/PPSA91762_000/download0/zarecomp"
#define RANDO DATA "/rando"
#define SRC APP "/" SRC_DIR
#define STAGE RANDO "/.pending-" RUN_ID
#define FINAL RANDO "/" RUN_ID
#define LOG "/data/main-push-run.log"
static const char *files[] = RUN_FILES;
static unsigned char a[1 << 18], b[1 << 18];
static FILE *f;
static int same(const char *x, const char *y) {
 FILE *p = fopen(x, "rb"), *q = fopen(y, "rb"); int ok = p && q;
 while (ok) { size_t n = fread(a, 1, sizeof a, p), m = fread(b, 1, sizeof b, q);
  if (n != m || memcmp(a, b, n)) ok = 0; if (n < sizeof a) { if (ferror(p) || ferror(q)) ok = 0; break; } }
 if (p) fclose(p); if (q) fclose(q); return ok;
}
static int copy_new(const char *src, const char *dst) {
 FILE *in = fopen(src, "rb"); if (!in) return -1;
 int fd = open(dst, O_CREAT | O_EXCL | O_WRONLY, 0666); if (fd < 0) { fclose(in); return -1; }
 FILE *out = fdopen(fd, "wb"); if (!out) { close(fd); fclose(in); return -1; }
 size_t n; int bad = 0;
 while ((n = fread(a, 1, sizeof a, in))) if (fwrite(a, 1, n, out) != n) { bad = 1; break; }
 bad |= ferror(in); fclose(in);
 if (fflush(out) || fsync(fd) || fclose(out) || chmod(dst, 0666)) bad = 1;
 return bad || !same(src, dst) ? -1 : 0;
}
static int parents(const char *path) {
 char p[1400]; if (strlen(path) >= sizeof p) return -1; strcpy(p, path);
 for (size_t i = strlen(STAGE) + 1; p[i]; i++) if (p[i] == '/') { p[i] = 0; struct stat s;
  if (stat(p, &s)) { if (errno != ENOENT || mkdir(p, 0777) || chmod(p, 0777)) return -1; }
  else if (!S_ISDIR(s.st_mode)) return -1; p[i] = '/'; }
 return 0;
}
int main(void) {
 f = fopen(LOG, "w"); if (!f) return 1; setvbuf(f, NULL, _IONBF, 0);
 fprintf(f, "START push run %s (existing runs and saves untouched)\n", RUN_ID);
 struct stat rs, s; int rc = 2, published = 0;
 if (stat(RANDO, &rs)) { fprintf(f, "FAILED rando stat errno=%d\n", errno); goto end; }
 if (chmod(RANDO, 0777)) { fprintf(f, "FAILED rando chmod errno=%d\n", errno); goto end; }
 if (!stat(FINAL, &s) || !stat(STAGE, &s)) { fprintf(f, "REFUSED run or pending folder already exists\n"); goto restore; }
 if (mkdir(STAGE, 0777) || chmod(STAGE, 0777)) { fprintf(f, "FAILED stage mkdir errno=%d\n", errno); goto restore; }
 for (unsigned i = 0; i < sizeof files / sizeof files[0]; i++) {
  char src[1400], dst[1400]; snprintf(src, sizeof src, SRC "/%s", files[i]); snprintf(dst, sizeof dst, STAGE "/%s", files[i]);
  if (parents(dst) || copy_new(src, dst)) { fprintf(f, "FAILED copy %s errno=%d\n", files[i], errno); goto restore; }
  fprintf(f, "COPIED %s\n", files[i]); }
 if (rename(STAGE, FINAL)) { fprintf(f, "FAILED publish errno=%d\n", errno); goto restore; }
 published = 1;
 if (copy_new(RANDO "/active.json", RANDO "/active.before-" RUN_ID ".json")) { fprintf(f, "FAILED keep active.json\n"); goto restore; }
 { char json[256]; int n = snprintf(json, sizeof json, "{\n  \"id\": \"%s\",\n  \"schema\": 1\n}", RUN_ID);
   int fd = open(RANDO "/active.json.new", O_CREAT | O_EXCL | O_WRONLY, 0666);
   if (fd < 0 || write(fd, json, n) != n || fsync(fd) || close(fd) || chmod(RANDO "/active.json.new", 0666)) {
    fprintf(f, "FAILED write active.json.new errno=%d\n", errno); unlink(RANDO "/active.json.new"); goto restore; }
   if (rename(RANDO "/active.json.new", RANDO "/active.json")) { fprintf(f, "FAILED swap active.json errno=%d\n", errno); goto restore; } }
 rc = 0;
restore:
 if (rc && published) { rename(FINAL, STAGE); fprintf(f, "UNPUBLISHED %s (left as %s)\n", FINAL, STAGE); }
 chmod(RANDO, rs.st_mode & 0777);
end:
 fprintf(f, "%s run=%s; restart required\n", rc ? "FAILED" : "COMPLETE", RUN_ID);
 fclose(f); return rc;
}
