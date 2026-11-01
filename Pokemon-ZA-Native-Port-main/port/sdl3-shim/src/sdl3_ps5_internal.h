/*
 * SDL3 shim for the PS5 port of Pokemon Legends Z-A Recomp: shared internals.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * The Sony prototypes below are declared here because the payload SDK ships the
 * stub libraries (target/lib/libScePad.so, libSceAudioOut.so, libSceUserService.so,
 * libkernel.so) without headers. Sources, in order of trust:
 *   [probe]    vk-probe/src/za_vk_probe.c r4: exercised on 13.60 (2026-10-27, PID 112):
 *              User Service, scePad (120-byte record, buttons at 0, connected at 0x4c),
 *              sceAudioOut (main port, 256-sample grains, 48 kHz, S16 stereo).
 *   [sdk]      ps5platform/kernel.h of the payload SDK fork (pin b83202be): declared and
 *              documented there, not exercised by our probe.
 *   [eden]     ProsperoEden third_party/ps5_pad.hpp: the button bits of the pad record.
 */
#ifndef SDL3_PS5_INTERNAL_H
#define SDL3_PS5_INTERNAL_H

#include <SDL3/SDL.h>

#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------ Sony: [probe] */
int sceKernelDebugOutText(int channel, const char *text);
int sceUserServiceInitialize(const void *params);
int sceUserServiceGetForegroundUser(int *user_id);
int sceUserServiceGetInitialUser(int *user_id);
int sceUserServiceTerminate(void);
int scePadInit(void);
int scePadOpen(int user_id, int port_type, int index, const void *params);
int scePadGetHandle(int user_id, int port_type, int index);
int scePadClose(int handle);
int scePadReadState(int handle, void *record);
int sceAudioOutInit(void);
int sceAudioOutOpen(int user_id, int port_type, int index, uint32_t grain, uint32_t frequency, uint32_t format);
int sceAudioOutClose(int handle);
int sceAudioOutOutput(int handle, const void *samples);
int sceAudioOutSetVolume(int handle, int flags, const int *volumes);

/* -------------------------------------------------------------- Sony: [sdk] */
int64_t sceKernelGetDirectMemorySize(void);
uint64_t sceKernelReadTsc(void);
uint64_t sceKernelGetTscFrequency(void);
int32_t scePthreadGetaffinity(pthread_t thread, uint64_t *mask);

/* The pad record, verbatim from the probe ([probe], after [eden]). */
struct ps5_pad_record {
    uint32_t buttons;
    uint8_t left_x, left_y, right_x, right_y;
    uint8_t l2, r2, analog_reserved[2];
    float orientation[4];
    float acceleration[3];
    float angular_velocity[3];
    uint8_t touch[24];
    int32_t connected;
    uint64_t timestamp_us;
    uint8_t extension[16];
    uint8_t connected_count;
    uint8_t reserved[2];
    uint8_t device_unique_data_length;
    uint8_t device_unique_data[12];
};
_Static_assert(sizeof(struct ps5_pad_record) == 120, "the pad record is 120 bytes");
_Static_assert(offsetof(struct ps5_pad_record, connected) == 0x4c, "connected is at 0x4c");
_Static_assert(offsetof(struct ps5_pad_record, timestamp_us) == 0x50, "the timestamp is at 0x50");

#define PS5_PAD_PORT_TYPE_STANDARD 0
/* Button bits of the record ([eden]; OPTIONS and INTERCEPTED also [probe]). r4 saw 0x0000fffe pressed. */
#define PS5_PAD_BUTTON_CREATE      0x00000001u
#define PS5_PAD_BUTTON_L3          0x00000002u
#define PS5_PAD_BUTTON_R3          0x00000004u
#define PS5_PAD_BUTTON_OPTIONS     0x00000008u
#define PS5_PAD_BUTTON_UP          0x00000010u
#define PS5_PAD_BUTTON_RIGHT       0x00000020u
#define PS5_PAD_BUTTON_DOWN        0x00000040u
#define PS5_PAD_BUTTON_LEFT        0x00000080u
#define PS5_PAD_BUTTON_L2          0x00000100u
#define PS5_PAD_BUTTON_R2          0x00000200u
#define PS5_PAD_BUTTON_L1          0x00000400u
#define PS5_PAD_BUTTON_R1          0x00000800u
#define PS5_PAD_BUTTON_TRIANGLE    0x00001000u
#define PS5_PAD_BUTTON_CIRCLE      0x00002000u
#define PS5_PAD_BUTTON_CROSS       0x00004000u
#define PS5_PAD_BUTTON_SQUARE      0x00008000u
#define PS5_PAD_BUTTON_TOUCH_PAD   0x00100000u
#define PS5_PAD_BUTTON_INTERCEPTED 0x80000000u /* the system took the input (the PS button's menu) */

#define PS5_USER_ID_SYSTEM 0xff
#define PS5_AUDIO_PORT_MAIN 0
#define PS5_AUDIO_FORMAT_S16_STEREO 1
#define PS5_AUDIO_VOLUME_BOTH 3 /* the left and right channel flags */
#define PS5_AUDIO_VOLUME_0DB 0x8000
#define PS5_AUDIO_RATE 48000
#define PS5_AUDIO_GRAIN 256 /* samples per sceAudioOutOutput: 5.3 ms, the pacing unit */

/* ------------------------------------------------------------- core helpers */
/* A line to stderr, "[sdl3-ps5] ..." (the title routes stderr to klog with ps5_klog_capture_stderr). */
void sdl3_ps5_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
/* CLOCK_MONOTONIC in nanoseconds (or the TSC with -DSDL3_PS5_TSC_TICKS=1). */
uint64_t sdl3_ps5_now_ns(void);
/* getenv, NULL for an unset or empty variable. */
const char *sdl3_ps5_env(const char *name);
/* The foreground user from User Service (initialised once, the initial user as the fallback); -1 when none. */
int sdl3_ps5_user_id(void);
void sdl3_ps5_user_quit(void);
/* pthread_create with an explicit stack (the console gives unasked threads 64 KiB only); sets the SDL error on failure. */
bool sdl3_ps5_thread_create(pthread_t *thread, size_t stack_bytes, void *(*fn)(void *), void *arg, const char *what);

/* ----------------------------------------------------------- events + pad */
void sdl3_ps5_events_init(void);
void sdl3_ps5_events_quit(void);
bool sdl3_ps5_queue_event(const SDL_Event *event);
bool sdl3_ps5_pad_init(void);
void sdl3_ps5_pad_quit(void);
void sdl3_ps5_pad_pump(void);

/* ------------------------------------------------------------------ audio */
bool sdl3_ps5_audio_init(void);
void sdl3_ps5_audio_quit(void);

/* ------------------------------------------------------------------ video */
void sdl3_ps5_video_quit(void);

#ifdef __cplusplus
}
#endif

#endif /* SDL3_PS5_INTERNAL_H */
