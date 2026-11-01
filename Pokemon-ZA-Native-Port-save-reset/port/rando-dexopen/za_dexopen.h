/* rando-dexopen: the Mega Dimension (Hyperspace) Pokedex list is visible and enumerated from the start of a run.
 *
 * The save flag FLAG_DLC_DEX_ENABLE (descriptor 0x7003e26880, set by DLC story event data) is READ by exactly two
 * translated functions and written by none (za-atlas, 30.10.2026). Both are patched by prepare-dexopen-hooks.py to
 * treat the flag as set whenever the flag manager's readiness word is non-zero, and both route through this module:
 *   f_70008d4178 (main_287.c)  DLC::IsHyperspaceDexEnabled  -> za_dexopen_hyperspace_dex_enabled(ready, flag)
 *                              (its 14 callers are Pokedex UI: list building, list switching, entry iteration, the
 *                              info pane, the mission panel's dex unit)
 *   f_700033f8d8 (main_115.c)  Pokedex::GetMegaDexCount     -> za_dexopen_mega_dex_flag(flag)
 *                              (the "include Hyperspace rows" filter of the Mega Dex count; callers: the counter
 *                              telemetry and two Pokedex UI units)
 * Nothing writes the flag or the save. The DLC story / Hyperspace access flags (FLAG_DLC_ANOTHER_DIMENSION_ENABLE,
 * FLAG_DLC_QUEST_ENABLE, SYS_WORK_DLC_PHASE) are untouched. One switch (default on) disables both patch sites, and
 * with the switch off each site computes exactly the original expression.
 */
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 1 (default): both sites treat FLAG_DLC_DEX_ENABLE as set. 0: original behaviour at both sites. */
int za_dexopen_enabled(void);
void za_dexopen_set_enabled(int on);

/* Site 1, f_70008d4178: ready = (readiness word != 0) as the game computed it (0/1), flag = the getter's result.
 * Returns ready when enabled, else ready & flag (the original `w0 = w8 & w19`). */
uint32_t za_dexopen_hyperspace_dex_enabled(uint32_t ready, uint32_t flag);

/* Site 2, f_700033f8d8: flag = the getter's result captured in x22. Returns 1 when enabled, else flag unchanged.
 * (The game then ANDs it with its own readiness bit and stores the "include Hyperspace rows" filter.) */
uint32_t za_dexopen_mega_dex_flag(uint32_t flag);

/* Diagnostics (lock-free counters): calls per site, calls whose result differed from the original expression, the
 * last flag value the game itself reported (ZA_DEXOPEN_FLAG_UNKNOWN before any ready call), trace lines emitted. */
enum { ZA_DEXOPEN_SITE_GETTER = 0, ZA_DEXOPEN_SITE_MEGADEX = 1, ZA_DEXOPEN_SITES = 2 };
#define ZA_DEXOPEN_FLAG_UNKNOWN 0xffffffffu
uint64_t za_dexopen_calls(int site);
uint64_t za_dexopen_forced(int site);
uint32_t za_dexopen_last_flag(int site);
uint64_t za_dexopen_trace_lines(int site);

#ifdef __cplusplus
}
#endif
