#include "libNativeCPURenderer.h"

i64 GetBufferSize(RenderContext* ctx) {
    return ctx->width * ctx->height * (ctx->enableAlpha ? 4 : 3);
}

RenderContext* CreateRenderContext(
    i64 width, i64 height,
    bool enableAlpha
) {
    RenderContext* ctx = new RenderContext();
    ctx->width = width;
    ctx->height = height;
    ctx->enableAlpha = enableAlpha;
    ctx->buffer = new f64[GetBufferSize(ctx)];

    ctx->transformMatrix[0] = 1;
    ctx->transformMatrix[1] = 0;
    ctx->transformMatrix[2] = 0;
    ctx->transformMatrix[3] = 1;
    ctx->transformMatrix[4] = 0;
    ctx->transformMatrix[5] = 0;
    ctx->colorTransform[0] = 1;
    ctx->colorTransform[1] = 1;
    ctx->colorTransform[2] = 1;
    ctx->colorTransform[3] = 1;

    ctx->stateStack = std::stack<RenderContextState>();

    return ctx;
}

void DestroyRenderContext(RenderContext* ctx) {
    return;
    delete[] ctx->buffer;
    delete ctx;
}

void ResizeRenderContext(RenderContext* ctx, i64 width, i64 height) {
    f64* newBuffer = new f64[width * height * (ctx->enableAlpha ? 4 : 3)];
    delete[] ctx->buffer;
    ctx->buffer = newBuffer;
    ctx->width = width;
    ctx->height = height;
}

void DestroyVideoCap(VideoCap* cap) {
    return;
    delete cap;
}

void GetBufferAsUInt8(RenderContext* ctx, iu8 *buffer) {
    i64 size = GetBufferSize(ctx);
    for (i64 i = 0; i < size; ++i) {
        buffer[i] = (iu8)(ctx->buffer[i] * 255);
    }
}

static const char* av_err2str_cpp(int err) {
    static char buf[AV_ERROR_MAX_STRING_SIZE];
    av_strerror(err, buf, sizeof(buf));
    return buf;
}

VideoCap* CreateVideoCap(i64 width, i64 height, f64 frameRate){
    VideoCap* cap = new VideoCap();
    cap->width = width;
    cap->height = height;
    cap->frameRate = frameRate;
    cap->frameIndex = 0;

    cap->formatCtx = avformat_alloc_context();
    const AVOutputFormat* fmt = av_guess_format("mp4", nullptr, nullptr);
    cap->formatCtx->oformat = fmt;

    return cap;
}

bool InitializeVideoCap(
    VideoCap* cap, const char* path,
    bool hasAudio, AudioClip* aClip, i64 aBitRate
) {
    const AVCodec* vCodec = avcodec_find_encoder(AV_CODEC_ID_H264);
    if (!vCodec) {
        delete cap;
        return false;
    }
    cap->stream = avformat_new_stream(cap->formatCtx, vCodec);
    cap->codecCtx = avcodec_alloc_context3(vCodec);
    cap->codecCtx->width = cap->width;
    cap->codecCtx->height = cap->height;
    cap->codecCtx->time_base = {1, (int)cap->frameRate};
    cap->codecCtx->framerate = {(int)cap->frameRate, 1};
    cap->codecCtx->pix_fmt = AV_PIX_FMT_YUV420P;
    cap->codecCtx->gop_size = 10;
    cap->codecCtx->max_b_frames = 1;

    avcodec_parameters_from_context(cap->stream->codecpar, cap->codecCtx);
    if (avcodec_open2(cap->codecCtx, vCodec, nullptr) < 0) {
        delete cap;
        return false;
    }

    cap->frame = av_frame_alloc();
    cap->frame->format = cap->codecCtx->pix_fmt;
    cap->frame->width  = cap->codecCtx->width;
    cap->frame->height = cap->codecCtx->height;
    av_frame_get_buffer(cap->frame, 0);
    cap->packet = av_packet_alloc();

    cap->hasAudio = hasAudio;

    if (cap->hasAudio) {
        const AVCodec* aCodec = avcodec_find_encoder(AV_CODEC_ID_AAC);
        if (!aCodec) { fprintf(stderr,"no AAC encoder\n"); return false; }

        cap->aStream = avformat_new_stream(cap->formatCtx, aCodec);
        cap->aCodecCtx = avcodec_alloc_context3(aCodec);

        cap->aCodecCtx->sample_fmt = AV_SAMPLE_FMT_FLTP;
        cap->aCodecCtx->bit_rate = aBitRate;
        cap->aCodecCtx->sample_rate = (int)aClip->sampleRate;
        cap->aCodecCtx->channels = (int)aClip->channels;
        cap->aCodecCtx->channel_layout = av_get_default_channel_layout(aClip->channels);
        cap->aCodecCtx->time_base = {1, cap->aCodecCtx->sample_rate};

        if (avcodec_open2(cap->aCodecCtx, aCodec, nullptr) < 0) return false;
        avcodec_parameters_from_context(cap->aStream->codecpar, cap->aCodecCtx);
        cap->aStream->time_base = cap->aCodecCtx->time_base;

        cap->audioPts = 0;
    }

    int ret = 0;
    if (!(cap->formatCtx->oformat->flags & AVFMT_NOFILE)) {
        ret = avio_open(&cap->formatCtx->pb, path, AVIO_FLAG_WRITE);
        if (ret < 0) {
            fprintf(stderr, "[CreateVideoCap] avio_open failed: %s\n", av_err2str_cpp(ret));
            DestroyVideoCap(cap);
            return false;
        }
    }
    ret = avformat_write_header(cap->formatCtx, nullptr);
    if (ret < 0) {
        fprintf(stderr, "[CreateVideoCap] avformat_write_header failed: %s\n", av_err2str_cpp(ret));
        DestroyVideoCap(cap);
        return false;
    }

    if (cap->hasAudio) {
        const int frameSize = cap->aCodecCtx->frame_size;

        for (i64 offset = 0; offset + frameSize <= aClip->numFrames; offset += frameSize)
        {
            AVFrame* f = av_frame_alloc();
            f->format = cap->aCodecCtx->sample_fmt;
            f->channel_layout = cap->aCodecCtx->channel_layout;
            f->sample_rate = cap->aCodecCtx->sample_rate;
            f->nb_samples = frameSize;
            f->channels = cap->aCodecCtx->channels;

            int r = av_frame_get_buffer(f, 0);
            if (r < 0) {
                fprintf(stderr, "[PutAudioIntoVideoCap] av_frame_get_buffer failed: %s\n", av_err2str_cpp(r));
                av_frame_free(&f);
                continue;
            }

            for (i64 c = 0; c < f->channels; ++c) {
                f32* data = (f32*)f->data[c];
                for (i64 i = 0; i < frameSize; ++i) {
                    data[i] = (f32)aClip->buffer[(i + offset) * aClip->channels + c];
                }
            }

            f->pts = cap->audioPts;
            cap->audioPts += frameSize;
            avcodec_send_frame(cap->aCodecCtx, f);

            if (offset + frameSize > aClip->numFrames) {
                avcodec_send_frame(cap->aCodecCtx, nullptr);
            }
            
            while (avcodec_receive_packet(cap->aCodecCtx, cap->packet) == 0) {
                av_packet_rescale_ts(cap->packet, cap->aCodecCtx->time_base, cap->aStream->time_base);
                cap->packet->stream_index = cap->aStream->index;
                av_interleaved_write_frame(cap->formatCtx, cap->packet);
                av_packet_unref(cap->packet);
            }

            av_frame_free(&f);
        }
    }

    return true;
}

