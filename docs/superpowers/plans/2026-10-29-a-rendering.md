# A 画面底层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把桌宠从"抠色透明"换成逐像素透明的分层窗口，按显示器感知 DPI，气泡最多两行并自动省略。

**Architecture:** tk 窗口只负责鼠标事件和右键菜单；每帧由纯 PIL 的 `render.compose` 合成一张 RGBA 图，经 `layered.LayeredWindow.show` 调 `UpdateLayeredWindow` 显示。窗口的位置和大小仍然只由 `root.geometry()` 决定（一套坐标），`UpdateLayeredWindow` 只换内容。气泡排版是纯函数 `bubble.layout`。DPI 由 `dpi.py` 在创建窗口前开启按显示器感知，并按她脚下的显示器换算缩放。

**Tech Stack:** Python 3.14、tkinter、Pillow 12.2、ctypes（user32 / gdi32 / shcore），测试用 unittest。

**Spec:** `docs/superpowers/specs/2026-10-29-desk-pet-polish-design.md`（本计划实现其中的「A 画面底层」；E、B、C 各自另写计划）

## Global Constraints

- 只支持 Windows；不新增第三方依赖（只有 Pillow）。
- 测试命令：`python -m unittest discover -s tests`（项目没有 pytest）；测试文件用 `sys.path.insert(0, .../pet)` 导入模块，照 `tests/test_motion.py` 的写法。
- `pet/motion.py`、`pet/breaks.py` 的接口不改，原有测试必须照常通过。
- 新代码：中文注释、frozen dataclass、纯函数优先（与 `motion.py` 一致）；不改动入参对象。
- 气泡：最大宽度 260 px（100% 缩放），最多 2 行，第 2 行放不下末尾加「…」；路径从中间省略、保留文件名；有第二行小字时正文只占 1 行。
- 字体：Microsoft YaHei UI（`msyh.ttc` 的 index 1），找不到时退回 `ImageFont.load_default`。
- DPI：先试 `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`，再退 `SetProcessDpiAwareness(2)`、`(1)`；跨屏时等她落地（`perch`/`walk`）后再换缩放。
- 对设计文档的一处修正：spec A1 写的是"窗口位置由 `UpdateLayeredWindow` 给，不再调 `geometry()`"。为了保持只有一套坐标、且 `winfo_x()` 继续可用，本计划改为**位置和大小只由 `geometry()` 给，`UpdateLayeredWindow` 不传位置**。Task 6 同步修改 spec 这一句。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `pet/layered.py`（新） | 唯一碰 GDI 的地方：给窗口加 `WS_EX_LAYERED`，把 RGBA 图预乘后交给 `UpdateLayeredWindow` |
| `pet/dpi.py`（新） | 开启 DPI 感知；查某个屏幕点所在显示器的缩放 |
| `pet/bubble.py`（新） | 气泡排版：换行、省略、路径缩短。纯函数 |
| `pet/render.py`（新） | 画气泡图、合成整帧。纯 PIL |
| `pet/pet.pyw`（改） | 去掉抠色和 Canvas 绘图，改为每帧 compose + show；按显示器重建缩放 |
| `tools/spike_layered.py`（新） | 一次性验证 tk + 分层窗口能否共存 |
| `tests/test_layered.py`、`test_dpi.py`、`test_bubble.py`、`test_render.py`（新） | 对应的单元测试 |
| `README.md`、spec（改） | 文档同步 |

---

### Task 1: 分层窗口 + 可行性验证（关卡）

**Files:**
- Create: `pet/layered.py`
- Create: `pet/dpi.py`
- Create: `tools/spike_layered.py`
- Test: `tests/test_layered.py`、`tests/test_dpi.py`

**Interfaces:**
- Produces:
  - `layered.premultiplied_bgra(image: Image.Image) -> bytes`
  - `layered.LayeredWindow(hwnd: int)`，方法 `show(image: Image.Image) -> bool`、`close() -> None`
  - `dpi.enable() -> str`（返回 `'per-monitor-v2' | 'per-monitor' | 'system' | 'unaware'`）
  - `dpi.scale_of_dpi(value: int) -> float`
  - `dpi.scale_at(x: int, y: int) -> float`

- [ ] **Step 1: 写失败的测试**

`tests/test_layered.py`：

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from PIL import Image  # noqa: E402

from layered import premultiplied_bgra  # noqa: E402


class PremultiplyTest(unittest.TestCase):
    def test_half_transparent_red_becomes_premultiplied_bgra(self):
        im = Image.new('RGBA', (1, 1), (255, 0, 0, 128))
        self.assertEqual(premultiplied_bgra(im), bytes([0, 0, 128, 128]))

    def test_fully_transparent_pixel_is_all_zero(self):
        im = Image.new('RGBA', (1, 1), (200, 100, 50, 0))
        self.assertEqual(premultiplied_bgra(im), bytes([0, 0, 0, 0]))

    def test_opaque_pixel_keeps_color(self):
        im = Image.new('RGBA', (1, 1), (10, 20, 30, 255))
        self.assertEqual(premultiplied_bgra(im), bytes([30, 20, 10, 255]))

    def test_rgb_input_is_treated_as_opaque(self):
        im = Image.new('RGB', (2, 1), (1, 2, 3))
        self.assertEqual(premultiplied_bgra(im), bytes([3, 2, 1, 255] * 2))


