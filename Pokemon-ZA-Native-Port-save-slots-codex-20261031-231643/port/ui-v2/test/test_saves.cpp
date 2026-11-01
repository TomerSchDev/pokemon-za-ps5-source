// ui-v2 host test of the saved-runs layer (ASan/UBSan): the compatibility rule, the slot container (za_slot.h:
// round trip, head-only reads, truncated / corrupt / newer files, the save-progress reader on a synthetic SwishCrypto
// save) and run deletion on a scratch root (one run, the active run, all unsupported, injected failures at every
// step, the leftover sweep, symlinks, foreign folders untouched).
// Usage: test_saves <new scratch root> [v3 report.json] [old v2 report.json] [a run's save/save_0/main] [slot-names.json]
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

#include <mbedtls/sha256.h>

#include "launcher_core.h"
#include "rando_v3.hpp"
#include "run_store.hpp"
#include "settings_codes.h"
#include "za_slot.h"

using namespace ui::launcher;
using za::Json;

static int failures = 0, checks = 0;
#define CHECK(cond)                                                               \
    do {                                                                          \
        checks++;                                                                 \
        if (!(cond)) {                                                            \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
            failures++;                                                           \
        }                                                                         \
    } while (0)

static std::string readText(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    std::stringstream ss;
    ss << in.rdbuf();
    return ss.str();
}
static void writeText(const std::string& path, const std::string& text) {
    std::ofstream out(path, std::ios::binary);
    out << text;
}
static bool exists(const std::string& path) {
    struct stat st {};
    return !lstat(path.c_str(), &st);
}
static void mkdirs(const std::string& path) {
    for (size_t i = 1; i <= path.size(); i++)
        if (i == path.size() || path[i] == '/') mkdir(path.substr(0, i).c_str(), 0755);
}

// ---------------------------------------------------------------- compatibility
static Json v3Report() {
    return {{"schema", 1}, {"seed", "1"}, {"algorithm", "za202-randomizer-alpha1"}, {"v3_algorithm", za::v3::Algorithm},
            {"build_id", ui::codes::CurrentGameBuild}, {"v3", {{"wild", Json::object()}}},
            {"ui_options", {{"schema", 2}, {"values", {{"wild_mode", "random"}}}}}, {"native_run_id", "r1"}, {"native_complete", true}};
}

static void testCompat(const char* realV3, const char* realV2) {
    Json r = v3Report();
    saves::Compat c = saves::compatibilityOfReport(r.dump());
    CHECK(c.supported && c.badge.empty() && c.reason.empty());
    // the old v2 generator's shape: no v3_algorithm, no v3, no ui_options
    Json old = {{"schema", 1}, {"seed", "6210203342"}, {"algorithm", "za202-randomizer-alpha1"}, {"build_id", ui::codes::CurrentGameBuild},
                {"options", {{"wild", true}}}};
    c = saves::compatibilityOfReport(old.dump());
    CHECK(!c.supported && c.badge == "OLD VERSION" && c.reason.find("za202-randomizer-alpha1") != std::string::npos);
    r = v3Report();
    r["v3_algorithm"] = "za202-randomizer-v4";
    c = saves::compatibilityOfReport(r.dump());
    CHECK(!c.supported && c.badge == "OLD VERSION" && c.reason.find("v4") != std::string::npos);
    r = v3Report();
    r["build_id"] = "0000";
    c = saves::compatibilityOfReport(r.dump());
    CHECK(!c.supported && c.badge == "OTHER GAME BUILD");
    r = v3Report();
    r.erase("v3");
    CHECK(!saves::compatibilityOfReport(r.dump()).supported && saves::compatibilityOfReport(r.dump()).badge == "DAMAGED");
    r = v3Report();
    r["ui_options"]["schema"] = "2";
    CHECK(!saves::compatibilityOfReport(r.dump()).supported);
    r = v3Report();
    r["ui_options"].erase("values");
    CHECK(!saves::compatibilityOfReport(r.dump()).supported);
    r = v3Report();
    r["v3_algorithm"] = 3;
    CHECK(!saves::compatibilityOfReport(r.dump()).supported);
    CHECK(!saves::compatibilityOfReport("").supported && saves::compatibilityOfReport("{").badge == "DAMAGED");
    CHECK(!saves::compatibilityOfReport("[1,2]").supported);
    // the real reports (read-only): a run made by r29-ui's v3 generator and one made by the old v2 generator
    if (realV3 && *realV3) {
        const std::string text = readText(realV3);
        CHECK(!text.empty());
        c = saves::compatibilityOfReport(text);
        CHECK(c.supported);
        std::printf("real v3 report: %s\n", c.supported ? "supported" : c.reason.c_str());
    }
    if (realV2 && *realV2) {
        const std::string text = readText(realV2);
        CHECK(!text.empty());
        c = saves::compatibilityOfReport(text);
        CHECK(!c.supported && c.badge == "OLD VERSION");
        std::printf("real v2 report: %s - %s\n", c.badge.c_str(), c.reason.c_str());
    }
}