void ReleaseVideoCap(VideoCap* cap){
    AVFormatContext* fmt = cap->formatCtx;

    int ret = avcodec_send_frame(cap->codecCtx, nullptr);
    if (ret < 0) {
        fprintf(stderr, "[ReleaseVideoCap] send_frame(NULL) failed: %s\n", av_err2str_cpp(ret));
    }

    while ((ret = avcodec_receive_packet(cap->codecCtx, cap->packet)) == 0) {
        av_packet_rescale_ts(cap->packet, cap->codecCtx->time_base, cap->stream->time_base);
        ret = av_interleaved_write_frame(fmt, cap->packet);
        if (ret < 0) {
            fprintf(stderr, "[ReleaseVideoCap] write_frame failed: %s\n", av_err2str_cpp(ret));
        }
        av_packet_unref(cap->packet);
    }

    av_write_trailer(fmt);

    if (!(fmt->oformat->flags & AVFMT_NOFILE)) avio_closep(&fmt->pb);

    avcodec_free_context(&cap->codecCtx);
    av_frame_free(&cap->frame);
    av_packet_free(&cap->packet);
    sws_freeContext(cap->swsCtx);
    avformat_free_context(fmt);

    cap->formatCtx = nullptr;
    cap->codecCtx = nullptr;
    cap->frame = nullptr;
    cap->packet = nullptr;
    cap->swsCtx = nullptr;
}

void PutRendererContextFrame(VideoCap* cap, RenderContext* ctx) {
    i64 pxCount = ctx->width * ctx->height;
    i64 ipp = ctx->enableAlpha ? 4 : 3;

    iu8* tbuffer = new iu8[pxCount * ipp];
    for (i64 i = 0; i < pxCount * ipp; ++i) {
        tbuffer[i] = (iu8)(ctx->buffer[i] * 255.0);
    }

    if (!cap->swsCtx) {
        cap->swsCtx = sws_getContext(
            ctx->width, ctx->height, ipp == 4 ? AV_PIX_FMT_RGBA : AV_PIX_FMT_RGB24,
            cap->width, cap->height, AV_PIX_FMT_YUV420P,
            SWS_BILINEAR, nullptr, nullptr, nullptr
        );
    }

    AVFrame* rgbFrame = av_frame_alloc();
    av_image_alloc(rgbFrame->data, rgbFrame->linesize, ctx->width, ctx->height, ipp == 4 ? AV_PIX_FMT_RGBA : AV_PIX_FMT_RGB24, 1);

    for (int y = 0; y < ctx->height; ++y) {
        memcpy(rgbFrame->data[0] + y * rgbFrame->linesize[0], tbuffer + y * ctx->width * ipp, ctx->width * ipp);
    }

    sws_scale(cap->swsCtx, (const uint8_t* const*)rgbFrame->data, rgbFrame->linesize, 0, ctx->height, cap->frame->data, cap->frame->linesize);

    cap->frame->pts = cap->frameIndex++;

    int ret = avcodec_send_frame(cap->codecCtx, cap->frame);
    if (ret < 0) goto END;

    while (ret >= 0) {
        ret = avcodec_receive_packet(cap->codecCtx, cap->packet);
        if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) break;
        av_packet_rescale_ts(cap->packet, cap->codecCtx->time_base, cap->stream->time_base);
        av_interleaved_write_frame(cap->formatCtx, cap->packet);
        av_packet_unref(cap->packet);
    }

END:
    delete[] tbuffer;
    av_freep(&rgbFrame->data[0]);
    av_frame_free(&rgbFrame);
}

void SaveContextState(RenderContext* ctx) {
    RenderContextState state;
    state.transformMatrix[0] = ctx->transformMatrix[0];
    state.transformMatrix[1] = ctx->transformMatrix[1];
    state.transformMatrix[2] = ctx->transformMatrix[2];
    state.transformMatrix[3] = ctx->transformMatrix[3];
    state.transformMatrix[4] = ctx->transformMatrix[4];
    state.transformMatrix[5] = ctx->transformMatrix[5];
    state.colorTransform[0] = ctx->colorTransform[0];
    state.colorTransform[1] = ctx->colorTransform[1];
    state.colorTransform[2] = ctx->colorTransform[2];
    state.colorTransform[3] = ctx->colorTransform[3];
    ctx->stateStack.push(state);
}

bool RestoreContextState(RenderContext* ctx) {
    if (ctx->stateStack.empty()) return false;

    RenderContextState state = ctx->stateStack.top();
    ctx->transformMatrix[0] = state.transformMatrix[0];
    ctx->transformMatrix[1] = state.transformMatrix[1];
    ctx->transformMatrix[2] = state.transformMatrix[2];
    ctx->transformMatrix[3] = state.transformMatrix[3];
    ctx->transformMatrix[4] = state.transformMatrix[4];
    ctx->transformMatrix[5] = state.transformMatrix[5];
    ctx->colorTransform[0] = state.colorTransform[0];
    ctx->colorTransform[1] = state.colorTransform[1];
    ctx->colorTransform[2] = state.colorTransform[2];
    ctx->colorTransform[3] = state.colorTransform[3];
    ctx->stateStack.pop();

    return true;
}

