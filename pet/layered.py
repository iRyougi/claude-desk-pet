"""分层窗口：把一张带透明度的图直接交给系统显示（UpdateLayeredWindow），边缘的半透明、抗锯齿都保留。

只负责"内容"：窗口的位置和大小仍由 tk 的 geometry() 决定，这里不传位置。只在 Windows 上能用。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

from PIL import Image, ImageChops

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
ULW_ALPHA = 0x2
AC_SRC_OVER = 0x0
AC_SRC_ALPHA = 0x1
DIB_RGB_COLORS = 0
BI_RGB = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG), ('biPlanes', wt.WORD),
                ('biBitCount', wt.WORD), ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG), ('biClrUsed', wt.DWORD),
                ('biClrImportant', wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wt.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [('BlendOp', ctypes.c_ubyte), ('BlendFlags', ctypes.c_ubyte),
                ('SourceConstantAlpha', ctypes.c_ubyte), ('AlphaFormat', ctypes.c_ubyte)]


user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wt.LONG
user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, wt.LONG]
user32.SetWindowLongW.restype = wt.LONG
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
                                       ctypes.POINTER(wt.POINT), wt.COLORREF, ctypes.POINTER(BLENDFUNCTION),
                                       wt.DWORD]
user32.UpdateLayeredWindow.restype = wt.BOOL
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]


def premultiplied_bgra(image: Image.Image) -> bytes:
    """UpdateLayeredWindow 要的像素格式：BGRA 顺序，颜色已经乘过透明度。"""
    r, g, b, a = image.convert('RGBA').split()
    return Image.merge('RGBA', (ImageChops.multiply(b, a), ImageChops.multiply(g, a),
                                ImageChops.multiply(r, a), a)).tobytes()


class LayeredWindow:
    """一个 tk 顶层窗口的"画布"。hwnd 是外层窗口：GetParent(root.winfo_id())。"""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
        self._dc = gdi32.CreateCompatibleDC(None)
        self._bitmap = None
        self._old = None
        self._bits = ctypes.c_void_p()
        self._size = None

    def _ensure(self, w: int, h: int) -> None:
        """准备一块 w×h 的位图；尺寸没变就复用上一块。"""
        if self._size == (w, h):
            return
        self._free_bitmap()
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # 负数：从上往下存，和 PIL 的行顺序一致
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(self._dc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        if not bitmap:
            raise OSError('CreateDIBSection 失败')
        self._old = gdi32.SelectObject(self._dc, bitmap)
        self._bitmap, self._bits, self._size = bitmap, bits, (w, h)

    def _free_bitmap(self) -> None:
        if self._bitmap:
            gdi32.SelectObject(self._dc, self._old)
            gdi32.DeleteObject(self._bitmap)
        self._bitmap, self._old, self._size = None, None, None

    def show(self, image: Image.Image) -> bool:
        """把这张图显示出来。窗口大小会变成图的大小，位置不变。返回系统调用是否成功。"""
        w, h = image.size
        data = premultiplied_bgra(image)
        self._ensure(w, h)
        ctypes.memmove(self._bits, data, len(data))
        size, src = wt.SIZE(w, h), wt.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        return bool(user32.UpdateLayeredWindow(self.hwnd, None, None, ctypes.byref(size), self._dc,
                                               ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA))

    def close(self) -> None:
        self._free_bitmap()
        if self._dc:
            gdi32.DeleteDC(self._dc)
            self._dc = None
