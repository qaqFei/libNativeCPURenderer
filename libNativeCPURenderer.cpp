#define i64 long long
#define f64 double
#define iu8 unsigned char
#define export extern "C"

#include <cmath>

struct RenderContext {
    i64 width;
    i64 height;
    bool enableAlpha;
    f64 transformMatrix[6];
    f64 *buffer;

    f64 colorTransform[4];
};

struct Texture {
    i64 width;
    i64 height;
    bool enableAlpha;
    f64 *buffer;
};

export i64 GetBufferSize(RenderContext* ctx) {
    return ctx->width * ctx->height * (ctx->enableAlpha ? 4 : 3);
}

export RenderContext* CreateRenderContext(
    i64 width, i64 height,
    bool enableAlpha
) {
    RenderContext* ctx = new RenderContext();
    ctx->width = width;
    ctx->height = height;
    ctx->enableAlpha = enableAlpha;
    ctx->transformMatrix[0] = 1;
    ctx->transformMatrix[1] = 0;
    ctx->transformMatrix[2] = 0;
    ctx->transformMatrix[3] = 0;
    ctx->transformMatrix[4] = 1;
    ctx->transformMatrix[5] = 0;
    ctx->buffer = new f64[GetBufferSize(ctx)];
    ctx->colorTransform[0] = 1;
    ctx->colorTransform[1] = 1;
    ctx->colorTransform[2] = 1;
    ctx->colorTransform[3] = 1;

    return ctx;
}

export void DestroyRenderContext(RenderContext* ctx) {
    delete[] ctx->buffer;
    delete ctx;
}

export void GetBufferAsUInt8(RenderContext* ctx, iu8 *buffer) {
    i64 size = GetBufferSize(ctx);
    for (i64 i = 0; i < size; ++i) {
        buffer[i] = (iu8)(ctx->buffer[i] * 255);
    }
}

export Texture* CreateTexture(
    i64 width, i64 height,
    bool enableAlpha,
    f64 *buffer
) {
    Texture* tex = new Texture();
    tex->width = width;
    tex->height = height;
    tex->enableAlpha = enableAlpha;
    tex->buffer = buffer;
    
    return tex;
}

export void DestroyTexture(Texture* tex) {
    delete[] tex->buffer;
    delete tex;
}

export void ApplyTransform(
    RenderContext* ctx,
    f64 matrix[6]
) {
    f64 a = matrix[0];
    f64 b = matrix[1];
    f64 c = matrix[2];
    f64 d = matrix[3];
    f64 e = matrix[4];
    f64 f = matrix[5];

    f64 m0 = ctx->transformMatrix[0] * a + ctx->transformMatrix[2] * b;
    f64 m1 = ctx->transformMatrix[1] * a + ctx->transformMatrix[3] * b;
    f64 m2 = ctx->transformMatrix[0] * c + ctx->transformMatrix[2] * d;
    f64 m3 = ctx->transformMatrix[1] * c + ctx->transformMatrix[3] * d;
    f64 m4 = ctx->transformMatrix[0] * e + ctx->transformMatrix[2] * f + ctx->transformMatrix[4];
    f64 m5 = ctx->transformMatrix[1] * e + ctx->transformMatrix[3] * f + ctx->transformMatrix[5];

    ctx->transformMatrix[0] = m0;
    ctx->transformMatrix[1] = m1;
    ctx->transformMatrix[2] = m2;
    ctx->transformMatrix[3] = m3;
    ctx->transformMatrix[4] = m4;
    ctx->transformMatrix[5] = m5;
}

export void Scale(
    RenderContext* ctx,
    f64 sx, f64 sy
) {
    f64 m[6] = {sx, 0, 0, sy, 0, 0};
    ApplyTransform(ctx, m);
}

export void Translate(
    RenderContext* ctx,
    f64 tx, f64 ty
) {
    f64 m[6] = {1, 0, 0, 1, tx, ty};
    ApplyTransform(ctx, m);
}

export void Rotate(
    RenderContext* ctx,
    f64 angle
) {
    f64 s = sin(angle);
    f64 c = cos(angle);
    f64 m[6] = {c, s, -s, c, 0, 0};
    ApplyTransform(ctx, m);
}

