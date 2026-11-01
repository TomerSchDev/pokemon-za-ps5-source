/* za_slot.h - the randomizer's per-run slot container, rando/<run id>/slot.zrs (format "ZARSLOT" 1.1).
 *
 * Header-only C11 (also valid C++20 under -Wall -Wextra -Werror, no exceptions/RTTI), so the C runtime (the
 * save-commit writer, a later branch) and the C++ launcher (the reader) share one implementation without a new link
 * object. Define ZA_SLOT_IMPLEMENTATION in exactly one translation unit before including it.
 *
 * Purpose: the launcher's save-slot cards need date, location, caught/seen and the run's settings without parsing a
 * 3 MB encrypted game save for every run. The container is written NEXT TO the game's own save, never instead of it:
 * the game save (rando/<id>/save/save_0/main) stays the source of truth and is never modified by this code.
 *
 * Layout (all integers little-endian):
 *   0x00  char[8]  magic "ZARSLOT\0"
 *   0x08  u16      version_major (1; a reader rejects any other major)
 *   0x0A  u16      version_minor (1; a newer minor may only append fields/sections - readers ignore what they do not know)
 *   0x0C  u32      header_size (64)
 *   0x10  u32      section_count (1..16)
 *   0x14  u32      flags (0)
 *   0x18  u64      file_size (the whole file)
 *   0x20  u32      table_crc32 (CRC-32/ISO-HDLC over bytes [0, 0x20) and the section table)
 *   0x24  ...      zero to 0x40
 *   0x40  section table: section_count x 32 bytes
 *           u32 type (FourCC, see ZA_SLOT_*), u32 flags (0 = stored), u64 offset, u64 length, u32 crc32, u32 zero
 *   then the sections, in this order: SUMM (1.0: 256 bytes, 1.1: 320; a reader needs only the first 0x40+N*32+SUMM bytes),
 *   RAND (JSON: randomizer extra info), SETT (JSON: seed + ui_options as in report.json), SAVE (the game save bytes).
 *
 * SUMM v1 (256 bytes):
 *   0x00 u32 summary_version (1)      0x04 u32 flags (ZA_SLOT_HAS_*)
 *   0x08 u64 save_unix_time           0x10 u64 created_unix_time
 *   0x18 u32 caught                   0x1C u32 seen
 *   0x20 u32 save_size                0x24 u32 zero
 *   0x28 u8[32] save_sha256 (zero when not computed)
 *   0x48 char[48] run_id   0x78 char[24] seed   0x90 char[32] location (game map name, ASCII)
 *   0xB0 char[32] generator algorithm   0xD0 char[48] game build id          (all NUL-padded, always NUL-terminated)
 * SUMM v2 (1.1, 320 bytes) = v1 + (summary_version 2):
 *   0x100 u32 story_phase (system_work SYS_WORK_PHASE, e.g. 21110)   0x104 u32 dlc_phase (SYS_WORK_DLC_PHASE)
 *   0x108 u32 research_level (Mable's research, block 0x85DBDCE9 @0)  0x10C u32 research_points (@8)
 *   0x110 f32 x, 0x114 f32 z, 0x118 f32 y (player position, block 0x910D381F: x @0x20, height y @0x24, z @0x28 -
 *   checked against the game's own jump points; PKHeX's Coordinates9a names +0x24 "Z")   0x11C..0x140 zero
 * A 1.0 file (256-byte SUMM) still reads: the v2 fields stay unknown (their ZA_SLOT_HAS_* flags clear).
 */
#ifndef ZA_SLOT_H
#define ZA_SLOT_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ZA_SLOT_MAGIC "ZARSLOT"
#define ZA_SLOT_VERSION_MAJOR 1u
#define ZA_SLOT_VERSION_MINOR 1u
#define ZA_SLOT_HEADER_SIZE 64u
#define ZA_SLOT_ENTRY_SIZE 32u
#define ZA_SLOT_MAX_SECTIONS 16u
#define ZA_SLOT_SUMMARY_SIZE 320u     /* written by 1.1 */
#define ZA_SLOT_SUMMARY_V1_SIZE 256u  /* the smallest SUMM a reader accepts (1.0) */
#define ZA_SLOT_SUMMARY_MAX 512u      /* the largest SUMM the head reader loads */
#define ZA_SLOT_FOURCC(a, b, c, d) ((uint32_t)(a) | (uint32_t)(b) << 8 | (uint32_t)(c) << 16 | (uint32_t)(d) << 24)
#define ZA_SLOT_SUMM ZA_SLOT_FOURCC('S', 'U', 'M', 'M')
#define ZA_SLOT_RAND ZA_SLOT_FOURCC('R', 'A', 'N', 'D')
#define ZA_SLOT_SETT ZA_SLOT_FOURCC('S', 'E', 'T', 'T')
#define ZA_SLOT_SAVE ZA_SLOT_FOURCC('S', 'A', 'V', 'E')