void GetBuffer(RenderContext* ctx, f64 *buffer) {
    i64 size = GetBufferSize(ctx);
    for (i64 i = 0; i < size; ++i) {
        buffer[i] = ctx->buffer[i];
    }
}

Texture* CreateTexture(
    i64 width, i64 height,
    bool enableAlpha,
    f64 *buffer
) {
    Texture* tex = new Texture();
    tex->width = width;
    tex->height = height;
    tex->enableAlpha = enableAlpha;
    i64 size = width * height * (enableAlpha ? 4 : 3);
    tex->buffer = new f64[size];

    for (i64 i = 0; i < size; ++i) {
        tex->buffer[i] = buffer[i];
    }
    
    return tex;
}

Texture* CreateTextureUInt8(
    i64 width, i64 height,
    bool enableAlpha,
    iu8 *buffer
) {
    Texture* tex = new Texture();
    tex->width = width;
    tex->height = height;
    tex->enableAlpha = enableAlpha;
    i64 size = width * height * (enableAlpha ? 4 : 3);
    tex->buffer = new f64[size];

    for (i64 i = 0; i < size; ++i) {
        tex->buffer[i] = buffer[i] / 255.0;
    }

    return tex;
}

void DestroyTexture(Texture* tex) {
    return;
    delete[] tex->buffer;
    delete tex;
}

Texture* CreateTextureFromRenderContext(RenderContext* ctx) {
    Texture* tex = new Texture();
    tex->width = ctx->width;
    tex->height = ctx->height;
    tex->enableAlpha = ctx->enableAlpha;
    i64 size = GetBufferSize(ctx);
    tex->buffer = new f64[size];

    for (i64 i = 0; i < size; ++i) {
        tex->buffer[i] = ctx->buffer[i];
    }
    
    return tex;
}

Texture* CreateTextureFromRenderContextShared(RenderContext* ctx) {
    Texture* tex = new Texture();
    tex->width = ctx->width;
    tex->height = ctx->height;
    tex->enableAlpha = ctx->enableAlpha;
    tex->buffer = ctx->buffer;
    return tex;
}

void SetTransform(
    RenderContext* ctx,
    f64 a, f64 b, f64 c, f64 d, f64 e, f64 f
) {
    ctx->transformMatrix[0] = a;
    ctx->transformMatrix[1] = b;
    ctx->transformMatrix[2] = c;
    ctx->transformMatrix[3] = d;
    ctx->transformMatrix[4] = e;
    ctx->transformMatrix[5] = f;
}

void ApplyTransform(
    RenderContext* ctx,
    f64 a, f64 b, f64 c, f64 d, f64 e, f64 f
) {
    f64 old[6];
    for (int i = 0; i < 6; ++i) old[i] = ctx->transformMatrix[i];

    ctx->transformMatrix[0] = old[0] * a + old[2] * b;
    ctx->transformMatrix[1] = old[1] * a + old[3] * b;
    ctx->transformMatrix[2] = old[0] * c + old[2] * d;
    ctx->transformMatrix[3] = old[1] * c + old[3] * d;
    ctx->transformMatrix[4] = old[0] * e + old[2] * f + old[4];
    ctx->transformMatrix[5] = old[1] * e + old[3] * f + old[5];
}

void InnerApplyTransform(
    RenderContext* ctx,
    f64 matrix[6]
) {
    ApplyTransform(ctx, matrix[0], matrix[1], matrix[2], matrix[3], matrix[4], matrix[5]);
}

void Scale(
    RenderContext* ctx,
    f64 sx, f64 sy
) {
    f64 m[6] = {sx, 0, 0, sy, 0, 0};
    InnerApplyTransform(ctx, m);
}

void Translate(
    RenderContext* ctx,
    f64 tx, f64 ty
) {
    f64 m[6] = {1, 0, 0, 1, tx, ty};
    InnerApplyTransform(ctx, m);
}

void Rotate(
    RenderContext* ctx,
    f64 angle
) {
    f64 s = sin(angle);
    f64 c = cos(angle);
    f64 m[6] = {c, s, -s, c, 0, 0};
    InnerApplyTransform(ctx, m);
}

inline void TransformPointFromMatrix(
    f64 matrix[6],
    f64 x, f64 y,
    f64 *out_x, f64 *out_y
) {
    *out_x = matrix[0] * x + matrix[2] * y + matrix[4];
    *out_y = matrix[1] * x + matrix[3] * y + matrix[5];
}

inline void TransformPoint(
    RenderContext* ctx,
    f64 x, f64 y,
    f64 *out_x, f64 *out_y
) {
    TransformPointFromMatrix(ctx->transformMatrix, x, y, out_x, out_y);
}

void GetTransform(
    RenderContext* ctx,
    f64 out_matrix[6]
) {
    for (int i = 0; i < 6; ++i) {
        out_matrix[i] = ctx->transformMatrix[i];
    }
}

void GetInverseTransform(
    RenderContext* ctx,
    f64 out_matrix[6]
) {
    f64 a = ctx->transformMatrix[0];
    f64 b = ctx->transformMatrix[1];
    f64 c = ctx->transformMatrix[2];
    f64 d = ctx->transformMatrix[3];
    f64 e = ctx->transformMatrix[4];
    f64 f = ctx->transformMatrix[5];

    f64 det = a * d - b * c;
    f64 inv_det = det != 0 ? 1 / det : 1e9;

    out_matrix[0] = d * inv_det;
    out_matrix[1] = -b * inv_det;
    out_matrix[2] = -c * inv_det;
    out_matrix[3] = a * inv_det;
    out_matrix[4] = (c * f - d * e) * inv_det;
    out_matrix[5] = (b * e - a * f) * inv_det;
}

bool SetPixel(
    RenderContext* ctx,
    i64 x, i64 y,
    f64 r, f64 g, f64 b, f64 a
) {
    if (x < 0) return false;
    if (x >= ctx->width) return false;
    if (y < 0) return false;
    if (y >= ctx->height) return false;

    i64 ipp = ctx->enableAlpha ? 4 : 3;
    i64 index = y * ctx->width * ipp + x * ipp;

    ctx->buffer[index + 0] = r;
    ctx->buffer[index + 1] = g;
    ctx->buffer[index + 2] = b;
    ctx->buffer[index + 3] = a;

    return true;
}