// ---------------------------------------------------------------- slot container
static std::vector<uint8_t> sampleContainer(const std::vector<uint8_t>& save) {
    za_slot_summary s;
    std::memset(&s, 0, sizeof s);
    s.flags = ZA_SLOT_HAS_CAUGHT | ZA_SLOT_HAS_SEEN | ZA_SLOT_HAS_LOCATION;
    s.save_time = 1793440215ull;
    s.created_time = 1793400000ull;
    s.caught = 14;
    s.seen = 37;
    s.flags |= ZA_SLOT_HAS_PHASE | ZA_SLOT_HAS_RESEARCH | ZA_SLOT_HAS_POSITION;
    s.story_phase = 21160;
    s.research_level = 4;
    s.research_points = 1234;
    s.x = 1.5f; s.z = -2.25f; s.y = 3.0f;
    std::snprintf(s.run_id, sizeof s.run_id, "%s", "r000000006ae61a20-5c3e9b07");
    std::snprintf(s.seed, sizeof s.seed, "%s", "1793440215");
    std::snprintf(s.location, sizeof s.location, "%s", "t1_city_main_long_name_cut_at_31_chars");
    std::snprintf(s.algorithm, sizeof s.algorithm, "%s", za::v3::Algorithm);
    std::snprintf(s.build_id, sizeof s.build_id, "%s", ui::codes::CurrentGameBuild);
    const std::string rand = R"({"schema":"za-slot-rand-1"})", sett = R"({"seed":"1793440215","ui_options":{"schema":2,"values":{}}})";
    const size_t need = za_slot_build(nullptr, 0, &s, rand.data(), rand.size(), sett.data(), sett.size(), save.data(), save.size());
    std::vector<uint8_t> out(need);
    CHECK(za_slot_build(out.data(), out.size() - 1, &s, rand.data(), rand.size(), sett.data(), sett.size(), save.data(), save.size()) == need);
    CHECK(za_slot_build(out.data(), out.size(), &s, rand.data(), rand.size(), sett.data(), sett.size(), save.data(), save.size()) == need);
    return out;
}

static void fixHeaderCrc(std::vector<uint8_t>& f) {
    const uint32_t count = uint32_t(f[0x10]) | uint32_t(f[0x11]) << 8;
    uint32_t crc = za_slot_crc32(0, f.data(), 0x20);
    crc = za_slot_crc32(crc, f.data() + 64, count * 32);
    for (int i = 0; i < 4; i++) f[0x20 + size_t(i)] = uint8_t(crc >> (8 * i));
}

