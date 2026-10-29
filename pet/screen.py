"""全屏判断、层级选择。纯函数，Win32 取数在 winapi.py。"""
from __future__ import annotations

from motion import Motion, Rect

DESKTOP_CLASSES = frozenset({'Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'})


def is_fullscreen(rect: Rect, cls: str, monitor: Rect) -> bool:
    """前台窗口是不是盖满了这块显示器（连任务栏也盖住）。桌面本身不算。"""
    if cls in DESKTOP_CLASSES:
        return False
    return (rect.left <= monitor.left and rect.top <= monitor.top
            and rect.right >= monitor.right and rect.bottom >= monitor.bottom)


def choose_z(motion: Motion | None, remind: int, speaking: bool):
    """她该在哪一层：'top' 置顶；否则返回她坐着的那个窗口的句柄，贴在它正上方一层（被别的窗口盖住时一起被盖住）。"""
    if motion is None or remind or speaking:
        return 'top'
    if motion.mode in ('perch', 'walk') and isinstance(motion.support, int):
        return motion.support
    return 'top'