inline bool ApplyPixel(
    RenderContext* ctx,
    i64 x, i64 y,
    f64 r, f64 g, f64 b, f64 a
) {
    if (x < 0) return false;
    if (x >= ctx->width) return false;
    if (y < 0) return false;
    if (y >= ctx->height) return false;

    r *= ctx->colorTransform[0];
    g *= ctx->colorTransform[1];
    b *= ctx->colorTransform[2];
    a *= ctx->colorTransform[3];

    i64 ipp = ctx->enableAlpha ? 4 : 3;
    i64 index = y * ctx->width * ipp + x * ipp;

    r = ctx->buffer[index + 0] * (1 - a) + r * a;
    g = ctx->buffer[index + 1] * (1 - a) + g * a;
    b = ctx->buffer[index + 2] * (1 - a) + b * a;

    ctx->buffer[index + 0] = r;
    ctx->buffer[index + 1] = g;
    ctx->buffer[index + 2] = b;

    if (ctx->enableAlpha) {
        ctx->buffer[index + 3] = a;
        a = ctx->buffer[index + 3] * (1 - a) + a * a;
    }

    return true;
}

inline void InterpolateColorFromBuffer(
    f64 *buffer, i64 width, i64 height, bool enableAlpha,
    f64 x, f64 y,
    f64 *out_r, f64 *out_g, f64 *out_b, f64 *out_a
) {
    if (x < 0) x = 0;
    if (x >= width - 1) x = width - 2;
    if (y < 0) y = 0;
    if (y >= height - 1) y = height - 2;

    i64 ipp = enableAlpha ? 4 : 3;
    i64 index = y * width * ipp + x * ipp;
    *out_r = buffer[index + 0];
    *out_g = buffer[index + 1];
    *out_b = buffer[index + 2];
    if (enableAlpha) {
        *out_a = buffer[index + 3];
    }

    return;

    i64 ix = (i64)x;
    i64 iy = (i64)y;
    i64 nx = ix + 1;
    i64 ny = iy + 1;

    i64 ipp = enableAlpha ? 4 : 3;

    i64 index0 = iy * width * ipp + ix * ipp;
    f64 r0 = buffer[index0 + 0];
    f64 g0 = buffer[index0 + 1];
    f64 b0 = buffer[index0 + 2];
    f64 a0 = enableAlpha ? buffer[index0 + 3] : 1;

    i64 index1 = iy * width * ipp + nx * ipp;
    f64 r1 = buffer[index1 + 0];
    f64 g1 = buffer[index1 + 1];
    f64 b1 = buffer[index1 + 2];
    f64 a1 = enableAlpha ? buffer[index1 + 3] : 1;

    i64 index2 = ny * width * ipp + ix * ipp;
    f64 r2 = buffer[index2 + 0];
    f64 g2 = buffer[index2 + 1];
    f64 b2 = buffer[index2 + 2];
    f64 a2 = enableAlpha ? buffer[index2 + 3] : 1;

    i64 index3 = ny * width * ipp + nx * ipp;
    f64 r3 = buffer[index3 + 0];
    f64 g3 = buffer[index3 + 1];
    f64 b3 = buffer[index3 + 2];
    f64 a3 = enableAlpha ? buffer[index3 + 3] : 1;

    f64 u = x - ix;
    f64 v = y - iy;

    f64 r = r0 * (1 - u) * (1 - v) + r1 * u * (1 - v) + r2 * (1 - u) * v + r3 * u * v;
    f64 g = g0 * (1 - u) * (1 - v) + g1 * u * (1 - v) + g2 * (1 - u) * v + g3 * u * v;
    f64 b = b0 * (1 - u) * (1 - v) + b1 * u * (1 - v) + b2 * (1 - u) * v + b3 * u * v;

    *out_r = r;
    *out_g = g;
    *out_b = b;

    if (enableAlpha) {
        f64 a = a0 * (1 - u) * (1 - v) + a1 * u * (1 - v) + a2 * (1 - u) * v + a3 * u * v;
        *out_a = a;
    }
}

void SetColorTransform(
    RenderContext* ctx,
    f64 r, f64 g, f64 b, f64 a
) {
    ctx->colorTransform[0] = r;
    ctx->colorTransform[1] = g;
    ctx->colorTransform[2] = b;
    ctx->colorTransform[3] = a;
}

void ApplyColorTransform(
    RenderContext* ctx,
    f64 r, f64 g, f64 b, f64 a
) {
    ctx->colorTransform[0] *= r;
    ctx->colorTransform[1] *= g;
    ctx->colorTransform[2] *= b;
    ctx->colorTransform[3] *= a;
}

void SetColor(
    RenderContext* ctx,
    f64 r, f64 g, f64 b, f64 a
) {
    if (r == g && g == b && b == a) {
        std::fill(ctx->buffer, ctx->buffer + ctx->width * ctx->height * (ctx->enableAlpha ? 4 : 3), r);
        return;
    }

    for (i64 i = 0; i < ctx->width; ++i) {
        for (i64 j = 0; j < ctx->height; ++j) {
            SetPixel(ctx, i, j, r, g, b, a);
        }
    }
}

void GetColor(
    RenderContext* ctx,
    f64 x, f64 y,
    f64 *out_r, f64 *out_g, f64 *out_b, f64 *out_a
) {
    if (x < 0) x = 0;
    if (x >= ctx->width) x = ctx->width - 1;
    if (y < 0) y = 0;
    if (y >= ctx->height) y = ctx->height - 1;

    i64 ix = (i64)x;
    i64 iy = (i64)y;
    
    i64 ipp = ctx->enableAlpha ? 4 : 3;
    i64 index = iy * ctx->width * ipp + ix * ipp;
    
    *out_r = ctx->buffer[index + 0];
    *out_g = ctx->buffer[index + 1];
    *out_b = ctx->buffer[index + 2];

    if (ctx->enableAlpha) *out_a = ctx->buffer[index + 3];
}

void FillColor(
    RenderContext* ctx,
    f64 r, f64 g, f64 b, f64 a
) {
    for (i64 i = 0; i < ctx->width; ++i) {
        for (i64 j = 0; j < ctx->height; ++j) {
            ApplyPixel(ctx, i, j, r, g, b, a);
        }
    }
}