/* SUMM flags */
#define ZA_SLOT_HAS_CAUGHT 1u
#define ZA_SLOT_HAS_SEEN 2u
#define ZA_SLOT_HAS_LOCATION 4u
#define ZA_SLOT_HAS_SAVE_HASH 8u
#define ZA_SLOT_HAS_PHASE 16u     /* story_phase and dlc_phase */
#define ZA_SLOT_HAS_RESEARCH 32u  /* research_level and research_points */
#define ZA_SLOT_HAS_POSITION 64u  /* x, y, z */

typedef struct za_slot_summary {
    uint32_t flags;
    uint64_t save_time, created_time;
    uint32_t caught, seen, save_size;
    uint8_t save_sha256[32];
    char run_id[48], seed[24], location[32], algorithm[32], build_id[48];
    /* 1.1 */
    uint32_t story_phase, dlc_phase, research_level, research_points;
    float x, y, z;
} za_slot_summary;

/* Reader results */
enum { ZA_SLOT_OK = 0, ZA_SLOT_MISSING = 1, ZA_SLOT_TRUNCATED = 2, ZA_SLOT_BAD_MAGIC = 3, ZA_SLOT_NEWER_MAJOR = 4,
       ZA_SLOT_BAD_TABLE = 5, ZA_SLOT_BAD_CRC = 6, ZA_SLOT_NO_SUMMARY = 7, ZA_SLOT_IO = 8 };
const char *za_slot_result_name(int result);

uint32_t za_slot_crc32(uint32_t crc, const void *data, size_t n);

/* Builds a container into out[0..cap). Returns the size needed (out may be NULL / cap too small: nothing written). */
size_t za_slot_build(uint8_t *out, size_t cap, const za_slot_summary *summary, const char *rand_json, size_t rand_len,
                     const char *sett_json, size_t sett_len, const uint8_t *save, size_t save_len);

/* Parses the summary from the first `n` bytes of a container (n may be the whole file or just its head: the header,
 * the table and SUMM are enough). Checks magic, major version, table CRC, bounds, SUMM CRC. */
int za_slot_parse_summary(const uint8_t *head, size_t n, za_slot_summary *out);

/* Full check of a complete file: every section's bounds and CRC, file_size. */
int za_slot_verify(const uint8_t *file, size_t n);

/* A section of a verified complete file (first of that type). Returns ZA_SLOT_OK or ZA_SLOT_NO_SUMMARY (not found). */
int za_slot_section(const uint8_t *file, size_t n, uint32_t type, const uint8_t **data, size_t *len);

/* Reads only the head of `path` (open + read of at most 0x40 + 16*32 + 512 bytes) and parses the summary. */
int za_slot_read_summary_file(const char *path, za_slot_summary *out);

/* Writes `data` to `path` atomically: unlink only <path>.new -> exclusive create -> write -> fsync -> close -> rename.
 * Returns 0 on success, else -1 with errno set; a temp created by this call is removed after an IO failure.
 * A name inserted before exclusive creation is left untouched. The previous slot stays on failure. */
int za_slot_write_atomic(const char *path, const uint8_t *data, size_t n);

/* Reads caught / seen counts (Pokedex block 0x2D87BE5C: 0x84-byte entries by internal species index, u32 caught-forms
 * @0, u32 seen-forms @4, then a tail that is not an entry (2.0.2: 0x27068 bytes = 1210 entries + 0x80);
 * PKHeX Zukan9a / PokeDexEntry9a) and the map name (block 0x910D381F, char[0x20] @0; PKHeX Coordinates9a) from an
 * ENCRYPTED Z-A main save (SwishCrypto: xorpad + per-block SCXorShift32; the caller's buffer is not modified - a
 * block is decrypted into scratch). `sha256` (may be NULL) checks the trailing hash first. Returns ZA_SLOT_HAS_*
 * flags of what was found (0 = nothing / not a valid save). */
typedef int (*za_slot_sha256_fn)(const uint8_t *data, size_t n, uint8_t out[32]);
uint32_t za_slot_save_progress(const uint8_t *save, size_t n, za_slot_sha256_fn sha256, uint32_t *caught, uint32_t *seen,
                               char location[32]);

