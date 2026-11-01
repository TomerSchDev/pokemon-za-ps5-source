#include "settings_codes.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <utility>
#include <vector>

namespace ui::codes {
namespace {

using Projection = std::map<std::string, std::string>;
struct Category {
    const char* id;
    std::vector<const char*> rows;
};
const std::array<Category, 7>& categories() {
    static const std::array<Category, 7> defs = {{
        {"wild", {"wild_mode", "wild_levels", "wild_mega_rate", "alpha_rate", "held_items", "forms"}},
        {"trainers", {"trainers_mode", "mega_trainers", "dlc_rematches", "trainer_levels", "trainer_moves", "trainer_items"}},
        {"starter", {"starter_mode", "starter_pick", "starter_level"}},
        {"research", {"research_rewards", "research_requirements"}},
        {"music", {"music"}},
        {"player", {"player_name", "starting_money"}},
        {"cheats", {"shiny_default", "capture_default", "fps_counter_default"}},
    }};
    return defs;
}

std::string decimal(int64_t value) {
    const bool negative = value < 0;
    uint64_t n = negative ? uint64_t(-(value + 1)) + 1 : uint64_t(value);
    char digits[21];
    size_t at = sizeof digits;
    do { digits[--at] = char('0' + n % 10); n /= 10; } while (n);
    if (negative) digits[--at] = '-';
    return std::string(digits + at, sizeof digits - at);
}

int optionIndex(const model::RowDef& row, const model::Values& values) {
    const int index = values.get(row.id, row.def);
    return index >= 0 && index < int(row.options.size()) ? index : row.def;
}

Projection project(const Category& category, const model::Values& values, const model::Values& defaults) {
    Projection result;
    for (const char* key : category.rows) {
        const model::RowDef* row = model::findRow(key);
        if (!row) { result[key] = "missing"; continue; }  // a mismatched model must not impersonate a default
        if (row->kind == model::Kind::Level || row->kind == model::Kind::Toggle) {
            const int index = optionIndex(*row, values);
            result[key] = index >= 0 && index < int(row->options.size()) ?
                "e:" + std::string(row->options[size_t(index)].id) : "invalid";
        } else if (row->kind == model::Kind::Text) {
            const auto found = values.texts.find(key);
            result[key] = "s:" + (found == values.texts.end() ? defaults.text(key) : found->second);
        } else if (row->kind == model::Kind::Number) {
            result[key] = "n:" + decimal(values.get(key, row->def));
        } else if (row->kind == model::Kind::Pick) {
            const model::RowDef* mode = model::findRow(row->dependsOn);
            const auto& list = model::starterList(mode ? optionIndex(*mode, values) : 2);
            if (list.empty()) result[key] = "null";
            else {
                const int index = std::clamp(values.get(key, row->def), 0, int(list.size()) - 1);
                result[key] = "n:" + decimal(list[size_t(index)].species);
            }
        }
    }
    return result;
}

void appendPair(std::string& out, const std::string& key, const std::string& value) {
    out += decimal(int64_t(key.size())); out += ':'; out += key;
    out += decimal(int64_t(value.size())); out += ':'; out += value;
}

std::string canonical(const char* category, const Projection& projection, const std::string& algorithm, const std::string& gameBuild) {
    std::string out = "ZA-SETTINGS-WORDS\n";
    appendPair(out, "schema", Schema);
    appendPair(out, "wordbank", WordBankVersion);
    appendPair(out, "wordbank_sha256", WordBankSha256);
    appendPair(out, "algorithm", algorithm);
    appendPair(out, "game_build", gameBuild);
    appendPair(out, "category", category);
    for (const auto& field : projection) appendPair(out, field.first, field.second);
    return out;
}

uint32_t rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }

// SHA-256 uses explicit big-endian loads/stores and unsigned 32-bit modular arithmetic.
// No platform crypto state, std::hash, locale, pointer representation or RNG is involved.
std::array<uint8_t, 32> sha256(const std::string& input) {
    static constexpr uint32_t k[64] = {
        0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
        0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
        0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
        0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
        0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
        0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
        0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
        0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u,
    };
    uint32_t h[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                     0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
    std::vector<uint8_t> bytes(input.begin(), input.end());
    const uint64_t bits = uint64_t(bytes.size()) * 8;
    bytes.push_back(0x80);
    while (bytes.size() % 64 != 56) bytes.push_back(0);
    for (int shift = 56; shift >= 0; shift -= 8) bytes.push_back(uint8_t(bits >> shift));
    for (size_t block = 0; block < bytes.size(); block += 64) {
        uint32_t w[64];
        for (size_t i = 0; i < 16; i++) {
            const size_t p = block + i * 4;
            w[i] = uint32_t(bytes[p]) << 24 | uint32_t(bytes[p+1]) << 16 |
                   uint32_t(bytes[p+2]) << 8 | uint32_t(bytes[p+3]);
        }
        for (size_t i = 16; i < 64; i++) {
            const uint32_t s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >> 3);
            const uint32_t s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >> 10);
            w[i] = w[i-16] + s0 + w[i-7] + s1;
        }
        uint32_t a=h[0], b=h[1], c=h[2], d=h[3], e=h[4], f=h[5], g=h[6], z=h[7];
        for (size_t i = 0; i < 64; i++) {
            const uint32_t s1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
            const uint32_t t1 = z + s1 + ((e & f) ^ (~e & g)) + k[i] + w[i];
            const uint32_t s0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
            const uint32_t t2 = s0 + ((a & b) ^ (a & c) ^ (b & c));
            z=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=z;
    }
    std::array<uint8_t, 32> result{};
    for (size_t i = 0; i < 8; i++) for (size_t j = 0; j < 4; j++) result[i*4+j] = uint8_t(h[i] >> (24-j*8));
    return result;
}

#include "settings_words.inc"
static_assert(sizeof kComparisonWords / sizeof kComparisonWords[0] == 256,
              "comparison word bank must contain exactly 256 words");

bool wordBankValid() {
    static const bool valid = [] {
        std::string serialized;
        for (const char* word : kComparisonWords) { serialized += word; serialized += '\n'; }
        static constexpr char hex[] = "0123456789abcdef";
        std::string actual;
        for (uint8_t byte : sha256(serialized)) { actual += hex[byte >> 4]; actual += hex[byte & 15]; }
        return actual == WordBankSha256;
    }();
    return valid;
}

std::string encode(const std::string& payload) {
    if (!wordBankValid()) return {};
    const auto digest = sha256(payload);
    std::string result;
    for (size_t i = 0; i < 4; i++) {
        if (i) result += '-';
        result += kComparisonWords[digest[i]];
    }
    return result;
}

}  // namespace