inline void GetBoarder(
    f64 mat[6],
    f64 x, f64 y, f64 width, f64 height,
    i64 *out_left, i64 *out_right, i64 *out_top, i64 *out_bottom,
    f64 max_width, f64 max_height
) {
    f64 lt_x, lt_y;
    f64 rt_x, rt_y;
    f64 lb_x, lb_y;
    f64 rb_x, rb_y;

    TransformPointFromMatrix(mat, x, y, &lt_x, &lt_y);
    TransformPointFromMatrix(mat, x + width, y, &rt_x, &rt_y);
    TransformPointFromMatrix(mat, x, y + height, &lb_x, &lb_y);
    TransformPointFromMatrix(mat, x + width, y + height, &rb_x, &rb_y);

    *out_left = (i64)std::min(std::min(lt_x, rt_x), std::min(lb_x, rb_x));
    *out_right = (i64)std::max(std::max(lt_x, rt_x), std::max(lb_x, rb_x));
    *out_top = (i64)std::min(std::min(lt_y, rt_y), std::min(lb_y, rb_y));
    *out_bottom = (i64)std::max(std::max(lt_y, rt_y), std::max(lb_y, rb_y));

    *out_left = std::max(0L, std::min((i64)max_width, *out_left));
    *out_right = std::max(0L, std::min((i64)max_width, *out_right));
    *out_top = std::max(0L, std::min((i64)max_height, *out_top));
    *out_bottom = std::max(0L, std::min((i64)max_height, *out_bottom));
}

void DrawTexture(
    RenderContext* ctx,
    Texture* tex,
    f64 x, f64 y,
    f64 width, f64 height
) {
    if (width == 0 || height == 0) return;

    f64 inv[6];
    GetInverseTransform(ctx, inv);
    f64 scaleX = tex->width / width;
    f64 scaleY = tex->height / height;

    i64 left, right, top, bottom;
    GetBoarder(ctx->transformMatrix, x, y, width, height, &left, &right, &top, &bottom, ctx->width, ctx->height);

    for (i64 i = left; i < right; ++i) {
        for (i64 j = top; j < bottom; ++j) {
            f64 invX, invY;
            TransformPointFromMatrix(inv, i, j, &invX, &invY);

            if (invX < x) continue;
            if (invX > x + width) continue;
            if (invY < y) continue;
            if (invY > y + height) continue;

            f64 u = (invX - x) * scaleX;
            f64 v = (invY - y) * scaleY;

            f64 r, g, b, a;
            InterpolateColorFromBuffer(tex->buffer, tex->width, tex->height, tex->enableAlpha, u, v, &r, &g, &b, &a);
            ApplyPixel(ctx, i, j, r, g, b, a);
        }
    }
}

void DrawSplittedTexture(
    RenderContext* ctx,
    Texture* tex,
    f64 x, f64 y,
    f64 width, f64 height,
    f64 uStart, f64 uEnd,
    f64 vStart, f64 vEnd
) {
    if (width == 0 || height == 0) return;

    f64 inv[6];
    GetInverseTransform(ctx, inv);
    f64 scaleX = tex->width / width;
    f64 scaleY = tex->height / height;

    i64 left, right, top, bottom;
    GetBoarder(ctx->transformMatrix, x, y, width, height, &left, &right, &top, &bottom, ctx->width, ctx->height);

    for (i64 i = left; i < right; ++i) {
        for (i64 j = top; j < bottom; ++j) {
            f64 invX, invY;
            TransformPointFromMatrix(inv, i, j, &invX, &invY);

            if (invX < x) continue;
            if (invX > x + width) continue;
            if (invY < y) continue;
            if (invY > y + height) continue;

            f64 u = (invX - x) * scaleX;
            f64 v = (invY - y) * scaleY;

            u = (uStart + (uEnd - uStart) * u / tex->width) * tex->width;
            v = (vStart + (vEnd - vStart) * v / tex->height) * tex->height;

            f64 r, g, b, a;
            InterpolateColorFromBuffer(tex->buffer, tex->width, tex->height, tex->enableAlpha, u, v, &r, &g, &b, &a);
            ApplyPixel(ctx, i, j, r, g, b, a);
        }
    }
}

inline bool pointInPolygon(
    f64 x, f64 y,
    f64 points[][2], i64 num_points
) {
    i64 n = num_points;
    i64 j = n - 1;
    bool res = false;
    for (i64 i = 0; i < n; ++i) {
        if (
            (points[i][1] > y) != (points[j][1] > y)
            && (
                x < (
                    (points[j][0] - points[i][0])
                    * (y - points[i][1])
                    / (points[j][1] - points[i][1])
                    + points[i][0]
                )
            )
        ) res = !res;
        j = i;
    }

    return res;
}

void DrawRect(
    RenderContext* ctx,
    f64 x, f64 y,
    f64 width, f64 height,
    f64 r, f64 g, f64 b, f64 a
) {
    if (width <= 0 || height <= 0) return;

    f64 inv[6];
    GetInverseTransform(ctx, inv);

    i64 left, right, top, bottom;
    GetBoarder(ctx->transformMatrix, x, y, width, height, &left, &right, &top, &bottom, ctx->width, ctx->height);

    for (i64 i = left; i < right; ++i) {
        for (i64 j = top; j < bottom; ++j) {
            f64 invX, invY;
            TransformPointFromMatrix(inv, i, j, &invX, &invY);

            if (invX < x) continue;
            if (invX > x + width) continue;
            if (invY < y) continue;
            if (invY > y + height) continue;
            
            ApplyPixel(ctx, i, j, r, g, b, a);
        }
    }
}

void DrawLine(
    RenderContext* ctx,
    f64 x1, f64 y1,
    f64 x2, f64 y2,
    f64 width,
    f64 r, f64 g, f64 b, f64 a
) {
    if (width <= 0) return;

    f64 inv[6];
    GetInverseTransform(ctx, inv);

    f64 dx = x2 - x1;
    f64 dy = y2 - y1;
    f64 len = sqrt(dx * dx + dy * dy);
    if (len == 0) return;

    f64 ux = dx / len;
    f64 uy = dy / len;

    f64 vx = -uy;
    f64 vy = ux;

    f64 halfWidth = width / 2;

    f64 points[][2] = {
        {x1 - vx * halfWidth, y1 - vy * halfWidth},
        {x1 + vx * halfWidth, y1 + vy * halfWidth},
        {x2 + vx * halfWidth, y2 + vy * halfWidth},
        {x2 - vx * halfWidth, y2 - vy * halfWidth},
    };

    for (i64 i = 0; i < ctx->width; ++i) {
        for (i64 j = 0; j < ctx->height; ++j) {
            f64 invX, invY;
            TransformPointFromMatrix(inv, i, j, &invX, &invY);

            if (!pointInPolygon(invX, invY, points, 4)) continue;

            ApplyPixel(ctx, i, j, r, g, b, a);
        }
    }
}

