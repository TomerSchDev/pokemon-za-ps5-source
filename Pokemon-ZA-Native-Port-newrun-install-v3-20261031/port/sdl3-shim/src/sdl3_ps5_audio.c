/*
 * SDL3 shim for the PS5 port of Pokemon Legends Z-A Recomp: audio streams over
 * libSceAudioOut.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * One port, opened as the probe's r4 audio stage opens it (user 0xff, the main
 * port, 256-sample grains, 48 kHz, S16 stereo; the pad's user as the fallback),
 * fed by one thread that mixes every unpaused stream into each grain and calls
 * sceAudioOutOutput, which returns when the previous grain has played: that call
 * is the pacing, and silence keeps the port paced when nothing is queued. A
 * stream holds what the runtime put into it in its own format (S16 or F32, 1, 2
 * or 6 channels, any rate: linear resampling to 48 kHz, 5.1 folded to stereo
 * with the runtime's own coefficients); SDL_GetAudioStreamQueued is the bytes
 * still held, as in SDL.
 */
#include "sdl3_ps5_internal.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define MAX_STREAMS 16
#define LOGICAL_DEVICE_BASE 0x100u
#define PHYSICAL_DEVICE_ID 1u
#define DEFAULT_DEVICE_FRAMES 1024
#define MAX_RING_BYTES (32u << 20)
#define GRAIN_SAMPLES (PS5_AUDIO_GRAIN * 2)

struct SDL_AudioStream {
    SDL_AudioSpec spec;
    size_t frame_size;
    uint8_t *ring; /* input bytes; cap and head are multiples of frame_size, so a frame never wraps */
    size_t cap, head, used;
    double pos; /* fractional read position in frames, [0, 1) between grains */
    float gain;
    bool paused;
    int slot;
    pthread_mutex_t lock;
};

static struct {
    bool initialized;
    int init_rc, open_rc, handle, user_id_used, volume_rc;
    int device_frames;
    pthread_t thread;
    bool thread_started;
    atomic_bool running;
    atomic_uint grains, failures;
    _Atomic int last_rc;
    SDL_AudioStream *streams[MAX_STREAMS];
    pthread_mutex_t list_lock;
} audio = {.handle = -1, .list_lock = PTHREAD_MUTEX_INITIALIZER};

/* ------------------------------------------------------------------ mixing */

/* Frame `index` from the head of the stream as stereo float. */
static void read_frame(const SDL_AudioStream *s, size_t index, float out[2])
{
    const uint8_t *p = s->ring + (s->head + index * s->frame_size) % s->cap;
    float ch[6] = {0, 0, 0, 0, 0, 0};
    const int n = s->spec.channels;
    if (s->spec.format == SDL_AUDIO_F32) {
        for (int i = 0; i < n; i++)
            memcpy(&ch[i], p + 4 * i, sizeof(float));
    } else {
        for (int i = 0; i < n; i++) {
            int16_t v;
            memcpy(&v, p + 2 * i, sizeof(v));
            ch[i] = (float)v / 32768.0f;
        }
    }
    switch (n) {
    case 1:
        out[0] = out[1] = ch[0];
        break;
    case 2:
        out[0] = ch[0];
        out[1] = ch[1];
        break;
    default: /* 6: L R C LFE SL SR, folded as runtime/services/audio.c folds its 5.1 sinks */
        out[0] = ch[0] + 0.707f * ch[2] + 0.251f * ch[3] + 0.707f * ch[4];
        out[1] = ch[1] + 0.707f * ch[2] + 0.251f * ch[3] + 0.707f * ch[5];
        break;
    }
}

