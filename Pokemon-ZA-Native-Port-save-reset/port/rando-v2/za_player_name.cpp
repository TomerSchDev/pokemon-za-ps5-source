#include "za_player_name.hpp"

#include <mbedtls/sha256.h>

#include <array>
#include <cstring>

namespace za::native {
namespace {
// ---- SwishCrypto (PKHeX Saves/Encryption/SwishCrypto/SwishCrypto.cs)
constexpr size_t HashSize = 0x20;
constexpr uint8_t IntroHash[64] = {
    0x9E, 0xC9, 0x9C, 0xD7, 0x0E, 0xD3, 0x3C, 0x44, 0xFB, 0x93, 0x03, 0xDC, 0xEB, 0x39, 0xB4, 0x2A,
    0x19, 0x47, 0xE9, 0x63, 0x4B, 0xA2, 0x33, 0x44, 0x16, 0xBF, 0x82, 0xA2, 0xBA, 0x63, 0x55, 0xB6,
    0x3D, 0x9D, 0xF2, 0x4B, 0x5F, 0x7B, 0x6A, 0xB2, 0x62, 0x1D, 0xC2, 0x1B, 0x68, 0xE5, 0xC8, 0xB5,
    0x3A, 0x05, 0x90, 0x00, 0xE8, 0xA8, 0x10, 0x3D, 0xE2, 0xEC, 0xF0, 0x0C, 0xB2, 0xED, 0x4F, 0x6D,
};
constexpr uint8_t OutroHash[64] = {
    0xD6, 0xC0, 0x1C, 0x59, 0x8B, 0xC8, 0xB8, 0xCB, 0x46, 0xE1, 0x53, 0xFC, 0x82, 0x8C, 0x75, 0x75,
    0x13, 0xE0, 0x45, 0xDF, 0x32, 0x69, 0x3C, 0x75, 0xF0, 0x59, 0xF8, 0xD9, 0xA2, 0x5F, 0xB2, 0x17,
    0xE0, 0x80, 0x52, 0xDB, 0xEA, 0x89, 0x73, 0x99, 0x75, 0x79, 0xAF, 0xCB, 0x2E, 0x80, 0x07, 0xE6,
    0xF1, 0x26, 0xE0, 0x03, 0x0A, 0xE6, 0x6F, 0xF6, 0x41, 0xBF, 0x7E, 0x59, 0xC2, 0xAE, 0x55, 0xFD,
};
constexpr size_t XorpadPeriod = 0x7F;  // the table is 0x80 long, the last byte is alignment padding
constexpr uint8_t Xorpad[XorpadPeriod] = {
    0xA0, 0x92, 0xD1, 0x06, 0x07, 0xDB, 0x32, 0xA1, 0xAE, 0x01, 0xF5, 0xC5, 0x1E, 0x84, 0x4F, 0xE3,
    0x53, 0xCA, 0x37, 0xF4, 0xA7, 0xB0, 0x4D, 0xA0, 0x18, 0xB7, 0xC2, 0x97, 0xDA, 0x5F, 0x53, 0x2B,
    0x75, 0xFA, 0x48, 0x16, 0xF8, 0xD4, 0x8A, 0x6F, 0x61, 0x05, 0xF4, 0xE2, 0xFD, 0x04, 0xB5, 0xA3,
    0x0F, 0xFC, 0x44, 0x92, 0xCB, 0x32, 0xE6, 0x1B, 0xB9, 0xB1, 0x2E, 0x01, 0xB0, 0x56, 0x53, 0x36,
    0xD2, 0xD1, 0x50, 0x3D, 0xDE, 0x5B, 0x2E, 0x0E, 0x52, 0xFD, 0xDF, 0x2F, 0x7B, 0xCA, 0x63, 0x50,
    0xA4, 0x67, 0x5D, 0x23, 0x17, 0xC0, 0x52, 0xE1, 0xA6, 0x30, 0x7C, 0x2B, 0xB6, 0x70, 0x36, 0x5B,
    0x2A, 0x27, 0x69, 0x33, 0xF5, 0x63, 0x7B, 0x36, 0x3F, 0x26, 0x9B, 0xA3, 0xED, 0x7A, 0x53, 0x00,
    0xA4, 0x48, 0xB3, 0x50, 0x9E, 0x14, 0xA0, 0x52, 0xDE, 0x7E, 0x10, 0x2B, 0x1B, 0x77, 0x6E,
};

constexpr uint32_t KMyStatus = 0xE3E89BD1, KParty = 0x3AA1A9AD, KBox = 0x0D66012C;
constexpr size_t MyStatusOt = 0x10, NameBytes = 0x1A;
constexpr size_t PartySlot = 0x1E0, BoxSlot = 0x198, Entity = 0x158, Stored = 0x148;
constexpr size_t PkId32 = 0x0C, PkOt = 0xF8, PkChecksum = 0x06;

uint32_t rd32(const uint8_t* p) { return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24; }
uint16_t rd16(const uint8_t* p) { return uint16_t(p[0] | p[1] << 8); }
void wr16(uint8_t* p, uint16_t v) { p[0] = uint8_t(v); p[1] = uint8_t(v >> 8); }

// SCXorShift32 (SCXorShift32.cs): popcount(seed) warm-up steps, 4 bytes per state.
struct XorShift {
    uint32_t state;
    int counter = 0;
    static uint32_t advance(uint32_t s) { s ^= s << 2; s ^= s >> 15; s ^= s << 13; return s; }
    explicit XorShift(uint32_t seed) : state(seed) {
        for (int i = __builtin_popcount(seed); i > 0; i--) state = advance(state);
    }
    uint8_t next() {
        const uint8_t r = uint8_t(state >> (counter << 3));
        if (counter == 3) { state = advance(state); counter = 0; } else ++counter;
        return r;
    }
    uint32_t next32() { uint32_t a = next(), b = next(), c = next(), d = next(); return a | b << 8 | c << 16 | d << 24; }
};

int typeSize(uint8_t t) {
    switch (t) {
    case 3: case 8: case 12: return 1;           // Bool3 (array element), Byte, SByte
    case 9: case 13: return 2;                   // UInt16, Int16
    case 10: case 14: case 16: return 4;         // UInt32, Int32, Single
    case 11: case 15: case 17: return 8;         // UInt64, Int64, Double
    default: return -1;
    }
}

// A block located in the de-xorpadded payload: its data range and the stream to (de)crypt the data.
struct Located { size_t data = 0, size = 0; uint32_t key = 0; int consumed = 0; bool found = false; };

bool hashOf(const uint8_t* payload, size_t n, uint8_t out[32]) {
    mbedtls_sha256_context ctx;
    mbedtls_sha256_init(&ctx);
    bool ok = !mbedtls_sha256_starts(&ctx, 0) && !mbedtls_sha256_update(&ctx, IntroHash, sizeof IntroHash) &&
              !mbedtls_sha256_update(&ctx, payload, n) && !mbedtls_sha256_update(&ctx, OutroHash, sizeof OutroHash) &&
              !mbedtls_sha256_finish(&ctx, out);
    mbedtls_sha256_free(&ctx);
    return ok;
}

bool hashValid(const SaveBytes& save) {
    if (save.size() <= HashSize) return false;
    uint8_t h[32];
    return hashOf(save.data(), save.size() - HashSize, h) && !memcmp(h, save.data() + save.size() - HashSize, 32);
}

// Walks every block header of the de-xorpadded payload; records the three keys the writer needs.
bool locate(const SaveBytes& plain, size_t payload, Located& my, Located& party, Located& box, std::string& error) {
    size_t at = 0;
    while (at < payload) {
        if (payload - at < 5) { error = "Save block header truncated"; return false; }
        const uint32_t key = rd32(&plain[at]);
        at += 4;
        XorShift x(key);
        const uint8_t type = uint8_t(plain[at++] ^ x.next());
        int consumed = 1;
        size_t size = 0;
        if (type == 1 || type == 2 || type == 3) {
            size = 0;
        } else if (type == 4) {
            if (payload - at < 4) { error = "Save object length truncated"; return false; }
            const uint32_t n = rd32(&plain[at]) ^ x.next32();
            at += 4; consumed += 4; size = n;
        } else if (type == 5) {
            if (payload - at < 5) { error = "Save array header truncated"; return false; }
            const uint32_t count = rd32(&plain[at]) ^ x.next32();
            at += 4;
            const int sub = typeSize(uint8_t(plain[at++] ^ x.next()));
            consumed += 5;
            if (sub < 0 || count > (1u << 28)) { error = "Save array type invalid"; return false; }
            size = size_t(count) * size_t(sub);
        } else {
            const int n = typeSize(type);
            if (n < 0) { error = "Save block type invalid"; return false; }
            size = size_t(n);
        }
        if (size > payload - at) { error = "Save block overruns the file"; return false; }
        Located* want = key == KMyStatus ? &my : key == KParty ? &party : key == KBox ? &box : nullptr;
        if (want) {
            if (want->found || type != 4) { error = "Unexpected trainer/party/box block layout"; return false; }
            *want = {at, size, key, consumed, true};
        }
        at += size;
    }
    if (!my.found || !party.found || !box.found) { error = "Trainer, party or box block missing"; return false; }
    if (my.size < MyStatusOt + NameBytes || party.size < 6 * PartySlot || box.size < BoxSlot) {
        error = "Trainer, party or box block too small"; return false;
    }
    return true;
}

// XORs a located block's data with its stream (decrypt and encrypt are the same operation).
void crypt(SaveBytes& plain, const Located& b) {
    XorShift x(b.key);
    for (int i = 0; i < b.consumed; i++) x.next();
    for (size_t i = 0; i < b.size; i++) plain[b.data + i] ^= x.next();
}

// ---- PA9 entity crypto (PKHeX PKM/Util/PokeCrypto.cs: Decrypt8 / Encrypt8 / CryptArray / Shuffle8)
constexpr uint8_t BlockPosition[] = {
    0, 1, 2, 3, 0, 1, 3, 2, 0, 2, 1, 3, 0, 3, 1, 2, 0, 2, 3, 1, 0, 3, 2, 1, 1, 0, 2, 3, 1, 0, 3, 2,
    2, 0, 1, 3, 3, 0, 1, 2, 2, 0, 3, 1, 3, 0, 2, 1, 1, 2, 0, 3, 1, 3, 0, 2, 2, 1, 0, 3, 3, 1, 0, 2,
    2, 3, 0, 1, 3, 2, 0, 1, 1, 2, 3, 0, 1, 3, 2, 0, 2, 1, 3, 0, 3, 1, 2, 0, 2, 3, 1, 0, 3, 2, 1, 0,
    0, 1, 2, 3, 0, 1, 3, 2, 0, 2, 1, 3, 0, 3, 1, 2, 0, 2, 3, 1, 0, 3, 2, 1, 1, 0, 2, 3, 1, 0, 3, 2,
};
constexpr uint8_t BlockPositionInvert[] = {0, 1, 2, 4, 3, 5, 6, 7, 12, 18, 13, 19, 8, 10, 14, 20,
                                           16, 22, 9, 11, 15, 21, 17, 23, 0, 1, 2, 4, 3, 5, 6, 7};
constexpr size_t EntityBlock = 80;

void cryptArray(uint8_t* p, size_t n, uint32_t seed) {
    for (size_t i = 0; i + 1 < n; i += 2) {
        seed = 0x41C64E6Du * seed + 0x00006073u;
        const uint16_t x = uint16_t(seed >> 16);
        p[i] ^= uint8_t(x);
        p[i + 1] ^= uint8_t(x >> 8);
    }
}

// The same in-place permutation as PokeCrypto.Shuffle<ulong>(data, sv, 80) with BlockCount = 4.
void shuffle(uint8_t* data, uint32_t sv) {
    if (!sv) return;
    uint8_t perm[4] = {0, 1, 2, 3}, slotOf[4] = {0, 1, 2, 3};
    const uint8_t* order = &BlockPosition[sv * 4];
    for (uint8_t i = 0; i < 3; i++) {
        const uint8_t desired = order[i];
        const uint8_t j = slotOf[desired];
        if (j == i) continue;
        uint8_t tmp[EntityBlock];
        memcpy(tmp, data + i * EntityBlock, EntityBlock);
        memcpy(data + i * EntityBlock, data + j * EntityBlock, EntityBlock);
        memcpy(data + j * EntityBlock, tmp, EntityBlock);
        const uint8_t blockAtI = perm[i];
        perm[j] = blockAtI;
        slotOf[blockAtI] = j;
    }
}

void decryptEntity(uint8_t* d) {
    const uint32_t pv = rd32(d), sv = (pv >> 13) & 31;
    cryptArray(d + 8, Stored - 8, pv);
    cryptArray(d + Stored, Entity - Stored, pv);
    shuffle(d + 8, sv);
}

void encryptEntity(uint8_t* d) {
    const uint32_t pv = rd32(d), sv = BlockPositionInvert[(pv >> 13) & 31];
    shuffle(d + 8, sv);
    cryptArray(d + 8, Stored - 8, pv);
    cryptArray(d + Stored, Entity - Stored, pv);
}

uint16_t entityChecksum(const uint8_t* d) {
    uint32_t sum = 0;
    for (size_t i = 8; i < Stored; i += 2) sum += rd16(d + i);
    return uint16_t(sum);
}

bool present(const uint8_t* encrypted) { return rd32(encrypted) != 0 || rd16(encrypted + 8) != 0; }

std::string readName(const uint8_t* field) {
    std::string out;
    for (size_t i = 0; i + 1 < NameBytes; i += 2) {
        const uint16_t c = rd16(field + i);
        if (!c) break;
        out += c < 0x80 ? char(c) : '?';  // non-ASCII names never match an ASCII replacement
    }
    return out;
}

bool sameName(const uint8_t* a, const uint8_t* b) {
    for (size_t i = 0; i + 1 < NameBytes; i += 2) {
        const uint16_t x = rd16(a + i), y = rd16(b + i);
        if (x != y) return false;
        if (!x) return true;
    }
    return true;
}

void writeName(uint8_t* field, const std::string& name) {
    memset(field, 0, NameBytes);  // StringConverterOption.ClearZero: no trash after the terminator
    for (size_t i = 0; i < name.size(); i++) wr16(field + 2 * i, uint16_t(uint8_t(name[i])));
}

// Renames the player's own Pokemon in one storage block (data already stream-decrypted).
void renameSlots(uint8_t* block, size_t size, size_t slotSize, uint32_t id32, const uint8_t* oldName,
                 const std::string& name, PlayerNameEdit& edit) {
    for (size_t at = 0; at + slotSize <= size; at += slotSize) {
        uint8_t* slot = block + at;
        if (!present(slot)) continue;
        uint8_t pk[Entity];
        memcpy(pk, slot, Entity);
        decryptEntity(pk);
        if (entityChecksum(pk) != rd16(pk + PkChecksum)) { edit.pokemonUnreadable++; continue; }
        if (rd32(pk + PkId32) != id32 || !sameName(pk + PkOt, oldName)) { edit.pokemonKept++; continue; }
        writeName(pk + PkOt, name);
        wr16(pk + PkChecksum, entityChecksum(pk));
        encryptEntity(pk);
        memcpy(slot, pk, Entity);
        edit.pokemonRenamed++;
    }
}

bool openPayload(const SaveBytes& save, SaveBytes& plain, size_t& payload, Located& my, Located& party, Located& box,
                 std::string& error) {
    if (save.size() < 0x10000 || save.size() > (64u << 20)) { error = "Save size is not a Z-A main save"; return false; }
    if (!hashValid(save)) { error = "Save hash is invalid"; return false; }
    payload = save.size() - HashSize;
    plain.assign(save.begin(), save.end());
    for (size_t i = 0; i < payload; i++) plain[i] ^= Xorpad[i % XorpadPeriod];
    return locate(plain, payload, my, party, box, error);
}
}  // namespace

bool validPlayerName(const std::string& name, std::string* why) {
    auto fail = [&](const char* w) { if (why) *why = w; return false; };
    if (name.empty()) return fail("Name is empty");
    if (name.size() > PlayerNameMax) return fail("Name is longer than 12 characters");
    if (name.front() == ' ' || name.back() == ' ') return fail("Name starts or ends with a space");
    for (unsigned char c : name) {
        const bool ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
                        c == ' ' || c == '-' || c == '.' || c == '!' || c == '?' || c == '\'' || c == '&';
        if (!ok) return fail("Name has a character the keyboard does not offer");
    }
    return true;
}

bool readPlayerName(const SaveBytes& save, std::string& name, std::string& error) {
    SaveBytes plain;
    size_t payload = 0;
    Located my, party, box;
    if (!openPayload(save, plain, payload, my, party, box, error)) return false;
    crypt(plain, my);
    name = readName(&plain[my.data + MyStatusOt]);
    return true;
}

bool applyPlayerName(SaveBytes& save, const std::string& name, PlayerNameEdit& edit, std::string& error) {
    edit = {};
    std::string why;
    if (!validPlayerName(name, &why)) { error = why; return false; }
    SaveBytes plain;
    size_t payload = 0;
    Located my, party, box;
    if (!openPayload(save, plain, payload, my, party, box, error)) return false;

    crypt(plain, my);
    uint8_t* status = &plain[my.data];
    uint8_t oldName[NameBytes];
    memcpy(oldName, status + MyStatusOt, NameBytes);
    edit.oldName = readName(oldName);
    const uint32_t id32 = rd32(status);
    writeName(status + MyStatusOt, name);
    crypt(plain, my);

    crypt(plain, party);
    renameSlots(&plain[party.data], 6 * PartySlot, PartySlot, id32, oldName, name, edit);
    crypt(plain, party);
    crypt(plain, box);
    renameSlots(&plain[box.data], box.size, BoxSlot, id32, oldName, name, edit);
    crypt(plain, box);

    for (size_t i = 0; i < payload; i++) plain[i] ^= Xorpad[i % XorpadPeriod];
    if (!hashOf(plain.data(), payload, &plain[payload])) { error = "Save hash could not be computed"; return false; }
    save.swap(plain);
    return true;
}
}  // namespace za::native