void DrawCircle(
    RenderContext* ctx,
    f64 x, f64 y,
    f64 radius,
    f64 r, f64 g, f64 b, f64 a
) {
    if (radius <= 0) return;
    
    f64 inv[6];
    GetInverseTransform(ctx, inv);

    i64 left, right, top, bottom;
    GetBoarder(ctx->transformMatrix, x - radius, y - radius, 2 * radius, 2 * radius, &left, &right, &top, &bottom, ctx->width, ctx->height);
    
    for (i64 i = left; i < right; ++i) {
        for (i64 j = top; j < bottom; ++j) {
            f64 invX, invY;
            TransformPointFromMatrix(inv, i, j, &invX, &invY);
            
            f64 dx = invX - x;
            f64 dy = invY - y;
            f64 dist = sqrt(dx * dx + dy * dy);

            if (dist > radius) continue;
            
            ApplyPixel(ctx, i, j, r, g, b, a);
        }
    }
}

Texture* ResampleTexture(
    Texture* tex,
    i64 width, i64 height
) {
    Texture* res = new Texture();
    res->width = width;
    res->height = height;
    i64 ipp = tex->enableAlpha ? 4 : 3;
    res->buffer = new f64[width * height * ipp];
    res->enableAlpha = tex->enableAlpha;

    for (i64 i = 0; i < width; ++i) {
        for (i64 j = 0; j < height; ++j) {
            InterpolateColorFromBuffer(
                tex->buffer, tex->width, tex->height, tex->enableAlpha,
                (f64)i / width * tex->width,
                (f64)j / height * tex->height,
                &res->buffer[j * res->width * ipp + i * ipp],
                &res->buffer[j * res->width * ipp + i * ipp + 1],
                &res->buffer[j * res->width * ipp + i * ipp + 2],
                tex->enableAlpha ? &res->buffer[j * res->width * ipp + i * ipp + 3] : nullptr
            );
        }
    }

    return res;
}

i64 GetTextureWidth(Texture* tex) {
    return tex->width;
}

i64 GetTextureHeight(Texture* tex) {
    return tex->height;
}

bool GetTextureEnableAlpha(Texture* tex) {
    return tex->enableAlpha;
}

i64 GetAudioClipBufferSizeFromData(i64 numFrames, i64 channels) {
    return numFrames * channels;
}

i64 GetAudioClipBufferSize(AudioClip* clip) {
    return GetAudioClipBufferSizeFromData(clip->numFrames, clip->channels);
}

AudioClip* CreateAudioClipFromBuffer(
    i64 sampleRate, i64 channels,
    i64 numFrames, f64 *buffer
) {
    AudioClip* clip = new AudioClip();
    clip->sampleRate = sampleRate;
    clip->channels = channels;
    clip->numFrames = numFrames;
    i64 size = GetAudioClipBufferSize(clip);
    clip->buffer = new f64[size];

    for (i64 i = 0; i < size; ++i) {
        clip->buffer[i] = buffer[i];
    }

    return clip;
}

AudioClip* CreateAudioClipFromInt16Buffer(
    i64 sampleRate, i64 channels,
    i64 numFrames, i16 *buffer
) {
    AudioClip* clip = new AudioClip();
    clip->sampleRate = sampleRate;
    clip->channels = channels;
    clip->numFrames = numFrames;
    i64 size = GetAudioClipBufferSize(clip);
    clip->buffer = new f64[size];

    for (i64 i = 0; i < clip->numFrames; ++i) {
        for (i64 j = 0; j < clip->channels; ++j) {
            clip->buffer[i * clip->channels + j] = (f64)buffer[i * clip->channels + j] / 32768.0;
        }
    }

    return clip;
}

AudioClip* CreateSilentAudioClip(i64 sampleRate, i64 channels, i64 numFrames) {
    AudioClip* clip = new AudioClip();
    clip->sampleRate = sampleRate;
    clip->channels = channels;
    clip->numFrames = numFrames;
    i64 size = GetAudioClipBufferSize(clip);
    clip->buffer = new f64[size];

    std::fill(clip->buffer, clip->buffer + size, 0.0);
    return clip;
}

void DestroyAudioClip(AudioClip* clip) {
    return;
    delete[] clip->buffer;
    delete clip;
}

AudioClip* CloneAudioClip(AudioClip* clip) {
    return CreateAudioClipFromBuffer(
        clip->sampleRate,
        clip->channels,
        clip->numFrames,
        clip->buffer
    );
}

void ApplyResampleAudioClip(
    AudioClip* clip,
    i64 sampleRate,
    i64 channels
) {
    if (clip->sampleRate == sampleRate && clip->channels == channels) return;
    f64 dur = GetAudioClipDuration(clip);
    i64 newNumSamples = dur * sampleRate;
    i64 newSize = GetAudioClipBufferSizeFromData(newNumSamples, channels);

    f64 *newBuffer = new f64[newSize];

    for (i64 i = 0; i < newNumSamples; ++i) {
        f64 secT = (f64)i / sampleRate;
        f64 oldSampleIndex = secT * clip->sampleRate;
        i64 oldSampleIndexFloor = floor(oldSampleIndex);
        i64 oldSampleIndexCeil = ceil(oldSampleIndex);

        if (oldSampleIndexFloor < 0) oldSampleIndexFloor = 0;
        if (oldSampleIndexFloor >= clip->numFrames - clip->channels) oldSampleIndexFloor = clip->numFrames - clip->channels - 1;
        if (oldSampleIndexCeil < 0) oldSampleIndexCeil = 0;
        if (oldSampleIndexCeil >= clip->numFrames - clip->channels) oldSampleIndexCeil = clip->numFrames - clip->channels - 1;

        f64 oldSampleIndexFrac = oldSampleIndex - oldSampleIndexFloor;
        
        if (clip->channels == channels) {
            for (i64 c = 0; c < channels; ++c) {
                f64 oldSampleValueFloor = clip->buffer[oldSampleIndexFloor * clip->channels + c];
                f64 oldSampleValueCeil = clip->buffer[oldSampleIndexCeil * clip->channels + c];
                f64 newSampleValue = oldSampleValueFloor + (oldSampleValueCeil - oldSampleValueFloor) * oldSampleIndexFrac;
                newBuffer[i * channels + c] = newSampleValue;
            }
        } else {
            f64 oldSampleValueFloorSum = 0;
            f64 oldSampleIndexCeilSum = 0;

            for (i64 c = 0; c < clip->channels; ++c) {
                oldSampleValueFloorSum += clip->buffer[oldSampleIndexFloor * clip->channels + c];
                oldSampleIndexCeilSum += clip->buffer[oldSampleIndexCeil * clip->channels + c];
            }

            oldSampleIndexFloor /= clip->channels;
            oldSampleIndexCeil /= clip->channels;

            for (i64 c = 0; c < channels; ++c) {
                f64 newSampleValue = oldSampleValueFloorSum / clip->channels + (oldSampleIndexCeilSum / clip->channels - oldSampleValueFloorSum / clip->channels) * oldSampleIndexFrac;
                newBuffer[i * channels + c] = newSampleValue;
            }
        }
    }

    delete[] clip->buffer;

    clip->buffer = newBuffer;
    clip->sampleRate = sampleRate;
    clip->channels = channels;
    clip->numFrames = newNumSamples;
}

