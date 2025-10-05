#define i128 long long
#define i64 long
#define i32 int
#define i16 short
#define f128 long double
#define f64 double
#define f32 float
#define iu8 unsigned char
#define LIB_NATIVE_CPU_RENDERER_VERSION 1

#include <cmath>
#include <stack>
#include <cstring>
#include <cstdio>

extern "C" {
    #include <libavcodec/avcodec.h>
    #include <libavformat/avformat.h>
    #include <libavutil/imgutils.h>
    #include <libswscale/swscale.h>
}

struct RenderContextState {
    f64 transformMatrix[6];
    f64 colorTransform[4];
};

struct RenderContext {
    i64 width;
    i64 height;
    bool enableAlpha;
    f64 *buffer;

    f64 transformMatrix[6];
    f64 colorTransform[4];

    std::stack<RenderContextState> stateStack;
};

struct Texture {
    i64 width;
    i64 height;
    bool enableAlpha;
    f64 *buffer;
};

struct VideoCap {
    i64 width;
    i64 height;
    f64 frameRate;

    AVFormatContext* formatCtx;
    AVCodecContext* codecCtx;
    AVStream* stream;
    AVFrame* frame;
    AVPacket* packet;
    SwsContext* swsCtx;
    i32 frameIndex;

    bool hasAudio;
    AVStream* aStream;
    AVCodecContext* aCodecCtx;
    i64 audioPts;
};

struct AudioClip {
    i64 sampleRate;
    i64 channels;
    i64 numFrames;

    f64 *buffer;
};

struct WapperedBytes {
    iu8 *data;
    i64 size;
};