if __name__ == '__main__':
    unittest.main()
```

`tests/test_dpi.py`：

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from dpi import scale_of_dpi  # noqa: E402


class ScaleOfDpiTest(unittest.TestCase):
    def test_common_values(self):
        self.assertEqual(scale_of_dpi(96), 1.0)
        self.assertEqual(scale_of_dpi(144), 1.5)
        self.assertEqual(scale_of_dpi(192), 2.0)

    def test_bad_value_falls_back_to_one(self):
        self.assertEqual(scale_of_dpi(0), 1.0)
        self.assertEqual(scale_of_dpi(-5), 1.0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_layered tests.test_dpi -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'layered'`（以及 `dpi`）

- [ ] **Step 3: 实现 `pet/layered.py`**

```python
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
```

- [ ] **Step 4: 实现 `pet/dpi.py`**

```python
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
```

- [ ] **Step 5: 跑测试，确认通过**

Run: `python -m unittest tests.test_layered tests.test_dpi -v`
Expected: 6 个测试全部 PASS

- [ ] **Step 6: 写验证脚本 `tools/spike_layered.py`**

```python
"""一次性验证：tk 窗口 + UpdateLayeredWindow 能不能共存。

用法：python tools/spike_layered.py [立绘名，默认 smile]
看四件事：边缘半透明没有锯齿和毛边；透明的地方鼠标能点穿；按住能拖动；右键能弹出菜单（菜单里"退出"）。
"""
import ctypes
import math
import os
import sys
import time
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'pet'))

import dpi  # noqa: E402

print('DPI 感知：', dpi.enable())

from PIL import Image  # noqa: E402

from layered import LayeredWindow  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else 'smile'
sprite = Image.open(os.path.join(ROOT, 'pet', 'sprites', name + '.png')).convert('RGBA')
W, H = sprite.width + 40, sprite.height + 40

root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
canvas = tk.Canvas(root, width=W, height=H, bg='black', highlightthickness=0, bd=0)
canvas.pack()
root.geometry(f'{W}x{H}+300+300')
root.update_idletasks()
layer = LayeredWindow(ctypes.windll.user32.GetParent(root.winfo_id()))
print('缩放：', dpi.scale_at(300, 300))

drag = None


def press(e):
    global drag
    drag = (e.x_root - root.winfo_x(), e.y_root - root.winfo_y())


def motion(e):
    if drag:
        root.geometry(f'+{e.x_root - drag[0]}+{e.y_root - drag[1]}')


def release(e):
    global drag
    drag = None


menu = tk.Menu(root, tearoff=0, font=('Microsoft YaHei UI', 10))
menu.add_command(label='退出', command=root.destroy)
canvas.bind('<ButtonPress-1>', press)
canvas.bind('<B1-Motion>', motion)
canvas.bind('<ButtonRelease-1>', release)
canvas.bind('<Button-3>', lambda e: menu.tk_popup(e.x_root, e.y_root))


def tick():
    frame = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    frame.alpha_composite(sprite, (20, 20 + round(4 * math.sin(time.time() * 2.2))))
    if not layer.show(frame):
        print('UpdateLayeredWindow 失败')
    root.after(33, tick)


tick()
root.mainloop()
layer.close()
```

- [ ] **Step 7: 运行验证脚本，请用户确认（关卡）**

Run: `python tools/spike_layered.py`，再试 `python tools/spike_layered.py jump`（发丝多的立绘）。
请用户在深色和浅色背景上各看一次，确认：
1. 边缘平滑，没有锯齿和深棕色描边；
2. 角色以外的透明区域能点到后面的窗口；
3. 按住能拖动，松手停住；
4. 右键弹出菜单，文字清晰，点"退出"能关；
5. 任务管理器里 CPU 占用不明显（个位数百分比以内）。

**任意一项不通过：停下，把现象报告给用户，不要继续后面的任务。**

- [ ] **Step 8: Commit**

```bash
git add pet/layered.py pet/dpi.py tools/spike_layered.py tests/test_layered.py tests/test_dpi.py
git commit -m "feat: layered window and per-monitor DPI helpers with a feasibility spike"
```

---

### Task 2: 气泡排版

**Files:**
- Create: `pet/bubble.py`
- Test: `tests/test_bubble.py`

**Interfaces:**
- Produces:
  - `bubble.ELLIPSIS = '…'`
  - `bubble.BubbleLayout(lines: tuple[str, ...], sub: str | None = None)`（frozen dataclass）
  - `bubble.shorten_path(path: str) -> str`
  - `bubble.fit_end(text: str, measure: Callable[[str], float], max_w: float) -> str`
  - `bubble.layout(text: str, measure: Callable[[str], float], max_w: float, sub: str | None = None) -> BubbleLayout`

