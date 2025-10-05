from __future__ import annotations

import ctypes
import struct
import math
import typing
import random
import queue

lib = ctypes.CDLL("./libNativeCPURenderer.so")

class Helpers:
    @staticmethod
    def get_wappered_bytes_data_ptr(bytes: int):
        GetWapperedBytesDataPtr = lib.GetWapperedBytesDataPtr
        GetWapperedBytesDataPtr.argtypes = (ctypes.c_void_p, )
        GetWapperedBytesDataPtr.restype = ctypes.c_void_p

        return GetWapperedBytesDataPtr(bytes)
    
    @staticmethod
    def get_wappered_bytes_data_size(bytes: int):
        GetWapperedBytesDataSize = lib.GetWapperedBytesDataSize
        GetWapperedBytesDataSize.argtypes = (ctypes.c_void_p, )
        GetWapperedBytesDataSize.restype = ctypes.c_long

        return GetWapperedBytesDataSize(bytes)
    
    @staticmethod
    def wappered_bytes_to_python(bytes: int):
        ptr = Helpers.get_wappered_bytes_data_ptr(bytes)
        size = Helpers.get_wappered_bytes_data_size(bytes)
        return ctypes.string_at(ptr, size)
    
    @staticmethod
    def create_milthm_hit_effect_textures(mask: Texture, n: int):
        CreateMilthmHitEffectTexture = lib.CreateMilthmHitEffectTexture
        CreateMilthmHitEffectTexture.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        CreateMilthmHitEffectTexture.restype = ctypes.c_void_p

        seed = random.random()

        texs = []
        for i in range(n):
            p = i / (n - 1)
            texs.append(PtrCreatedTexture(CreateMilthmHitEffectTexture(
                mask._ptr, seed, p, 0x96 / 0xff, 0x90 / 0xff, 0xfd / 0xff
            )))
        
        return texs

