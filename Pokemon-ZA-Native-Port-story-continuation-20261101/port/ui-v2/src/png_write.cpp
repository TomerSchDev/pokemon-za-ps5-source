#include "png_write.h"

#include <cstdio>
#include <cstring>
#include <zlib.h>

namespace ui {

static void put32(std::vector<uint8_t>& v, uint32_t x) {
    v.push_back(uint8_t(x >> 24));
    v.push_back(uint8_t(x >> 16));
    v.push_back(uint8_t(x >> 8));
    v.push_back(uint8_t(x));
}

static void chunk(std::vector<uint8_t>& out, const char* type, const uint8_t* data, size_t n) {
    put32(out, uint32_t(n));
    size_t start = out.size();
    out.insert(out.end(), type, type + 4);
    if (n) out.insert(out.end(), data, data + n);
    uint32_t crc = (uint32_t)crc32(0, out.data() + start, uInt(n + 4));
    put32(out, crc);
}

std::vector<uint8_t> encodePng(const uint8_t* rgba, int width, int height) {
    std::vector<uint8_t> out;
    if (width <= 0 || height <= 0) return out;
    std::vector<uint8_t> raw(size_t(height) * (size_t(width) * 4 + 1));
    for (int y = 0; y < height; y++) {
        uint8_t* row = &raw[size_t(y) * (size_t(width) * 4 + 1)];
        row[0] = 0;  // filter: none
        std::memcpy(row + 1, rgba + size_t(y) * width * 4, size_t(width) * 4);
    }
    uLongf bound = compressBound(uLong(raw.size()));
    std::vector<uint8_t> z(bound);
    if (compress2(z.data(), &bound, raw.data(), uLong(raw.size()), 6) != Z_OK) return out;
    z.resize(bound);
    static const uint8_t sig[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    out.insert(out.end(), sig, sig + 8);
    std::vector<uint8_t> ihdr;
    put32(ihdr, uint32_t(width));
    put32(ihdr, uint32_t(height));
    ihdr.push_back(8);  // bit depth
    ihdr.push_back(6);  // RGBA
    ihdr.push_back(0);
    ihdr.push_back(0);
    ihdr.push_back(0);
    chunk(out, "IHDR", ihdr.data(), ihdr.size());
    chunk(out, "IDAT", z.data(), z.size());
    chunk(out, "IEND", nullptr, 0);
    return out;
}

bool writePng(const std::string& path, const uint8_t* rgba, int width, int height) {
    auto bytes = encodePng(rgba, width, height);
    if (bytes.empty()) return false;
    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f) return false;
    bool ok = std::fwrite(bytes.data(), 1, bytes.size(), f) == bytes.size();
    if (std::fclose(f)) ok = false;
    return ok;
}

static uint32_t get32(const uint8_t* p) { return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3]; }

bool readPngRGBA(const std::string& path, std::vector<uint8_t>& rgba, int& width, int& height) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    std::vector<uint8_t> file;
    uint8_t buf[65536];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) file.insert(file.end(), buf, buf + n);
    std::fclose(f);
    if (file.size() < 33 || std::memcmp(file.data() + 1, "PNG", 3) != 0) return false;
    size_t at = 8;
    std::vector<uint8_t> idat;
    width = height = 0;
    int depth = 0, type = 0;
    while (at + 12 <= file.size()) {
        uint32_t len = get32(&file[at]);
        const uint8_t* ty = &file[at + 4];
        const uint8_t* data = &file[at + 8];
        if (at + 12 + len > file.size()) return false;
        if (!std::memcmp(ty, "IHDR", 4)) {
            width = int(get32(data));
            height = int(get32(data + 4));
            depth = data[8];
            type = data[9];
        } else if (!std::memcmp(ty, "IDAT", 4)) {
            idat.insert(idat.end(), data, data + len);
        } else if (!std::memcmp(ty, "IEND", 4)) {
            break;
        }
        at += 12 + len;
    }
    if (width <= 0 || height <= 0 || depth != 8 || (type != 6 && type != 2)) return false;
    int bpp = type == 6 ? 4 : 3;
    size_t stride = size_t(width) * bpp + 1;
    std::vector<uint8_t> raw(stride * height);
    uLongf outLen = uLongf(raw.size());
    if (uncompress(raw.data(), &outLen, idat.data(), uLong(idat.size())) != Z_OK || outLen != raw.size()) return false;
    rgba.assign(size_t(width) * height * 4, 255);
    std::vector<uint8_t> prev(stride - 1, 0);
    for (int y = 0; y < height; y++) {
        uint8_t filter = raw[size_t(y) * stride];
        uint8_t* row = &raw[size_t(y) * stride + 1];
        for (size_t i = 0; i < stride - 1; i++) {
            uint8_t a = i >= size_t(bpp) ? row[i - bpp] : 0, b = prev[i], c = i >= size_t(bpp) ? prev[i - bpp] : 0;
            switch (filter) {
                case 1: row[i] = uint8_t(row[i] + a); break;
                case 2: row[i] = uint8_t(row[i] + b); break;
                case 3: row[i] = uint8_t(row[i] + ((a + b) >> 1)); break;
                case 4: {
                    int p = a + b - c, pa = std::abs(p - a), pb = std::abs(p - b), pc = std::abs(p - c);
                    row[i] = uint8_t(row[i] + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c));
                    break;
                }
                default: break;
            }
        }
        std::memcpy(prev.data(), row, stride - 1);
        for (int x = 0; x < width; x++)
            for (int k = 0; k < bpp; k++) rgba[(size_t(y) * width + x) * 4 + k] = row[size_t(x) * bpp + k];
    }
    return true;
}

}  // namespace ui
