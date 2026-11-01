/*
 * SDL3 shim for the PS5 port of Pokemon Legends Z-A Recomp: init, error, log,
 * hints, timers, cpuinfo, filesystem, threads, surfaces.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "sdl3_ps5_internal.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

/* ------------------------------------------------------------------ logging */

void sdl3_ps5_log(const char *fmt, ...)
{
    char line[512];
    va_list args;
    va_start(args, fmt);
    vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);
    fprintf(stderr, "[sdl3-ps5] %s\n", line);
    fflush(stderr);
}

const char *sdl3_ps5_env(const char *name)
{
    const char *value = getenv(name);
    return value && *value ? value : NULL;
}

/* ------------------------------------------------------------------- error */

static _Thread_local char error_text[512];
static _Atomic unsigned errors_logged;

bool SDL_SetError(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    vsnprintf(error_text, sizeof(error_text), fmt, args);
    va_end(args);
    /* The first errors go to klog too: nothing else shows them on the console. */
    if (atomic_fetch_add(&errors_logged, 1) < 50)
        sdl3_ps5_log("error: %s", error_text);
    return false;
}

const char *SDL_GetError(void)
{
    return error_text;
}

bool SDL_ClearError(void)
{
    error_text[0] = '\0';
    return true;
}

/* --------------------------------------------------------------------- log */

#define LOG_CATEGORIES 32
static SDL_LogPriority log_priorities[LOG_CATEGORIES]; /* SDL_LOG_PRIORITY_INVALID = the default */

static SDL_LogPriority default_log_priority(int category)
{
    switch (category) {
    case SDL_LOG_CATEGORY_APPLICATION: return SDL_LOG_PRIORITY_INFO;
    case SDL_LOG_CATEGORY_ASSERT: return SDL_LOG_PRIORITY_WARN;
    case SDL_LOG_CATEGORY_TEST: return SDL_LOG_PRIORITY_VERBOSE;
    default: return SDL_LOG_PRIORITY_ERROR;
    }
}

SDL_LogPriority SDL_GetLogPriority(int category)
{
    if (category >= 0 && category < LOG_CATEGORIES && log_priorities[category] != SDL_LOG_PRIORITY_INVALID)
        return log_priorities[category];
    return default_log_priority(category);
}

void SDL_SetLogPriority(int category, SDL_LogPriority priority)
{
    if (category >= 0 && category < LOG_CATEGORIES)
        log_priorities[category] = priority;
}

void SDL_SetLogPriorities(SDL_LogPriority priority)
{
    for (int i = 0; i < LOG_CATEGORIES; i++)
        log_priorities[i] = priority;
}

void SDL_ResetLogPriorities(void)
{
    memset(log_priorities, 0, sizeof(log_priorities));
}

void SDL_LogMessageV(int category, SDL_LogPriority priority, const char *fmt, va_list ap)
{
    static const char *const names[SDL_LOG_PRIORITY_COUNT] = {"INVALID", "TRACE", "VERBOSE", "DEBUG",
                                                              "INFO",    "WARN",  "ERROR",   "CRITICAL"};
    if (priority <= SDL_LOG_PRIORITY_INVALID || priority >= SDL_LOG_PRIORITY_COUNT)
        return;
    if (priority < SDL_GetLogPriority(category))
        return;
    char line[1024];
    vsnprintf(line, sizeof(line), fmt, ap);
    fprintf(stderr, "[sdl3] %s: %s\n", names[priority], line);
    fflush(stderr);
}

void SDL_LogMessage(int category, SDL_LogPriority priority, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    SDL_LogMessageV(category, priority, fmt, ap);
    va_end(ap);
}

#define LOG_AT(name, prio)                                   \
    void name(int category, const char *fmt, ...)            \
    {                                                        \
        va_list ap;                                          \
        va_start(ap, fmt);                                   \
        SDL_LogMessageV(category, prio, fmt, ap);            \
        va_end(ap);                                          \
    }
LOG_AT(SDL_LogTrace, SDL_LOG_PRIORITY_TRACE)
LOG_AT(SDL_LogVerbose, SDL_LOG_PRIORITY_VERBOSE)
LOG_AT(SDL_LogDebug, SDL_LOG_PRIORITY_DEBUG)
LOG_AT(SDL_LogInfo, SDL_LOG_PRIORITY_INFO)
LOG_AT(SDL_LogWarn, SDL_LOG_PRIORITY_WARN)
LOG_AT(SDL_LogError, SDL_LOG_PRIORITY_ERROR)
LOG_AT(SDL_LogCritical, SDL_LOG_PRIORITY_CRITICAL)
#undef LOG_AT