/* Everything the slot card reads from the save, into `s` (only these fields are written: caught, seen, location,
 * story_phase, dlc_phase, research_level, research_points, x, y, z). Also:
 *   system_work block 0xFADA7742: (u64 key, u64 value) pairs, key = FNV-1a-64 with GF's offset basis
 *     0xCBF29CE484222645 over the name (PKHeX FnvHash): SYS_WORK_PHASE 0x992FE2A6DEC12926,
 *     SYS_WORK_DLC_PHASE 0xD479E73FCE51A050;
 *   Mable status block 0x85DBDCE9: u32 LevelCurrent @0, u32 Points @8 (PKHeX MableStatus9a).
 * Returns the ZA_SLOT_HAS_* flags found (0 = not a valid save). */
uint32_t za_slot_save_read(const uint8_t *save, size_t n, za_slot_sha256_fn sha256, za_slot_summary *s);

/* For the in-game writer: a new container with a fresh summary and save copy, keeping the RAND and SETT sections of
 * `old` (a complete container that must pass za_slot_verify). Returns the size needed, 0 when `old` is unusable. */
size_t za_slot_rebuild(uint8_t *out, size_t cap, const uint8_t *old, size_t old_len, const za_slot_summary *summary,
                       const uint8_t *save, size_t save_len);

#ifdef __cplusplus
}
#endif
#endif /* ZA_SLOT_H */

#ifdef ZA_SLOT_IMPLEMENTATION
#ifndef ZA_SLOT_IMPLEMENTED
#define ZA_SLOT_IMPLEMENTED
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#ifdef _WIN32  /* rename() refuses an existing target there: the atomic replace is MoveFileEx's */
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif
#ifndef O_BINARY
#define O_BINARY 0
#endif


#ifdef __cplusplus
extern "C" {
#endif

static uint16_t za_slot_rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t za_slot_rd32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t za_slot_rd64(const uint8_t *p) { return (uint64_t)za_slot_rd32(p) | (uint64_t)za_slot_rd32(p + 4) << 32; }
static void za_slot_wr16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void za_slot_wr32(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i)); }
static void za_slot_wr64(uint8_t *p, uint64_t v) { for (int i = 0; i < 8; i++) p[i] = (uint8_t)(v >> (8 * i)); }
static void za_slot_wrf32(uint8_t *p, float f) { uint32_t v; memcpy(&v, &f, 4); za_slot_wr32(p, v); }
static float za_slot_rdf32(const uint8_t *p) { uint32_t v = za_slot_rd32(p); float f; memcpy(&f, &v, 4); return f; }

const char *za_slot_result_name(int r) {
    switch (r) {
        case ZA_SLOT_OK: return "ok";
        case ZA_SLOT_MISSING: return "missing";
        case ZA_SLOT_TRUNCATED: return "truncated";
        case ZA_SLOT_BAD_MAGIC: return "bad magic";
        case ZA_SLOT_NEWER_MAJOR: return "newer major version";
        case ZA_SLOT_BAD_TABLE: return "bad section table";
        case ZA_SLOT_BAD_CRC: return "checksum mismatch";
        case ZA_SLOT_NO_SUMMARY: return "section missing";
        case ZA_SLOT_IO: return "read error";
        default: return "unknown";
    }
}

uint32_t za_slot_crc32(uint32_t crc, const void *data, size_t n) {
    /* CRC-32/ISO-HDLC (zlib's crc32), nibble table: no init, no global state */
    static const uint32_t t[16] = {0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu, 0x76DC4190u, 0x6B6B51F4u,
                                   0x4DB26158u, 0x5005713Cu, 0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu,
                                   0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu};
    const uint8_t *p = (const uint8_t *)data;
    crc = ~crc;
    for (size_t i = 0; i < n; i++) {
        crc ^= p[i];
        crc = (crc >> 4) ^ t[crc & 15];
        crc = (crc >> 4) ^ t[crc & 15];
    }
    return ~crc;
}

static void za_slot_putstr(uint8_t *dst, size_t cap, const char *s) {
    memset(dst, 0, cap);
    if (!s) return;
    size_t n = strlen(s);
    if (n > cap - 1) n = cap - 1;
    memcpy(dst, s, n);
}
static void za_slot_getstr(char *dst, size_t cap, const uint8_t *src) {
    memcpy(dst, src, cap);
    dst[cap - 1] = 0;
}