/* Adds one grain of the stream to `mix` and consumes what it played (the stream lock is held). */
static void pull_stream(SDL_AudioStream *s, float mix[GRAIN_SAMPLES])
{
    const size_t avail = s->used / s->frame_size;
    if (avail == 0)
        return;
    const double step = (double)s->spec.freq / (double)PS5_AUDIO_RATE;
    const float gain = s->gain;
    double pos = s->pos;
    for (int i = 0; i < PS5_AUDIO_GRAIN; i++) {
        const size_t index = (size_t)pos;
        if (index >= avail)
            break; /* underrun: the rest of the grain is silence */
        float a[2];
        read_frame(s, index, a);
        const double frac = pos - (double)index;
        if (frac > 0.0 && index + 1 < avail) {
            float b[2];
            read_frame(s, index + 1, b);
            a[0] += (float)frac * (b[0] - a[0]);
            a[1] += (float)frac * (b[1] - a[1]);
        }
        mix[2 * i] += a[0] * gain;
        mix[2 * i + 1] += a[1] * gain;
        pos += step;
    }
    size_t consumed = (size_t)pos;
    if (consumed > avail)
        consumed = avail;
    s->head = (s->head + consumed * s->frame_size) % s->cap;
    s->used -= consumed * s->frame_size;
    s->pos = pos - (double)consumed;
    if (s->pos < 0.0)
        s->pos = 0.0;
}

static void *mixer_thread(void *arg)
{
    (void)arg;
    float mix[GRAIN_SAMPLES];
    int16_t block[GRAIN_SAMPLES];
    while (atomic_load(&audio.running)) {
        memset(mix, 0, sizeof(mix));
        pthread_mutex_lock(&audio.list_lock);
        for (int i = 0; i < MAX_STREAMS; i++) {
            SDL_AudioStream *s = audio.streams[i];
            if (!s)
                continue;
            pthread_mutex_lock(&s->lock);
            if (!s->paused)
                pull_stream(s, mix);
            pthread_mutex_unlock(&s->lock);
        }
        pthread_mutex_unlock(&audio.list_lock);
        for (int i = 0; i < GRAIN_SAMPLES; i++) {
            float v = mix[i];
            if (v > 1.0f)
                v = 1.0f;
            if (v < -1.0f)
                v = -1.0f;
            block[i] = (int16_t)(v * 32767.0f);
        }
        /* Returns when the previous grain has played: the pacing of this loop (the probe's audio_step). */
        const int rc = sceAudioOutOutput(audio.handle, block);
        atomic_store(&audio.last_rc, rc);
        if (rc < 0) {
            atomic_fetch_add(&audio.failures, 1);
            usleep(5000);
        } else {
            atomic_fetch_add(&audio.grains, 1);
        }
    }
    return NULL;
}

/* -------------------------------------------------------------- lifecycle */