static void testContainer(const std::string& scratch) {
    CHECK(za_slot_crc32(0, "123456789", 9) == 0xCBF43926u);  // the CRC-32/ISO-HDLC check value
    std::vector<uint8_t> save(70000);
    for (size_t i = 0; i < save.size(); i++) save[i] = uint8_t(i * 31 + 7);
    std::vector<uint8_t> f = sampleContainer(save);
    CHECK(f.size() == 64 + 4 * 32 + 320 + 27 + 59 + save.size());
    za_slot_summary s;
    CHECK(za_slot_parse_summary(f.data(), f.size(), &s) == ZA_SLOT_OK);
    CHECK(s.caught == 14 && s.seen == 37 && s.save_time == 1793440215ull && s.created_time == 1793400000ull && s.save_size == save.size());
    CHECK(!std::strcmp(s.run_id, "r000000006ae61a20-5c3e9b07") && !std::strcmp(s.seed, "1793440215"));
    CHECK(std::strlen(s.location) == 31 && !std::strcmp(s.algorithm, za::v3::Algorithm) && !std::strcmp(s.build_id, ui::codes::CurrentGameBuild));
    CHECK(za_slot_verify(f.data(), f.size()) == ZA_SLOT_OK);
    const uint8_t* data = nullptr;
    size_t len = 0;
    CHECK(za_slot_section(f.data(), f.size(), ZA_SLOT_SAVE, &data, &len) == ZA_SLOT_OK && len == save.size() && !std::memcmp(data, save.data(), len));
    CHECK(za_slot_section(f.data(), f.size(), ZA_SLOT_SETT, &data, &len) == ZA_SLOT_OK && std::string((const char*)data, len).find("ui_options") != std::string::npos);
    CHECK(za_slot_section(f.data(), f.size(), ZA_SLOT_FOURCC('N', 'O', 'P', 'E'), &data, &len) == ZA_SLOT_NO_SUMMARY);
    // the head alone is enough for the summary; one byte less is not
    const size_t head = 64 + 4 * 32 + 320;
    CHECK(s.story_phase == 21160 && s.research_level == 4 && s.research_points == 1234 && s.x == 1.5f && s.z == -2.25f && s.y == 3.0f);
    CHECK(za_slot_parse_summary(f.data(), head, &s) == ZA_SLOT_OK);
    CHECK(za_slot_parse_summary(f.data(), head - 1, &s) == ZA_SLOT_TRUNCATED);
    CHECK(za_slot_parse_summary(f.data(), 63, &s) == ZA_SLOT_TRUNCATED);
    CHECK(za_slot_parse_summary(f.data(), 100, &s) == ZA_SLOT_TRUNCATED);
    // a truncated file: the summary still reads, the full verify refuses it
    CHECK(za_slot_verify(f.data(), f.size() - 1) == ZA_SLOT_TRUNCATED);
    // corruption in each place
    {
        auto g = f; g[0] ^= 1;
        CHECK(za_slot_parse_summary(g.data(), g.size(), &s) == ZA_SLOT_BAD_MAGIC);
    }
    {
        auto g = f; g[0x08] = 2; fixHeaderCrc(g);
        CHECK(za_slot_parse_summary(g.data(), g.size(), &s) == ZA_SLOT_NEWER_MAJOR);
    }
    {
        auto g = f; g[0x0A] = 7; fixHeaderCrc(g);  // a newer minor version is read
        CHECK(za_slot_parse_summary(g.data(), g.size(), &s) == ZA_SLOT_OK && za_slot_verify(g.data(), g.size()) == ZA_SLOT_OK);
    }
    {
        auto g = f; g[64 + 8] ^= 0x10;  // the SUMM offset, without fixing the table CRC
        CHECK(za_slot_parse_summary(g.data(), g.size(), &s) == ZA_SLOT_BAD_CRC);
    }
    {
        auto g = f; g[64 + 16] = 0xFF; g[64 + 17] = 0xFF; g[64 + 18] = 0xFF; fixHeaderCrc(g);  // SUMM length past the file
        CHECK(za_slot_parse_summary(g.data(), g.size(), &s) == ZA_SLOT_BAD_TABLE);
    }
    {
        auto g = f; g[0x10] = 0; fixHeaderCrc(g);  // zero sections
        CHECK(za_slot_parse_summary(g.data(), g.size(), &s) == ZA_SLOT_BAD_TABLE);
    }
    {
        auto g = f; g[head - 10] ^= 0x40;  // inside SUMM
        CHECK(za_slot_parse_summary(g.data(), g.size(), &s) == ZA_SLOT_BAD_CRC);
    }
    {
        auto g = f; g[g.size() - 5] ^= 0x40;  // inside SAVE: the cheap reader does not see it, the full verify does
        CHECK(za_slot_parse_summary(g.data(), g.size(), &s) == ZA_SLOT_OK && za_slot_verify(g.data(), g.size()) == ZA_SLOT_BAD_CRC);
    }
    // a 1.0 file (SUMM v1, 256 bytes): still read, the 1.1 fields unknown
    {
        const size_t summAt = 64 + 4 * 32;  // where the 1.1 file keeps SUMM
        std::vector<uint8_t> g(64 + 32 + 256, 0);
        std::memcpy(g.data(), f.data(), 0x10);  // magic, major
        g[0x0A] = 0;                             // minor 0
        g[0x10] = 1;                             // one section
        const uint64_t total = g.size();
        for (int i = 0; i < 8; i++) g[0x18 + size_t(i)] = uint8_t(total >> (8 * i));
        std::memcpy(g.data() + 96, f.data() + summAt, 256);
        g[96] = 1;  // summary_version 1
        const uint32_t crc = za_slot_crc32(0, g.data() + 96, 256);
        uint8_t* e = g.data() + 64;
        e[0] = 'S'; e[1] = 'U'; e[2] = 'M'; e[3] = 'M';
        e[8] = 96;
        e[16] = 0; e[17] = 1;  // length 256
        for (int i = 0; i < 4; i++) e[24 + i] = uint8_t(crc >> (8 * i));
        fixHeaderCrc(g);
        za_slot_summary v1;
        CHECK(za_slot_parse_summary(g.data(), g.size(), &v1) == ZA_SLOT_OK && v1.caught == 14 && za_slot_verify(g.data(), g.size()) == ZA_SLOT_OK);
        CHECK(!(v1.flags & (ZA_SLOT_HAS_PHASE | ZA_SLOT_HAS_RESEARCH | ZA_SLOT_HAS_POSITION)) && v1.story_phase == 0);
    }
    // rebuild (the in-game writer's path): RAND / SETT kept, SUMM and SAVE replaced; an unusable old file gives 0
    {
        std::vector<uint8_t> save2(save.size(), 0x33);
        za_slot_summary s2 = s;
        s2.save_time = 1793500000ull;
        s2.caught = 15;
        const size_t need = za_slot_rebuild(nullptr, 0, f.data(), f.size(), &s2, save2.data(), save2.size());
        CHECK(need == f.size());
        std::vector<uint8_t> g(need);
        CHECK(za_slot_rebuild(g.data(), g.size(), f.data(), f.size(), &s2, save2.data(), save2.size()) == need);
        za_slot_summary back;
        CHECK(za_slot_verify(g.data(), g.size()) == ZA_SLOT_OK && za_slot_parse_summary(g.data(), g.size(), &back) == ZA_SLOT_OK);
        CHECK(back.caught == 15 && back.save_time == 1793500000ull && back.story_phase == 21160);
        const uint8_t *a = nullptr, *bb = nullptr;
        size_t al = 0, bl = 0;
        CHECK(za_slot_section(f.data(), f.size(), ZA_SLOT_SETT, &a, &al) == ZA_SLOT_OK && za_slot_section(g.data(), g.size(), ZA_SLOT_SETT, &bb, &bl) == ZA_SLOT_OK &&
              al == bl && !std::memcmp(a, bb, al));
        CHECK(za_slot_section(g.data(), g.size(), ZA_SLOT_SAVE, &a, &al) == ZA_SLOT_OK && al == save2.size() && a[0] == 0x33);
        auto bad = f;
        bad[bad.size() - 1] ^= 1;
        CHECK(za_slot_rebuild(nullptr, 0, bad.data(), bad.size(), &s2, save2.data(), save2.size()) == 0);
    }
    // files: missing, atomic write (no temp left), garbage, an empty file
    const std::string path = scratch + "/container/slot.zrs";
    mkdirs(scratch + "/container");
    CHECK(za_slot_read_summary_file(path.c_str(), &s) == ZA_SLOT_MISSING);
    CHECK(za_slot_write_atomic(path.c_str(), f.data(), f.size()) == 0);
    CHECK(!exists(path + ".new") && za_slot_read_summary_file(path.c_str(), &s) == ZA_SLOT_OK && s.caught == 14);
    writeText(path + "2", "not a container at all, just text that is long enough to cover a header and more bytes");
    CHECK(za_slot_read_summary_file((path + "2").c_str(), &s) == ZA_SLOT_BAD_MAGIC);
    writeText(path + "3", "");
    CHECK(za_slot_read_summary_file((path + "3").c_str(), &s) == ZA_SLOT_TRUNCATED);
    CHECK(za_slot_write_atomic((scratch + "/no/such/dir/slot.zrs").c_str(), f.data(), f.size()) == -1);
}