size_t za_slot_build(uint8_t *out, size_t cap, const za_slot_summary *s, const char *rand_json, size_t rand_len,
                     const char *sett_json, size_t sett_len, const uint8_t *save, size_t save_len) {
    const uint32_t count = 4;
    const size_t table = ZA_SLOT_HEADER_SIZE, data0 = table + count * ZA_SLOT_ENTRY_SIZE;
    const size_t lens[4] = {ZA_SLOT_SUMMARY_SIZE, rand_len, sett_len, save_len};
    const uint32_t types[4] = {ZA_SLOT_SUMM, ZA_SLOT_RAND, ZA_SLOT_SETT, ZA_SLOT_SAVE};
    size_t total = data0;
    for (int i = 0; i < 4; i++) total += lens[i];
    if (!out || cap < total || !s) return total;
    memset(out, 0, data0 + ZA_SLOT_SUMMARY_SIZE);
    memcpy(out, ZA_SLOT_MAGIC, 8);
    za_slot_wr16(out + 0x08, (uint16_t)ZA_SLOT_VERSION_MAJOR);
    za_slot_wr16(out + 0x0A, (uint16_t)ZA_SLOT_VERSION_MINOR);
    za_slot_wr32(out + 0x0C, ZA_SLOT_HEADER_SIZE);
    za_slot_wr32(out + 0x10, count);
    za_slot_wr64(out + 0x18, (uint64_t)total);
    /* SUMM */
    uint8_t *m = out + data0;
    za_slot_wr32(m + 0x00, 2);
    za_slot_wr32(m + 0x04, s->flags);
    za_slot_wr64(m + 0x08, s->save_time);
    za_slot_wr64(m + 0x10, s->created_time);
    za_slot_wr32(m + 0x18, s->caught);
    za_slot_wr32(m + 0x1C, s->seen);
    za_slot_wr32(m + 0x20, (uint32_t)save_len);
    memcpy(m + 0x28, s->save_sha256, 32);
    za_slot_putstr(m + 0x48, 48, s->run_id);
    za_slot_putstr(m + 0x78, 24, s->seed);
    za_slot_putstr(m + 0x90, 32, s->location);
    za_slot_putstr(m + 0xB0, 32, s->algorithm);
    za_slot_putstr(m + 0xD0, 48, s->build_id);
    za_slot_wr32(m + 0x100, s->story_phase);
    za_slot_wr32(m + 0x104, s->dlc_phase);
    za_slot_wr32(m + 0x108, s->research_level);
    za_slot_wr32(m + 0x10C, s->research_points);
    za_slot_wrf32(m + 0x110, s->x);
    za_slot_wrf32(m + 0x114, s->z);
    za_slot_wrf32(m + 0x118, s->y);
    size_t at = data0 + ZA_SLOT_SUMMARY_SIZE;
    if (rand_len) memcpy(out + at, rand_json, rand_len);
    at += rand_len;
    if (sett_len) memcpy(out + at, sett_json, sett_len);
    at += sett_len;
    if (save_len) memcpy(out + at, save, save_len);
    /* table */
    at = data0;
    for (uint32_t i = 0; i < count; i++) {
        uint8_t *e = out + table + i * ZA_SLOT_ENTRY_SIZE;
        za_slot_wr32(e + 0, types[i]);
        za_slot_wr32(e + 4, 0);
        za_slot_wr64(e + 8, (uint64_t)at);
        za_slot_wr64(e + 16, (uint64_t)lens[i]);
        za_slot_wr32(e + 24, za_slot_crc32(0, out + at, lens[i]));
        za_slot_wr32(e + 28, 0);
        at += lens[i];
    }
    uint32_t crc = za_slot_crc32(0, out, 0x20);
    crc = za_slot_crc32(crc, out + table, count * ZA_SLOT_ENTRY_SIZE);
    za_slot_wr32(out + 0x20, crc);
    return total;
}

/* header + table checks shared by the summary reader and the full verify */
static int za_slot_check_head(const uint8_t *h, size_t n, uint32_t *count, uint64_t *file_size) {
    if (n < ZA_SLOT_HEADER_SIZE) return ZA_SLOT_TRUNCATED;
    if (memcmp(h, ZA_SLOT_MAGIC, 8)) return ZA_SLOT_BAD_MAGIC;
    if (za_slot_rd16(h + 0x08) != ZA_SLOT_VERSION_MAJOR) return ZA_SLOT_NEWER_MAJOR;
    const uint32_t hs = za_slot_rd32(h + 0x0C), c = za_slot_rd32(h + 0x10);
    if (hs < ZA_SLOT_HEADER_SIZE || hs > 4096 || c < 1 || c > ZA_SLOT_MAX_SECTIONS) return ZA_SLOT_BAD_TABLE;
    if (hs != ZA_SLOT_HEADER_SIZE) return ZA_SLOT_BAD_TABLE; /* 1.x keeps the 64-byte header */
    if (n < (size_t)hs + c * ZA_SLOT_ENTRY_SIZE) return ZA_SLOT_TRUNCATED;
    uint32_t crc = za_slot_crc32(0, h, 0x20);
    crc = za_slot_crc32(crc, h + hs, c * ZA_SLOT_ENTRY_SIZE);
    if (crc != za_slot_rd32(h + 0x20)) return ZA_SLOT_BAD_CRC;
    const uint64_t fs = za_slot_rd64(h + 0x18);
    for (uint32_t i = 0; i < c; i++) {
        const uint8_t *e = h + hs + i * ZA_SLOT_ENTRY_SIZE;
        const uint64_t off = za_slot_rd64(e + 8), len = za_slot_rd64(e + 16);
        if (off < (uint64_t)hs + c * ZA_SLOT_ENTRY_SIZE || off > fs || len > fs - off) return ZA_SLOT_BAD_TABLE;
    }
    *count = c;
    *file_size = fs;
    return ZA_SLOT_OK;
}