void ResampleAudioClipLike(
    AudioClip* clip,
    AudioClip* like
) {
    ApplyResampleAudioClip(clip, like->sampleRate, like->channels);
}

i64 OverlayAudioClip(
    AudioClip* target,
    AudioClip* source,
    i64 startFrame,
    bool autoResample
) {
    if (autoResample) {
        if (target->sampleRate != source->sampleRate || target->channels != source->channels) {
            source = CloneAudioClip(source);
            ResampleAudioClipLike(source, target);
        }
    }

    if (target->sampleRate != source->sampleRate) return -1;
    if (target->channels != source->channels) return -2;

    for (i64 i = 0; i < source->numFrames; ++i) {
        if (startFrame + i >= target->numFrames) break;
        i64 targetIndex = startFrame + i;
        for (i64 c = 0; c < source->channels; ++c) {
            target->buffer[targetIndex * source->channels + c] += source->buffer[i * source->channels + c];
        }
    }

    return 0;
}

i64 OverlayAudioClipSecond(
    AudioClip* target,
    AudioClip* source,
    f64 startSecond,
    bool autoResample
) {
    return OverlayAudioClip(target, source, (i64)(startSecond * target->sampleRate), autoResample);
}

WapperedBytes* SaveAudioClipAsWav(AudioClip* clip) {
    i64 dataSize = 0;

    dataSize += 4; // RIFF
    dataSize += 4; // Remaining size
    dataSize += 4; // WAVE

    dataSize += 4; // "fmt "
    dataSize += 4; // Fmt size
    dataSize += 2; // Wave format
    dataSize += 2; // Num channels
    dataSize += 4; // Sample rate
    dataSize += 4; // Byte rate
    dataSize += 2; // Align
    dataSize += 2; // BitsPerSample

    dataSize += 4; // data
    dataSize += 4; // Data size
    dataSize += GetAudioClipBufferSize(clip) * 2;

    iu8* data = new iu8[dataSize];
    *(iu8*)&data[0] = 'R';
    *(iu8*)&data[1] = 'I';
    *(iu8*)&data[2] = 'F';
    *(iu8*)&data[3] = 'F';
    *(i32*)&data[4] = dataSize - 8;
    *(iu8*)&data[8] = 'W';
    *(iu8*)&data[9] = 'A';
    *(iu8*)&data[10] = 'V';
    *(iu8*)&data[11] = 'E';

    *(iu8*)&data[12] = 'f';
    *(iu8*)&data[13] = 'm';
    *(iu8*)&data[14] = 't';
    *(iu8*)&data[15] = ' ';
    *(i32*)&data[16] = 0x10;
    *(i16*)&data[20] = 1; // PCM
    *(i16*)&data[22] = clip->channels;
    *(i32*)&data[24] = clip->sampleRate;
    *(i32*)&data[28] = clip->sampleRate * clip->channels * 2;
    *(i16*)&data[32] = clip->channels * 2;
    *(i16*)&data[34] = 2 * 8;
    
    *(iu8*)&data[36] = 'd';
    *(iu8*)&data[37] = 'a';
    *(iu8*)&data[38] = 't';
    *(iu8*)&data[39] = 'a';
    *(i32*)&data[40] = GetAudioClipBufferSize(clip) * 2;

    i16 *dst = (i16*)&data[44];
    
    for (i64 i = 0; i < clip->numFrames; ++i) {
        for (i64 c = 0; c < clip->channels; ++c) {
            f64 v = clip->buffer[i * clip->channels + c];
            i16 v16 = (i16)((v > 1.0 ? 1.0 : (v < -1.0 ? -1.0 : v)) * 32767.0);
            dst[i * clip->channels + c] = v16;
        }
    }

    WapperedBytes* result = new WapperedBytes();
    result->data = data;
    result->size = dataSize;
    return result;
}

i64 GetAudioClipSampleRate(AudioClip* clip) {
    return clip->sampleRate;
}

i64 GetAudioClipChannels(AudioClip* clip) {
    return clip->channels;
}

i64 GetAudioClipNumFrames(AudioClip* clip) {
    return clip->numFrames;
}

f64 GetAudioClipDuration(AudioClip* clip) {
    return (f64)clip->numFrames / (f64)clip->sampleRate;
}

iu8* GetWapperedBytesDataPtr(WapperedBytes* bytes) {
    return bytes->data;
}

i64 GetWapperedBytesDataSize(WapperedBytes* bytes) {
    return bytes->size;
}

void ApplyVolumeGain(AudioClip* clip, f64 gain) {
    i64 size = GetAudioClipBufferSize(clip);
    for (i64 i = 0; i < size; ++i) {
        clip->buffer[i] *= gain;
    }
}

i64 GetVersion() {
    return LIB_NATIVE_CPU_RENDERER_VERSION;
}

void ApplyCutAudioClip(AudioClip* clip, i64 startFrame, i64 endFrame) {
    f64* newBuffer = new f64[GetAudioClipBufferSizeFromData(endFrame - startFrame, clip->channels)];

    for (i64 i = 0; i < endFrame - startFrame; ++i) {
        if (startFrame + i >= clip->numFrames) break;
        for (i64 c = 0; c < clip->channels; ++c) {
            newBuffer[i * clip->channels + c] = clip->buffer[(startFrame + i) * clip->channels + c];
        }
    }

    delete[] clip->buffer;
    
    clip->buffer = newBuffer;
    clip->numFrames = endFrame - startFrame;
}