// A synthetic SwishCrypto save: blocks {key, type, length, data} XORed with SCXorShift32(key), the 0x7F xorpad over
// the payload, SHA-256(intro + payload + outro) at the end. Only the reader's view is needed, so the intro/outro salts
// are left out: the test passes its own hash function over the payload.
struct Xs {
    uint32_t state; int counter = 0;
    static uint32_t adv(uint32_t s) { s ^= s << 2; s ^= s >> 15; s ^= s << 13; return s; }
    explicit Xs(uint32_t seed) : state(seed) { for (int i = __builtin_popcount(seed); i > 0; i--) state = adv(state); }
    uint8_t next() { uint8_t r = uint8_t(state >> (counter << 3)); if (counter == 3) { state = adv(state); counter = 0; } else counter++; return r; }
};
static const uint8_t Xorpad[0x7F] = {
    0xA0, 0x92, 0xD1, 0x06, 0x07, 0xDB, 0x32, 0xA1, 0xAE, 0x01, 0xF5, 0xC5, 0x1E, 0x84, 0x4F, 0xE3, 0x53, 0xCA, 0x37, 0xF4,
    0xA7, 0xB0, 0x4D, 0xA0, 0x18, 0xB7, 0xC2, 0x97, 0xDA, 0x5F, 0x53, 0x2B, 0x75, 0xFA, 0x48, 0x16, 0xF8, 0xD4, 0x8A, 0x6F,
    0x61, 0x05, 0xF4, 0xE2, 0xFD, 0x04, 0xB5, 0xA3, 0x0F, 0xFC, 0x44, 0x92, 0xCB, 0x32, 0xE6, 0x1B, 0xB9, 0xB1, 0x2E, 0x01,
    0xB0, 0x56, 0x53, 0x36, 0xD2, 0xD1, 0x50, 0x3D, 0xDE, 0x5B, 0x2E, 0x0E, 0x52, 0xFD, 0xDF, 0x2F, 0x7B, 0xCA, 0x63, 0x50,
    0xA4, 0x67, 0x5D, 0x23, 0x17, 0xC0, 0x52, 0xE1, 0xA6, 0x30, 0x7C, 0x2B, 0xB6, 0x70, 0x36, 0x5B, 0x2A, 0x27, 0x69, 0x33,
    0xF5, 0x63, 0x7B, 0x36, 0x3F, 0x26, 0x9B, 0xA3, 0xED, 0x7A, 0x53, 0x00, 0xA4, 0x48, 0xB3, 0x50, 0x9E, 0x14, 0xA0, 0x52,
    0xDE, 0x7E, 0x10, 0x2B, 0x1B, 0x77, 0x6E,
};
static void addObject(std::vector<uint8_t>& p, uint32_t key, const std::vector<uint8_t>& data) {
    for (int i = 0; i < 4; i++) p.push_back(uint8_t(key >> (8 * i)));
    Xs x(key);
    p.push_back(uint8_t(4 ^ x.next()));
    const uint32_t n = uint32_t(data.size());
    for (int i = 0; i < 4; i++) p.push_back(uint8_t(uint8_t(n >> (8 * i)) ^ x.next()));
    for (uint8_t b : data) p.push_back(uint8_t(b ^ x.next()));
}
static int payloadHash(const uint8_t* d, size_t n, uint8_t out[32]) { return mbedtls_sha256(d, n, out, 0); }
static std::vector<uint8_t> syntheticSave(bool withDex, bool withCoords) {
    std::vector<uint8_t> p;
    addObject(p, 0x11111111u, std::vector<uint8_t>(0x10000, 0x5A));  // filler: a real save is megabytes
    if (withDex) {
        std::vector<uint8_t> dex(0x84 * 5 + 0x80, 0);  // whole entries + a tail, as the 2.0.2 block
        dex[0x84 * 5] = 0xFF;                          // the tail is never read as an entry
        dex[0] = 0xFF;                               // index 0 = no species: never counted
        dex[0x84 * 1 + 0] = 1; dex[0x84 * 1 + 4] = 1;  // caught + seen
        dex[0x84 * 2 + 4] = 2;                       // seen only
        dex[0x84 * 3 + 0] = 4; dex[0x84 * 3 + 4] = 4;  // caught + seen (another form)
        addObject(p, 0x2D87BE5Cu, dex);
    }
    if (withCoords) {
        std::vector<uint8_t> coords(0x40, 0);
        std::memcpy(coords.data(), "t1_city", 7);
        const float xyz[3] = {12.5f, 3.25f, -40.0f};  // x @0x20, height y @0x24, z @0x28
        std::memcpy(coords.data() + 0x20, xyz, sizeof xyz);
        addObject(p, 0x910D381Fu, coords);
        // system_work: (u64 key, u64 value) pairs - an unrelated key, SYS_WORK_PHASE = 30350, SYS_WORK_DLC_PHASE = 7
        std::vector<uint8_t> work(16 * 4, 0);
        auto put = [&](size_t i, uint64_t k, uint64_t v) {
            for (int b = 0; b < 8; b++) { work[i * 16 + size_t(b)] = uint8_t(k >> (8 * b)); work[i * 16 + 8 + size_t(b)] = uint8_t(v >> (8 * b)); }
        };
        put(0, 0x1111222233334444ull, 99);
        put(1, 0x992FE2A6DEC12926ull, 30350);
        put(2, 0xD479E73FCE51A050ull, 7);
        addObject(p, 0xFADA7742u, work);
        std::vector<uint8_t> mable(12, 0);
        mable[0] = 6;     // level
        mable[8] = 0x10;  // points 0x2710 = 10000
        mable[9] = 0x27;
        addObject(p, 0x85DBDCE9u, mable);
    }
    for (size_t i = 0; i < p.size(); i++) p[i] ^= Xorpad[i % 0x7F];
    uint8_t h[32];
    payloadHash(p.data(), p.size(), h);
    p.insert(p.end(), h, h + 32);
    return p;
}

