#include "za_music.hpp"
#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <map>
#include <set>
#include <unistd.h>
#include <vector>

namespace za::native {
namespace {
constexpr const char* BuildId = "b1f12fd919eae86ab8a978317677e64bce443d1f";
constexpr const char* Categories[] = {"town", "zone", "battle", "boss"};
constexpr uint8_t PlaylistType = 13;  // CAkMusicRanSeqCntr
constexpr size_t MaxBank = 16u << 20;

uint32_t rd32(const Bytes& d, size_t p) {
    return uint32_t(d[p]) | (uint32_t(d[p + 1]) << 8) | (uint32_t(d[p + 2]) << 16) | (uint32_t(d[p + 3]) << 24);
}
void wr32(Bytes& d, size_t p, uint32_t v) {
    for (int i = 0; i < 4; i++) d[p + i] = uint8_t(v >> (8 * i));
}
std::string hex8(uint32_t v) {
    char b[9];
    snprintf(b, sizeof b, "%08x", v);
    return b;
}
// Fail-closed accessors: JSON_NOEXCEPTION builds abort on a wrong type, so every field is checked first.
bool str(const Json& o, const char* k, std::string& v) {
    if (!o.is_object() || !o.contains(k) || !o.at(k).is_string()) return false;
    v = o.at(k).get<std::string>();
    return true;
}
bool uint(const Json& o, const char* k, uint64_t& v) {
    if (!o.is_object() || !o.contains(k) || !o.at(k).is_number_unsigned()) return false;
    v = o.at(k).get<uint64_t>();
    return true;
}
bool hexId(const Json& j, uint32_t& out) {
    if (!j.is_string()) return false;
    const std::string s = j.get<std::string>();
    if (s.size() != 8) return false;
    uint32_t v = 0;
    for (char c : s) {
        const int n = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
        if (n < 0) return false;
        v = (v << 4) | uint32_t(n);
    }
    out = v;
    return v != 0;
}
bool sha(const std::string& s) {
    return s.size() == 64 && std::all_of(s.begin(), s.end(), [](char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); });
}

// The bank's HIRC object types by id, and the HIRC body range. Checks every section and object size.
struct Hirc {
    std::map<uint32_t, uint8_t> types;
    size_t begin = 0, end = 0;
};
bool indexBank(const Bytes& d, Hirc& h) {
    size_t p = 0;
    bool header = false;
    while (p + 8 <= d.size()) {
        const uint32_t tag = rd32(d, p), size = rd32(d, p + 4);
        if (size > d.size() - p - 8) return false;
        if (tag == 0x44484b42u) {  // BKHD: Wwise 2022.1 bank version 145
            if (size < 8 || rd32(d, p + 8) != 145) return false;
            header = true;
        }
        if (tag == 0x43524948u) {  // HIRC
            if (size < 4 || h.end) return false;
            h.begin = p + 8;
            h.end = p + 8 + size;
            const uint32_t n = rd32(d, p + 8);
            size_t q = p + 12;
            for (uint32_t i = 0; i < n; i++) {
                if (q + 9 > h.end) return false;
                const uint32_t sz = rd32(d, q + 1), id = rd32(d, q + 5);
                if (sz < 4 || sz > h.end - q - 5 || !h.types.emplace(id, d[q]).second) return false;
                q += 5 + size_t(sz);
            }
            if (q != h.end) return false;
        }
        p += 8 + size_t(size);
    }
    return p == d.size() && header && h.end;
}

// Domain-separated SHA-256 choice in [0, bound), uniform by rejection (same construction as research rewards).
uint64_t choose(const std::string& seed, const char* mode, const std::string& scope, size_t step, uint64_t bound) {
    const uint64_t rem = (UINT64_MAX % bound + 1) % bound;
    for (int attempt = 0; attempt < 1000; attempt++) {
        const auto text = Json::array({MusicAlgorithm, BuildId, seed, mode, scope, step, attempt}).dump();
        const auto hash = sha256(Bytes(text.begin(), text.end()));
        uint64_t word = 0;
        for (int i = 0; i < 16; i++) word = (word << 4) | uint64_t(hash[i] <= '9' ? hash[i] - '0' : hash[i] - 'a' + 10);
        if (!rem || word <= UINT64_MAX - rem) return word % bound;
    }
    std::abort();
}
// Fisher-Yates permutation, then every fixed point is swapped with its successor: a derangement for n >= 2.
std::vector<size_t> derangement(size_t n, const std::string& seed, const char* mode, const std::string& scope) {
    std::vector<size_t> p(n);
    for (size_t i = 0; i < n; i++) p[i] = i;
    for (size_t i = n; i-- > 1;) std::swap(p[i], p[size_t(choose(seed, mode, scope, i, i + 1))]);
    if (n > 1)
        for (size_t i = 0; i < n; i++)
            if (p[i] == i) std::swap(p[i], p[(i + 1) % n]);
    return p;
}

struct Unit {
    std::string category;
    std::vector<uint32_t> members;
    size_t slots = 0;
};
struct Slot {
    size_t offset;
    uint32_t song;
    size_t unit, member;
};
}  // namespace