void ApplySpeedAudioClip(AudioClip* clip, f64 speed) {
    clip->sampleRate *= speed;
}

void DrawVerticalGrd(
    RenderContext* ctx,
    f64 x, f64 y, f64 width, f64 height,
    f64 top_r, f64 top_g, f64 top_b, f64 top_a,
    f64 bottom_r, f64 bottom_g, f64 bottom_b, f64 bottom_a
) {
    if (width <= 0 || height <= 0) return;

    f64 inv[6];
    GetInverseTransform(ctx, inv);

    i64 left, right, top, bottom;
    GetBoarder(ctx->transformMatrix, x, y, width, height, &left, &right, &top, &bottom, ctx->width, ctx->height);

    for (i64 i = left; i < right; ++i) {
        for (i64 j = top; j < bottom; ++j) {
            f64 invX, invY;
            TransformPointFromMatrix(inv, i, j, &invX, &invY);

            if (invX < x) continue;
            if (invX > x + width) continue;
            if (invY < y) continue;
            if (invY > y + height) continue;
            
            f64 p = (invY - y) / height;
            f64 r = top_r + (bottom_r - top_r) * p;
            f64 g = top_g + (bottom_g - top_g) * p;
            f64 b = top_b + (bottom_b - top_b) * p;
            f64 a = top_a + (bottom_a - top_a) * p;
            ApplyPixel(ctx, i, j, r, g, b, a);
        }
    }
}

namespace ShaderUtils {
    struct vec2 {
        f64 x, y;
    };
    
    inline f64 dot(vec2 a, vec2 b) {
        return a.x * b.x + a.y * b.y;
    }

    inline vec2 sin_vec2(vec2 v) {
        return { sin(v.x), sin(v.y) };
    }

    inline f64 fract(f64 x) {
        return x - floor(x);
    }

    inline vec2 fract_vec2(vec2 v) {
        return { fract(v.x), fract(v.y) };
    }

    inline f64 rand(vec2 n) {
        return fract(sin(dot(n, {12.9898, 78.233})) * 43758.5453);
    }

    inline vec2 floor_vec2(vec2 v) {
        return { floor(v.x), floor(v.y) };
    }

    inline vec2 operator+(vec2 a, vec2 b) { return { a.x + b.x, a.y + b.y }; }
    inline vec2 operator+(vec2 a, f64 b) { return { a.x + b, a.y + b }; }
    inline vec2 operator*(vec2 a, f64 b) { return { a.x * b, a.y * b }; }
    inline vec2 operator*(f64 a, vec2 b) { return { a * b.x, a * b.y }; }
    inline vec2 operator*(vec2 a, vec2 b) { return { a.x * b.x, a.y * b.y }; }
    inline vec2 operator-(vec2 a, f64 b) { return { a.x - b, a.y - b }; }
    inline vec2 operator-(f64 a, vec2 b) { return { a - b.x, a - b.y }; }
    inline vec2 operator-(vec2 a, vec2 b) { return { a.x - b.x, a.y - b.y }; }

    inline f64 mix(f64 a, f64 b, f64 t) {
        return a + (b - a) * t;
    }

    inline f64 clamp(f64 x, f64 minVal, f64 maxVal) {
        return x < minVal ? minVal : (x > maxVal ? maxVal : x);
    }

    inline f64 length(vec2 v) {
        return sqrt(v.x * v.x + v.y * v.y);
    }

    inline f64 atan2_vec2(vec2 v) {
        return atan2(v.y, v.x);
    }

    inline f64 noise(vec2 p) {
        vec2 ip = floor_vec2(p);
        vec2 u = fract_vec2(p);
        
        f64 a = rand(ip);
        f64 b = rand(ip + vec2{1.0, 0.0});
        f64 c = rand(ip + vec2{0.0, 1.0});
        f64 d = rand(ip + vec2{1.0, 1.0});
        
        vec2 smooth = u * u * (vec2{3.0, 3.0} - 2.0 * u);
        return mix(mix(a, b, smooth.x), mix(c, d, smooth.x), smooth.y);
    }

    inline f64 circularNoise(vec2 uv, f64 density, f64 seed) {
        vec2 center = uv - vec2{0.5, 0.5};
        f64 radius = length(center) * density;
        f64 angle = abs(atan2_vec2(center));
        
        if (uv.y > 0.5) {
            angle += sin(angle) * 2.0;
        }

        vec2 seedOffset = {seed * 100.0, seed * 100.0};
        vec2 polarCoord = vec2{radius, angle} + seedOffset;

        f64 n = 0.0;
        n += noise(polarCoord) * 0.7;
        n += noise(polarCoord * 2.0) * 0.3;
        n += noise(polarCoord * 4.0) * 0.1;

        return n;
    }
}

inline void GetMilthmHitEffectPixel(f64 seed, f64 t, f64 x, f64 y, f64* a) {
    using namespace ShaderUtils;

    f64 n = circularNoise({x, y}, 50.0, seed);
    *a = (n < t) ? 0.0 : 1.0;
}

void GetPixelChannel(Texture* tex, i64 x, i64 y, i64 channel, f64* res) {
    *res = tex->buffer[x * tex->height * 4 + y * 4 + channel];
}

Texture* CreateMilthmHitEffectTexture(Texture* mask, f64 seed, f64 t, f64 r, f64 g, f64 b) {
    if (!mask->enableAlpha) return nullptr;

    Texture* tex = new Texture();
    tex->width = mask->width;
    tex->height = mask->height;
    tex->enableAlpha = true;
    tex->buffer = new f64[mask->width * mask->height * 4];

    for (i64 i = 0; i < mask->width; ++i) {
        for (i64 j = 0; j < mask->height; ++j) {
            f64 a;
            GetMilthmHitEffectPixel(seed, t, (f64)i / mask->width, (f64)j / mask->height, &a);
            f64 mask_a;
            GetPixelChannel(mask, i, j, TEXTURE_CHANNEL_A, &mask_a);
            tex->buffer[i * mask->height * 4 + j * 4 + 0] = r;
            tex->buffer[i * mask->height * 4 + j * 4 + 1] = g;
            tex->buffer[i * mask->height * 4 + j * 4 + 2] = b;
            tex->buffer[i * mask->height * 4 + j * 4 + 3] = a * mask_a;
        }
    }

    return tex;
}
