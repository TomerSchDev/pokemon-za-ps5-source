/* rando-dexcount: the count behind the game's have_pokemon_encyclopedia_total_condition also includes the
 * Hyperspace (Mega Dimension DLC) Pokedex.
 *
 * Two translated functions call into this module (prepare-dexcount-hooks.py):
 *   f_7000a1158c (main_310.c)  evaluator of have_pokemon_encyclopedia_total_condition -> za_dexcount_combine()
 *   f_700082b5c4 (main_261.c)  quest-item value shown as "Number Registered N/M" (item type 2) -> za_dexcount_display()
 * Both pass the game's own two counts, f_700033e770(manager, 0, 0) (Lumiose list) and f_700033e770(manager, 1, 0)
 * (Hyperspace list); the lists are disjoint (232 + 132 species), so each registered species counts once.
 * The Pokedex screens, the completion conditions, the Hyperspace dex's own condition
 * (have_dimension_encyclopedia_total_condition) and the save data are untouched.
 */
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 1 (default): the hooked functions also ask the game for the Hyperspace count. 0: original behaviour. */
int za_dexcount_extra_enabled(void);
void za_dexcount_set_enabled(int on);

/* Saturating sum used by the condition evaluator / by the mission panel. Lock-free, any game thread. */
uint32_t za_dexcount_combine(uint32_t lumiose, uint32_t hyperspace);
uint32_t za_dexcount_display(uint32_t lumiose, uint32_t hyperspace);

/* Diagnostics: last values seen by the evaluator and number of evaluations / panel reads. */
uint32_t za_dexcount_last_lumiose(void);
uint32_t za_dexcount_last_hyperspace(void);
uint32_t za_dexcount_last_combined(void);
uint64_t za_dexcount_evaluations(void);
uint64_t za_dexcount_displays(void);

#ifdef __cplusplus
}
#endif