int za_slot_parse_summary(const uint8_t *h, size_t n, za_slot_summary *out) {
    uint32_t count = 0;
    uint64_t fs = 0;
    int r = za_slot_check_head(h, n, &count, &fs);
    if (r) return r;
    for (uint32_t i = 0; i < count; i++) {
        const uint8_t *e = h + ZA_SLOT_HEADER_SIZE + i * ZA_SLOT_ENTRY_SIZE;
        if (za_slot_rd32(e) != ZA_SLOT_SUMM) continue;
        const uint64_t off = za_slot_rd64(e + 8), len = za_slot_rd64(e + 16);
        if (len < ZA_SLOT_SUMMARY_V1_SIZE || len > 65536) return ZA_SLOT_BAD_TABLE;
        if (off + len > (uint64_t)n) return ZA_SLOT_TRUNCATED;
        const uint8_t *m = h + off;
        if (za_slot_crc32(0, m, (size_t)len) != za_slot_rd32(e + 24)) return ZA_SLOT_BAD_CRC;
        if (za_slot_rd32(m) < 1) return ZA_SLOT_BAD_TABLE;
        memset(out, 0, sizeof *out);
        out->flags = za_slot_rd32(m + 0x04);
        out->save_time = za_slot_rd64(m + 0x08);
        out->created_time = za_slot_rd64(m + 0x10);
        out->caught = za_slot_rd32(m + 0x18);
        out->seen = za_slot_rd32(m + 0x1C);
        out->save_size = za_slot_rd32(m + 0x20);
        memcpy(out->save_sha256, m + 0x28, 32);
        za_slot_getstr(out->run_id, 48, m + 0x48);
        za_slot_getstr(out->seed, 24, m + 0x78);
        za_slot_getstr(out->location, 32, m + 0x90);
        za_slot_getstr(out->algorithm, 32, m + 0xB0);
        za_slot_getstr(out->build_id, 48, m + 0xD0);
        if (za_slot_rd32(m) >= 2 && len >= 0x140) {
            out->story_phase = za_slot_rd32(m + 0x100);
            out->dlc_phase = za_slot_rd32(m + 0x104);
            out->research_level = za_slot_rd32(m + 0x108);
            out->research_points = za_slot_rd32(m + 0x10C);
            out->x = za_slot_rdf32(m + 0x110);
            out->z = za_slot_rdf32(m + 0x114);
            out->y = za_slot_rdf32(m + 0x118);
        } else {
            out->flags &= ~(ZA_SLOT_HAS_PHASE | ZA_SLOT_HAS_RESEARCH | ZA_SLOT_HAS_POSITION);
        }
        return ZA_SLOT_OK;
    }
    return ZA_SLOT_NO_SUMMARY;
}

int za_slot_verify(const uint8_t *f, size_t n) {
    uint32_t count = 0;
    uint64_t fs = 0;
    int r = za_slot_check_head(f, n, &count, &fs);
    if (r) return r;
    if (fs != (uint64_t)n) return ZA_SLOT_TRUNCATED;
    int summ = 0;
    for (uint32_t i = 0; i < count; i++) {
        const uint8_t *e = f + ZA_SLOT_HEADER_SIZE + i * ZA_SLOT_ENTRY_SIZE;
        const uint64_t off = za_slot_rd64(e + 8), len = za_slot_rd64(e + 16);
        if (za_slot_crc32(0, f + off, (size_t)len) != za_slot_rd32(e + 24)) return ZA_SLOT_BAD_CRC;
        if (za_slot_rd32(e) == ZA_SLOT_SUMM) summ = 1;
    }
    return summ ? ZA_SLOT_OK : ZA_SLOT_NO_SUMMARY;
}