- [ ] **Step 1: 写失败的测试 `tests/test_bubble.py`**

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from bubble import BubbleLayout, fit_end, layout, shorten_path  # noqa: E402

M = len   # 每个字宽 1：测试里"宽度"就是字数
W = 10


class ShortenPathTest(unittest.TestCase):
    def test_keeps_first_dir_and_file_name(self):
        self.assertEqual(shorten_path('pet/sprites/extra/motion.py'), 'pet/…/motion.py')

    def test_short_path_unchanged(self):
        self.assertEqual(shorten_path('pet/motion.py'), 'pet/motion.py')

    def test_backslash_path(self):
        self.assertEqual(shorten_path('C:\\code\\pet\\motion.py'), 'C:\\…\\motion.py')


class FitEndTest(unittest.TestCase):
    def test_fits_unchanged(self):
        self.assertEqual(fit_end('一二三', M, W), '一二三')

    def test_too_long_gets_ellipsis_within_width(self):
        out = fit_end('一二三四五六七八九十十一', M, W)
        self.assertEqual(out, '一二三四五六七八九…')
        self.assertLessEqual(M(out), W)


class LayoutTest(unittest.TestCase):
    def test_short_text_one_line(self):
        self.assertEqual(layout('轮到你啦！', M, W), BubbleLayout(('轮到你啦！',)))

    def test_wraps_into_two_lines(self):
        text = '一二三四五六七八九十甲乙丙丁戊'
        self.assertEqual(layout(text, M, W).lines, ('一二三四五六七八九十', '甲乙丙丁戊'))

    def test_more_than_two_lines_truncates_second(self):
        text = '一二三四五六七八九十' + '甲乙丙丁戊己庚辛壬癸' + '子丑寅卯'
        lines = layout(text, M, W).lines
        self.assertEqual(lines, ('一二三四五六七八九十', '甲乙丙丁戊己庚辛壬…'))

    def test_long_path_is_shortened_in_the_middle(self):
        lines = layout('在改 pet/sprites/extra/motion.py', M, W).lines
        self.assertEqual(''.join(lines), '在改 pet/…/motion.py')
        self.assertEqual(len(lines), 2)

    def test_path_left_alone_when_it_fits(self):
        self.assertEqual(''.join(layout('改 a/b/c.py', M, W).lines), '改 a/b/c.py')

    def test_sub_line_leaves_one_body_line(self):
        out = layout('一二三四五六七八九十十一', M, W, sub='claude-desk-pet · sts2-ai 在等你')
        self.assertEqual(out.lines, ('一二三四五六七八九…',))
        self.assertEqual(out.sub, 'claude-de…')

    def test_line_does_not_start_with_space(self):
        lines = layout('aaaaaaaaaa bbb', M, W).lines
        self.assertEqual(lines, ('aaaaaaaaaa', 'bbb'))

    def test_newline_starts_new_line(self):
        self.assertEqual(layout('第一行\n第二行', M, W).lines, ('第一行', '第二行'))

    def test_empty_text(self):
        self.assertEqual(layout('', M, W).lines, ('',))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_bubble -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'bubble'`

- [ ] **Step 3: 实现 `pet/bubble.py`**

```python
"""气泡排版：把一句话排成最多两行，放不下就省略。

纯函数：量文字宽度的函数（measure）由调用方给，测试里可以用 len。
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

ELLIPSIS = '…'
PATH = re.compile(r'[^\s]*[\\/][^\s]*')   # 文字里带 / 或 \ 的一段，当作路径
Measure = Callable[[str], float]


@dataclass(frozen=True)
class BubbleLayout:
    lines: tuple            # 正文，1～2 行
    sub: str | None = None  # 正文下面的灰色小字（多会话信息）；有它时正文只占 1 行


def shorten_path(path: str) -> str:
    """pet/sprites/extra/motion.py → pet/…/motion.py：保留第一段和文件名。只有一两段的原样返回。"""
    parts = [p for p in re.split(r'[\\/]', path) if p]
    if len(parts) <= 2:
        return path
    sep = '\\' if '\\' in path and '/' not in path else '/'
    return f'{parts[0]}{sep}{ELLIPSIS}{sep}{parts[-1]}'


def fit_end(text: str, measure: Measure, max_w: float) -> str:
    """放得下就原样；放不下就从末尾删字，加上「…」。"""
    if measure(text) <= max_w:
        return text
    while text and measure(text + ELLIPSIS) > max_w:
        text = text[:-1]
    return text + ELLIPSIS


def _wrap(text: str, measure: Measure, max_w: float) -> list:
    """逐字换行（中文没有空格可断）；换行后行首的空格去掉。"""
    lines = []
    for para in text.split('\n'):
        cur = ''
        for ch in para:
            if cur and measure(cur + ch) > max_w:
                lines.append(cur)
                cur = '' if ch == ' ' else ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def layout(text: str, measure: Measure, max_w: float, sub: str | None = None) -> BubbleLayout:
    max_lines = 1 if sub else 2
    if measure(text.replace('\n', '')) > max_w * max_lines:
        text = PATH.sub(lambda m: shorten_path(m.group(0)), text)
    lines = _wrap(text, measure, max_w)
    if len(lines) > max_lines:
        rest = ''.join(lines[max_lines - 1:])
        lines = lines[:max_lines - 1] + [fit_end(rest + ELLIPSIS, measure, max_w)]
    return BubbleLayout(tuple(lines), fit_end(sub, measure, max_w) if sub else None)
```

注意 `fit_end(rest + ELLIPSIS, ...)`：被截掉的那一行即使刚好放得下，也必须带「…」表示后面还有字。`fit_end` 会先删掉末尾的「…」本身再补回去，结果只有一个「…」。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m unittest tests.test_bubble -v`
Expected: 15 个测试全部 PASS

- [ ] **Step 5: Commit**

```bash
git add pet/bubble.py tests/test_bubble.py
git commit -m "feat: bubble layout with two-line wrap, ellipsis and path shortening"
```

---

### Task 3: 整帧合成

**Files:**
- Create: `pet/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `bubble.BubbleLayout`
- Produces:
  - `render.BubbleStyle(font, small, scale: float)`（frozen dataclass），类方法 `BubbleStyle.make(scale: float) -> BubbleStyle`，方法 `measure(text: str) -> float`
  - `render.bubble_image(layout: BubbleLayout, style: BubbleStyle) -> Image.Image`（RGBA，尖角朝下、在底边正中）
  - `render.paste(dst: Image.Image, src: Image.Image, x: int, y: int) -> None`（就地合成到 `dst`；超出边界的部分裁掉）
  - `render.compose(sprite: Image.Image, sprite_bottom: int, bubble: Image.Image | None, bubble_bottom: int, min_w: int, height: int) -> Image.Image`

- [ ] **Step 1: 写失败的测试 `tests/test_render.py`**

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from PIL import Image, ImageFont  # noqa: E402

from bubble import BubbleLayout  # noqa: E402
from render import BubbleStyle, bubble_image, compose, paste  # noqa: E402

STYLE = BubbleStyle(font=ImageFont.load_default(13), small=ImageFont.load_default(11), scale=1.0)


def alphas(im):
    return list(im.getchannel('A').getdata())


class BubbleImageTest(unittest.TestCase):
    def test_two_lines_taller_than_one(self):
        one = bubble_image(BubbleLayout(('abc',)), STYLE)
        two = bubble_image(BubbleLayout(('abc', 'def')), STYLE)
        self.assertGreater(two.height, one.height)

    def test_sub_line_makes_it_taller(self):
        plain = bubble_image(BubbleLayout(('abc',)), STYLE)
        with_sub = bubble_image(BubbleLayout(('abc',), 'x · y'), STYLE)
        self.assertGreater(with_sub.height, plain.height)

    def test_wider_text_wider_bubble(self):
        short = bubble_image(BubbleLayout(('ab',)), STYLE)
        long = bubble_image(BubbleLayout(('abcdefghijkl',)), STYLE)
        self.assertGreater(long.width, short.width)

    def test_edges_are_antialiased(self):
        a = alphas(bubble_image(BubbleLayout(('abc',)), STYLE))
        self.assertTrue(any(0 < v < 255 for v in a))
        self.assertEqual(a[0], 0)  # 圆角外面的角落是透明的

    def test_tail_tip_at_bottom_center(self):
        im = bubble_image(BubbleLayout(('abcdef',)), STYLE)
        self.assertGreater(im.getpixel((im.width // 2, im.height - 3))[3], 0)
        self.assertEqual(im.getpixel((2, im.height - 3))[3], 0)


class PasteTest(unittest.TestCase):
    def test_clips_negative_offset_without_error(self):
        dst = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
        paste(dst, Image.new('RGBA', (3, 3), (255, 0, 0, 255)), -1, -1)
        self.assertEqual(dst.getpixel((0, 0))[3], 255)
        self.assertEqual(dst.getpixel((2, 2))[3], 0)

    def test_fully_outside_does_nothing(self):
        dst = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
        paste(dst, Image.new('RGBA', (3, 3), (255, 0, 0, 255)), 10, 10)
        self.assertEqual(set(alphas(dst)), {0})


class ComposeTest(unittest.TestCase):
    def sprite(self, alpha=60):
        return Image.new('RGBA', (10, 20), (255, 0, 0, alpha))

    def test_keeps_partial_alpha(self):
        out = compose(self.sprite(60), sprite_bottom=90, bubble=None, bubble_bottom=0, min_w=40, height=100)
        self.assertEqual(out.getpixel((20, 85))[3], 60)

    def test_sprite_bottom_lands_on_line(self):
        out = compose(self.sprite(255), sprite_bottom=90, bubble=None, bubble_bottom=0, min_w=40, height=100)
        self.assertEqual(out.getpixel((20, 89))[3], 255)
        self.assertEqual(out.getpixel((20, 90))[3], 0)
        self.assertEqual(out.getpixel((20, 69))[3], 0)

    def test_rest_is_transparent(self):
        out = compose(self.sprite(255), sprite_bottom=90, bubble=None, bubble_bottom=0, min_w=40, height=100)
        self.assertEqual(out.getpixel((0, 0))[3], 0)
        self.assertEqual(out.getpixel((39, 99))[3], 0)

    def test_width_is_max_of_min_and_bubble(self):
        wide = Image.new('RGBA', (80, 10), (255, 255, 255, 255))
        self.assertEqual(compose(self.sprite(), 90, None, 0, 40, 100).width, 40)
        self.assertEqual(compose(self.sprite(), 90, wide, 20, 40, 100).width, 80)

    def test_bubble_bottom_and_centered(self):
        b = Image.new('RGBA', (20, 10), (255, 255, 255, 255))
        out = compose(self.sprite(), 90, b, bubble_bottom=30, min_w=40, height=100)
        self.assertEqual(out.getpixel((20, 29))[3], 255)
        self.assertEqual(out.getpixel((20, 30))[3], 0)
        self.assertEqual(out.getpixel((9, 25))[3], 0)
        self.assertEqual(out.getpixel((10, 25))[3], 255)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_render -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'render'`

- [ ] **Step 3: 实现 `pet/render.py`**

```python
"""一帧画面：立绘 + 气泡，合成一张带透明度的图（RGBA）。纯 PIL，不碰窗口。"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from bubble import BubbleLayout

