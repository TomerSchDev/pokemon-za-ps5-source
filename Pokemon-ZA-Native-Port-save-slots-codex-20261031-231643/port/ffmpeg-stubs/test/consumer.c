/*
 * ffmpeg-stubs consumer: calls the 24 FFmpeg functions the way runtime/hle/movie.c and runtime/ui/launcher.mm do
 * (same headers, same argument types, the same struct fields read), so that build-check.sh can compile it as C and
 * as C++ (launcher.mm is C++) against the real FFmpeg 8 headers and compare its imports with the stubs' exports.
 * Compile-only: nothing here runs.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/imgutils.h>
#include <libavutil/time.h>
#include <libswscale/swscale.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

int ffmpeg_stubs_consumer(const char *host, uint8_t *rgba, int w, int h, uint8_t *nv12, int stride)
{
    AVFormatContext *fmt = NULL;
    /* movie.c ex_set_data_source */
    if (avformat_open_input(&fmt, host, NULL, NULL) < 0 || avformat_find_stream_info(fmt, NULL) < 0) return 1;
    int ntracks = 0;
    for (unsigned i = 0; i < fmt->nb_streams && ntracks < 16; i++)
        if (fmt->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO ||
            fmt->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_AUDIO)
            ntracks++;
    /* launcher.mm load_background */
    int si = av_find_best_stream(fmt, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    if (si < 0) si = 0;
    AVStream *st = fmt->streams[si];
    AVCodecParameters *p = st->codecpar;
    const AVCodec *codec = avcodec_find_decoder(p->codec_id);
    AVCodecContext *cc = avcodec_alloc_context3(codec);
    avcodec_parameters_to_context(cc, p);
    cc->thread_count = 4; /* movie.c dec_configure: before avcodec_open2 */
    int64_t got_time = 0;
    if (codec && avcodec_open2(cc, codec, NULL) == 0) {
        int width = p->width, height = p->height, rate = p->sample_rate, channels = p->ch_layout.nb_channels;
        (void)width; (void)height; (void)rate; (void)channels; (void)codec->name;
        AVPacket *pkt = av_packet_alloc();
        AVFrame *fr = av_frame_alloc();
        int64_t want = (int64_t)(6.0 / av_q2d(st->time_base));
        av_seek_frame(fmt, si, want, AVSEEK_FLAG_BACKWARD);
        while (av_read_frame(fmt, pkt) >= 0) {
            if (pkt->stream_index == si && avcodec_send_packet(cc, pkt) == 0)
                while (avcodec_receive_frame(cc, fr) == 0) {
                    int64_t t = fr->pts != AV_NOPTS_VALUE ? fr->pts : fr->best_effort_timestamp;
                    AVFrame *pending = av_frame_clone(fr); /* movie.c dec_send_input: the output queue */
                    av_frame_free(&pending);
                    got_time = t;
                }
            av_packet_unref(pkt);
        }
        /* movie.c dec_send_input: end of stream, then a packet pointing into the game's buffer */
        avcodec_send_packet(cc, NULL);
        pkt->data = nv12;
        pkt->size = stride;
        pkt->pts = got_time;
        avcodec_send_packet(cc, pkt);
        av_packet_unref(pkt);
        /* launcher.mm: the frame to RGBA; movie.c dec_get_output_buffer: NV12 to RGBA */
        SwsContext *sws = sws_getContext(w, h, (enum AVPixelFormat)fr->format, w, h, AV_PIX_FMT_RGBA, SWS_BILINEAR, NULL, NULL, NULL);
        if (!sws) sws = sws_getContext(w, h, AV_PIX_FMT_NV12, w, h, AV_PIX_FMT_RGBA, SWS_BILINEAR, NULL, NULL, NULL);
        const uint8_t *src[2] = {nv12, nv12 + stride * ((h + 15) & ~15)};
        int src_stride[2] = {stride, stride};
        uint8_t *dst[1] = {rgba};
        int dst_ls[1] = {w * 4};
        sws_scale(sws, src, src_stride, 0, h, dst, dst_ls);
        sws_scale(sws, (const uint8_t *const *)fr->data, fr->linesize, 0, h, dst, dst_ls); /* (C++ converts this itself) */
        sws_freeContext(sws);
        av_frame_free(&fr);
        av_packet_free(&pkt);
    }
    avcodec_free_context(&cc);
    /* movie.c ex_get_sample_time / ex_fill */
    AVRational us = {1, 1000000};
    int64_t ts = av_rescale_q(got_time, st->time_base, us);
    double now = av_gettime_relative() / 1e6;
    int64_t to = fmt->duration - 500000;
    if (av_seek_frame(fmt, -1, to, AVSEEK_FLAG_BACKWARD) >= 0) ntracks++;
    avformat_close_input(&fmt);
    return (int)(ts & 1) + (now > 0.5) + ntracks;
}