int za_slot_section(const uint8_t *f, size_t n, uint32_t type, const uint8_t **data, size_t *len) {
    uint32_t count = 0;
    uint64_t fs = 0;
    int r = za_slot_check_head(f, n, &count, &fs);
    if (r) return r;
    for (uint32_t i = 0; i < count; i++) {
        const uint8_t *e = f + ZA_SLOT_HEADER_SIZE + i * ZA_SLOT_ENTRY_SIZE;
        if (za_slot_rd32(e) != type) continue;
        const uint64_t off = za_slot_rd64(e + 8), l = za_slot_rd64(e + 16);
        if (off + l > (uint64_t)n) return ZA_SLOT_TRUNCATED;
        *data = f + off;
        *len = (size_t)l;
        return ZA_SLOT_OK;
    }
    return ZA_SLOT_NO_SUMMARY;
}

int za_slot_read_summary_file(const char *path, za_slot_summary *out) {
    enum { HeadMax = ZA_SLOT_HEADER_SIZE + ZA_SLOT_MAX_SECTIONS * ZA_SLOT_ENTRY_SIZE + ZA_SLOT_SUMMARY_MAX };
    uint8_t head[HeadMax];
    int fd = open(path, O_RDONLY | O_BINARY);
    if (fd < 0) return errno == ENOENT ? ZA_SLOT_MISSING : ZA_SLOT_IO;
    size_t got = 0;
    while (got < sizeof head) {
        ssize_t r = read(fd, head + got, sizeof head - got);
        if (r < 0 && errno == EINTR) continue;
        if (r < 0) { close(fd); return ZA_SLOT_IO; }
        if (r == 0) break;
        got += (size_t)r;
    }
    close(fd);
    return za_slot_parse_summary(head, got, out);
}

int za_slot_write_atomic(const char *path, const uint8_t *data, size_t n) {
    char temp[1100];
    if (snprintf(temp, sizeof temp, "%s.new", path) >= (int)sizeof temp) { errno = ENAMETOOLONG; return -1; }
    /* The launcher and the in-game writer run at different times; each has one
     * writer. A stale private temp may be a symlink: unlink its name, never
     * truncate/follow its target. An insertion after unlink is rejected by
     * O_EXCL. Unexpected unlink failures preserve the old slot unchanged. */
    if (unlink(temp) && errno != ENOENT) return -1;
    int flags = O_WRONLY | O_CREAT | O_EXCL | O_BINARY;
#ifdef O_NOFOLLOW
    flags |= O_NOFOLLOW;
#endif
    int fd = open(temp, flags, 0644);
    if (fd < 0) return -1;
    size_t at = 0;
    int ok = 1;
    while (at < n) {
        ssize_t w = write(fd, data + at, n - at);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) { ok = 0; break; }
        at += (size_t)w;
    }
    int saved = errno;
    if (ok && fsync(fd)) { ok = 0; saved = errno; }
    if (close(fd) && ok) { ok = 0; saved = errno; }
#ifdef _WIN32
    if (ok && !MoveFileExA(temp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) { ok = 0; saved = EACCES; }
#else
    if (ok && rename(temp, path)) { ok = 0; saved = errno; }
#endif
    if (!ok) { unlink(temp); errno = saved; return -1; }
    return 0;
}

