#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Research adapter: serialize all calls on one worker. Not integrated in r15.
 * Initialize once on that worker; finish after all requests. Caller frees output.
 * stage: vert=0, frag=1, comp=2. No filesystem access/includes or GPU access.
 * Validation is performed externally with spirv-val in the research test. */
int za_glsl_init(void);
void za_glsl_finish(void);
int za_glsl_compile(const char *source, int stage, uint32_t **words,
                    size_t *word_count, char *error, size_t error_size);
#ifdef __cplusplus
}
#endif
