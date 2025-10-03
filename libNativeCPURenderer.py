import ctypes

lib = ctypes.CDLL("./libNativeCPURenderer.so")

class RenderContext:
    def __init__(self, width: int, height: int, enableAlpha: bool):
        self.width = width
        self.height = height
        self.enableAlpha = enableAlpha
        
        CreateRenderContext = lib.CreateRenderContext
        CreateRenderContext.argtypes = (ctypes.c_longlong, ctypes.c_longlong, ctypes.c_bool)
        CreateRenderContext.restype = ctypes.c_void_p

        self._ptr = lib.CreateRenderContext(width, height, enableAlpha)
        print(f"CreateRenderContext: {self._ptr}")
    
    def __del__(self):
        DestroyRenderContext = lib.DestroyRenderContext
        DestroyRenderContext.argtypes = (ctypes.c_void_p,)
        DestroyRenderContext.restype = None
        DestroyRenderContext(self._ptr)
        self._ptr = 0

    def get_buffer_size(self):
        GetBufferSize = lib.GetBufferSize
        GetBufferSize.argtypes = (ctypes.c_void_p, )
        GetBufferSize.restype = ctypes.c_longlong

        return GetBufferSize(self._ptr)
    
    def get_buffer(self):
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
    
    def as_pilimg(self):
        from PIL import Image
        return Image.frombytes("RGBA", (self.width, self.height), self.get_buffer())

if __name__ == "__main__":
    ctx = RenderContext(128, 128, True)
    ctx.fill_color(0.5, 0.5, 0.6, 0.5)
    ctx.as_pilimg().save("./test.png")