export void TransformPoint(
    RenderContext* ctx,
    f64 x, f64 y,
    f64 *out_x, f64 *out_y
) {
    *out_x = ctx->transformMatrix[0] * x + ctx->transformMatrix[2] * y + ctx->transformMatrix[4];
    *out_y = ctx->transformMatrix[1] * x + ctx->transformMatrix[3] * y + ctx->transformMatrix[5];
}

export void GetInverseTransform(
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

export bool ApplyPixel(
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

    i64 index = y * ctx->width * 4 + x * 4;

    r = ctx->buffer[index + 0] * (1 - a) + r * a;
    g = ctx->buffer[index + 1] * (1 - a) + g * a;
    b = ctx->buffer[index + 2] * (1 - a) + b * a;
    a = ctx->buffer[index + 3] * (1 - a) + a * a;

    ctx->buffer[index + 0] = r;
    ctx->buffer[index + 1] = g;
    ctx->buffer[index + 2] = b;
    ctx->buffer[index + 3] = a;

    return true;
}

export void InterpolateColorFromBuffer(
    f64 *buffer, i64 width, i64 height,
    f64 x, f64 y,
    f64 *out_r, f64 *out_g, f64 *out_b, f64 *out_a
) {
    if (x < 0) x = 0;
    if (x >= width) x = width - 1;
    if (y < 0) y = 0;
    if (y >= height) y = height - 1;

    i64 ix = (i64)x;
    i64 iy = (i64)y;
    i64 nx = ix + 1;
    i64 ny = iy + 1;

    i64 index0 = iy * width * 4 + ix * 4;
    f64 r0 = buffer[index0 + 0];
    f64 g0 = buffer[index0 + 1];
    f64 b0 = buffer[index0 + 2];
    f64 a0 = buffer[index0 + 3];

    i64 index1 = iy * width * 4 + nx * 4;
    f64 r1 = buffer[index1 + 0];
    f64 g1 = buffer[index1 + 1];
    f64 b1 = buffer[index1 + 2];
    f64 a1 = buffer[index1 + 3];

    i64 index2 = ny * width * 4 + ix * 4;
    f64 r2 = buffer[index2 + 0];
    f64 g2 = buffer[index2 + 1];
    f64 b2 = buffer[index2 + 2];
    f64 a2 = buffer[index2 + 3];

    i64 index3 = ny * width * 4 + nx * 4;
    f64 r3 = buffer[index3 + 0];
    f64 g3 = buffer[index3 + 1];
    f64 b3 = buffer[index3 + 2];
    f64 a3 = buffer[index3 + 3];

    f64 u = x - ix;
    f64 v = y - iy;

    f64 r = r0 * (1 - u) * (1 - v) + r1 * u * (1 - v) + r2 * (1 - u) * v + r3 * u * v;
    f64 g = g0 * (1 - u) * (1 - v) + g1 * u * (1 - v) + g2 * (1 - u) * v + g3 * u * v;
    f64 b = b0 * (1 - u) * (1 - v) + b1 * u * (1 - v) + b2 * (1 - u) * v + b3 * u * v;
    f64 a = a0 * (1 - u) * (1 - v) + a1 * u * (1 - v) + a2 * (1 - u) * v + a3 * u * v;

    *out_r = r;
    *out_g = g;
    *out_b = b;
    *out_a = a;
}

export void FillColor(
    RenderContext* ctx,
    f64 r, f64 g, f64 b, f64 a
) {
    for (i64 i = 0; i < ctx->width; ++i) {
        for (i64 j = 0; j < ctx->height; ++j) {
            ApplyPixel(ctx, i, j, r, g, b, a);
        }
    }
}

export void DrawTexture(
    RenderContext* ctx,
    Texture* tex,
    f64 x, f64 y,
    f64 width, f64 height
) {
    f64 inv[6];
    GetInverseTransform(ctx, inv);

    for (i64 i = 0; i < width; ++i) {
        for (i64 j = 0; j < height; ++j) {
            f64 invX, invY;
            TransformPoint(ctx, i, j, &invX, &invY);

            if (invX < x) continue;
            if (invX > x + width) continue;
            if (invY < y) continue;
            if (invY > y + height) continue;

            f64 u = invX - x;
            f64 v = invY - y;

            f64 r, g, b, a;
            InterpolateColorFromBuffer(tex->buffer, tex->width, tex->height, u, v, &r, &g, &b, &a);
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

}

void DrawRect(
    RenderContext* ctx,
    f64 x, f64 y,
    f64 width, f64 height,
    f64 r, f64 g, f64 b, f64 a
) {

}