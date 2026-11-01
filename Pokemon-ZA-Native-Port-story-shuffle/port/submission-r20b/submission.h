#ifndef ZA_SUBMISSION_R20B_H
#define ZA_SUBMISSION_R20B_H
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

/* One completed NVN list still has its own upload/main buffers and logical
 * sequence. Storage holds 8 lists; selected caps 2/4 leave ring overlap.
 * The 8-list profile fills the renderer ring and is a diagnostic comparator. */
#define ZA_BATCH_LISTS 8u
#define ZA_BATCH_CBS (2u * ZA_BATCH_LISTS)
#define ZA_BATCH_DRAWS UINT64_C(400)
#define ZA_BATCH_COMMANDS UINT64_C(32768)
#define ZA_BATCH_NS UINT64_C(2000000)
typedef enum {
    ZA_SUB_EACH, ZA_SUB_END, ZA_SUB_FENCE, ZA_SUB_DRAWS, ZA_SUB_LISTS,
    ZA_SUB_COMMANDS, ZA_SUB_AGE, ZA_SUB_WAIT, ZA_SUB_INTERNAL,
    ZA_SUB_PRESENT, ZA_SUB_CAPACITY, ZA_SUB_SWITCH, ZA_SUB_REASONS
} ZaSubmitReason;
static const char *const za_submit_reason_names[ZA_SUB_REASONS] = {
    "each", "end", "fence", "draws", "lists", "commands", "age", "wait",
    "internal", "present", "capacity", "switch"
};

/* 0 rejects malformed input; startup chooses baseline 1 on rejection. */
static inline unsigned za_submission_parse_profile(const char *text) {
    if (!text) return 0;
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') ++text;
    unsigned limit = 0, len = 0;
    if (!strncmp(text, "each", 4)) { limit = 1; len = 4; }
    else if (!strncmp(text, "batch2", 6)) { limit = 2; len = 6; }
    else if (!strncmp(text, "batch4", 6)) { limit = 4; len = 6; }
    else if (!strncmp(text, "batch8", 6)) { limit = 8; len = 6; }
    else return 0;
    text += len;
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') ++text;
    return *text ? 0 : limit;
}
static inline const char *za_submission_profile_name(unsigned limit) {
    return limit == 2 ? "batch2" : limit == 4 ? "batch4" : limit == 8 ? "batch8" : "each";
}
static void za_submission_flush_to(uint64_t seq, ZaSubmitReason reason);
static void za_submission_report(void);
#endif