static void testSourceReport(const std::string& scratch) {
    const std::string run = scratch + "/source-report";
    mkdirs(run + "/save/save_0");
    auto save = syntheticSave(true, true);
    uint8_t digest[32];
    CHECK(!saves::swishHash(save.data(), save.size() - 32, digest));
    std::copy(digest, digest + 32, save.end() - 32);
    const std::string saveText(reinterpret_cast<const char*>(save.data()), save.size());
    writeText(run + "/save/save_0/main", saveText);
    Json report = v3Report();
    report["future_extra"] = {{"version", 7}, {"nested", Json::array({"unknown", 42, true})}};
    const std::string original = report.dump();
    writeText(run + "/report.json", original);
    std::string error;
    CHECK(saves::writeSlotContainer(run, original, 200, 100, error));
    const std::string file = readText(run + "/slot.zrs");
    const auto* data = reinterpret_cast<const uint8_t*>(file.data());
    CHECK(za_slot_verify(data, file.size()) == ZA_SLOT_OK);
    const uint8_t* rand = nullptr;
    size_t randLen = 0;
    CHECK(za_slot_section(data, file.size(), ZA_SLOT_RAND, &rand, &randLen) == ZA_SLOT_OK);
    const std::string randText(reinterpret_cast<const char*>(rand), randLen);
    CHECK(Json::parse(randText)["source_report"] == report);
    za_slot_summary summary;
    CHECK(za_slot_parse_summary(data, file.size(), &summary) == ZA_SLOT_OK);
    summary.save_time++;
    const size_t need = za_slot_rebuild(nullptr, 0, data, file.size(), &summary, save.data(), save.size());
    std::vector<uint8_t> rebuilt(need);
    CHECK(need && za_slot_rebuild(rebuilt.data(), rebuilt.size(), data, file.size(), &summary, save.data(), save.size()) == need);
    CHECK(za_slot_verify(rebuilt.data(), rebuilt.size()) == ZA_SLOT_OK);
    const uint8_t* after = nullptr;
    size_t afterLen = 0;
    CHECK(za_slot_section(rebuilt.data(), rebuilt.size(), ZA_SLOT_RAND, &after, &afterLen) == ZA_SLOT_OK);
    CHECK(std::string(reinterpret_cast<const char*>(after), afterLen) == randText);
    CHECK(readText(run + "/report.json") == original && readText(run + "/save/save_0/main") == saveText);
    CHECK(!saves::writeSlotContainer(run, std::string((1u << 20) + 1, ' '), 200, 100, error));
    CHECK(readText(run + "/slot.zrs") == file);
    const auto legacy = ui::launcher::Controller::loadCards(scratch, "", nullptr);
    const auto explicitNames = ui::launcher::Controller::loadCards(scratch, "", nullptr, nullptr);
    CHECK(legacy.size() == explicitNames.size());
    for (size_t i = 0; i < legacy.size(); ++i)
        CHECK(legacy[i].id == explicitNames[i].id && legacy[i].supported == explicitNames[i].supported &&
              legacy[i].badge == explicitNames[i].badge && legacy[i].summary == explicitNames[i].summary);
}