void SDL_Log(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    SDL_LogMessageV(SDL_LOG_CATEGORY_APPLICATION, SDL_LOG_PRIORITY_INFO, fmt, ap);
    va_end(ap);
}

/* ------------------------------------------------------------------- hints */

#define HINTS 16
static struct {
    char name[64];
    char value[64];
} hints[HINTS];
static pthread_mutex_t hints_lock = PTHREAD_MUTEX_INITIALIZER;

bool SDL_SetHint(const char *name, const char *value)
{
    if (!name || !*name)
        return SDL_SetError("SDL_SetHint: invalid hint name");
    pthread_mutex_lock(&hints_lock);
    int slot = -1;
    for (int i = 0; i < HINTS; i++) {
        if (hints[i].name[0] == '\0' && slot < 0)
            slot = i;
        if (strcmp(hints[i].name, name) == 0) {
            slot = i;
            break;
        }
    }
    if (slot >= 0) {
        snprintf(hints[slot].name, sizeof(hints[slot].name), "%s", name);
        snprintf(hints[slot].value, sizeof(hints[slot].value), "%s", value ? value : "");
    }
    pthread_mutex_unlock(&hints_lock);
    return true; /* accepted; nothing on the console reads them */
}

const char *SDL_GetHint(const char *name)
{
    const char *value = NULL;
    if (!name)
        return NULL;
    pthread_mutex_lock(&hints_lock);
    for (int i = 0; i < HINTS; i++) {
        if (strcmp(hints[i].name, name) == 0) {
            value = hints[i].value;
            break;
        }
    }
    pthread_mutex_unlock(&hints_lock);
    return value;
}

/* -------------------------------------------------------------- messagebox */

bool SDL_ShowSimpleMessageBox(SDL_MessageBoxFlags flags, const char *title, const char *message, SDL_Window *window)
{
    (void)window;
    const char *kind = (flags & SDL_MESSAGEBOX_ERROR) ? "error" : (flags & SDL_MESSAGEBOX_WARNING) ? "warning" : "message";
    sdl3_ps5_log("%s box: %s: %s", kind, title ? title : "", message ? message : "");
    return true;
}

/* ----------------------------------------------------------------- version */

int SDL_GetVersion(void)
{
    return SDL_VERSION;
}

const char *SDL_GetRevision(void)
{
    return "sdl3-ps5-shim (SDL 3.4.18 ABI; VK_KHR_display, libScePad, libSceAudioOut)";
}

/* ------------------------------------------------------------------ stdinc */

void *SDL_malloc(size_t size)
{
    return malloc(size ? size : 1);
}

void *SDL_calloc(size_t nmemb, size_t size)
{
    return calloc(nmemb ? nmemb : 1, size ? size : 1);
}

void *SDL_realloc(void *mem, size_t size)
{
    return realloc(mem, size ? size : 1);
}

void SDL_free(void *mem)
{
    free(mem);
}

char *SDL_strdup(const char *str)
{
    if (!str)
        return NULL;
    const size_t n = strlen(str) + 1;
    char *copy = malloc(n);
    if (copy)
        memcpy(copy, str, n);
    return copy;
}

/* ------------------------------------------------------------------ timers */

#ifndef SDL3_PS5_TSC_TICKS
#define SDL3_PS5_TSC_TICKS 0
#endif

static pthread_once_t ticks_once = PTHREAD_ONCE_INIT;
static uint64_t ticks_start;
#if SDL3_PS5_TSC_TICKS
static uint64_t tsc_hz;
#endif

uint64_t sdl3_ps5_now_ns(void)
{
#if SDL3_PS5_TSC_TICKS
    /* sceKernelReadTsc: 12 ns per read against the 20 us of a clock_gettime syscall (PS5_Vulkan HARDWARE_FINDINGS);
     * declared in ps5platform/kernel.h, not exercised by our probe, hence opt-in. */
    if (tsc_hz)
        return (uint64_t)(((unsigned __int128)sceKernelReadTsc() * 1000000000ull) / tsc_hz);
#endif
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
}

