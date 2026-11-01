/*
 * FFmpeg stubs for the PS5 port of Pokemon Legends Z-A Recomp: the 24 libavcodec / libavformat / libavutil /
 * libswscale functions that runtime/hle/movie.c (the movie:: HLE: Extractor and Decoder) and runtime/ui/launcher.mm
 * (the title-movie thumbnail) call, with the signatures of the FFmpeg 8.0.1 headers the compile audit used
 * (MSYS2 ucrt64: libavcodec 62, libavformat 62, libavutil 60, libswscale 9), without any FFmpeg.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Every entry point that opens or decodes something fails the FFmpeg way (a negative AVERROR, *ps = NULL), so the
 * runtime's own failure paths run: movie::Extractor::SetDataSource returns 1 ("[movie] cannot open ..."), the game
 * sees no tracks and no decoder is ever configured; the launcher's background stays empty. Allocation and release
 * functions work on real (zeroed) objects so that a caller which allocates before checking (movie.c dec_configure
 * writes ctx->thread_count before avcodec_open2) cannot dereference NULL. The pure helpers (av_rescale_q,
 * av_gettime_relative) are implemented for real.
 */
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/error.h>
#include <libavutil/frame.h>
#include <libavutil/mathematics.h>
#include <libavutil/time.h>
#include <libswscale/swscale.h>

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* the first few refusals go to stderr (the title's klog capture); the game may retry every boot */
static void ffs_refused(const char *what, const char *detail)
{
    static int n;
    if (n++ < 20) {
        fprintf(stderr, "[ffmpeg-stubs] %s: not available in this build (no FFmpeg on the PS5)%s%s\n", what,
                detail ? ": " : "", detail ? detail : "");
        fflush(stderr);
    }
}

/* ------------------------------------------------------------------ libavformat */

int avformat_open_input(AVFormatContext **ps, const char *url, const AVInputFormat *fmt, AVDictionary **options)
{
    (void)fmt;
    (void)options;
    if (ps) *ps = NULL; /* as FFmpeg on failure: the context is freed and *ps set to NULL */
    ffs_refused("avformat_open_input", url);
    return AVERROR(ENOSYS);
}

int avformat_find_stream_info(AVFormatContext *ic, AVDictionary **options)
{
    (void)ic;
    (void)options;
    return AVERROR(ENOSYS);
}

int av_find_best_stream(AVFormatContext *ic, enum AVMediaType type, int wanted_stream_nb, int related_stream,
                        const struct AVCodec **decoder_ret, int flags)
{
    (void)ic;
    (void)type;
    (void)wanted_stream_nb;
    (void)related_stream;
    (void)flags;
    if (decoder_ret) *decoder_ret = NULL;
    return AVERROR_STREAM_NOT_FOUND;
}

int av_read_frame(AVFormatContext *s, AVPacket *pkt)
{
    (void)s;
    (void)pkt;
    return AVERROR_EOF;
}

int av_seek_frame(AVFormatContext *s, int stream_index, int64_t timestamp, int flags)
{
    (void)s;
    (void)stream_index;
    (void)timestamp;
    (void)flags;
    return AVERROR(ENOSYS);
}

void avformat_close_input(AVFormatContext **s)
{
    /* no context is ever created here (avformat_open_input always fails), so there is nothing to free */
    if (s) *s = NULL;
}

/* ------------------------------------------------------------------ libavcodec */

const AVCodec *avcodec_find_decoder(enum AVCodecID id)
{
    (void)id;
    return NULL; /* no decoder of any kind */
}

AVCodecContext *avcodec_alloc_context3(const AVCodec *codec)
{
    (void)codec;
    /* a real, zeroed context: movie.c's dec_configure writes ctx->thread_count before avcodec_open2 refuses it */
    return calloc(1, sizeof(AVCodecContext));
}

void avcodec_free_context(AVCodecContext **avctx)
{
    if (!avctx || !*avctx) return;
    free(*avctx);
    *avctx = NULL;
}

int avcodec_parameters_to_context(AVCodecContext *codec, const struct AVCodecParameters *par)
{
    (void)codec;
    (void)par;
    return AVERROR(ENOSYS);
}

int avcodec_open2(AVCodecContext *avctx, const AVCodec *codec, AVDictionary **options)
{
    (void)avctx;
    (void)codec;
    (void)options;
    ffs_refused("avcodec_open2", NULL);
    return AVERROR_DECODER_NOT_FOUND;
}

int avcodec_send_packet(AVCodecContext *avctx, const AVPacket *avpkt)
{
    (void)avctx;
    (void)avpkt;
    return AVERROR(EINVAL); /* FFmpeg's answer for a codec that was never opened */
}

int avcodec_receive_frame(AVCodecContext *avctx, AVFrame *frame)
{
    (void)avctx;
    (void)frame;
    return AVERROR_EOF; /* nothing will ever come out */
}

static void ffs_packet_defaults(AVPacket *pkt)
{
    memset(pkt, 0, sizeof *pkt);
    pkt->pts = AV_NOPTS_VALUE;
    pkt->dts = AV_NOPTS_VALUE;
    pkt->pos = -1;
}

AVPacket *av_packet_alloc(void)
{
    AVPacket *pkt = malloc(sizeof *pkt);
    if (pkt) ffs_packet_defaults(pkt);
    return pkt;
}

void av_packet_free(AVPacket **pkt)
{
    if (!pkt || !*pkt) return;
    free(*pkt);
    *pkt = NULL;
}

void av_packet_unref(AVPacket *pkt)
{
    /* nothing is ever reference-counted here: the packet's fields the caller set (movie.c: data, size, pts
     * pointing into its own input buffer) go back to their defaults, as after FFmpeg's unref */
    if (pkt) ffs_packet_defaults(pkt);
}

/* ------------------------------------------------------------------ libavutil */

AVFrame *av_frame_alloc(void)
{
    AVFrame *f = calloc(1, sizeof *f);
    if (!f) return NULL;
    f->pts = AV_NOPTS_VALUE;
    f->pkt_dts = AV_NOPTS_VALUE;
    f->best_effort_timestamp = AV_NOPTS_VALUE;
    f->format = -1; /* "unknown", as FFmpeg's get_frame_defaults */
    return f;
}

void av_frame_free(AVFrame **frame)
{
    if (!frame || !*frame) return;
    free(*frame);
    *frame = NULL;
}

AVFrame *av_frame_clone(const AVFrame *src)
{
    (void)src;
    return NULL; /* a frame without buffers cannot be cloned; nothing is ever decoded here anyway */
}

int64_t av_gettime_relative(void)
{
    /* a monotonic microsecond clock, as FFmpeg's (CLOCK_MONOTONIC) */
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (int64_t)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

int64_t av_rescale_q(int64_t a, AVRational bq, AVRational cq)
{
    /* a * bq / cq, rounded to nearest with halves away from zero (AV_ROUND_NEAR_INF), 128-bit like FFmpeg */
    int64_t b = (int64_t)bq.num * cq.den, c = (int64_t)cq.num * bq.den;
    if (c == 0) return INT64_MIN;
    if (a == AV_NOPTS_VALUE) return a;
    __int128 num = (__int128)a * b;
    __int128 q = num / c, rem = num % c;
    __int128 ac = c < 0 ? -(__int128)c : c, ar = rem < 0 ? -rem : rem;
    if (2 * ar >= ac) q += ((num < 0) != (c < 0)) ? -1 : 1;
    return (int64_t)q;
}

/* ------------------------------------------------------------------ libswscale */

SwsContext *sws_getContext(int srcW, int srcH, enum AVPixelFormat srcFormat, int dstW, int dstH,
                           enum AVPixelFormat dstFormat, int flags, SwsFilter *srcFilter, SwsFilter *dstFilter,
                           const double *param)
{
    (void)srcW;
    (void)srcH;
    (void)srcFormat;
    (void)dstW;
    (void)dstH;
    (void)dstFormat;
    (void)flags;
    (void)srcFilter;
    (void)dstFilter;
    (void)param;
    ffs_refused("sws_getContext", NULL);
    return NULL;
}

int sws_scale(SwsContext *c, const uint8_t *const srcSlice[], const int srcStride[], int srcSliceY, int srcSliceH,
              uint8_t *const dst[], const int dstStride[])
{
    /* movie.c calls this with the NULL context sws_getContext gave it (dec_get_output_buffer): no conversion, and
     * the destination is left alone - a configured decoder cannot exist here, so the path is not reached */
    (void)c;
    (void)srcSlice;
    (void)srcStride;
    (void)srcSliceY;
    (void)srcSliceH;
    (void)dst;
    (void)dstStride;
    return AVERROR(EINVAL);
}

void sws_freeContext(SwsContext *swsContext)
{
    (void)swsContext; /* never non-NULL here */
}
