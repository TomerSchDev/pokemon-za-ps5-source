#ifndef ZA_SUBMISSION_R20_H
#define ZA_SUBMISSION_R20_H
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

/* One completed NVN list still has its own upload/main buffers and logical
 * sequence. Only their queue submission is batched. Keep below the 8-slot
 * renderer ring so a batch never needs its own completion to allocate a slot. */
#define ZA_BATCH_LISTS 8u
#define ZA_BATCH_CBS (2u * ZA_BATCH_LISTS)
#define ZA_BATCH_DRAWS UINT64_C(400)
#define ZA_BATCH_COMMANDS UINT64_C(32768)
#define ZA_BATCH_NS UINT64_C(2000000)
typedef enum {
    ZA_SUB_EACH, ZA_SUB_END, ZA_SUB_FENCE, ZA_SUB_DRAWS, ZA_SUB_LISTS,
    ZA_SUB_COMMANDS, ZA_SUB_AGE, ZA_SUB_WAIT, ZA_SUB_INTERNAL,
    ZA_SUB_PRESENT, ZA_SUB_CAPACITY, ZA_SUB_REASONS
} ZaSubmitReason;
static const char *const za_submit_reason_names[ZA_SUB_REASONS] = {
    "each", "end", "fence", "draws", "lists", "commands", "age", "wait",
    "internal", "present", "capacity"
};

/* Strict startup profile: missing/malformed input is the baseline. */
static inline bool za_submission_profile_batch(const char *text) {
    if (!text) return false;
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') ++text;
    if (strncmp(text, "batch", 5)) return false;
    text += 5;
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') ++text;
    return *text == 0;
}
static void za_submission_flush_to(uint64_t seq, ZaSubmitReason reason);
static void za_submission_report(void);
#endif
