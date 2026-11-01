#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct ZaItem { uint16_t id, cap; uint8_t pocket; const char *name; } ZaItem;
unsigned za_items_count(void);
const ZaItem *za_items_at(unsigned index);
int za_items_request(unsigned index, unsigned amount);
void za_items_reset(void);
int za_items_ready(void);
int za_items_pending(void);
const char *za_items_status(void);
unsigned za_items_last_count(void);
unsigned za_items_applied(void);
void za_items_pump(void *cpu);
#ifdef __cplusplus
}
#endif
