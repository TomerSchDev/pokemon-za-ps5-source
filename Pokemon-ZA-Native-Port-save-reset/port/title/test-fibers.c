/* Exercise the exact title's context switch on the x86-64 host. This does not
 * claim PS5 memory/signal/syscall compatibility. */
#include "platform/ps5_fiber.h"
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    void *stack = malloc(65536);
    if (!stack) return 2;
    char why[256] = {0};
    for (int i = 0; i < 10000; ++i) {
        if (!plat_fiber_selftest(stack, 65536, why, sizeof why)) {
            fprintf(stderr, "fiber iteration %d: %s\n", i, why);
            free(stack);
            return 1;
        }
    }
    free(stack);
    puts("PASS: 10,000 host fiber round trips, stack and floating-point state checks");
    return 0;
}
