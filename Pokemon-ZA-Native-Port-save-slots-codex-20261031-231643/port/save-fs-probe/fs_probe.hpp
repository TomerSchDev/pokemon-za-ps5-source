#pragma once
namespace za::save_fs_probe {
// Production uses only the side title's /download0; no argv/env path override.
int run() noexcept;
const char* summary() noexcept;
#ifdef ZA_SAVE_FS_PROBE_HOST_TEST
int run_host(const char* private_parent) noexcept;
#endif
}