static void ticks_init(void)
{
#if SDL3_PS5_TSC_TICKS
    tsc_hz = sceKernelGetTscFrequency();
    sdl3_ps5_log("ticks: TSC at %llu Hz", (unsigned long long)tsc_hz);
#endif
    ticks_start = sdl3_ps5_now_ns();
}

Uint64 SDL_GetTicksNS(void)
{
    pthread_once(&ticks_once, ticks_init);
    return sdl3_ps5_now_ns() - ticks_start;
}

Uint64 SDL_GetTicks(void)
{
    return SDL_GetTicksNS() / 1000000ull;
}

Uint64 SDL_GetPerformanceCounter(void)
{
    return sdl3_ps5_now_ns();
}

Uint64 SDL_GetPerformanceFrequency(void)
{
    return 1000000000ull;
}

void SDL_DelayNS(Uint64 ns)
{
    /* nanosleep (exported by libkernel); clock_nanosleep is not, so the absolute form is not used. */
    struct timespec request = {(time_t)(ns / 1000000000ull), (long)(ns % 1000000000ull)};
    while (nanosleep(&request, &request) != 0 && errno == EINTR) {
    }
}

void SDL_Delay(Uint32 ms)
{
    SDL_DelayNS((Uint64)ms * 1000000ull);
}

void SDL_DelayPrecise(Uint64 ns)
{
    const uint64_t target = sdl3_ps5_now_ns() + ns;
    for (;;) {
        const uint64_t now = sdl3_ps5_now_ns();
        if (now >= target)
            return;
        const uint64_t left = target - now;
        if (left > 1500000ull) {
            SDL_DelayNS(left - 1000000ull); /* sleep up to a millisecond short, then spin on the clock */
        } else if (left > 100000ull) {
            sched_yield();
        }
    }
}

/* ----------------------------------------------------------------- cpuinfo */

int SDL_GetNumLogicalCPUCores(void)
{
    static int cached;
    if (cached)
        return cached;
    int count = 0;
    /* The CPUs a title's threads may run on: the affinity mask of this thread (PROBE.md: 0x1fff, 13 CPUs;
     * sysconf answers 16, which the title cannot use). */
    uint64_t mask = 0;
    if (scePthreadGetaffinity(pthread_self(), &mask) == 0 && mask != 0)
        count = __builtin_popcountll(mask);
    if (count <= 0) {
        const long online = sysconf(_SC_NPROCESSORS_ONLN);
        count = online > 0 ? (int)online : 13;
    }
    sdl3_ps5_log("cpu: %d logical cores (affinity mask 0x%llx)", count, (unsigned long long)mask);
    cached = count;
    return count;
}

int SDL_GetSystemRAM(void)
{
    const int64_t bytes = sceKernelGetDirectMemorySize();
    if (bytes <= 0)
        return 12288; /* PROBE.md: 12 GiB of direct memory */
    return (int)(bytes / (1024 * 1024));
}

/* -------------------------------------------------------------- filesystem */