static void testNames() {
    saves::Names n;
    CHECK(!n.parse("") && !n.parse("{}") && !n.parse(R"({"schema":"za-slot-names-2"})") && !n.loaded);
    CHECK(n.mission(21110, 0) == "Phase 21110" && n.mission(0, 0).empty() && n.place("t1", 0, 0) == "t1");  // nothing loaded: the ids
    CHECK(n.parse(R"({"schema":"za-slot-names-1",
        "missions":[{"phase_min":20000,"phase_max":29999,"label":"Main Mission 2","title":"A New Life"},
                    {"phase_min":30000,"phase_max":39999,"title":"Only a title"},
                    {"phase_min":50,"phase_max":10,"label":"backwards: dropped"}, {"phase_min":-1,"phase_max":5,"label":"negative: dropped"}],
        "dlc_missions":[{"phase_min":1,"phase_max":99,"label":"DLC 1","title":"Hyperspace"}],
        "maps":{"t1":"Lumiose City","t2":""},
        "areas":[{"map":"t1","name":"Vert Sector 3","x0":10,"z0":-10,"x1":-10,"z1":10},{"map":"t1","name":"","x0":0,"z0":0,"x1":1,"z1":1}]})"));
    CHECK(n.loaded && n.missions.size() == 2 && n.maps.size() == 1 && n.areas.size() == 1);
    CHECK(n.mission(21110, 0) == "Main Mission 2  \xC2\xB7  A New Life" && n.mission(30350, 0) == "Only a title");
    CHECK(n.mission(99999, 5) == "DLC 1  \xC2\xB7  Hyperspace" && n.mission(99999, 0) == "Phase 99999");
    CHECK(n.place("t1", 0, 0) == "Lumiose City \xE2\x80\x94 Vert Sector 3" && n.place("t1", 50, 0) == "Lumiose City" && n.place("t9", 0, 0) == "t9");
    CHECK(n.place("t2", 0, 0) == "t2");
}

