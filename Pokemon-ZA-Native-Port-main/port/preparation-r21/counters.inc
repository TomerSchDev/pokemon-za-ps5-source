/* Baseline startup. Switches happen under exec_lock after a checked GPU drain.
 * Counters have the same serialized execution owner as stage_set/renderer_stats. */
static _Atomic unsigned za_prep_flags;
typedef struct {
    uint64_t calls, vertex, fragment, compute, ordinary_visits, special_visits;
    uint64_t rscale_builds, rscale_skips, allocs, updates, writes;
} ZaPrepCounters;
static ZaPrepCounters za_prep_counts[4];
uint32_t za_preparation_profile_flags(void) { return atomic_load_explicit(&za_prep_flags, memory_order_relaxed); }
const char *za_preparation_profile_name(void) { return za_prep_name(za_preparation_profile_flags()); }
static void za_preparation_report(void) {
    unsigned flags = za_preparation_profile_flags();
    const ZaPrepCounters *c = &za_prep_counts[flags];
    LOG("[za-r21-prep] profile=%s flags=%u calls=%llu vs=%llu fs=%llu cs=%llu ordinary_visits=%llu special_visits=%llu rscale_builds=%llu rscale_skips=%llu allocs=%llu updates=%llu writes=%llu\n",
        za_prep_name(flags), flags, (unsigned long long)c->calls,
        (unsigned long long)c->vertex, (unsigned long long)c->fragment, (unsigned long long)c->compute,
        (unsigned long long)c->ordinary_visits, (unsigned long long)c->special_visits,
        (unsigned long long)c->rscale_builds, (unsigned long long)c->rscale_skips,
        (unsigned long long)c->allocs, (unsigned long long)c->updates, (unsigned long long)c->writes);
}