static bool directory_exists(const char *path)
{
    /* access() fails with EPERM for every path on the console (PROBE.md): stat instead. */
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

static bool make_directories(const char *path)
{
    char buffer[1024];
    const size_t length = strlen(path);
    if (length == 0 || length >= sizeof(buffer)) {
        errno = ENAMETOOLONG;
        return false;
    }
    memcpy(buffer, path, length + 1);
    while (length > 1 && buffer[strlen(buffer) - 1] == '/')
        buffer[strlen(buffer) - 1] = '\0';
    for (char *p = buffer + 1; *p; p++) {
        if (*p != '/')
            continue;
        *p = '\0';
        if (!directory_exists(buffer) && mkdir(buffer, 0755) != 0 && errno != EEXIST) {
            *p = '/';
            return false;
        }
        *p = '/';
    }
    if (!directory_exists(buffer) && mkdir(buffer, 0755) != 0 && errno != EEXIST)
        return false;
    return directory_exists(buffer);
}

const char *SDL_GetBasePath(void)
{
    return "/app0/";
}

bool SDL_CreateDirectory(const char *path)
{
    if (!path || !*path)
        return SDL_SetError("SDL_CreateDirectory: invalid path");
    if (make_directories(path))
        return true;
    return SDL_SetError("SDL_CreateDirectory(%s): %s", path, strerror(errno));
}

char *SDL_GetPrefPath(const char *org, const char *app)
{
    if (!app || !*app) {
        SDL_SetError("SDL_GetPrefPath: an application name is required");
        return NULL;
    }
    const char *root = sdl3_ps5_env("SDL3_PS5_PREF_ROOT");
    if (!root)
        root = "/download0";
    char path[1024];
    if (org && *org)
        snprintf(path, sizeof(path), "%s/%s/%s/", root, org, app);
    else
        snprintf(path, sizeof(path), "%s/%s/", root, app);
    if (!make_directories(path)) {
        SDL_SetError("SDL_GetPrefPath(%s): %s", path, strerror(errno));
        return NULL;
    }
    return SDL_strdup(path);
}

/* ----------------------------------------------------------------- threads */

bool sdl3_ps5_thread_create(pthread_t *thread, size_t stack_bytes, void *(*fn)(void *), void *arg, const char *what)
{
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    if (stack_bytes)
        pthread_attr_setstacksize(&attr, stack_bytes);
    const int rc = pthread_create(thread, &attr, fn, arg);
    pthread_attr_destroy(&attr);
    if (rc != 0)
        return SDL_SetError("pthread_create(%s, %zu KiB stack): %d", what, stack_bytes / 1024, rc);
    return true;
}

struct SDL_Thread {
    pthread_t thread;
    SDL_ThreadFunction fn;
    void *data;
    int status;
    bool finished, detached;
    pthread_mutex_t lock;
    char name[32];
};

static void thread_release(SDL_Thread *t)
{
    pthread_mutex_destroy(&t->lock);
    free(t);
}

static void *thread_main(void *arg)
{
    SDL_Thread *t = arg;
    const int status = t->fn(t->data);
    pthread_mutex_lock(&t->lock);
    t->status = status;
    t->finished = true;
    const bool detached = t->detached;
    pthread_mutex_unlock(&t->lock);
    if (detached)
        thread_release(t); /* nobody will wait: the last one out frees */
    return NULL;
}

SDL_Thread *SDL_CreateThreadRuntime(SDL_ThreadFunction fn, const char *name, void *data, SDL_FunctionPointer pfnBeginThread,
                                    SDL_FunctionPointer pfnEndThread)
{
    (void)pfnBeginThread;
    (void)pfnEndThread;
    if (!fn) {
        SDL_SetError("SDL_CreateThread: NULL function");
        return NULL;
    }
    SDL_Thread *t = calloc(1, sizeof(*t));
    if (!t) {
        SDL_SetError("SDL_CreateThread: out of memory");
        return NULL;
    }
    t->fn = fn;
    t->data = data;
    snprintf(t->name, sizeof(t->name), "%s", name ? name : "sdl");
    pthread_mutex_init(&t->lock, NULL);
    /* Unasked, a thread gets 64 KiB on the console (PROBE.md); SDL threads of the runtime encode PNGs. */
    size_t stack = 2u << 20;
    const char *env = sdl3_ps5_env("SDL3_PS5_THREAD_STACK_KB");
    if (env && atoi(env) >= 64)
        stack = (size_t)atoi(env) << 10;
    if (!sdl3_ps5_thread_create(&t->thread, stack, thread_main, t, t->name)) {
        thread_release(t);
        return NULL;
    }
    return t;
}

void SDL_WaitThread(SDL_Thread *thread, int *status)
{
    if (!thread) {
        if (status)
            *status = -1;
        return;
    }
    pthread_join(thread->thread, NULL);
    if (status)
        *status = thread->status;
    thread_release(thread);
}

void SDL_DetachThread(SDL_Thread *thread)
{
    if (!thread)
        return;
    pthread_detach(thread->thread);
    pthread_mutex_lock(&thread->lock);
    const bool finished = thread->finished;
    thread->detached = true;
    pthread_mutex_unlock(&thread->lock);
    if (finished)
        thread_release(thread); /* it ended before the detach: free it here */
}

/* ---------------------------------------------------------------- surfaces */

static bool surface_format_ok(SDL_PixelFormat format)
{
    return format == SDL_PIXELFORMAT_ABGR8888 || format == SDL_PIXELFORMAT_RGBA8888;
}

SDL_Surface *SDL_CreateSurface(int width, int height, SDL_PixelFormat format)
{
    if (width <= 0 || height <= 0 || !surface_format_ok(format)) {
        SDL_SetError("SDL_CreateSurface: %dx%d format 0x%x is not supported by the PS5 shim", width, height, (unsigned)format);
        return NULL;
    }
    SDL_Surface *s = calloc(1, sizeof(*s));
    void *pixels = calloc((size_t)width * (size_t)height, 4);
    if (!s || !pixels) {
        free(s);
        free(pixels);
        SDL_SetError("SDL_CreateSurface: out of memory");
        return NULL;
    }
    s->format = format;
    s->w = width;
    s->h = height;
    s->pitch = width * 4;
    s->pixels = pixels;
    s->refcount = 1;
    return s;
}

SDL_Surface *SDL_CreateSurfaceFrom(int width, int height, SDL_PixelFormat format, void *pixels, int pitch)
{
    if (width <= 0 || height <= 0 || !surface_format_ok(format) || !pixels || pitch < width * 4) {
        SDL_SetError("SDL_CreateSurfaceFrom: %dx%d pitch %d format 0x%x is not supported by the PS5 shim", width, height,
                     pitch, (unsigned)format);
        return NULL;
    }
    SDL_Surface *s = calloc(1, sizeof(*s));
    if (!s) {
        SDL_SetError("SDL_CreateSurfaceFrom: out of memory");
        return NULL;
    }
    s->flags = SDL_SURFACE_PREALLOCATED;
    s->format = format;
    s->w = width;
    s->h = height;
    s->pitch = pitch;
    s->pixels = pixels;
    s->refcount = 1;
    return s;
}

void SDL_DestroySurface(SDL_Surface *surface)
{
    if (!surface)
        return;
    if (--surface->refcount > 0)
        return;
    if (!(surface->flags & SDL_SURFACE_PREALLOCATED))
        free(surface->pixels);
    free(surface);
}

SDL_Surface *SDL_ConvertSurface(SDL_Surface *surface, SDL_PixelFormat format)
{
    if (!surface) {
        SDL_SetError("SDL_ConvertSurface: NULL surface");
        return NULL;
    }
    if (format != surface->format) {
        SDL_SetError("SDL_ConvertSurface: the PS5 shim copies only between identical formats (0x%x -> 0x%x)",
                     (unsigned)surface->format, (unsigned)format);
        return NULL;
    }
    SDL_Surface *copy = SDL_CreateSurface(surface->w, surface->h, format);
    if (!copy)
        return NULL;
    const size_t row = (size_t)surface->w * 4;
    for (int y = 0; y < surface->h; y++)
        memcpy((uint8_t *)copy->pixels + (size_t)y * (size_t)copy->pitch,
               (const uint8_t *)surface->pixels + (size_t)y * (size_t)surface->pitch, row);
    return copy;
}

SDL_Surface *SDL_LoadPNG(const char *file)
{
    SDL_SetError("SDL_LoadPNG(%s): PNG is not provided by the PS5 shim", file ? file : "");
    return NULL;
}

bool SDL_SavePNG(SDL_Surface *surface, const char *file)
{
    (void)surface;
    return SDL_SetError("SDL_SavePNG(%s): PNG is not provided by the PS5 shim", file ? file : "");
}

/* ------------------------------------------------------------ user service */

static struct {
    bool tried;
    int init_rc, foreground_rc, initial_rc, user_id;
} user = {.user_id = -1};
static pthread_mutex_t user_lock = PTHREAD_MUTEX_INITIALIZER;

int sdl3_ps5_user_id(void)
{
    pthread_mutex_lock(&user_lock);
    if (!user.tried) {
        /* As the probe (and ProsperoEden) open their pads: User Service, the foreground user, the initial user
         * as the fallback. r4: init rc 0, foreground user 375927969. */
        user.tried = true;
        user.init_rc = sceUserServiceInitialize(NULL);
        user.foreground_rc = sceUserServiceGetForegroundUser(&user.user_id);
        if (user.foreground_rc < 0 || user.user_id < 0) {
            user.user_id = -1;
            user.initial_rc = sceUserServiceGetInitialUser(&user.user_id);
            if (user.initial_rc < 0)
                user.user_id = -1;
        }
        sdl3_ps5_log("user service: init rc=0x%08x, foreground rc=0x%08x, initial rc=0x%08x, user %d",
                     (unsigned)user.init_rc, (unsigned)user.foreground_rc, (unsigned)user.initial_rc, user.user_id);
    }
    const int id = user.user_id;
    pthread_mutex_unlock(&user_lock);
    return id;
}

void sdl3_ps5_user_quit(void)
{
    pthread_mutex_lock(&user_lock);
    if (user.tried && user.init_rc == 0)
        sceUserServiceTerminate();
    user.tried = false;
    user.user_id = -1;
    pthread_mutex_unlock(&user_lock);
}

/* -------------------------------------------------------------------- init */

static pthread_mutex_t init_lock = PTHREAD_MUTEX_INITIALIZER;
static SDL_InitFlags initialized;

static bool init_locked(SDL_InitFlags flags)
{
    SDL_InitFlags want = flags;
    if (want & (SDL_INIT_AUDIO | SDL_INIT_VIDEO | SDL_INIT_JOYSTICK | SDL_INIT_GAMEPAD | SDL_INIT_SENSOR | SDL_INIT_CAMERA))
        want |= SDL_INIT_EVENTS;
    if (want & SDL_INIT_GAMEPAD)
        want |= SDL_INIT_JOYSTICK;
    const SDL_InitFlags todo = want & ~initialized;
    if (todo & SDL_INIT_EVENTS) {
        sdl3_ps5_events_init();
        initialized |= SDL_INIT_EVENTS;
    }
    if (todo & SDL_INIT_VIDEO) {
        /* The display is driven by RADV's VK_KHR_display on VideoOut: nothing to open here. */
        initialized |= SDL_INIT_VIDEO;
    }
    if (todo & (SDL_INIT_JOYSTICK | SDL_INIT_GAMEPAD)) {
        /* No pad is not a failure (SDL: the subsystem is up, SDL_GetGamepads is empty); the rcs are logged. */
        sdl3_ps5_pad_init();
        initialized |= todo & (SDL_INIT_JOYSTICK | SDL_INIT_GAMEPAD);
    }
    if (todo & SDL_INIT_AUDIO) {
        if (!sdl3_ps5_audio_init())
            return false; /* the runtime logs "SDL audio init failed" and runs without sound */
        initialized |= SDL_INIT_AUDIO;
    }
    initialized |= todo & (SDL_INIT_HAPTIC | SDL_INIT_SENSOR | SDL_INIT_CAMERA); /* accepted, nothing behind them */
    return true;
}

bool SDL_InitSubSystem(SDL_InitFlags flags)
{
    pthread_mutex_lock(&init_lock);
    const bool ok = init_locked(flags);
    pthread_mutex_unlock(&init_lock);
    return ok;
}

bool SDL_Init(SDL_InitFlags flags)
{
    return SDL_InitSubSystem(flags);
}

SDL_InitFlags SDL_WasInit(SDL_InitFlags flags)
{
    return flags ? (initialized & flags) : initialized;
}

void SDL_QuitSubSystem(SDL_InitFlags flags)
{
    pthread_mutex_lock(&init_lock);
    if ((flags & SDL_INIT_AUDIO) && (initialized & SDL_INIT_AUDIO)) {
        sdl3_ps5_audio_quit();
        initialized &= ~SDL_INIT_AUDIO;
    }
    if ((flags & (SDL_INIT_JOYSTICK | SDL_INIT_GAMEPAD)) && (initialized & (SDL_INIT_JOYSTICK | SDL_INIT_GAMEPAD))) {
        sdl3_ps5_pad_quit();
        initialized &= ~(SDL_INIT_JOYSTICK | SDL_INIT_GAMEPAD);
    }
    if ((flags & SDL_INIT_VIDEO) && (initialized & SDL_INIT_VIDEO)) {
        sdl3_ps5_video_quit();
        initialized &= ~SDL_INIT_VIDEO;
    }
    initialized &= ~(flags & (SDL_INIT_HAPTIC | SDL_INIT_SENSOR | SDL_INIT_CAMERA));
    pthread_mutex_unlock(&init_lock);
}

void SDL_Quit(void)
{
    SDL_QuitSubSystem(initialized);
    pthread_mutex_lock(&init_lock);
    sdl3_ps5_events_quit();
    sdl3_ps5_user_quit();
    initialized = 0;
    pthread_mutex_unlock(&init_lock);
}
