// Minimal PNG writer (zlib deflate, 8-bit RGBA, no filtering) for the host mockups and render tests.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace ui {
// Encodes straight-alpha RGBA8 rows. Returns the file bytes (empty on failure).
std::vector<uint8_t> encodePng(const uint8_t* rgba, int width, int height);
bool writePng(const std::string& path, const uint8_t* rgba, int width, int height);
// Decodes a PNG written by encodePng (8-bit RGBA, filter 0 rows). Only what the mockup pipeline needs.
bool readPngRGBA(const std::string& path, std::vector<uint8_t>& rgba, int& width, int& height);
}  // namespace ui
