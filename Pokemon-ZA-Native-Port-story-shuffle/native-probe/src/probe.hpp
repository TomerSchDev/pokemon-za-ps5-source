#pragma once

#include <cstdint>

namespace za::probe {
void start() noexcept;
void video_result(const char *stage, int result, bool ready = false) noexcept;
void tick() noexcept;
const char *memory_summary() noexcept;
const char *storage_summary() noexcept;
}
