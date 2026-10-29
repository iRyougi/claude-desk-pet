"""Win32：读取前台窗口的位置和所在显示器的工作区。只在 Windows 上能用。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

from motion import Rect, WinInfo

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

DWMWA_EXTENDED_FRAME_BOUNDS = 9   # 不含阴影的真实窗口边界
DWMWA_CLOAKED = 14                # 被系统"隐藏"的窗口（比如别的虚拟桌面上的）
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
MONITOR_DEFAULTTONEAREST = 2
SPI_GETWORKAREA = 0x30
MIN_SIZE = (160, 80)

# 桌面、任务栏、开始菜单这些不是"窗口"，她不会坐上去
SKIP_CLASSES = frozenset({
    'Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd', 'NotifyIconOverflowWindow',
    'Windows.UI.Core.CoreWindow', 'XamlExplorerHostIslandWindow', 'TopLevelWindowForOverflowXamlIsland',
})


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('rcMonitor', wt.RECT), ('rcWork', wt.RECT), ('dwFlags', wt.DWORD)]


user32.GetForegroundWindow.restype = wt.HWND
for _name in ('IsWindow', 'IsWindowVisible', 'IsIconic', 'IsZoomed', 'GetWindowRect', 'GetClassNameW',
              'GetWindowThreadProcessId', 'MonitorFromWindow'):
    getattr(user32, _name).argtypes = {
        'GetWindowRect': [wt.HWND, ctypes.POINTER(wt.RECT)],
        'GetClassNameW': [wt.HWND, wt.LPWSTR, ctypes.c_int],
        'GetWindowThreadProcessId': [wt.HWND, ctypes.POINTER(wt.DWORD)],
        'MonitorFromWindow': [wt.HWND, wt.DWORD],
    }.get(_name, [wt.HWND])
user32.MonitorFromWindow.restype = wt.HANDLE
user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]


def _rect(r: wt.RECT) -> Rect:
    return Rect(r.left, r.top, r.right, r.bottom)


def _frame(hwnd: int) -> Rect | None:
    r = wt.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
    return _rect(r)


def _cloaked(hwnd: int) -> bool:
    v = wt.DWORD()
    return dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v)) == 0 and v.value != 0


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid(hwnd: int) -> int:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def work_area_of(hwnd: int) -> Rect:
    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return _rect(info.rcWork)
    return primary_work_area()


def primary_work_area() -> Rect:
    r = wt.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
    return _rect(r)


def window_info(hwnd: int) -> WinInfo | None:
    """这个窗口现在能不能坐：还在、可见、没最小化、没被隐藏、不是工具窗口、够大。"""
    if not hwnd or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    if _cloaked(hwnd) or _class_name(hwnd) in SKIP_CLASSES:
        return None
    if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return None
    rect = _frame(hwnd)
    if rect is None or rect.width < MIN_SIZE[0] or rect.bottom - rect.top < MIN_SIZE[1]:
        return None
    return WinInfo(hwnd=int(hwnd), rect=rect, work=work_area_of(hwnd), maximized=bool(user32.IsZoomed(hwnd)))


def foreground_window(own_pid: int) -> WinInfo | None:
    """前台窗口。是她自己的窗口、桌面、任务栏之类的，返回 None（调用方继续待在原来的窗口上）。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or _pid(hwnd) == own_pid:
        return None
    return window_info(hwnd)