std::string categoryCode(const std::string& categoryId, const model::Values& values, const std::string& algorithm, const std::string& gameBuild) {
    if (algorithm.empty() || gameBuild.empty()) return {};
    const auto defaults = model::defaults();
    for (const auto& category : categories()) if (categoryId == category.id)
        return encode(canonical(category.id, project(category, values, defaults), algorithm, gameBuild));
    return {};
}

std::string configurationCode(const model::Values& values, const std::string& algorithm, const std::string& gameBuild) {
    if (algorithm.empty() || gameBuild.empty()) return {};
    const auto defaults = model::defaults();
    Projection all;
    for (const auto& category : categories()) for (const auto& field : project(category, values, defaults))
        all[std::string(category.id) + "." + field.first] = field.second;
    return encode(canonical("configuration", all, algorithm, gameBuild));
}

SettingsCodes compute(const model::Values& values, const std::string& algorithm, const std::string& gameBuild) {
    return {categoryCode("wild", values, algorithm, gameBuild), categoryCode("trainers", values, algorithm, gameBuild),
            categoryCode("starter", values, algorithm, gameBuild), categoryCode("research", values, algorithm, gameBuild),
            categoryCode("music", values, algorithm, gameBuild), categoryCode("player", values, algorithm, gameBuild),
            categoryCode("cheats", values, algorithm, gameBuild), configurationCode(values, algorithm, gameBuild)};
}

const std::string& forPage(const SettingsCodes& codes, const std::string& pageId) {
    if (pageId == "wild") return codes.wild;
    if (pageId == "trainers") return codes.trainers;
    if (pageId == "starter") return codes.starter;
    if (pageId == "research") return codes.research;
    if (pageId == "music") return codes.music;
    if (pageId == "player") return codes.player;
    if (pageId == "cheats") return codes.cheats;
    if (pageId == "play" || pageId == "saved") return codes.overall;
    static const std::string empty;
    return empty;
}

}  // namespace ui::codes
