/* SDL3 shim (PS5): SDL_audio.h - subset of SDL 3.4.18, backed by libSceAudioOut. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_audio_h_
#define SDL_audio_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_error.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SDL_AUDIO_MASK_BITSIZE    (0xFFu)
#define SDL_AUDIO_MASK_FLOAT      (1u << 8)
#define SDL_AUDIO_MASK_BIG_ENDIAN (1u << 12)
#define SDL_AUDIO_MASK_SIGNED     (1u << 15)

typedef enum SDL_AudioFormat {
    SDL_AUDIO_UNKNOWN = 0x0000u,
    SDL_AUDIO_U8 = 0x0008u,
    SDL_AUDIO_S8 = 0x8008u,
    SDL_AUDIO_S16LE = 0x8010u,
    SDL_AUDIO_S16BE = 0x9010u,
    SDL_AUDIO_S32LE = 0x8020u,
    SDL_AUDIO_S32BE = 0x9020u,
    SDL_AUDIO_F32LE = 0x8120u,
    SDL_AUDIO_F32BE = 0x9120u,
    /* little-endian target */
    SDL_AUDIO_S16 = SDL_AUDIO_S16LE,
    SDL_AUDIO_S32 = SDL_AUDIO_S32LE,
    SDL_AUDIO_F32 = SDL_AUDIO_F32LE
} SDL_AudioFormat;

#define SDL_AUDIO_BITSIZE(x)        ((x) & SDL_AUDIO_MASK_BITSIZE)
#define SDL_AUDIO_BYTESIZE(x)       (SDL_AUDIO_BITSIZE(x) / 8)
#define SDL_AUDIO_ISFLOAT(x)        ((x) & SDL_AUDIO_MASK_FLOAT)
#define SDL_AUDIO_ISBIGENDIAN(x)    ((x) & SDL_AUDIO_MASK_BIG_ENDIAN)
#define SDL_AUDIO_ISLITTLEENDIAN(x) (!SDL_AUDIO_ISBIGENDIAN(x))
#define SDL_AUDIO_ISSIGNED(x)       ((x) & SDL_AUDIO_MASK_SIGNED)
#define SDL_AUDIO_ISINT(x)          (!SDL_AUDIO_ISFLOAT(x))
#define SDL_AUDIO_ISUNSIGNED(x)     (!SDL_AUDIO_ISSIGNED(x))

typedef Uint32 SDL_AudioDeviceID;
#define SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK  ((SDL_AudioDeviceID)0xFFFFFFFFu)
#define SDL_AUDIO_DEVICE_DEFAULT_RECORDING ((SDL_AudioDeviceID)0xFFFFFFFEu)

typedef struct SDL_AudioSpec {
    SDL_AudioFormat format;
    int channels;
    int freq;
} SDL_AudioSpec;

#define SDL_AUDIO_FRAMESIZE(x) (SDL_AUDIO_BYTESIZE((x).format) * (x).channels)

typedef struct SDL_AudioStream SDL_AudioStream;
typedef void(SDLCALL *SDL_AudioStreamCallback)(void *userdata, SDL_AudioStream *stream, int additional_amount, int total_amount);

/* The device is the main port of the console: S16 stereo 48 kHz. S16/F32 input, 1/2/6 channels, any rate (resampled). */
extern SDL_DECLSPEC bool SDLCALL SDL_GetAudioDeviceFormat(SDL_AudioDeviceID devid, SDL_AudioSpec *spec, int *sample_frames);
/* Opens a logical device with a stream bound to it; starts paused (SDL_ResumeAudioStreamDevice). Callbacks are not supported. */
extern SDL_DECLSPEC SDL_AudioStream *SDLCALL SDL_OpenAudioDeviceStream(SDL_AudioDeviceID devid, const SDL_AudioSpec *spec, SDL_AudioStreamCallback callback, void *userdata);
extern SDL_DECLSPEC SDL_AudioDeviceID SDLCALL SDL_GetAudioStreamDevice(SDL_AudioStream *stream);
extern SDL_DECLSPEC bool SDLCALL SDL_PutAudioStreamData(SDL_AudioStream *stream, const void *buf, int len);
/* Bytes put but not yet consumed, in the input format of the stream (SDL semantics). */
extern SDL_DECLSPEC int SDLCALL SDL_GetAudioStreamQueued(SDL_AudioStream *stream);
extern SDL_DECLSPEC bool SDLCALL SDL_ClearAudioStream(SDL_AudioStream *stream);
extern SDL_DECLSPEC bool SDLCALL SDL_PauseAudioStreamDevice(SDL_AudioStream *stream);
extern SDL_DECLSPEC bool SDLCALL SDL_ResumeAudioStreamDevice(SDL_AudioStream *stream);
extern SDL_DECLSPEC bool SDLCALL SDL_SetAudioStreamGain(SDL_AudioStream *stream, float gain);
extern SDL_DECLSPEC float SDLCALL SDL_GetAudioStreamGain(SDL_AudioStream *stream);
extern SDL_DECLSPEC void SDLCALL SDL_DestroyAudioStream(SDL_AudioStream *stream);

#ifdef __cplusplus
}
#endif

#endif /* SDL_audio_h_ */