/* ---- SwishCrypto reading (same constants as port/rando-v2/za_player_name.cpp; PKHeX SwishCrypto) */
static const uint8_t za_slot_xorpad[0x7F] = {
    0xA0, 0x92, 0xD1, 0x06, 0x07, 0xDB, 0x32, 0xA1, 0xAE, 0x01, 0xF5, 0xC5, 0x1E, 0x84, 0x4F, 0xE3, 0x53, 0xCA, 0x37, 0xF4,
    0xA7, 0xB0, 0x4D, 0xA0, 0x18, 0xB7, 0xC2, 0x97, 0xDA, 0x5F, 0x53, 0x2B, 0x75, 0xFA, 0x48, 0x16, 0xF8, 0xD4, 0x8A, 0x6F,
    0x61, 0x05, 0xF4, 0xE2, 0xFD, 0x04, 0xB5, 0xA3, 0x0F, 0xFC, 0x44, 0x92, 0xCB, 0x32, 0xE6, 0x1B, 0xB9, 0xB1, 0x2E, 0x01,
    0xB0, 0x56, 0x53, 0x36, 0xD2, 0xD1, 0x50, 0x3D, 0xDE, 0x5B, 0x2E, 0x0E, 0x52, 0xFD, 0xDF, 0x2F, 0x7B, 0xCA, 0x63, 0x50,
    0xA4, 0x67, 0x5D, 0x23, 0x17, 0xC0, 0x52, 0xE1, 0xA6, 0x30, 0x7C, 0x2B, 0xB6, 0x70, 0x36, 0x5B, 0x2A, 0x27, 0x69, 0x33,
    0xF5, 0x63, 0x7B, 0x36, 0x3F, 0x26, 0x9B, 0xA3, 0xED, 0x7A, 0x53, 0x00, 0xA4, 0x48, 0xB3, 0x50, 0x9E, 0x14, 0xA0, 0x52,
    0xDE, 0x7E, 0x10, 0x2B, 0x1B, 0x77, 0x6E,
};
typedef struct { uint32_t state; int counter; } za_slot_xs;
static uint32_t za_slot_xs_adv(uint32_t s) { s ^= s << 2; s ^= s >> 15; s ^= s << 13; return s; }
static void za_slot_xs_init(za_slot_xs *x, uint32_t seed) {
    x->state = seed;
    x->counter = 0;
    for (int i = __builtin_popcount(seed); i > 0; i--) x->state = za_slot_xs_adv(x->state);
}
static uint8_t za_slot_xs_next(za_slot_xs *x) {
    const uint8_t r = (uint8_t)(x->state >> (x->counter << 3));
    if (x->counter == 3) { x->state = za_slot_xs_adv(x->state); x->counter = 0; } else x->counter++;
    return r;
}
static uint32_t za_slot_xs_next32(za_slot_xs *x) {
    uint32_t a = za_slot_xs_next(x), b = za_slot_xs_next(x), c = za_slot_xs_next(x), d = za_slot_xs_next(x);
    return a | b << 8 | c << 16 | d << 24;
}
static int za_slot_type_size(uint8_t t) {
    switch (t) {
        case 3: case 8: case 12: return 1;
        case 9: case 13: return 2;
        case 10: case 14: case 16: return 4;
        case 11: case 15: case 17: return 8;
        default: return -1;
    }
}
static uint8_t za_slot_plain(const uint8_t *save, size_t i) { return (uint8_t)(save[i] ^ za_slot_xorpad[i % 0x7F]); }
static uint32_t za_slot_plain32(const uint8_t *save, size_t i) {
    return (uint32_t)za_slot_plain(save, i) | (uint32_t)za_slot_plain(save, i + 1) << 8 |
           (uint32_t)za_slot_plain(save, i + 2) << 16 | (uint32_t)za_slot_plain(save, i + 3) << 24;
}

