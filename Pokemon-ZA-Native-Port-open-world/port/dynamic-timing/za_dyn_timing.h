/* Dynamic frame timing for Pokémon Legends: Z-A 2.0.2 (main b1f12fd919eae86ab8a978317677e64bce443d1f), native PS5.
 *
 * Host-testable model: pure C11, no platform calls, no globals. The port glue (za_dyn_glue.c) calls za_dt_frame()
 * once per game frame from the frame-mode hook (main+0x1b296d8, f_7001b29660 in main_660.c) with the host clock,
 * publishes the decision, and the step hooks (the three SetFrameMode thunks that read the duration table
 * main+0x3393e20) ask za_dt_step_for() for the duration of the mode the game passes them.
 *
 * What the game does with these numbers (analysis/dynamic-timing-design-HE.md has the evidence):
 *   mode      - the frame mode index the game reads from its config byte [[clock+0x40]+0x20] (0: 60 Hz, 1: 30 Hz);
 *               it becomes the present interval (mode+1, through gfx+0x140) and the index of the duration table.
 *   step_ns   - the duration every update group gets for the frame (table[mode] in the original game), turned into
 *               float seconds by the consumers. The model never hands out a step outside [16,666,667, 33,333,334] ns
 *               (the game's own 60 and 30 steps) unless allow_sub60_step is set (an experiment, see the doc).
 *   The table itself is never written: the animation play-rate code (f_7001015260, f_70010273f0) divides the
 *   step by the ORIGINAL table[mode] and the DRS controllers use it as a GPU budget, so it must keep its values. */
#ifndef ZA_DYN_TIMING_H
#define ZA_DYN_TIMING_H
#include <stdbool.h>
#include <stdint.h>

#define ZA_DT_NS_60 UINT64_C(16666667)  /* main+0x3393e20 [0] */
#define ZA_DT_NS_30 UINT64_C(33333334)  /* main+0x3393e28 [1] */
#define ZA_DT_TABLE_N 5
extern const uint64_t za_dt_table_202[ZA_DT_TABLE_N]; /* {16666667, 33333334, 50000000, 66666667, 83333334} */

typedef enum { ZA_DT_POLICY_OFF = 0, ZA_DT_POLICY_SAFE = 1, ZA_DT_POLICY_RC3_COMPAT = 2 } ZaDtPolicy;

typedef struct {
    ZaDtPolicy policy;
    double alpha;              /* EMA weight of a new frame-period sample (RC3: 0.05) */
    int enter30_below;         /* mode 0 -> 1 when (int)fps < this (RC3: 46, i.e. 45 FPS and below) */
    int leave30_from;          /* mode 1 -> 0 when (int)fps >= this for min_dwell frames (RC3: 46, no hysteresis) */
    uint32_t min_dwell;        /* frames a 1 -> 0 return must hold (0: at once). Drops (0 -> 1) are never delayed. */
    int nominal30_below;       /* mode 1 and (int)fps < this: the original 30 step (RC3: 31; 0: off) */
    int nominal60_from;        /* mode 0 and (int)fps >= this: the original 60 step (RC3: 58; 0: off). SAFE
                                * turns both snaps off: its step is the smoothed period, clamped to the band. */
    bool quantize_fps;         /* RC3: step = 1e9 / (int)fps; SAFE: step = the smoothed period itself */
    bool prime_from_first;     /* SAFE: the EMA starts at the first real sample (RC3 starts from 0 / tick 0) */
    uint64_t gap_ns;           /* a frame longer than this (load, suspend, clock jump) is not a sample (0: off) */
    uint64_t sample_cap_ns;    /* samples are clamped to this before the EMA (0: off) */
    uint64_t key_timeout_ns;   /* another frame-clock object takes over after the primary is silent this long */
    double drift_gain;         /* fraction of the accumulated wall-sim lag repaid per frame (0: off) */
    double drift_max_frac;     /* the repayment is at most this fraction of the step */
    uint64_t drift_cap_ns;     /* lag (sim behind wall) carried at most this; sim ahead at most one 60 step.
                                * Frame time beyond 33.3 ms is forgiven, never repaid. */
    double burst_margin;       /* never hand out more than (1 + this) x the frame that just ended (0: off) -
                                * no fast-forward when frames get faster than the smoothed period */
    bool honor_registry;       /* RC3: the original step while the byte at main+0x610b980 is non-zero */
    bool force_present_60;     /* the SDK patch's equivalent: present interval 1 (mode 0) while dynamic is active */
    bool allow_sub60_step;     /* experiment: steps below 16.67 ms when frames are faster (needs 120 Hz pacing) */
    uint64_t min_step_ns;      /* floor with allow_sub60_step (8,333,333 for 120 Hz) */
} ZaDtConfig;

typedef struct {
    uint64_t now_ns;           /* host monotonic clock at the hook (plat_now_ns) */
    int32_t original_mode;     /* the config byte [[clock+0x40]+0x20] (sign-extended, as ldrsb) */
    uint8_t variable_flag;     /* the config byte [[clock+0x40]+0x21]: the game's own variable-step path */
    uint8_t registry_byte;     /* the byte RC3 reads at main+0x610b980 (0 unless honor_registry) */
    uint64_t key;              /* the frame-clock object (x19 at the hook) */
} ZaDtInput;

typedef struct {
    bool active;               /* dynamic owns this frame */
    int32_t mode;              /* returned at main+0x1b296d8 (w20) */
    int32_t present_mode;      /* passed to f_70017fafd4 at main+0x1b296f0: present interval = present_mode + 1 */
    uint64_t step_ns;          /* duration for SetFrameMode(i, mode) */
} ZaDtDecision;

typedef struct {
    bool primed, have_sample, active, skip_next;
    uint64_t key, last_ns, key_seen_ns;
    double ema_ns, fps, lag_ns;
    int32_t mode;
    uint32_t dwell, up_streak;
    uint64_t step_ns;
    /* counters (logs and tests) */
    uint64_t frames, samples, switches_down, switches_up, gaps, capped, rollbacks, duplicates, foreign,
             adoptions, standdowns, fast_frames, registry_frames;
    double wall_ns, sim_ns;    /* in-band frames only: sum of the (capped) samples and of the steps handed out */
} ZaDtState;

void za_dt_config_default(ZaDtConfig *c, ZaDtPolicy policy);
void za_dt_reset(ZaDtState *s);
ZaDtDecision za_dt_frame(ZaDtState *s, const ZaDtConfig *c, const ZaDtInput *in);
/* The duration a SetFrameMode thunk hands to its group for `mode`, given the value it loaded from the table. */
uint64_t za_dt_step_for(const ZaDtDecision *d, int32_t mode, uint64_t original_ns);
/* Pass-through decision for an original mode (what the unmodified game would do). */
ZaDtDecision za_dt_passthrough(int32_t original_mode);

/* One 64-bit word for publishing between the hook threads: [63] active, [62:56] mode, [55:48] present mode,
 * [47:0] step ns. */
uint64_t za_dt_pack(const ZaDtDecision *d);
ZaDtDecision za_dt_unpack(uint64_t w);

/* Test/console knob: the release deadline that holds the game at `fps` (a frame limiter in the hook). */
uint64_t za_dt_limiter_deadline(uint64_t last_release_ns, uint64_t now_ns, uint32_t fps);

/* The animation play rate f_7001015260 / f_70010273f0 compute: (double)step / (double)(table[mode] - 1), as float.
 * 1.0 means "one nominal frame of animation per update". */
float za_dt_anim_rate(uint64_t step_ns, uint64_t table_ns);

#endif
