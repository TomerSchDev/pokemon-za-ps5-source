/* PC proof accelerator (diagnostic DLL only, identical in the baseline and the fix build): the randomizer's own
 * production CAPTURE hook point (port/randomizer/prepare-cheat-hooks.py, main_145.c label L_7000447554, after the
 * target's eligibility check) with the production policy (cheat_policy.hpp captureScore) fixed at mode 4 = max score
 * when ZA_DEXCOUNT_PC_CAPTURE=max. Blocked targets and zero scores stay untouched, exactly as in production.
 * It only changes the catch roll; Pokedex registration and the mission counter are not involved. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

static int g_mode = -1;
static unsigned g_changed;

uint32_t za_cheat_capture_score(uint32_t bits, uint64_t ptr) {
    if (g_mode < 0) { const char *e = getenv("ZA_DEXCOUNT_PC_CAPTURE"); g_mode = e && !strcmp(e, "max") ? 4 : 0; }
    if (!ptr || !g_mode) return bits;
    const uint8_t *p = (const uint8_t *)(uintptr_t)ptr;
    uint64_t target;
    memcpy(&target, p + 0x10, 8);
    float score;
    memcpy(&score, &bits, 4);
    if (p[0x2e] != 0 || !target || !isfinite(score) || score <= 0) return bits;
    score = 255.f;
    memcpy(&bits, &score, 4);
    g_changed++;
    fprintf(stderr, "[dexcount-pc] capture score set to max (%u)\n", g_changed);
    return bits;
}