ORANGE = (232, 116, 59, 255)
PAPER = (255, 250, 243, 255)
INK = (58, 42, 26, 255)
SUB_INK = (150, 136, 122, 255)
SS = 3                      # 气泡的形状按 3 倍画再缩小，边缘才平滑；文字直接按原尺寸画（字体自带抗锯齿）
FONT_FILE, FONT_INDEX = 'msyh.ttc', 1   # Microsoft YaHei UI


def _font(px: int):
    try:
        return ImageFont.truetype(FONT_FILE, px, index=FONT_INDEX)
    except OSError:
        return ImageFont.load_default(px)


@dataclass(frozen=True)
class BubbleStyle:
    font: object     # 正文字体（PIL FreeTypeFont）
    small: object    # 第二行小字
    scale: float

    @classmethod
    def make(cls, scale: float) -> 'BubbleStyle':
        # 和原来 tk 的 10 号、8 号字一样大：1 磅 = 96/72 像素
        return cls(font=_font(round(10 * 96 / 72 * scale)), small=_font(round(8 * 96 / 72 * scale)), scale=scale)

    def px(self, v: float) -> int:
        return round(v * self.scale)

    def measure(self, text: str) -> float:
        return self.font.getlength(text)


def _shape(w: int, box_h: int, tail: int, s: BubbleStyle, k: int) -> Image.Image:
    """气泡的外形（圆角框 + 底部正中的小尖角），按 k 倍画。"""
    W, H, B = w * k, (box_h + tail) * k, max(2, s.px(2)) * k
    r, bottom, cx = s.px(12) * k, box_h * k, w * k // 2
    left, right, tip = cx - s.px(4) * k, cx + s.px(8) * k, bottom + tail * k
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, bottom - 1), radius=r, fill=ORANGE)
    d.polygon([(left, bottom - B), (cx, tip), (right, bottom - B)], fill=ORANGE)
    d.rounded_rectangle((B, B, W - 1 - B, bottom - 1 - B), radius=max(1, r - B), fill=PAPER)
    d.polygon([(left + B, bottom - 2 * B), (cx, tip - 2 * B), (right - B, bottom - 2 * B)], fill=PAPER)
    return im