const char* musicModeId(MusicMode mode) {
    switch (mode) {
    case MusicMode::Category: return "category";
    case MusicMode::Chaos: return "chaos";
    default: return "off";
    }
}
const char* musicModeLabel(MusicMode mode) {
    switch (mode) {
    case MusicMode::Category: return "SHUFFLE BY CATEGORY";
    case MusicMode::Chaos: return "CHAOS";
    default: return "OFF";
    }
}
bool parseMusicMode(const std::string& id, MusicMode& mode) {
    for (int i = 0; i < MusicModeCount; i++)
        if (id == musicModeId(MusicMode(i))) {
            mode = MusicMode(i);
            return true;
        }
    return false;
}

bool shuffleMusic(const std::string& planText, const Bytes& original, const std::string& seed, MusicMode mode,
                  Bytes& out, Json& report, std::string& error) {
    auto fail = [&](const char* m) {
        error = m;
        return false;
    };
    if (mode != MusicMode::Category && mode != MusicMode::Chaos) return fail("Music mode has nothing to build");
    if (seed.empty() || seed.size() > 64) return fail("Invalid music seed");
    const Json plan = Json::parse(planText, nullptr, false);
    std::string s;
    uint64_t n = 0;
    if (plan.is_discarded() || !plan.is_object() || !uint(plan, "schema", n) || n != 1 || !str(plan, "algorithm", s) ||
        s != MusicAlgorithm || !str(plan, "build_id", s) || s != BuildId)
        return fail("Music plan version mismatch");
    if (!plan.contains("categories") || plan.at("categories") != Json(std::vector<std::string>(std::begin(Categories), std::end(Categories))))
        return fail("Music plan categories mismatch");
    if (!plan.contains("bank") || !str(plan.at("bank"), "path", s) || s != MusicBankPath) return fail("Music plan bank mismatch");
    std::string bankSha;
    if (!uint(plan.at("bank"), "bytes", n) || n != original.size() || n > MaxBank || !str(plan.at("bank"), "sha256", bankSha) ||
        !sha(bankSha) || sha256(original) != bankSha)
        return fail("Game music bank does not match the plan");
    Hirc hirc;
    if (!indexBank(original, hirc)) return fail("Game music bank structure invalid");
    if (!plan.contains("units") || !plan.at("units").is_array() || plan.at("units").empty() || plan.at("units").size() > 4096 ||
        !plan.contains("slots") || !plan.at("slots").is_array() || plan.at("slots").empty() || plan.at("slots").size() > 65536)
        return fail("Music plan tables invalid");
    std::vector<Unit> units;
    std::set<uint32_t> allMembers;
    for (const auto& u : plan.at("units")) {
        Unit unit;
        if (!uint(u, "unit", n) || n != units.size() || !str(u, "category", unit.category) ||
            std::find_if(std::begin(Categories), std::end(Categories), [&](const char* c) { return unit.category == c; }) == std::end(Categories) ||
            !u.contains("members") || !u.at("members").is_array() || u.at("members").empty() || u.at("members").size() > 64)
            return fail("Music plan unit invalid");
        for (const auto& m : u.at("members")) {
            uint32_t id = 0;
            if (!hexId(m, id) || !allMembers.insert(id).second) return fail("Music plan song invalid");
            const auto type = hirc.types.find(id);
            if (type == hirc.types.end() || type->second != PlaylistType) return fail("Music plan song is not a music playlist");
            unit.members.push_back(id);
        }
        units.push_back(std::move(unit));
    }
    std::vector<Slot> slots;
    for (const auto& j : plan.at("slots")) {
        Slot slot{};
        uint64_t off = 0, unit = 0;
        if (!uint(j, "offset", off) || !uint(j, "unit", unit) || !j.contains("song") || !hexId(j.at("song"), slot.song) ||
            unit >= units.size() || off < hirc.begin || off > hirc.end - 4 || (!slots.empty() && off <= slots.back().offset))
            return fail("Music plan slot invalid");
        slot.offset = size_t(off);
        slot.unit = size_t(unit);
        const auto& members = units[slot.unit].members;
        const auto at = std::find(members.begin(), members.end(), slot.song);
        if (at == members.end() || rd32(original, slot.offset) != slot.song) return fail("Music plan slot does not match the bank");
        slot.member = size_t(at - members.begin());
        units[slot.unit].slots++;
        slots.push_back(slot);
    }
    for (const auto& u : units)
        if (!u.slots) return fail("Music plan unit without slots");

    // unit -> replacement unit
    std::vector<size_t> target(units.size());
    const char* modeId = musicModeId(mode);
    if (mode == MusicMode::Category) {
        for (const char* category : Categories) {
            std::vector<size_t> list;
            for (size_t i = 0; i < units.size(); i++)
                if (units[i].category == category) list.push_back(i);
            const auto p = derangement(list.size(), seed, modeId, category);
            for (size_t i = 0; i < list.size(); i++) target[list[i]] = list[p[i]];
        }
    } else {
        const auto p = derangement(units.size(), seed, modeId, "all");
        for (size_t i = 0; i < units.size(); i++) target[i] = p[i];
    }
    out = original;
    size_t changed = 0;
    for (const auto& slot : slots) {
        const auto& to = units[target[slot.unit]].members;
        const uint32_t song = to[slot.member % to.size()];
        if (song != slot.song) changed++;
        wr32(out, slot.offset, song);
    }
    // Self-check: same size and structure, only slot words differ, each slot holds a planned song of its target.
    Hirc after;
    if (out.size() != original.size() || !indexBank(out, after) || after.types != hirc.types) return fail("Music output structure check failed");
    size_t next = 0;
    for (size_t i = 0; i < out.size(); i++) {
        if (out[i] == original[i]) continue;
        while (next < slots.size() && slots[next].offset + 4 <= i) next++;
        if (next == slots.size() || i < slots[next].offset) return fail("Music output changed an unplanned byte");
    }
    Json assignments = Json::array();
    for (size_t i = 0; i < units.size(); i++)
        assignments.push_back({{"unit", i}, {"category", units[i].category}, {"song", hex8(units[i].members[0])},
                               {"to_unit", target[i]}, {"to_category", units[target[i]].category},
                               {"to_song", hex8(units[target[i]].members[0])}});
    report = {{"algorithm", MusicAlgorithm}, {"mode", modeId}, {"plan_sha256", sha256(Bytes(planText.begin(), planText.end()))},
              {"bank_path", MusicBankPath}, {"original_sha256", bankSha}, {"sha256", sha256(out)},
              {"units", units.size()}, {"slots", slots.size()}, {"changed_slots", changed}, {"assignments", assignments}};
    return true;
}