bool sdl3_ps5_audio_init(void)
{
    if (audio.initialized)
        return true;
    audio.init_rc = sceAudioOutInit();
    /* The system user, as the probe (and ProsperoEden) open the port; the pad's user as the fallback. */
    audio.user_id_used = PS5_USER_ID_SYSTEM;
    audio.open_rc = sceAudioOutOpen(PS5_USER_ID_SYSTEM, PS5_AUDIO_PORT_MAIN, 0, PS5_AUDIO_GRAIN, PS5_AUDIO_RATE,
                                    PS5_AUDIO_FORMAT_S16_STEREO);
    if (audio.open_rc < 0) {
        const int user = sdl3_ps5_user_id();
        if (user >= 0) {
            audio.user_id_used = user;
            audio.open_rc = sceAudioOutOpen(user, PS5_AUDIO_PORT_MAIN, 0, PS5_AUDIO_GRAIN, PS5_AUDIO_RATE,
                                            PS5_AUDIO_FORMAT_S16_STEREO);
        }
    }
    sdl3_ps5_log("audio: sceAudioOutInit rc=0x%08x; sceAudioOutOpen(user 0x%x, main port, %u samples, %u Hz, S16 stereo) rc=0x%08x",
                 (unsigned)audio.init_rc, (unsigned)audio.user_id_used, (unsigned)PS5_AUDIO_GRAIN, (unsigned)PS5_AUDIO_RATE,
                 (unsigned)audio.open_rc);
    if (audio.open_rc < 0)
        return SDL_SetError("sceAudioOutOpen failed: 0x%08x", (unsigned)audio.open_rc);
    audio.handle = audio.open_rc;
    int volumes[8];
    for (size_t i = 0; i < sizeof(volumes) / sizeof(volumes[0]); i++)
        volumes[i] = PS5_AUDIO_VOLUME_0DB;
    audio.volume_rc = sceAudioOutSetVolume(audio.handle, PS5_AUDIO_VOLUME_BOTH, volumes);
    if (audio.volume_rc < 0)
        sdl3_ps5_log("audio: sceAudioOutSetVolume rc=0x%08x", (unsigned)audio.volume_rc);

    /* What SDL_GetAudioDeviceFormat reports as the device period: the runtime sizes its queues from it
     * (2 periods ahead). 1024 frames = 21 ms, 4 grains. */
    audio.device_frames = DEFAULT_DEVICE_FRAMES;
    const char *env = sdl3_ps5_env("SDL3_PS5_AUDIO_DEVICE_FRAMES");
    if (env) {
        const int frames = atoi(env);
        if (frames >= PS5_AUDIO_GRAIN && frames <= 8192)
            audio.device_frames = frames;
    }

    atomic_store(&audio.running, true);
    if (!sdl3_ps5_thread_create(&audio.thread, 1u << 20, mixer_thread, NULL, "sdl3-audio")) {
        atomic_store(&audio.running, false);
        sceAudioOutClose(audio.handle);
        audio.handle = -1;
        return false;
    }
    audio.thread_started = true;
    audio.initialized = true;
    sdl3_ps5_log("audio: mixer thread started; device period %d frames", audio.device_frames);
    return true;
}

void sdl3_ps5_audio_quit(void)
{
    if (!audio.initialized)
        return;
    atomic_store(&audio.running, false);
    pthread_join(audio.thread, NULL);
    audio.thread_started = false;
    const int drain_rc = sceAudioOutOutput(audio.handle, NULL);
    const int close_rc = sceAudioOutClose(audio.handle);
    sdl3_ps5_log("audio: %u grains written, %u failures (last rc=0x%08x); drain rc=0x%08x, close rc=0x%08x",
                 atomic_load(&audio.grains), atomic_load(&audio.failures), (unsigned)atomic_load(&audio.last_rc),
                 (unsigned)drain_rc, (unsigned)close_rc);
    audio.handle = -1;
    audio.initialized = false;
    /* Open streams stay valid objects; they simply play no more. */
}

/* ---------------------------------------------------------------- the API */

static bool spec_supported(const SDL_AudioSpec *spec)
{
    return spec && (spec->format == SDL_AUDIO_S16 || spec->format == SDL_AUDIO_F32) &&
           (spec->channels == 1 || spec->channels == 2 || spec->channels == 6) && spec->freq >= 8000 &&
           spec->freq <= 192000;
}

bool SDL_GetAudioDeviceFormat(SDL_AudioDeviceID devid, SDL_AudioSpec *spec, int *sample_frames)
{
    if (devid == 0 || devid == SDL_AUDIO_DEVICE_DEFAULT_RECORDING)
        return SDL_SetError("SDL_GetAudioDeviceFormat: no such audio device (%u)", (unsigned)devid);
    if (spec) {
        spec->format = SDL_AUDIO_S16;
        spec->channels = 2;
        spec->freq = PS5_AUDIO_RATE;
    }
    if (sample_frames)
        *sample_frames = audio.initialized ? audio.device_frames : DEFAULT_DEVICE_FRAMES;
    return true;
}

