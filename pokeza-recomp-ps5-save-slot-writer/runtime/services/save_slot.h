// The randomizer's per-run slot container (rando/<run id>/slot.zrs, format services/za_slot.h) follows the game's own
// save: every IFileSystem Commit of the run's save file system (fs.c) wakes a background writer that, after a short
// debounce, reads <run>/save/save_0/main, checks its SwishCrypto hash and rewrites slot.zrs atomically next to it (the
// RAND / SETT sections kept, a fresh SUMM and SAVE). The game's save is only ever read, never written, renamed or
// waited for. The launcher writes the first slot.zrs: without a valid one the writer only logs and skips.
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// fs.c, mounting a randomizer save file system: start the writer thread once (no-op when already running).
void save_slot_arm(void);
// fs.c, IFileSystem Commit (the IPC path): note the run ("rando/<id>") and wake the writer. No file IO, no allocation,
// no logging: a mutex, a counter, a condition signal.
void save_slot_commit(const char *run_dir);

#ifdef SAVE_SLOT_TEST  // host tests (tools/save_slot/test_save_slot.c)
typedef struct { uint64_t signals, writes, skips, runs; } SaveSlotStats;
void save_slot_test_set_debounce_ms(unsigned ms);
SaveSlotStats save_slot_test_stats(void);
int save_slot_test_wait_idle(unsigned timeout_ms);  // 1 when every signal so far was handled
void save_slot_test_pause(int on);                  // hold the writer before its next run (on = 1) / let it go
int save_slot_sha256(const uint8_t *data, size_t n, uint8_t out[32]);
int save_slot_swish_hash(const uint8_t *payload, size_t n, uint8_t out[32]);
#endif

#ifdef __cplusplus
}
#endif
