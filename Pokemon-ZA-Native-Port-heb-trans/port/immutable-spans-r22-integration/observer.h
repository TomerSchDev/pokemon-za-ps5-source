#ifndef ZA_OBSERVER_H
#define ZA_OBSERVER_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void za_observer_init(void);
bool za_observer_enabled(void);
/* All calls, including input injection, have UI/render-thread ownership. */
void za_observer_frame(uint64_t frame, bool submitted, bool represented,
                       uint64_t shader_activity, void *texture,
                       void (*save_texture)(void *, const char *));
void za_observer_input(uint64_t frame, uint64_t *buttons,
                       int32_t *lx, int32_t *ly, int32_t *rx, int32_t *ry);
/* Only continue the exact active run named in the request; never create one. */
bool za_observer_menu(const char *active_run);
#ifdef __cplusplus
}
#endif
#endif
