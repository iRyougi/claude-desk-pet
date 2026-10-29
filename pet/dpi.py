"""DPI：让程序按显示器感知缩放，并查某个屏幕点所在显示器的缩放比例。

enable() 要在创建任何窗口、导入 winapi 之前调用，窗口坐标才是真实像素。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
PER_MONITOR_AWARE_V2 = -4


def enable() -> str:
    """尽量开到"按显示器感知 V2"；老系统依次退回。返回最后生效的级别。"""
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(PER_MONITOR_AWARE_V2)):
            return 'per-monitor-v2'
    except (AttributeError, OSError):
        pass
    for level, name in ((2, 'per-monitor'), (1, 'system')):
        try:
            if ctypes.windll.shcore.SetProcessDpiAwareness(level) == 0:
                return name
        except (AttributeError, OSError):
            pass
    return 'unaware'


def scale_of_dpi(value: int) -> float:
    """96 DPI 是 100%。拿到的值不对就当 100%。"""
    return value / 96 if value > 0 else 1.0


def scale_at(x: int, y: int) -> float:
    """屏幕上 (x, y) 所在（或最近的）显示器的缩放比例；系统接口失败时当作 100%。"""
    try:
        user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
        user32.MonitorFromPoint.restype = wt.HANDLE
        shcore = ctypes.windll.shcore
        shcore.GetDpiForMonitor.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT)]
        monitor = user32.MonitorFromPoint(wt.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
        dx, dy = wt.UINT(), wt.UINT()
        if monitor and shcore.GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(dx), ctypes.byref(dy)) == 0:
            return scale_of_dpi(dx.value)
    except (AttributeError, OSError):
        pass
    return 1.0