def bubble_image(layout: BubbleLayout, style: BubbleStyle) -> Image.Image:
    s = style
    pad_x, pad_y, line_h, sub_h, tail = s.px(10), s.px(7), s.px(19), s.px(16), s.px(10)
    widths = [s.font.getlength(t) for t in layout.lines]
    if layout.sub:
        widths.append(s.small.getlength(layout.sub))
    w = round(max(widths + [0])) + 2 * pad_x
    box_h = 2 * pad_y + line_h * len(layout.lines) + (sub_h if layout.sub else 0)
    shape = _shape(w, box_h, tail, s, SS)
    im = shape.resize((w, box_h + tail), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    y = pad_y
    for text, tw in zip(layout.lines, widths):
        d.text(((w - tw) / 2, y), text, font=s.font, fill=INK)
        y += line_h
    if layout.sub:
        d.text(((w - widths[-1]) / 2, y + s.px(1)), layout.sub, font=s.small, fill=SUB_INK)
    return im


def paste(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """把 src 按透明度叠到 dst 的 (x, y)；超出 dst 的部分裁掉（alpha_composite 不接受负坐标）。"""
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(src.width, dst.width - x), min(src.height, dst.height - y)
    if right <= left or bottom <= top:
        return
    dst.alpha_composite(src, (x + left, y + top), (left, top, right, bottom))


def compose(sprite: Image.Image, sprite_bottom: int, bubble: Image.Image | None, bubble_bottom: int,
            min_w: int, height: int) -> Image.Image:
    """整帧：立绘底边中点落在 (宽/2, sprite_bottom)；气泡水平居中、底边（尖角）落在 bubble_bottom。
    宽度取 min_w 和气泡宽里大的那个。"""
    w = max(min_w, bubble.width if bubble else 0)
    out = Image.new('RGBA', (w, height), (0, 0, 0, 0))
    paste(out, sprite, w // 2 - sprite.width // 2, sprite_bottom - sprite.height)
    if bubble is not None:
        paste(out, bubble, w // 2 - bubble.width // 2, bubble_bottom - bubble.height)
    return out
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m unittest tests.test_render -v`
Expected: 12 个测试全部 PASS。如果 `test_tail_tip_at_bottom_center` 不通过，先打印 `im.height`、尖角所在行的透明度，检查 `_shape` 里尖角的坐标（尖角高 10 px，倒数第 3 行应该还在尖角里）。

- [ ] **Step 5: Commit**

```bash
git add pet/render.py tests/test_render.py
git commit -m "feat: compose sprite and antialiased bubble into one RGBA frame"
```

---

### Task 4: 把桌宠接到新渲染上

**Files:**
- Modify: `pet/pet.pyw`（导入、常量、`prepare`、`__init__`、`build`、`sprite_image`、`draw_bubble`、`apply_pose`、`refresh`、`resize`、`move`、`frame`、`watch_surface`）

**Interfaces:**
- Consumes: `dpi.enable`、`dpi.scale_at`、`layered.LayeredWindow`、`bubble.layout`、`render.BubbleStyle.make`、`render.bubble_image`、`render.compose`
- Produces: `Pet.rebuild()`（重建缩放、保持脚底位置）、`Pet.check_dpi()`、`Pet.bubble_for(text: str) -> Image.Image`、`Pet.fit_width(width: int)`、`Pet.update_motion(now, dt)`（原 `move` 去掉摆窗口）。E、B、C 的计划会用到这些名字。

这个任务没有新的单元测试（都是界面接线），靠原有测试 + 手动冒烟验证。

- [ ] **Step 1: 改导入和常量**

把文件开头这段：

```python
from PIL import Image, ImageOps, ImageTk
```

改为：

```python
from PIL import Image, ImageOps
```

把下面这段：

```python
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import winapi  # noqa: E402  要等 DPI 感知设好以后再导入，窗口坐标才是真实像素
```

改为：

```python
import dpi  # noqa: E402

dpi.enable()

import winapi  # noqa: E402  要等 DPI 感知设好以后再导入，窗口坐标才是真实像素
from bubble import layout  # noqa: E402
from layered import LayeredWindow  # noqa: E402
from render import BubbleStyle, bubble_image, compose  # noqa: E402
```

把常量：

```python
KEY = '#ff00fe'       # 透明色：画布上这个颜色的像素会被挖空
EDGE = (58, 36, 26)   # 半透明边缘和这个深棕色混合，避免边缘发出洋红色的毛边
ORANGE = '#e8743b'
```

改为：

```python
BUBBLE_MAX_W = 260    # 气泡最宽多少像素（100% 缩放）；放不下就换行，最多两行
BUBBLE_AREA = 66      # 角色头顶留给气泡的高度（两行正文 + 尖角）
BUBBLE_CACHE = 64     # 最多缓存多少张气泡图（文件名一直在变，不能无限存）
```

- [ ] **Step 2: 改 `prepare`**

整个函数替换为：

```python
def prepare(path, k, flip=False):
    """按 k 倍缩放立绘（可水平翻转），保留透明度。按预乘透明度缩放，边缘才不会发黑。"""
    im = Image.open(path).convert('RGBA')
    if flip:
        im = ImageOps.mirror(im)
    size = (max(1, round(im.width * k)), max(1, round(im.height * k)))
    return im.convert('RGBa').resize(size, Image.LANCZOS).convert('RGBA')
```

- [ ] **Step 3: 改 `__init__` 的窗口部分**

把：

```python
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', KEY)
        self.root.configure(bg=KEY)
        self.scale = self.root.winfo_fpixels('1i') / 96

        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0)
```

改为：

```python
        self.root.attributes('-topmost', True)
        self.scale = dpi.scale_at(self.settings.get('x', 0), self.settings.get('y', 0))

        # 画布只用来接鼠标事件；看得见的画面每帧由 render 合成、交给分层窗口
        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0, bd=0)
```

把：

```python
        self.build()
        self.place_window()
        self.make_menu()
```

改为：

```python
        self.build()
        self.place_window()
        self.root.update_idletasks()
        self.layer = LayeredWindow(user32.GetParent(self.root.winfo_id()))
        self.make_menu()
```

- [ ] **Step 4: 改 `build`、`sprite_image`，删掉 `draw_bubble`，新增 `bubble_for`、`fit_width`**

`build` 整个替换为：

```python
    def build(self):
        s = self.scale
        self.k = SIZES.get(self.settings.get('size', '中'), 190) * s / BASE_H
        self.cache = {}
        self.bubble_cache = {}
        self.style = BubbleStyle.make(s)
        sizes = []
        for name in SPRITE_FILES:
            with Image.open(os.path.join(HERE, 'sprites', name + '.png')) as im:
                sizes.append(im.size)
        self.char_h = round(max(h for _, h in sizes) * self.k)
        self.char_w = round(max(w for w, _ in sizes) * self.k)
        self.bubble_h = round(BUBBLE_AREA * s)
        self.min_w = max(self.char_w, round(190 * s))
        self.W = self.min_w
        self.line_y = self.bubble_h + round(8 * s) + self.char_h   # 站着时脚底、坐着时屁股落在窗口边上的那条线
        self.leg_room = round(0.32 * self.char_h)                  # 线下面留给垂下来的两条腿
        self.H = self.line_y + self.leg_room + round(6 * s)
        self.px_per_frame = STRIDE_PX / WALK_FRAMES * self.k  # 脚步每前进这么多像素，走路动画换一帧
        self.speed = STRIDES_PER_S * STRIDE_PX * self.k  # 像素/秒
        self.canvas.config(width=self.W, height=self.H)
        self.pose_key = None
        self.bubble_dy = 0
```

`sprite_image` 替换为：

```python
    def sprite_image(self, file, flip):
        key = (file, flip)
        if key not in self.cache:
            self.cache[key] = prepare(os.path.join(HERE, 'sprites', file + '.png'), self.k, flip)
        return self.cache[key]

    def bubble_for(self, text):
        """这句话的气泡图；同一句话只画一次。"""
        if text not in self.bubble_cache:
            if len(self.bubble_cache) >= BUBBLE_CACHE:
                self.bubble_cache = {}
            lay = layout(text, self.style.measure, round(BUBBLE_MAX_W * self.scale))
            self.bubble_cache[text] = bubble_image(lay, self.style)
        return self.bubble_cache[text]

    def fit_width(self, width):
        """气泡变宽变窄时窗口跟着变，脚底的中心点不动。"""
        if width == self.W:
            return
        x = self.root.winfo_x() + (self.W - width) // 2
        self.W = width
        self.canvas.config(width=width)
        self.root.geometry(f'{width}x{self.H}+{x}+{self.root.winfo_y()}')
        self.win_pos = None
```

删除整个 `draw_bubble` 方法。

- [ ] **Step 5: 改 `apply_pose`、`refresh`**

`apply_pose` 替换为：

```python
    def apply_pose(self):
        """按当前情况挑立绘；坐着的时候气泡跟着往下挪，贴着头顶。返回 (姿势, 立绘图)。"""
        pose = self.current_pose()
        key = (pose.file, pose.flip)
        img = self.sprite_image(*key)
        if key != self.pose_key:
            if self.pose_key and pose.anchor != self.anchor:
                self.hop_at = time.time()  # 站起来/坐下去：身体落点差了一截，蹦一下盖过那一下突兀的跳变
            self.pose_key, self.anchor = key, pose.anchor
        self.bubble_dy = round((1 - pose.anchor) * img.height)
        return pose, img
```

`refresh` 替换为：

```python
    def refresh(self):
        self.apply_pose()  # 画面每帧都会重新合成，这里只需要更新姿势
```

- [ ] **Step 6: 改 `resize`，新增 `rebuild`、`check_dpi`**

`resize` 替换为：

```python
    def resize(self):
        self.settings['size'] = self.size_var.get()
        save_settings(self.settings)
        self.rebuild()

    def rebuild(self):
        """换大小或换缩放后重建立绘；脚底位置不变。"""
        bottom_x = self.root.winfo_x() + self.W // 2
        bottom_y = self.root.winfo_y() + self.line_y
        self.build()
        self.win_pos = None  # 走动模式下，下一帧会按她的位置重新摆
        self.root.geometry(f'{self.W}x{self.H}+{bottom_x - self.W // 2}+{bottom_y - self.line_y}')

    def check_dpi(self):
        """她落在缩放不同的另一块屏上了：按那块屏的缩放重建。拖着、在空中的时候不换，免得大小一路跳。"""
        if self.drag is not None:
            return
        if self.roam and self.motion:
            if self.motion.mode not in ('perch', 'walk'):
                return
            x, y = self.motion.x, self.motion.y - 1
        else:
            x, y = self.root.winfo_x() + self.W // 2, self.root.winfo_y() + self.line_y - 1
        scale = dpi.scale_at(round(x), round(y))
        if abs(scale - self.scale) > 0.01:
            self.scale = scale
            self.rebuild()
```

- [ ] **Step 7: `watch_surface` 里调用 `check_dpi`**

在 `watch_surface` 的 `try` 块末尾（`self.target_hwnd = win.hwnd if win else None` 那两行之后）加：

```python
            self.check_dpi()
```

- [ ] **Step 8: 把 `move` 改名为 `update_motion` 并去掉摆窗口**

`move` 整个替换为：

```python
    def update_motion(self, now, dt):
        follow = self.follow_surface()
        if self.motion is None:
            ground = choose_surface(None, self.work_areas[0], need_above=self.line_y)
            self.motion = spawn(follow if self.following else ground, 0.8, now)  # 一开始待在当前窗口靠右的位置
        else:
            m = self.motion
            if self.following and m.mode in ('perch', 'walk') and m.support != follow.key:
                m = hop_to(m, follow, now, self.scale)  # 你切到了别的窗口：她跳过去
            self.motion = tick(m, self.fresh_surfaces(follow), now, dt, speed=self.speed, scale=self.scale,
                               can_wander=self.can_wander())
```

- [ ] **Step 9: 改 `frame`**

整个替换为：

```python
    def frame(self):
        t = time.time()
        dt = min(0.1, max(0.0, t - self.last_frame))
        self.last_frame = t
        if self.speech and t >= self.speech[1]:
            self.speech = None
        if self.roam:
            self.update_motion(t, dt)
        pose, img = self.apply_pose()
        since = t - self.hop_at
        hop = -14 * math.sin(since / 0.28 * math.pi) if since < 0.28 else 0  # 换状态时小跳一下
        sprite_bottom = (self.line_y + round((1 - pose.anchor) * img.height)
                         + round((self.bob_for(pose.file, t) + hop) * self.scale))
        text = self.display_text()
        if (self.claude_state() == 'thinking' and self.text.endswith('中')
                and not self.break_state.level and not self.speech_state()):
            text = self.text + '.' * (int(t * 2.5) % 3 + 1)  # “思考中” 后面的点点点一跳一跳
        image = compose(img, sprite_bottom, self.bubble_for(text), self.bubble_h + self.bubble_dy,
                        self.min_w, self.H)
        self.fit_width(image.width)
        if self.roam and self.motion and self.drag is None and not self.hidden:
            self.put_window(self.motion.x, self.motion.y)
        if not self.hidden and not self.layer.show(image):
            raise OSError('UpdateLayeredWindow 失败')  # animate() 会记一次日志
```

- [ ] **Step 10: 检查没有残留**

Run: `grep -n "KEY\|EDGE\|ORANGE\|ImageTk\|draw_bubble\|bubble_text\|self.sprite\b\|self.move(" pet/pet.pyw`
Expected: 没有输出。有输出就按上面的步骤改掉对应的地方。

- [ ] **Step 11: 跑全部测试**

Run: `python -m unittest discover -s tests`
Expected: 全部通过（原有 134 个 + Task 1～3 新增的）

- [ ] **Step 12: 手动冒烟**

Run（Git Bash）: `python pet/launch.py pet/pet.pyw "$USERPROFILE/.claude/desk-pet"`（先在右键菜单里退出正在运行的旧桌宠）
请用户确认：
1. 她出现在当前窗口顶边，边缘平滑、没有深棕色描边；
2. 气泡圆角平滑，尖角对着她；Claude 改文件时文件名太长会换行或省略；
3. 拖起来、甩出去、落到窗口上都正常；坐下时气泡跟着往下挪；
4. 右键菜单正常，改大小后她的脚底位置不变；
5. 有两块缩放不同的屏幕的话：把她拖到另一块屏放下，落地后大小变得和那块屏的其他内容相称；
6. `%USERPROFILE%\.claude\desk-pet\pet-error.log` 里没有新的报错。

- [ ] **Step 13: Commit**

```bash
git add pet/pet.pyw
git commit -m "feat: render the pet through a per-pixel-alpha layered window"
```

---

### Task 5: 文档同步和收尾

**Files:**
- Modify: `README.md`（「自定义」一节的"换立绘"）
- Modify: `docs/superpowers/specs/2026-10-29-desk-pet-polish-design.md`（A1 关于窗口位置的那一条）

- [ ] **Step 1: 改 README 的"换立绘"**

把：

```markdown
- **换立绘**：把 `pet/sprites/` 里的 PNG 换成你自己的图（透明背景，文件名保持不变）
```

改为：

```markdown
- **换立绘**：把 `pet/sprites/` 里的 PNG 换成你自己的图（透明背景，文件名保持不变）。半透明的边缘、发丝、阴影都会照原样显示，不需要另外描边
```

- [ ] **Step 2: 改 spec A1 那一条**

把：

```markdown
- 窗口位置由 `UpdateLayeredWindow` 的目标坐标给，不再调 `root.geometry()` 移动（避免两套坐标打架）。
```

改为：

```markdown
- 窗口位置和大小只由 `root.geometry()` 决定，`UpdateLayeredWindow` 不传位置、只换内容（只有一套坐标，`winfo_x()` 照常可用）。
```

- [ ] **Step 3: 跑全部测试**

Run: `python -m unittest discover -s tests`
Expected: 全部通过

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-29-desk-pet-polish-design.md
git commit -m "docs: note per-pixel alpha sprites and the single-coordinate window rule"
```
