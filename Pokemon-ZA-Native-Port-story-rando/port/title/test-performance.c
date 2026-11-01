#include "performance.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    ZaPerformance s = {0};
    assert(za_performance_step(&s, 1, 0, 0) == 1);
    assert(za_performance_step(&s, -2, 0, 0) == -2);
    s.enabled = true;
    assert(za_performance_step(&s, 1, 0, 0) == 0);
    uint64_t t = 0, p = 0;
    for (int i = 0; i < 15; i++) {
        t += UINT64_C(1000000000); p += 60;
        assert(za_performance_step(&s, 1, t, p) == 0);
    }
    /* A single capture/loading stall must not permanently disable the trial. */
    t += UINT64_C(6000000000); p += 1;
    assert(za_performance_step(&s, 1, t, p) == 0);
    t += UINT64_C(1000000000); p += 60;
    assert(za_performance_step(&s, 1, t, p) == 0 && s.slow == 0);
    for (int i = 0; i < 4; i++) {
        t += UINT64_C(1000000000); p += 45;
        assert(za_performance_step(&s, 1, t, p) == 0);
    }
    t += UINT64_C(1000000000); p += 45;
    assert(za_performance_step(&s, 1, t, p) == 1 && s.fell_back);
    assert(za_performance_step(&s, 1, t + UINT64_C(1000000000), p + 60) == 1);
    s = (ZaPerformance){.enabled = true};
    assert(za_performance_step(&s, 1, 5, 5) == 0);
    assert(za_performance_step(&s, 1, 4, 5) == 1 && s.fell_back);
    puts("PASS: original config, sustained 60, isolated stall, low-FPS fallback, sticky fallback, clock reset");
}