static void testSaveProgress(const char* realSave, const char* realNames) {
    uint32_t caught = 99, seen = 99;
    char location[32];
    std::vector<uint8_t> save = syntheticSave(true, true);
    uint32_t flags = za_slot_save_progress(save.data(), save.size(), payloadHash, &caught, &seen, location);
    CHECK(flags == (ZA_SLOT_HAS_CAUGHT | ZA_SLOT_HAS_SEEN | ZA_SLOT_HAS_LOCATION) && caught == 2 && seen == 3 && !std::strcmp(location, "t1_city"));
    flags = za_slot_save_progress(save.data(), save.size(), nullptr, &caught, &seen, location);
    CHECK(flags == (ZA_SLOT_HAS_CAUGHT | ZA_SLOT_HAS_SEEN | ZA_SLOT_HAS_LOCATION) && caught == 2);
    {
        za_slot_summary all;
        std::memset(&all, 0, sizeof all);
        const uint32_t f2 = za_slot_save_read(save.data(), save.size(), payloadHash, &all);
        CHECK(f2 == (ZA_SLOT_HAS_CAUGHT | ZA_SLOT_HAS_SEEN | ZA_SLOT_HAS_LOCATION | ZA_SLOT_HAS_POSITION | ZA_SLOT_HAS_PHASE | ZA_SLOT_HAS_RESEARCH));
        CHECK(all.story_phase == 30350 && all.dlc_phase == 7 && all.research_level == 6 && all.research_points == 10000);
        CHECK(all.x == 12.5f && all.z == -40.0f && all.y == 3.25f && all.caught == 2);
    }
    // a changed byte: the hash refuses it (and the input is never written)
    const std::vector<uint8_t> before = save;
    save[100] ^= 1;
    CHECK(za_slot_save_progress(save.data(), save.size(), payloadHash, &caught, &seen, location) == 0 && caught == 0 && location[0] == 0);
    save[100] ^= 1;
    CHECK(save == before);
    // blocks absent: nothing reported
    save = syntheticSave(false, false);
    CHECK(za_slot_save_progress(save.data(), save.size(), payloadHash, &caught, &seen, location) == 0);
    save = syntheticSave(true, false);
    CHECK(za_slot_save_progress(save.data(), save.size(), payloadHash, &caught, &seen, location) == (ZA_SLOT_HAS_CAUGHT | ZA_SLOT_HAS_SEEN));
    // too small / truncated
    CHECK(za_slot_save_progress(save.data(), 1000, nullptr, &caught, &seen, location) == 0);
    CHECK(za_slot_save_progress(save.data(), save.size() - 7, nullptr, &caught, &seen, location) == 0 || caught == 2);
    if (realSave && *realSave) {
        std::vector<uint8_t> real;
        const std::string bytes = readText(realSave);
        real.assign(bytes.begin(), bytes.end());
        za_slot_summary rs;
        std::memset(&rs, 0, sizeof rs);
        flags = za_slot_save_read(real.data(), real.size(), saves::swishHash, &rs);
        std::printf("real save %zu bytes: flags=%u caught=%u seen=%u map=\"%s\" x=%.1f z=%.1f phase=%u dlc=%u research=%u/%u\n", real.size(), flags,
                    rs.caught, rs.seen, rs.location, double(rs.x), double(rs.z), rs.story_phase, rs.dlc_phase, rs.research_level, rs.research_points);
        CHECK((flags & ZA_SLOT_HAS_CAUGHT) && rs.caught == 2 && rs.seen == 3);  // the independent Python decoder: 2 / 3
        CHECK((flags & ZA_SLOT_HAS_PHASE) && rs.story_phase == 21110 && (flags & ZA_SLOT_HAS_RESEARCH) && rs.research_level == 1);
        CHECK((flags & ZA_SLOT_HAS_LOCATION) && std::string(rs.location) == "t1");
        if (realNames && *realNames) {
            saves::Names names;
            CHECK(names.parse(readText(realNames)));
            const std::string mission = names.mission(rs.story_phase, rs.dlc_phase), place = names.place(rs.location, rs.x, rs.z);
            std::printf("real save names: mission=\"%s\" place=\"%s\"\n", mission.c_str(), place.c_str());
            CHECK(!mission.empty() && mission.rfind("Phase ", 0) != 0 && place != "t1");
            // the real save stands in front of the station (z about -889.7): a sub-area, not just the map
            CHECK(place.find(" \xE2\x80\x94 ") != std::string::npos && rs.z < -800.0f && rs.y > -5.0f && rs.y < 5.0f);
        }
    }
}

// ---------------------------------------------------------------- deletion
static std::string failRenameFrom, failUnlinkPath, failUnlinkSuffix;
static int testRename(const char* a, const char* b) {
    if (!failRenameFrom.empty() && std::string(a).find(failRenameFrom) != std::string::npos) { errno = EACCES; return -1; }
    return ::rename(a, b);
}
static int testUnlink(const char* p) {
    const std::string s = p;
    if (!failUnlinkPath.empty() && s == failUnlinkPath) { errno = EIO; return -1; }
    if (!failUnlinkSuffix.empty() && s.size() >= failUnlinkSuffix.size() && s.compare(s.size() - failUnlinkSuffix.size(), failUnlinkSuffix.size(), failUnlinkSuffix) == 0) {
        errno = EIO;
        return -1;
    }
    return ::unlink(p);
}
static saves::FsOps testOps() { return {testRename, testUnlink, ::rmdir}; }

static void fakeRun(const std::string& root, const std::string& id) {
    mkdirs(root + "/" + id + "/save/save_0");
    mkdirs(root + "/" + id + "/romfs/a/b");
    writeText(root + "/" + id + "/report.json", "{\"native_run_id\":\"" + id + "\"}");
    writeText(root + "/" + id + "/save/save_0/main", "SAVE");
    writeText(root + "/" + id + "/romfs/a/b/table.bin", "TABLE");
    writeText(root + "/" + id + "/cheats.txt", "za-cheats-v2\n0 0 1 0\n");
}
static void setActive(const std::string& root, const std::string& id) { writeText(root + "/active.json", "{\"id\":\"" + id + "\",\"schema\":1}"); }