class RenderContext:
    def __init__(self, width: int, height: int, enable_alpha: bool):
        self.width = width
        self.height = height
        self.enable_alpha = enable_alpha
        
        CreateRenderContext = lib.CreateRenderContext
        CreateRenderContext.argtypes = (ctypes.c_long, ctypes.c_long, ctypes.c_bool)
        CreateRenderContext.restype = ctypes.c_void_p

        self._ptr = lib.CreateRenderContext(width, height, enable_alpha)
        self._can_release = True
    
    def __del__(self):
        if not self._can_release:
            return

        DestroyRenderContext = lib.DestroyRenderContext
        DestroyRenderContext.argtypes = (ctypes.c_void_p,)
        DestroyRenderContext.restype = None
        DestroyRenderContext(self._ptr)
        self._ptr = 0

    def get_buffer_size(self):
        GetBufferSize = lib.GetBufferSize
        GetBufferSize.argtypes = (ctypes.c_void_p, )
        GetBufferSize.restype = ctypes.c_long

        return GetBufferSize(self._ptr)

    def get_buffer(self):
        GetBuffer = lib.GetBuffer
        GetBuffer.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        GetBuffer.restype = None

        buffer_size = self.get_buffer_size()
        buffer = (ctypes.c_double * buffer_size)()
        GetBuffer(self._ptr, ctypes.byref(buffer))
        return list(buffer)
    
    def get_buffer_as_uint8(self):
        GetBufferAsUInt8 = lib.GetBufferAsUInt8
        GetBufferAsUInt8.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        GetBufferAsUInt8.restype = None

        buffer = bytearray(self.get_buffer_size())
        GetBufferAsUInt8(self._ptr, (ctypes.c_byte * len(buffer)).from_buffer(buffer))
        return buffer
    
    def fill_color(self, r: float, g: float, b: float, a: float):
        FillColor = lib.FillColor
        FillColor.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        FillColor.restype = None

        FillColor(self._ptr, r, g, b, a)
    
    def draw_texture(self, tex: Texture, x: float, y: float, w: float, h: float):
        DrawTexture = lib.DrawTexture
        DrawTexture.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        DrawTexture.restype = None

        DrawTexture(self._ptr, tex._ptr, x, y, w, h)
    
    def resize(self, width: int, height: int):
        ResizeRenderContext = lib.ResizeRenderContext
        ResizeRenderContext.argtypes = (ctypes.c_void_p, ctypes.c_long, ctypes.c_long)
        ResizeRenderContext.restype = None
        
        ResizeRenderContext(self._ptr, width, height)
        self.width = width
        self.height = height
    
    def draw_splitted_texture(self, tex: Texture, x: float, y: float, width: float, height: flaot, u_start: float, u_end: float, v_start: float, v_end: float):
        DrawSplittedTexture = lib.DrawSplittedTexture
        DrawSplittedTexture.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        DrawSplittedTexture.restype = None

        DrawSplittedTexture(self._ptr, tex._ptr, x, y, width, height, u_start, u_end, v_start, v_end)

    def apply_transform(self, a: float, b: float, c: float, d: float, e: float, f: float):
        ApplyTransform = lib.ApplyTransform
        ApplyTransform.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        ApplyTransform.restype = None
        
        ApplyTransform(self._ptr, a, b, c, d, e, f)
    
    def scale(self, sx: float, sy: float):
        Scale = lib.Scale
        Scale.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double)
        Scale.restype = None
        
        Scale(self._ptr, sx, sy)
    
    def rotate(self, angle: float):
        Rotate = lib.Rotate
        Rotate.argtypes = (ctypes.c_void_p, ctypes.c_double)
        Rotate.restype = None
        
        Rotate(self._ptr, angle)
    
    def translate(self, tx: float, ty: float):
        Translate = lib.Translate
        Translate.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double)
        Translate.restype = None
        
        Translate(self._ptr, tx, ty)
    
    def rotate_degree(self, deg: float):
        self.rotate(deg * math.pi / 180)
    
    def save_state(self):
        SaveContextState = lib.SaveContextState
        SaveContextState.argtypes = (ctypes.c_void_p,)
        SaveContextState.restype = None

        SaveContextState(self._ptr)
    
    def restore_state(self):
        RestoreContextState = lib.RestoreContextState
        RestoreContextState.argtypes = (ctypes.c_void_p,)
        RestoreContextState.restype = None

        RestoreContextState(self._ptr)
    
    def draw_line(self, x0: float, y0: float, x1: float, y1: float, width: float, r: float, g: float, b: float, a: float):
        DrawLine = lib.DrawLine
        DrawLine.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        DrawLine.restype = None

        DrawLine(self._ptr, x0, y0, x1, y1, width, r, g, b, a)
    
    def draw_rect(self, x: float, y: float, width: float, height: float, r: float, g: float, b: float, a: float):
        DrawRect = lib.DrawRect
        DrawRect.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        DrawRect.restype = None

        DrawRect(self._ptr, x, y, width, height, r, g, b, a)
    
    def get_transform(self):
        GetTransform = lib.GetTransform
        GetTransform.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        GetTransform.restype = None

        out = (ctypes.c_double * 6)()
        GetTransform(self._ptr, ctypes.byref(out))
        return tuple(out)
    
    def get_inverse_transform(self):
        GetInverseTransform = lib.GetInverseTransform
        GetInverseTransform.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        GetInverseTransform.restype = None
        
        out = (ctypes.c_double * 6)()
        GetInverseTransform(self._ptr, ctypes.byref(out))
        return tuple(out)
    
    def apply_pixel(self, x: int, y: int, r: float, g: float, b: float, a: float):
        ApplyPixel = lib.ApplyPixel
        ApplyPixel.argtypes = (ctypes.c_void_p, ctypes.c_long, ctypes.c_long, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        ApplyPixel.restype = None

        ApplyPixel(self._ptr, x, y, r, g, b, a)
    
    def draw_circle(self, x: float, y: float, radius: float, r: float, g: float, b: float, a: float):
        DrawCircle = lib.DrawCircle
        DrawCircle.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        DrawCircle.restype = None

        DrawCircle(self._ptr, x, y, radius, r, g, b, a)
    
    def set_transform(self, a: float, b: float, c: float, d: float, e: float, f: float):
        SetTransform = lib.SetTransform
        SetTransform.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        SetTransform.restype = None

        SetTransform(self._ptr, a, b, c, d, e, f)
    
    def set_color_transform(self, r: float, g: float, b: float, a: float):
        SetColorTransform = lib.SetColorTransform
        SetColorTransform.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        SetColorTransform.restype = None

        SetColorTransform(self._ptr, r, g, b, a)
    
    def apply_color_transform(self, r: float, g: float, b: float, a: float):
        ApplyColorTransform = lib.ApplyColorTransform
        ApplyColorTransform.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        ApplyColorTransform.restype = None

        ApplyColorTransform(self._ptr, r, g, b, a)
    
    def set_pixel(self, x: int, y: int, r: float, g: float, b: float, a: float):
        SetPixel = lib.SetPixel
        SetPixel.argtypes = (ctypes.c_void_p, ctypes.c_long, ctypes.c_long, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        SetPixel.restype = None

        SetPixel(self._ptr, x, y, r, g, b, a)

    def set_color(self, r: float, g: float, b: float, a: float):
        SetColor = lib.SetColor
        SetColor.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        SetColor.restype = None

        SetColor(self._ptr, r, g, b, a)
    
    def get_color(self, x: int, y: int):
        GetColor = lib.GetColor
        GetColor.argtypes = (ctypes.c_void_p, ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        GetColor.restype = None

        out = (ctypes.c_double(), ctypes.c_double(), ctypes.c_double(), ctypes.c_double())
        GetColor(self._ptr, x, y, ctypes.byref(out[0]), ctypes.byref(out[1]), ctypes.byref(out[2]), ctypes.byref(out[3]))
        return tuple(map(lambda x: x.value, out))
    
    def draw_vertical_grd(self, x: float, y: float, width: float, height: float, top_r: float, top_g: float, top_b: float, top_a: float, bottom_r: float, bottom_g: float, bottom_b: float, bottom_a: float):
        DrawVerticalGrd = lib.DrawVerticalGrd
        DrawVerticalGrd.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double)
        DrawVerticalGrd.restype = None

        DrawVerticalGrd(self._ptr, x, y, width, height, top_r, top_g, top_b, top_a, bottom_r, bottom_g, bottom_b, bottom_a)
    
    def draw_vertical_mut_grd(self, x: float, y: float, width: float, height: float, steps: list[tuple[tuple[float, float, float, float, float]]]):
        for i, (p, s) in enumerate(steps):
            if i == len(steps) - 1:
                break

            np, ns = steps[i + 1]
            ty = y + height * p
            theight = height * (np - p)
            self.draw_vertical_grd(x, ty, width, theight, s[0], s[1], s[2], s[3], ns[0], ns[1], ns[2], ns[3])

    def as_texure(self):
        CreateTextureFromRenderContext = lib.CreateTextureFromRenderContext
        CreateTextureFromRenderContext.argtypes = (ctypes.c_void_p,)
        CreateTextureFromRenderContext.restype = ctypes.c_void_p

        return PtrCreatedTexture(CreateTextureFromRenderContext(self._ptr))
    
    def as_texture_shared(self):
        CreateTextureFromRenderContextShared = lib.CreateTextureFromRenderContextShared
        CreateTextureFromRenderContextShared.argtypes = (ctypes.c_void_p,)
        CreateTextureFromRenderContextShared.restype = ctypes.c_void_p

        res = PtrCreatedTexture(CreateTextureFromRenderContextShared(self._ptr))
        res._can_release = False
        return res
    
    def as_pilimg(self):
        from PIL import Image
        return Image.frombytes("RGBA", (self.width, self.height), self.get_buffer_as_uint8())

class MultiThreadedRenderContextPreparer(RenderContext):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frames = []
        self.end_of_frame()

        proxy_methods = (
            
        )
    
    def end_of_frame(self):
        self.frames.append(queue.Queue())

class Texture:
    def __init__(self, width: int, height: int, enableAlpha: bool, data: typing.ByteString, is_uint8: bool = True):
        if width * height * (3 if not enableAlpha else 4) * (1 if is_uint8 else 8) != len(data):
            raise ValueError("data size not match")

        self.width = width
        self.height = height
        self.enableAlpha = enableAlpha
        
        data = bytearray(data)

        if is_uint8:
            CreateTextureUInt8 = lib.CreateTextureUInt8
            CreateTextureUInt8.argtypes = (ctypes.c_long, ctypes.c_long, ctypes.c_bool, ctypes.c_void_p)
            CreateTextureUInt8.restype = ctypes.c_void_p

            self._ptr = CreateTextureUInt8(width, height, enableAlpha, (ctypes.c_byte * len(data)).from_buffer(data))
        else:
            CreateTexture = lib.CreateTexture
            CreateTexture.argtypes = (ctypes.c_long, ctypes.c_long, ctypes.c_bool, ctypes.c_void_p)
            CreateTexture.restype = ctypes.c_void_p

            self._ptr = CreateTexture(width, height, enableAlpha, (ctypes.c_double * len(data) // 8).from_buffer(data))
        
    def __del__(self):
        DestroyTexture = lib.DestroyTexture
        DestroyTexture.argtypes = (ctypes.c_void_p,)
        DestroyTexture.restype = None

        DestroyTexture(self._ptr)
    
    def _update_props(self):
        GetTextureWidth = lib.GetTextureWidth
        GetTextureWidth.argtypes = (ctypes.c_void_p,)
        GetTextureWidth.restype = ctypes.c_long

        GetTextureHeight = lib.GetTextureHeight
        GetTextureHeight.argtypes = (ctypes.c_void_p,)
        GetTextureHeight.restype = ctypes.c_long

        GetTextureEnableAlpha = lib.GetTextureEnableAlpha
        GetTextureEnableAlpha.argtypes = (ctypes.c_void_p,)
        GetTextureEnableAlpha.restype = ctypes.c_bool

        self.width = GetTextureWidth(self._ptr)
        self.height = GetTextureHeight(self._ptr)
        self.enableAlpha = GetTextureEnableAlpha(self._ptr)
    
    def resample(self, width: int, height: int):
        ResampleTexture = lib.ResampleTexture
        ResampleTexture.argtypes = (ctypes.c_void_p, ctypes.c_long, ctypes.c_long)
        ResampleTexture.restype = ctypes.c_void_p

        new = ResampleTexture(self._ptr, width, height)
        return PtrCreatedTexture(new)
    
    @staticmethod
    def from_pilimg(img):
        from PIL import Image

        if not isinstance(img, Image.Image):
            raise TypeError("img must be a PIL.Image.Image")
        
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        
        return Texture(img.width, img.height, img.mode == "RGBA", img.tobytes())
    
class PtrCreatedTexture(Texture):
    def __init__(self, ptr: int):
        self._ptr = ptr
        self._update_props()

class VideoCap:
    def __init__(self, width: int, height: int, frame_rate: float):
        self.width = width
        self.height = height
        self.frame_rate = frame_rate

        CreateVideoCap = lib.CreateVideoCap
        CreateVideoCap.argtypes = (ctypes.c_long, ctypes.c_long, ctypes.c_double)
        CreateVideoCap.restype = ctypes.c_void_p

        self._ptr = CreateVideoCap(width, height, frame_rate)
    
    def initialize(
        self,
        path: str, hasAudio: bool = False,
        a_clip: typing.Optional[AudioClip] = None,
        a_bitrate: int = 80000
    ):
        InitializeVideoCap = lib.InitializeVideoCap
        InitializeVideoCap.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool, ctypes.c_void_p, ctypes.c_long)
        InitializeVideoCap.restype = ctypes.c_bool

        res = InitializeVideoCap(
            self._ptr, path.encode("utf-8"), hasAudio,
            a_clip._ptr if a_clip is not None else 0,
            a_bitrate
        )

        if not res:
            raise Exception("failed")
    
    def __del__(self):
        DestroyVideoCap = lib.DestroyVideoCap
        DestroyVideoCap.argtypes = (ctypes.c_void_p,)
        DestroyVideoCap.restype = None
        
        DestroyVideoCap(self._ptr)
    
    def put_renderer_context_frame(self, ctx: RenderContext):
        PutRendererContextFrame = lib.PutRendererContextFrame
        PutRendererContextFrame.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        PutRendererContextFrame.restype = None
        
        PutRendererContextFrame(self._ptr, ctx._ptr)
    
    def release(self):
        ReleaseVideoCap = lib.ReleaseVideoCap
        ReleaseVideoCap.argtypes = (ctypes.c_void_p, )
        ReleaseVideoCap.restype = None
        
        ReleaseVideoCap(self._ptr)
    
    def put_audio(self, audio: AudioClip, bit_rate: int = 80000):
        PutAudioIntoVideoCap = lib.PutAudioIntoVideoCap
        PutAudioIntoVideoCap.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)
        PutAudioIntoVideoCap.restype = ctypes.c_bool

        res = PutAudioIntoVideoCap(self._ptr, audio._ptr, bit_rate)
        if not res:
            raise Exception("failed")
        
class AudioClip:
    def __init__(self, sample_rate: int, channels: int, data: typing.Iterable[float]):
        CreateAudioClipFromBuffer = lib.CreateAudioClipFromBuffer
        CreateAudioClipFromBuffer.argtypes = (ctypes.c_long, ctypes.c_long, ctypes.c_long, c_void_p)
        CreateAudioClipFromBuffer.restype = ctypes.c_void_p

        buffer = (ctypes.c_double * len(data)).from_buffer(data)
        self._ptr = CreateAudioClipFromBuffer(sample_rate, channels, len(data), buffer)
        self._update_props()
    
    def _update_props(self):
        GetAudioClipSampleRate = lib.GetAudioClipSampleRate
        GetAudioClipSampleRate.argtypes = (ctypes.c_void_p,)
        GetAudioClipSampleRate.restype = ctypes.c_long

        GetAudioClipChannels = lib.GetAudioClipChannels
        GetAudioClipChannels.argtypes = (ctypes.c_void_p,)
        GetAudioClipChannels.restype = ctypes.c_long

        GetAudioClipNumFrames = lib.GetAudioClipNumFrames
        GetAudioClipNumFrames.argtypes = (ctypes.c_void_p,)
        GetAudioClipNumFrames.restype = ctypes.c_long

        self._sample_rate = GetAudioClipSampleRate(self._ptr)
        self._channels = GetAudioClipChannels(self._ptr)
        self._num_frames = GetAudioClipNumFrames(self._ptr)

    @staticmethod
    def from_pydub_seg(seg):
        from pydub import AudioSegment

        if not isinstance(seg, AudioSegment):
            raise TypeError("seg must be a pydub.AudioSegment")
        
        if seg.sample_width != 2:
            seg = seg.set_sample_width(2)

        data = seg.get_array_of_samples(array_type_override="h")
        return Int16CreatedAudioClip(seg.frame_rate, seg.channels, data)
    
    @staticmethod
    def slient(sample_rate: int, channels: int, num_frames: int):
        CreateSilentAudioClip = lib.CreateSilentAudioClip
        CreateSilentAudioClip.argtypes = (ctypes.c_long, ctypes.c_long, ctypes.c_long)
        CreateSilentAudioClip.restype = ctypes.c_void_p

        return PtrCreatedAudioClip(CreateSilentAudioClip(sample_rate, channels, num_frames))
    
    def clone(self):
        CloneAudioClip = lib.CloneAudioClip
        CloneAudioClip.argtypes = (ctypes.c_void_p,)
        CloneAudioClip.restype = ctypes.c_void_p

        return PtrCreatedAudioClip(CloneAudioClip(self._ptr))
    
    def resample(self, sample_rate: int, channels: int):
        ApplyResampleAudioClip = lib.ApplyResampleAudioClip
        ApplyResampleAudioClip.argtypes = (ctypes.c_void_p, ctypes.c_long, ctypes.c_long)
        ApplyResampleAudioClip.restype = None

        ApplyResampleAudioClip(self._ptr, sample_rate, channels)
    
    def resample_like(clip: AudioClip, like: AudioClip):
        ResampleAudioClipLike = lib.ResampleAudioClipLike
        ResampleAudioClipLike.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        ResampleAudioClipLike.restype = None

        ResampleAudioClipLike(clip._ptr, like._ptr)
    
    def overlay(target: AudioClip, source: AudioClip, start_time: int|float, *, time_unit: typing.Literal["frame", "second"] = "frame", auto_resample: bool = False):
        if time_unit not in ("frame", "second"):
            raise ValueError("time_unit must be 'frame' or 'second'")

        if time_unit == "frame":
            start_time = int(start_time)

        OverlayAudioClip = lib.OverlayAudioClip if time_unit == "frame" else lib.OverlayAudioClipSecond
        OverlayAudioClip.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_bool)
        OverlayAudioClip.restype = ctypes.c_long

        res = OverlayAudioClip(target._ptr, source._ptr, start_time, auto_resample)

        if res != 0:
            match res:
                case -1: raise ValueError(f"target and source must have the same sample rate")
                case -2: raise ValueError(f"target and source must have the channels")
                case _: raise ValueError(f"unknown error code: {res}")
    
    def save_as_wav(self):
        SaveAudioClipAsWav = lib.SaveAudioClipAsWav
        SaveAudioClipAsWav.argtypes = (ctypes.c_void_p, )
        SaveAudioClipAsWav.restype = ctypes.c_void_p

        wappered = SaveAudioClipAsWav(self._ptr)
        return Helpers.wappered_bytes_to_python(wappered)

    @property
    def duration(self):
        GetAudioClipDuration = lib.GetAudioClipDuration
        GetAudioClipDuration.argtypes = (ctypes.c_void_p,)
        GetAudioClipDuration.restype = ctypes.c_double

        return GetAudioClipDuration(self._ptr)
    
    def apply_volume_gain(self, gain: float):
        ApplyVolumeGain = lib.ApplyVolumeGain
        ApplyVolumeGain.argtypes = (ctypes.c_void_p, ctypes.c_double)
        ApplyVolumeGain.restype = None
        
        ApplyVolumeGain(self._ptr, gain)
    
    def cut(self, start: int|float, end: int|float, *, time_unit: typing.Literal["frame", "second"] = "frame"):
        if time_unit not in ("frame", "second"):
            raise ValueError("time_unit must be 'frame' or 'second'")
        
        if time_unit == "frame":
            start = int(start)
            end = int(end)
        else:
            start = int(start * self._sample_rate)
            end = int(end * self._sample_rate)
        
        ApplyCutAudioClip = lib.ApplyCutAudioClip
        ApplyCutAudioClip.argtypes = (ctypes.c_void_p, ctypes.c_long, ctypes.c_long)
        ApplyCutAudioClip.restype = None

        ApplyCutAudioClip(self._ptr, start, end)
    
    def apply_speed(self, speed: float):
        ApplySpeedAudioClip = lib.ApplySpeedAudioClip
        ApplySpeedAudioClip.argtypes = (ctypes.c_void_p, ctypes.c_double)
        ApplySpeedAudioClip.restype = None
        
        ApplySpeedAudioClip(self._ptr, speed)
    
    def __del__(self):
        DestroyAudioClip = lib.DestroyAudioClip
        DestroyAudioClip.argtypes = (ctypes.c_void_p,)
        DestroyAudioClip.restype = None
        
        DestroyAudioClip(self._ptr)

class Int16CreatedAudioClip(AudioClip):
    def __init__(self, sample_rate: int, channels: int, data: typing.Iterable[int]):
        CreateAudioClipFromInt16Buffer = lib.CreateAudioClipFromInt16Buffer
        CreateAudioClipFromInt16Buffer.argtypes = (ctypes.c_long, ctypes.c_long, ctypes.c_long, ctypes.c_void_p)
        CreateAudioClipFromInt16Buffer.restype = ctypes.c_void_p

        buffer = (ctypes.c_short * len(data)).from_buffer(data)
        
        self._ptr = CreateAudioClipFromInt16Buffer(sample_rate, channels, len(data) // channels, buffer)
        self._update_props()

class PtrCreatedAudioClip(AudioClip):
    def __init__(self, ptr: int):
        self._ptr = ptr
        self._update_props()

def get_version():
    GetVersion = lib.GetVersion
    GetVersion.argtypes = ()
    GetVersion.restype = ctypes.c_long

    return GetVersion()

if __name__ == "__main__":
    from PIL import Image
    import tqdm
    import math
    import json
    from pydub import AudioSegment

    ctxS = 4
    ctx = RenderContext(1024 // ctxS, 1024 // ctxS, True)
    ctx.scale(1 / ctxS, 1 / ctxS)
    cap = VideoCap(1024, 1024, 60)

    seg = AudioSegment.from_file("./../test_files/audio.ogg")
    clip = AudioClip.from_pydub_seg(seg)

    seg2 = AudioSegment.from_file("./../test_files/audio2.ogg")
    clip2 = AudioClip.from_pydub_seg(seg2)

    clip.apply_volume_gain(0.7)
    clip2.apply_volume_gain(1.1)

    data = json.load(open("./../test_files/audio_overlay_test.json", "r"))
    for i in tqdm.tqdm(data):
        clip.overlay(clip2, i, time_unit="second", auto_resample=True)

    wav = clip.save_as_wav()

    with open("./../test_files/testgen_audio.wav", "wb") as f:
        f.write(wav)

    clip.resample(44100, 2)
    cap.initialize("./../test_files/testgen_test.mp4", True, clip)
    
    piltex = Image.open("./../test_files/image.png")
    tex = Texture.from_pilimg(piltex).resample(16, 16)

    for i in tqdm.tqdm(range(60 * 120)):
        t = i / 60
        ctx.set_color(1, 1, 1, 1)
        ctx.save_state()
        ctx.apply_color_transform(t % 1, (t + 1.4) % 1, (t + 2.8) % 1, 1)
        w = 768 * (1 + math.sin(t * 2 * math.pi) / 4)
        h = 768 * (1 + math.cos(t * 3 * math.pi) / 4)
        ctx.draw_texture(tex, w * 1.5 / 2, h * 1.3 / 2, w, h)

        ctx.draw_line(w * 0.1, h * 0.1, w, h, (w + h) / 300, 0, 1, 0, 1)
        ctx.draw_circle(w * 0.3, h * 0.3, 100, 1, 1, 0, 0.4);
        ctx.draw_rect(w * 0.6, h * 0.6, w * 0.1, h * 0.1, 0, 1, 0, 0.4)
        ctx.restore_state()
        cap.put_renderer_context_frame(ctx)
    
    cap.release()