uint32_t za_slot_save_read(const uint8_t *save, size_t n, za_slot_sha256_fn sha256, za_slot_summary *out) {
    const uint32_t KPokedex = 0x2D87BE5Cu, KCoordinates = 0x910D381Fu, KSystemWork = 0xFADA7742u, KMable = 0x85DBDCE9u;
    const uint64_t KPhase = 0x992FE2A6DEC12926ull, KDlcPhase = 0xD479E73FCE51A050ull;
    const size_t DexEntry = 0x84;
    uint32_t found = 0;
    out->caught = out->seen = 0;
    out->location[0] = 0;
    out->story_phase = out->dlc_phase = out->research_level = out->research_points = 0;
    out->x = out->y = out->z = 0;
    if (!save || n < 0x10000 || n > (64u << 20)) return 0;
    if (sha256) {
        uint8_t h[32];
        if (sha256(save, n - 32, h) || memcmp(h, save + n - 32, 32)) return 0;
    }
    const size_t payload = n - 32;
    size_t at = 0;
    while (at < payload) {
        if (payload - at < 5) return 0;
        const uint32_t key = za_slot_plain32(save, at);
        at += 4;
        za_slot_xs x;
        za_slot_xs_init(&x, key);
        const uint8_t type = (uint8_t)(za_slot_plain(save, at++) ^ za_slot_xs_next(&x));
        size_t size = 0;
        if (type == 1 || type == 2 || type == 3) {
            size = 0;
        } else if (type == 4) {
            if (payload - at < 4) return 0;
            size = za_slot_plain32(save, at) ^ za_slot_xs_next32(&x);
            at += 4;
        } else if (type == 5) {
            if (payload - at < 5) return 0;
            const uint32_t count = za_slot_plain32(save, at) ^ za_slot_xs_next32(&x);
            at += 4;
            const int sub = za_slot_type_size((uint8_t)(za_slot_plain(save, at++) ^ za_slot_xs_next(&x)));
            if (sub < 0 || count > (1u << 28)) return 0;
            size = (size_t)count * (size_t)sub;
        } else {
            const int sz = za_slot_type_size(type);
            if (sz < 0) return 0;
            size = (size_t)sz;
        }
        if (size > payload - at) return 0;
        if (type == 4 && key == KPokedex && size >= 2 * DexEntry) {
            /* entry by entry with the block's stream; index 0 is the empty species slot. The 2.0.2 block is
             * 1210 entries + a 0x80-byte tail (0x27068 bytes): only whole entries from the start are read. */
            uint32_t c = 0, sn = 0;
            uint8_t e[8];
            const size_t whole = size / DexEntry * DexEntry;
            for (size_t k = 0; k < whole; k++) {
                const uint8_t b = (uint8_t)(za_slot_plain(save, at + k) ^ za_slot_xs_next(&x));
                const size_t in = k % DexEntry;
                if (in < 8) e[in] = b;
                if (in == 7 && k >= DexEntry) {
                    if (za_slot_rd32(e)) c++;
                    if (za_slot_rd32(e + 4)) sn++;
                }
            }
            out->caught = c;
            out->seen = sn;
            found |= ZA_SLOT_HAS_CAUGHT | ZA_SLOT_HAS_SEEN;
        } else if (type == 4 && key == KCoordinates && size >= 0x2C) {
            uint8_t d[0x2C];
            for (size_t k = 0; k < sizeof d; k++) d[k] = (uint8_t)(za_slot_plain(save, at + k) ^ za_slot_xs_next(&x));
            char name[32];
            memcpy(name, d, 32);
            name[31] = 0;
            int ok = name[0] != 0;
            for (size_t k = 0; k < 31 && name[k]; k++)
                if ((unsigned char)name[k] < 0x20 || (unsigned char)name[k] > 0x7E) ok = 0;
            if (ok) { memcpy(out->location, name, 32); found |= ZA_SLOT_HAS_LOCATION; }
            out->x = za_slot_rdf32(d + 0x20);
            out->y = za_slot_rdf32(d + 0x24);  /* height */
            out->z = za_slot_rdf32(d + 0x28);
            found |= ZA_SLOT_HAS_POSITION;
        } else if (type == 4 && key == KSystemWork && size >= 16) {
            int phase = 0, dlc = 0;
            uint8_t e[16];
            for (size_t k = 0; k + 16 <= size; k += 16) {
                for (size_t i = 0; i < 16; i++) e[i] = (uint8_t)(za_slot_plain(save, at + k + i) ^ za_slot_xs_next(&x));
                const uint64_t wk = za_slot_rd64(e), wv = za_slot_rd64(e + 8);
                if (wk == KPhase) { out->story_phase = (uint32_t)(wv > 0xFFFFFFFFull ? 0xFFFFFFFFull : wv); phase = 1; }
                if (wk == KDlcPhase) { out->dlc_phase = (uint32_t)(wv > 0xFFFFFFFFull ? 0xFFFFFFFFull : wv); dlc = 1; }
            }
            if (phase) found |= ZA_SLOT_HAS_PHASE;
            (void)dlc;  /* absent until the DLC starts: 0 */
        } else if (type == 4 && key == KMable && size >= 12) {
            uint8_t d[12];
            for (size_t k = 0; k < sizeof d; k++) d[k] = (uint8_t)(za_slot_plain(save, at + k) ^ za_slot_xs_next(&x));
            out->research_level = za_slot_rd32(d);
            out->research_points = za_slot_rd32(d + 8);
            found |= ZA_SLOT_HAS_RESEARCH;
        }
        at += size;
    }
    return found;
}

uint32_t za_slot_save_progress(const uint8_t *save, size_t n, za_slot_sha256_fn sha256, uint32_t *caught, uint32_t *seen,
                               char location[32]) {
    za_slot_summary s;
    memset(&s, 0, sizeof s);
    const uint32_t f = za_slot_save_read(save, n, sha256, &s) & (ZA_SLOT_HAS_CAUGHT | ZA_SLOT_HAS_SEEN | ZA_SLOT_HAS_LOCATION);
    if (caught) *caught = s.caught;
    if (seen) *seen = s.seen;
    if (location) memcpy(location, s.location, 32);
    return f;
}

size_t za_slot_rebuild(uint8_t *out, size_t cap, const uint8_t *old, size_t old_len, const za_slot_summary *summary,
                       const uint8_t *save, size_t save_len) {
    const uint8_t *rand = NULL, *sett = NULL;
    size_t rand_len = 0, sett_len = 0;
    if (!old || za_slot_verify(old, old_len) != ZA_SLOT_OK) return 0;
    if (za_slot_section(old, old_len, ZA_SLOT_RAND, &rand, &rand_len) != ZA_SLOT_OK) rand_len = 0;
    if (za_slot_section(old, old_len, ZA_SLOT_SETT, &sett, &sett_len) != ZA_SLOT_OK) sett_len = 0;
    return za_slot_build(out, cap, summary, (const char *)rand, rand_len, (const char *)sett, sett_len, save, save_len);
}

#ifdef __cplusplus
}
#endif
#endif /* ZA_SLOT_IMPLEMENTED */
#endif /* ZA_SLOT_IMPLEMENTATION */