static void testDelete(const std::string& scratch) {
    const std::string root = scratch + "/rando";
    mkdirs(root);
    const std::string a = "r000000006ae10000-aaaaaaaa", b = "r000000006ae20000-bbbbbbbb", c = "r000000006ae30000-cccccccc";
    fakeRun(root, a);
    fakeRun(root, b);
    fakeRun(root, c);
    mkdirs(root + "/.pending-r000000006ae40000-dddddddd");  // an interrupted generation: never touched
    writeText(root + "/player-name.txt", "Tomer\n");
    writeText(scratch + "/outside.txt", "keep");
    symlink((scratch + "/outside.txt").c_str(), (root + "/" + c + "/link").c_str());
    setActive(root, b);
    CHECK(saves::runDirectories(root) == (std::vector<std::string>{c, b, a}));
    CHECK(saves::activeMarker(root) == b);
    std::string error;

    // one run (not active): gone, everything else as it was
    CHECK(saves::deleteRun(root, a, error) == saves::DeleteResult::Deleted && error.empty());
    CHECK(!exists(root + "/" + a) && !exists(root + "/.deleting-" + a) && exists(root + "/" + b + "/save/save_0/main"));
    CHECK(saves::activeMarker(root) == b && exists(root + "/player-name.txt") && exists(root + "/.pending-r000000006ae40000-dddddddd"));
    // a run with a symlink inside: the link goes, its target outside stays
    CHECK(saves::deleteRun(root, c, error) == saves::DeleteResult::Deleted);
    CHECK(!exists(root + "/" + c) && readText(scratch + "/outside.txt") == "keep");
    // bad ids, missing runs
    CHECK(saves::deleteRun(root, "../outside.txt", error) == saves::DeleteResult::Failed && !error.empty());
    CHECK(saves::deleteRun(root, ".pending-r000000006ae40000-dddddddd", error) == saves::DeleteResult::Failed);
    CHECK(saves::deleteRun(root, a, error) == saves::DeleteResult::Failed && error.find("missing") != std::string::npos);
    CHECK(saves::deleteRun(root, "", error) == saves::DeleteResult::Failed);

    // the rename fails: nothing changed
    failRenameFrom = b;
    CHECK(saves::deleteRun(root, b, error, testOps()) == saves::DeleteResult::Failed && error.find("Nothing was deleted") != std::string::npos);
    CHECK(exists(root + "/" + b + "/save/save_0/main") && saves::activeMarker(root) == b && !exists(root + "/.deleting-" + b));
    failRenameFrom.clear();
    // clearing the active marker fails: the run is put back, nothing changed
    failUnlinkPath = root + "/active.json";
    CHECK(saves::deleteRun(root, b, error, testOps()) == saves::DeleteResult::Failed && error.find("put back") != std::string::npos);
    CHECK(exists(root + "/" + b + "/romfs/a/b/table.bin") && saves::activeMarker(root) == b && !exists(root + "/.deleting-" + b));
    failUnlinkPath.clear();
    // a file inside cannot be erased: the run is already out of every listing, active.json is gone, the leftover is
    // hidden and the next start's sweep finishes it
    failUnlinkSuffix = "/table.bin";
    CHECK(saves::deleteRun(root, b, error, testOps()) == saves::DeleteResult::DeletedWithLeftovers && !error.empty());
    CHECK(!exists(root + "/" + b) && exists(root + "/.deleting-" + b) && !exists(root + "/active.json"));
    CHECK(saves::runDirectories(root).empty());
    CHECK(saves::sweepDeleting(root, testOps()) == 0 && exists(root + "/.deleting-" + b));  // still failing
    failUnlinkSuffix.clear();
    CHECK(saves::sweepDeleting(root) == 1 && !exists(root + "/.deleting-" + b));
    CHECK(exists(root + "/.pending-r000000006ae40000-dddddddd") && exists(root + "/player-name.txt"));
    // a stale .deleting-<id> from an earlier attempt is finished before a new delete of the same id
    fakeRun(root, a);
    fakeRun(root, ".deleting-" + a);
    CHECK(saves::deleteRun(root, a, error) == saves::DeleteResult::Deleted && !exists(root + "/.deleting-" + a));
    // the active run, deleted cleanly: no active run afterwards; another run's marker is never touched
    fakeRun(root, a);
    fakeRun(root, b);
    setActive(root, a);
    CHECK(saves::deleteRun(root, b, error) == saves::DeleteResult::Deleted && saves::activeMarker(root) == a);
    CHECK(saves::deleteRun(root, a, error) == saves::DeleteResult::Deleted && !exists(root + "/active.json"));
    // "delete all unsupported" = one deleteRun per run; the first failure stops it and the rest stay whole
    fakeRun(root, a);
    fakeRun(root, b);
    fakeRun(root, c);
    failRenameFrom = b;
    int deleted = 0;
    for (const auto& id : saves::runDirectories(root)) {  // c, b, a
        if (saves::deleteRun(root, id, error, testOps()) == saves::DeleteResult::Failed) break;
        deleted++;
    }
    failRenameFrom.clear();
    CHECK(deleted == 1 && !exists(root + "/" + c) && exists(root + "/" + b + "/report.json") && exists(root + "/" + a + "/report.json"));
}

int main(int argc, char** argv) {
    if (argc < 2) { std::fprintf(stderr, "usage: test_saves <new scratch root> [v3 report] [v2 report] [save main]\n"); return 2; }
    const std::string scratch = argv[1];
    mkdirs(scratch);
    testCompat(argc > 2 ? argv[2] : nullptr, argc > 3 ? argv[3] : nullptr);
    testContainer(scratch);
    testSourceReport(scratch);
    testNames();
    testSaveProgress(argc > 4 ? argv[4] : nullptr, argc > 5 ? argv[5] : nullptr);
    testDelete(scratch);
    if (failures) { std::fprintf(stderr, "%d of %d check(s) failed\n", failures, checks); return 1; }
    std::printf("PASS: saves (%d checks: compatibility rule, slot container, save progress reader, deletion with injected failures)\n", checks);
    return 0;
}