bool randomizeMusic(const std::string& planText, const BankReader& read, const std::string& seed, MusicMode mode,
                    Result& result, std::string& error) {
    if (mode == MusicMode::Off) {
        result.report["music"] = {{"algorithm", MusicAlgorithm}, {"mode", "off"}};
        result.report["options"]["music"] = "off";
        return true;
    }
    const Json plan = Json::parse(planText, nullptr, false);
    if (plan.is_discarded() || !plan.is_object()) {
        error = "Music plan is not valid JSON";
        return false;
    }
    Bytes original, out;
    if (!read(plan, original)) {
        error = "Cannot read the game's music bank";
        return false;
    }
    Json report;
    if (!shuffleMusic(planText, original, seed, mode, out, report, error)) return false;
    result.report["table_sha256"][MusicTableName] = report.at("sha256");
    result.report["music"] = std::move(report);
    result.report["options"]["music"] = musicModeId(mode);
    result.tables[MusicTableName] = std::move(out);
    return true;
}

bool readBankFromRomfs(const std::string& image, const Json& plan, Bytes& bank) {
    bank.clear();
    uint64_t off = 0, size = 0;
    if (!plan.is_object() || !plan.contains("bank") || !uint(plan.at("bank"), "romfs_image_offset", off) ||
        !uint(plan.at("bank"), "bytes", size) || !size || size > MaxBank || off > UINT64_MAX - size)
        return false;
    const int fd = open(image.c_str(), O_RDONLY);
    if (fd < 0) return false;
    bank.resize(size_t(size));
    size_t at = 0;
    bool ok = true;
    while (at < bank.size()) {
        const ssize_t got = pread(fd, bank.data() + at, bank.size() - at, off_t(off + at));
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) {
            ok = false;
            break;
        }
        at += size_t(got);
    }
    if (close(fd)) ok = false;
    if (!ok) bank.clear();
    return ok;
}
}  // namespace za::native