SDL_AudioStream *SDL_OpenAudioDeviceStream(SDL_AudioDeviceID devid, const SDL_AudioSpec *spec, SDL_AudioStreamCallback callback,
                                           void *userdata)
{
    (void)userdata;
    if (!audio.initialized) {
        SDL_SetError("SDL_OpenAudioDeviceStream: the audio subsystem is not initialized");
        return NULL;
    }
    if (devid != SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK && devid != PHYSICAL_DEVICE_ID) {
        SDL_SetError("SDL_OpenAudioDeviceStream: no such playback device (%u)", (unsigned)devid);
        return NULL;
    }
    if (callback) {
        SDL_SetError("SDL_OpenAudioDeviceStream: stream callbacks are not supported by the PS5 shim");
        return NULL;
    }
    if (!spec_supported(spec)) {
        SDL_SetError("SDL_OpenAudioDeviceStream: unsupported format (0x%x, %d channels, %d Hz): S16/F32, 1/2/6 channels",
                     spec ? (unsigned)spec->format : 0u, spec ? spec->channels : 0, spec ? spec->freq : 0);
        return NULL;
    }
    SDL_AudioStream *s = calloc(1, sizeof(*s));
    if (!s) {
        SDL_SetError("SDL_OpenAudioDeviceStream: out of memory");
        return NULL;
    }
    s->spec = *spec;
    s->frame_size = (size_t)SDL_AUDIO_BYTESIZE(spec->format) * (size_t)spec->channels;
    s->cap = s->frame_size * (size_t)spec->freq; /* a second of input */
    s->ring = malloc(s->cap);
    s->gain = 1.0f;
    s->paused = true; /* SDL: the device starts paused until SDL_ResumeAudioStreamDevice */
    s->slot = -1;
    pthread_mutex_init(&s->lock, NULL);
    if (!s->ring) {
        pthread_mutex_destroy(&s->lock);
        free(s);
        SDL_SetError("SDL_OpenAudioDeviceStream: out of memory");
        return NULL;
    }
    pthread_mutex_lock(&audio.list_lock);
    for (int i = 0; i < MAX_STREAMS; i++) {
        if (!audio.streams[i]) {
            audio.streams[i] = s;
            s->slot = i;
            break;
        }
    }
    pthread_mutex_unlock(&audio.list_lock);
    if (s->slot < 0) {
        pthread_mutex_destroy(&s->lock);
        free(s->ring);
        free(s);
        SDL_SetError("SDL_OpenAudioDeviceStream: %d streams are open already", MAX_STREAMS);
        return NULL;
    }
    sdl3_ps5_log("audio: stream %d opened: %s, %d channel(s), %d Hz", s->slot,
                 spec->format == SDL_AUDIO_F32 ? "F32" : "S16", spec->channels, spec->freq);
    return s;
}

SDL_AudioDeviceID SDL_GetAudioStreamDevice(SDL_AudioStream *stream)
{
    return stream ? LOGICAL_DEVICE_BASE + (SDL_AudioDeviceID)stream->slot : 0;
}