extern "C" {
    i64 GetBufferSize(RenderContext* ctx);
    RenderContext* CreateRenderContext(i64 width, i64 height, bool enableAlpha);
    void DestroyRenderContext(RenderContext* ctx);
    VideoCap* CreateVideoCap(i64 width, i64 height, f64 frameRate);
    bool InitializeVideoCap(VideoCap* cap, const char* path, bool hasAudio, AudioClip* aClip, i64 aBitRate);
    void DestroyVideoCap(VideoCap* cap);
    void PutRendererContextFrame(VideoCap* cap, RenderContext* ctx);
    void ReleaseVideoCap(VideoCap* cap);
    void SaveContextState(RenderContext* ctx);
    bool RestoreContextState(RenderContext* ctx);
    void GetBuffer(RenderContext* ctx, f64 *buffer);
    void GetBufferAsUInt8(RenderContext* ctx, iu8 *buffer);
    Texture* CreateTexture(i64 width, i64 height, bool enableAlpha, f64 *buffer);
    Texture* CreateTextureUInt8(i64 width, i64 height, bool enableAlpha, iu8 *buffer);
    void DestroyTexture(Texture* tex);
    Texture* CreateTextureFromRenderContext(RenderContext* ctx);
    void SetTransform(RenderContext* ctx, f64 a, f64 b, f64 c, f64 d, f64 e, f64 f);
    void ApplyTransform(RenderContext* ctx, f64 a, f64 b, f64 c, f64 d, f64 e, f64 f);
    void Scale(RenderContext* ctx, f64 sx, f64 sy);
    void Translate(RenderContext* ctx, f64 tx, f64 ty);
    void Rotate(RenderContext* ctx, f64 angle);
    void TransformPoint(RenderContext* ctx, f64 x, f64 y, f64 *out_x, f64 *out_y);
    void GetTransform(RenderContext* ctx, f64 out_matrix[6]);
    void GetInverseTransform(RenderContext* ctx, f64 out_matrix[6]);
    bool SetPixel(RenderContext* ctx, i64 x, i64 y, f64 r, f64 g, f64 b, f64 a);
    bool ApplyPixel(RenderContext* ctx, i64 x, i64 y, f64 r, f64 g, f64 b, f64 a);
    void SetColorTransform(RenderContext* ctx, f64 r, f64 g, f64 b, f64 a);
    void ApplyColorTransform(RenderContext* ctx, f64 r, f64 g, f64 b, f64 a);
    void SetColor(RenderContext* ctx, f64 r, f64 g, f64 b, f64 a);
    void GetColor(RenderContext* ctx, f64 x, f64 y, f64 *out_r, f64 *out_g, f64 *out_b, f64 *out_a);
    void FillColor(RenderContext* ctx, f64 r, f64 g, f64 b, f64 a);
    void DrawTexture(RenderContext* ctx, Texture* tex, f64 x, f64 y, f64 width, f64 height);
    void DrawRect(RenderContext* ctx, f64 x, f64 y, f64 width, f64 height, f64 r, f64 g, f64 b, f64 a);
    void DrawLine(RenderContext* ctx, f64 x1, f64 y1, f64 x2, f64 y2, f64 width, f64 r, f64 g, f64 b, f64 a);
    void DrawCircle(RenderContext* ctx, f64 x, f64 y, f64 radius, f64 r, f64 g, f64 b, f64 a);
    Texture* ResampleTexture(Texture* tex, i64 width, i64 height);
    i64 GetTextureWidth(Texture* tex);
    i64 GetTextureHeight(Texture* tex);
    bool GetTextureEnableAlpha(Texture* tex);
    i64 GetAudioClipBufferSizeFromData(i64 numFrames, i64 channels);
    i64 GetAudioClipBufferSize(AudioClip* clip);
    AudioClip* CreateAudioClipFromBuffer(i64 sampleRate, i64 channels, i64 numFrames, f64 *buffer);
    AudioClip* CreateAudioClipFromInt16Buffer(i64 sampleRate, i64 channels, i64 numFrames, i16 *buffer);
    AudioClip* CreateSilentAudioClip(i64 sampleRate, i64 channels, i64 numFrames);
    void DestroyAudioClip(AudioClip* clip);
    AudioClip* CloneAudioClip(AudioClip* clip);
    void ApplyResampleAudioClip(AudioClip* clip, i64 sampleRate, i64 channels);
    void ResampleAudioClipLike(AudioClip* clip, AudioClip* like);
    i64 OverlayAudioClip(AudioClip* target, AudioClip* source, i64 startFrame, bool autoResample);
    i64 OverlayAudioClipSecond(AudioClip* target, AudioClip* source, f64 startSecond, bool autoResample);
    WapperedBytes* SaveAudioClipAsWav(AudioClip* clip);
    i64 GetAudioClipSampleRate(AudioClip* clip);
    i64 GetAudioClipChannels(AudioClip* clip);
    i64 GetAudioClipNumFrames(AudioClip* clip);
    f64 GetAudioClipDuration(AudioClip* clip);
    iu8* GetWapperedBytesDataPtr(WapperedBytes* bytes);
    i64 GetWapperedBytesDataSize(WapperedBytes* bytes);
    void ApplyVolumeGain(AudioClip* clip, f64 gain);
    bool PutAudioIntoVideoCap(VideoCap* vCap, AudioClip* aClip, i64 bitRate);
    i64 GetVersion();
    void ApplyCutAudioClip(AudioClip* clip, i64 startFrame, i64 endFrame);
    void ApplySpeedAudioClip(AudioClip* clip, f64 speed);
    void DrawVerticalGrd(RenderContext* ctx, f64 x, f64 y, f64 width, f64 height, f64 top_r, f64 top_g, f64 top_b, f64 top_a, f64 bottom_r, f64 bottom_g, f64 bottom_b, f64 bottom_a);
    void DrawSplittedTexture(RenderContext* ctx, Texture* tex, f64 x, f64 y, f64 width, f64 height, f64 uStart, f64 uEnd, f64 vStart, f64 vEnd);
    Texture* CreateTextureFromRenderContextShared(RenderContext* ctx);
    void ResizeRenderContext(RenderContext* ctx, i64 width, i64 height);
}