bool SDL_PutAudioStreamData(SDL_AudioStream *stream, const void *buf, int len)
{
    if (!stream)
        return SDL_SetError("SDL_PutAudioStreamData: NULL stream");
    if (len < 0 || (len > 0 && !buf))
        return SDL_SetError("SDL_PutAudioStreamData: invalid buffer");
    if (len == 0)
        return true;
    const size_t n = (size_t)len;
    pthread_mutex_lock(&stream->lock);
    if (stream->used + n > stream->cap) {
        size_t cap = stream->cap;
        while (cap < stream->used + n)
            cap *= 2;
        cap = (cap + stream->frame_size - 1) / stream->frame_size * stream->frame_size;
        if (cap > MAX_RING_BYTES) {
            pthread_mutex_unlock(&stream->lock);
            return SDL_SetError("SDL_PutAudioStreamData: more than %u bytes queued", (unsigned)MAX_RING_BYTES);
        }
        uint8_t *ring = malloc(cap);
        if (!ring) {
            pthread_mutex_unlock(&stream->lock);
            return SDL_SetError("SDL_PutAudioStreamData: out of memory");
        }
        /* linearise: the used bytes from head, in one or two pieces */
        const size_t first = stream->cap - stream->head;
        if (stream->used <= first) {
            memcpy(ring, stream->ring + stream->head, stream->used);
        } else {
            memcpy(ring, stream->ring + stream->head, first);
            memcpy(ring + first, stream->ring, stream->used - first);
        }
        free(stream->ring);
        stream->ring = ring;
        stream->cap = cap;
        stream->head = 0;
    }
    const size_t tail = (stream->head + stream->used) % stream->cap;
    const size_t first = stream->cap - tail;
    if (n <= first) {
        memcpy(stream->ring + tail, buf, n);
    } else {
        memcpy(stream->ring + tail, buf, first);
        memcpy(stream->ring, (const uint8_t *)buf + first, n - first);
    }
    stream->used += n;
    pthread_mutex_unlock(&stream->lock);
    return true;
}

int SDL_GetAudioStreamQueued(SDL_AudioStream *stream)
{
    if (!stream) {
        SDL_SetError("SDL_GetAudioStreamQueued: NULL stream");
        return -1;
    }
    pthread_mutex_lock(&stream->lock);
    const size_t used = stream->used;
    pthread_mutex_unlock(&stream->lock);
    return used > (size_t)INT32_MAX ? INT32_MAX : (int)used;
}

bool SDL_ClearAudioStream(SDL_AudioStream *stream)
{
    if (!stream)
        return SDL_SetError("SDL_ClearAudioStream: NULL stream");
    pthread_mutex_lock(&stream->lock);
    stream->used = 0;
    stream->head = 0;
    stream->pos = 0.0;
    pthread_mutex_unlock(&stream->lock);
    return true;
}

bool SDL_PauseAudioStreamDevice(SDL_AudioStream *stream)
{
    if (!stream)
        return SDL_SetError("SDL_PauseAudioStreamDevice: NULL stream");
    pthread_mutex_lock(&stream->lock);
    stream->paused = true;
    pthread_mutex_unlock(&stream->lock);
    return true;
}

bool SDL_ResumeAudioStreamDevice(SDL_AudioStream *stream)
{
    if (!stream)
        return SDL_SetError("SDL_ResumeAudioStreamDevice: NULL stream");
    pthread_mutex_lock(&stream->lock);
    stream->paused = false;
    pthread_mutex_unlock(&stream->lock);
    return true;
}

bool SDL_SetAudioStreamGain(SDL_AudioStream *stream, float gain)
{
    if (!stream)
        return SDL_SetError("SDL_SetAudioStreamGain: NULL stream");
    if (gain < 0.0f)
        return SDL_SetError("SDL_SetAudioStreamGain: negative gain");
    pthread_mutex_lock(&stream->lock);
    stream->gain = gain;
    pthread_mutex_unlock(&stream->lock);
    return true;
}

float SDL_GetAudioStreamGain(SDL_AudioStream *stream)
{
    if (!stream) {
        SDL_SetError("SDL_GetAudioStreamGain: NULL stream");
        return 0.0f;
    }
    pthread_mutex_lock(&stream->lock);
    const float gain = stream->gain;
    pthread_mutex_unlock(&stream->lock);
    return gain;
}

void SDL_DestroyAudioStream(SDL_AudioStream *stream)
{
    if (!stream)
        return;
    pthread_mutex_lock(&audio.list_lock);
    if (stream->slot >= 0 && stream->slot < MAX_STREAMS && audio.streams[stream->slot] == stream)
        audio.streams[stream->slot] = NULL;
    pthread_mutex_unlock(&audio.list_lock);
    pthread_mutex_destroy(&stream->lock);
    free(stream->ring);
    free(stream);
}
