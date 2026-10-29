# E 系统集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全屏时自动避让、坐在窗口上时跟着窗口的层级、在 Claude 里用 `/pet` 子命令控制桌宠、设置文件不再被写坏。

**Architecture:** 纯判断放在新的 `pet/screen.py`（全屏、该置顶还是贴着窗口）和 `pet/commands.py`（解析 `/pet` 参数）；Win32 取数和改层级加在 `pet/winapi.py`；原子写 JSON 放在 `pet/files.py`。插件 `hooks/register.ts` 只认子命令名、写 `command.json`、显示用法；参数检查和执行都在桌宠这边。

**Tech Stack:** Python 3.14、tkinter、ctypes；TypeScript（Claude Code 插件引擎），测试用 unittest；插件用 `claude plugin validate` 校验。

**Spec:** `docs/superpowers/specs/2026-10-29-desk-pet-polish-design.md`（本计划实现其中的「E 系统集成」）

**前置:** A、B、C 已完成（`Pet.layer.hwnd`、`Pet.react`、`Pet.chat_var`、`toggle_chat` 可用）。

## Global Constraints

- 只支持 Windows；不新增第三方依赖；测试 `python -m unittest discover -s tests`，输出不能有警告；中文注释、frozen dataclass、纯函数、不改动入参。
- 全屏：前台窗口不是桌面、不是她自己，矩形盖满她所在那块显示器（`rcMonitor`，含任务栏）才算；只看她所在的屏；全屏时隐藏，退出后恢复；全屏期间到点的休息提醒推迟到退出全屏后再出。
- 层级：坐在窗口顶边上（`motion.support` 是窗口句柄，`perch`/`walk`）时不置顶、贴在那个窗口正上方一层；站在屏幕底边、被拎着、在空中、提醒休息、临时说话时置顶；每 0.25 秒校正一次，已经对了就不调用；`SetWindowPos` 失败时退回置顶并只记一次日志。
- `/pet` 子命令只用英文：`/pet`、`hide`、`home`、`size small|medium|large`、`follow on|off`、`roam on|off`、`sound on|off`、`chat on|off`、`break on|off|30|45|50|60|90`、`break test`、`rest`、`quit`、`help`；参数打错列出用法；注册时带 `argumentHint` 和 `immediate: true`。
- 传话：插件写 `<运行目录>/command.json` = `{ id, args, ts }`（`ts` 是 `$.clock.now()` 的毫秒）；桌宠在 `poll()` 里读，`id` 处理过就不再执行；超过 30 秒的命令忽略；桌宠没在运行时插件先启动它。执行后在气泡里回一句。
- 设置文件：先写 `settings.json.tmp` 再 `os.replace`。

### 与 spec 的差异（本计划的决定）

- spec E3 要插件端有 `parsePetCommand` 纯函数并用 `claude plugin test` 测。项目没有 TS 测试基础设施；为了把 TypeScript 改动压到最小，插件只检查第一个词是不是已知子命令（不是就返回用法），完整的参数解析放在 Python 的 `commands.parse` 并用 unittest 测；参数错了由桌宠在气泡里说"看不懂"。
- 插件引擎的文件接口没有改名操作，`command.json` 不是原子写入；桌宠读到半截文件（JSON 解析失败）就当这次没有命令，下一次轮询再读。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `pet/screen.py`（新） | `is_fullscreen`、`choose_z` 纯判断 |
| `pet/commands.py`（新） | `/pet` 参数解析 |
| `pet/files.py`（新） | 原子写 JSON |
| `pet/winapi.py`（改） | 前台窗口外框、显示器矩形、置顶/贴着窗口 |
| `pet/pet.pyw`（改） | 接线 |
| `hooks/register.ts`（改） | `/pet` 子命令、写 `command.json` |
| `.claude-plugin/plugin.json`（改） | 版本号 0.3.0 |
| `README.md`（改） | 文档 |
| `tests/test_screen.py`、`test_commands.py`、`test_files.py`（新） | 测试 |

---

### Task 1: 三个纯模块

**Files:**
- Create: `pet/screen.py`、`pet/commands.py`、`pet/files.py`
- Create: `tests/test_screen.py`、`tests/test_commands.py`、`tests/test_files.py`

**Interfaces:**
- Produces:
  - `screen.DESKTOP_CLASSES`；`screen.is_fullscreen(rect: Rect, cls: str, monitor: Rect) -> bool`；`screen.choose_z(motion: Motion | None, remind: int, speaking: bool) -> 'top' | int`
  - `commands.Command(name: str, value: object = None)`；`commands.parse(args: str) -> Command | str`（字符串是出错提示）；`commands.SIZES = {'small': '小', 'medium': '中', 'large': '大'}`；`commands.SWITCHES`；`commands.BREAK_MINUTES = (30, 45, 50, 60, 90)`
  - `files.write_json_atomic(path: str, data) -> None`

- [ ] **Step 1: 写失败的测试**

`tests/test_screen.py`：

```python
import os
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from motion import Rect, Surface, hold, spawn  # noqa: E402
from screen import choose_z, is_fullscreen  # noqa: E402

MON = Rect(0, 0, 1920, 1080)
WIN = Surface(key=1234, left=100.0, right=900.0, y=300.0, kind='window')
GROUND = Surface(key=('ground', 0, 0, None), left=0.0, right=1920.0, y=1040.0, kind='ground')


class FullscreenTest(unittest.TestCase):
    def test_covering_the_whole_monitor_is_fullscreen(self):
        self.assertTrue(is_fullscreen(Rect(0, 0, 1920, 1080), 'UnityWndClass', MON))

    def test_slightly_larger_still_counts(self):
        self.assertTrue(is_fullscreen(Rect(-8, -8, 1928, 1088), 'Chrome_WidgetWin_1', MON))

    def test_maximized_above_the_taskbar_is_not(self):
        self.assertFalse(is_fullscreen(Rect(0, 0, 1920, 1040), 'Chrome_WidgetWin_1', MON))

    def test_desktop_is_not(self):
        self.assertFalse(is_fullscreen(Rect(0, 0, 1920, 1080), 'Progman', MON))
        self.assertFalse(is_fullscreen(Rect(0, 0, 1920, 1080), 'WorkerW', MON))

    def test_fullscreen_on_another_monitor_is_not(self):
        self.assertFalse(is_fullscreen(Rect(1920, 0, 3840, 1080), 'UnityWndClass', MON))


class ChooseZTest(unittest.TestCase):
    def test_sitting_on_a_window_stays_just_above_it(self):
        self.assertEqual(choose_z(spawn(WIN, 0.5, 0.0), 0, False), 1234)

    def test_walking_on_a_window_too(self):
        m = replace(spawn(WIN, 0.5, 0.0), mode='walk', target_frac=0.8)
        self.assertEqual(choose_z(m, 0, False), 1234)

    def test_on_the_ground_is_topmost(self):
        self.assertEqual(choose_z(spawn(GROUND, 0.5, 0.0), 0, False), 'top')

    def test_held_reminding_or_speaking_is_topmost(self):
        m = spawn(WIN, 0.5, 0.0)
        self.assertEqual(choose_z(hold(m, 5.0, 5.0), 0, False), 'top')
        self.assertEqual(choose_z(m, 2, False), 'top')
        self.assertEqual(choose_z(m, 0, True), 'top')

    def test_no_body_is_topmost(self):
        self.assertEqual(choose_z(None, 0, False), 'top')


if __name__ == '__main__':
    unittest.main()
```

`tests/test_commands.py`：

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from commands import Command, parse  # noqa: E402


class ParseTest(unittest.TestCase):
    def test_bare_pet_means_show(self):
        self.assertEqual(parse(''), Command('show'))
        self.assertEqual(parse('   '), Command('show'))

    def test_simple_commands(self):
        for word in ('show', 'hide', 'home', 'rest', 'quit'):
            self.assertEqual(parse(word), Command(word))

    def test_size(self):
        self.assertEqual(parse('size small'), Command('size', '小'))
        self.assertEqual(parse('size medium'), Command('size', '中'))
        self.assertEqual(parse('size large'), Command('size', '大'))

    def test_switches(self):
        self.assertEqual(parse('follow on'), Command('follow', True))
        self.assertEqual(parse('roam off'), Command('roam', False))
        self.assertEqual(parse('sound off'), Command('sound', False))
        self.assertEqual(parse('chat on'), Command('chat', True))

    def test_break(self):
        self.assertEqual(parse('break off'), Command('break', False))
        self.assertEqual(parse('break 45'), Command('break-minutes', 45))
        self.assertEqual(parse('break test'), Command('break-test'))

    def test_case_and_spaces_do_not_matter(self):
        self.assertEqual(parse('  Size   LARGE '), Command('size', '大'))

    def test_mistakes_give_a_message(self):
        for bad in ('size huge', 'follow maybe', 'break 42', 'hide now', 'jump', 'size', '隐藏'):
            out = parse(bad)
            self.assertIsInstance(out, str, bad)
            self.assertIn('/pet help', out)


if __name__ == '__main__':
    unittest.main()
```

`tests/test_files.py`：

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from files import write_json_atomic  # noqa: E402


class WriteJsonAtomicTest(unittest.TestCase):
    def test_writes_utf8_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'settings.json')
            write_json_atomic(p, {'size': '中'})
            with open(p, encoding='utf-8') as f:
                self.assertEqual(json.load(f), {'size': '中'})
            self.assertFalse(os.path.exists(p + '.tmp'))

    def test_a_failed_write_leaves_the_old_file_alone(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'settings.json')
            write_json_atomic(p, {'size': '大'})
            with self.assertRaises(TypeError):
                write_json_atomic(p, {'bad': {1, 2}})   # set 不能写成 JSON
            with open(p, encoding='utf-8') as f:
                self.assertEqual(json.load(f), {'size': '大'})
            self.assertFalse(os.path.exists(p + '.tmp'))

    def test_creates_the_folder(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'sub', 'settings.json')
            write_json_atomic(p, {})
            self.assertTrue(os.path.exists(p))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_screen tests.test_commands tests.test_files -v`
Expected: FAIL，三个 `ModuleNotFoundError`

- [ ] **Step 3: 实现 `pet/screen.py`**

```python
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
```

- [ ] **Step 4: 实现 `pet/commands.py`**

```python
"""/pet 后面跟的参数：解析成桌宠要执行的命令。只认英文。"""
from __future__ import annotations

from dataclasses import dataclass

SIZES = {'small': '小', 'medium': '中', 'large': '大'}
SWITCHES = frozenset({'follow', 'roam', 'sound', 'chat'})
SIMPLE = frozenset({'show', 'hide', 'home', 'rest', 'quit'})
BREAK_MINUTES = (30, 45, 50, 60, 90)


@dataclass(frozen=True)
class Command:
    name: str          # show / hide / home / rest / quit / size / follow / roam / sound / chat /
                       # break / break-minutes / break-test
    value: object = None


def parse(args: str):
    """返回 Command；看不懂时返回一句提示（字符串）。"""
    words = args.strip().lower().split()
    if not words:
        return Command('show')
    head, rest = words[0], words[1:]
    if head in SIMPLE and not rest:
        return Command(head)
    if len(rest) == 1:
        value = rest[0]
        if head == 'size' and value in SIZES:
            return Command('size', SIZES[value])
        if head in SWITCHES and value in ('on', 'off'):
            return Command(head, value == 'on')
        if head == 'break':
            if value in ('on', 'off'):
                return Command('break', value == 'on')
            if value == 'test':
                return Command('break-test')
            if value.isdigit() and int(value) in BREAK_MINUTES:
                return Command('break-minutes', int(value))
    return f'看不懂「/pet {args.strip()}」，输入 /pet help 看用法'
```

- [ ] **Step 5: 实现 `pet/files.py`**

```python
"""写文件的小工具。"""
from __future__ import annotations

import json
import os


def write_json_atomic(path: str, data) -> None:
    """先写到 .tmp 再替换：写到一半出错（或程序被关掉），原来的文件还是完整的。"""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
```

- [ ] **Step 6: 跑测试，确认通过；全部测试；Commit**

Run: `python -m unittest tests.test_screen tests.test_commands tests.test_files -v` — Expected: 全部 PASS
Run: `python -m unittest discover -s tests` — Expected: 全部通过

```bash
git add pet/screen.py pet/commands.py pet/files.py tests/test_screen.py tests/test_commands.py tests/test_files.py
git commit -m "feat: fullscreen and z-order decisions, /pet argument parsing, atomic JSON writes"
```

---

### Task 2: Win32 和桌宠接线

**Files:**
- Modify: `pet/winapi.py`
- Modify: `pet/pet.pyw`

**Interfaces:**
- Consumes: Task 1 全部接口；`Pet.layer.hwnd`（A）；`Pet.react`、`Pet.chat_var`、`Pet.toggle_chat`（C）
- Produces:
  - `winapi.foreground_frame(own_pid: int) -> tuple[int, Rect, str] | None`
  - `winapi.monitor_rect_at(x: int, y: int) -> Rect`
  - `winapi.set_topmost(hwnd: int) -> bool`
  - `winapi.place_above(hwnd: int, target: int) -> bool`
  - `Pet.run_command(args: str)`、`Pet.check_command()`

没有新的单元测试（Win32 + 界面接线），靠全部测试 + 手动冒烟。

- [ ] **Step 1: `pet/winapi.py` 加四个函数**

在常量区加：

```python
GW_HWNDNEXT = 2
GW_HWNDPREV = 3
WS_EX_TOPMOST = 0x8
HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
```

在 argtypes 设置区（`dwmapi.DwmGetWindowAttribute.argtypes = ...` 之后）加：

```python
user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
user32.GetWindow.restype = wt.HWND
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowPos.restype = wt.BOOL
user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
user32.MonitorFromPoint.restype = wt.HANDLE
```

在文件末尾加：

```python
def foreground_frame(own_pid: int):
    """前台窗口的 (句柄, 外框, 类名)；没有前台窗口或是她自己时返回 None。不做"能不能坐"的过滤（全屏判断用）。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or _pid(hwnd) == own_pid:
        return None
    rect = _frame(hwnd)
    if rect is None:
        return None
    return int(hwnd), rect, _class_name(hwnd)


def monitor_rect_at(x: int, y: int) -> Rect:
    """屏幕上 (x, y) 所在（或最近的）显示器的整个矩形，含任务栏。"""
    mon = user32.MonitorFromPoint(wt.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return _rect(info.rcMonitor)
    return primary_work_area()


_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE


def set_topmost(hwnd: int) -> bool:
    return bool(user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, _FLAGS))


def place_above(hwnd: int, target: int) -> bool:
    """把 hwnd 放到 target 正上方一层（不置顶）。已经在那儿就什么都不做。"""
    if user32.GetWindow(hwnd, GW_HWNDNEXT) == target and not user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST:
        return True
    if not user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, _FLAGS):
        return False
    above = user32.GetWindow(target, GW_HWNDPREV)
    if not above or above == hwnd or user32.GetWindowLongW(above, GWL_EXSTYLE) & WS_EX_TOPMOST:
        above = HWND_TOP   # target 上面是置顶窗口（或没有窗口）：放到普通窗口的最上面
    return bool(user32.SetWindowPos(hwnd, above, 0, 0, 0, 0, _FLAGS))
```

- [ ] **Step 2: `pet/pet.pyw` 导入和常量**

在 `from sessions import ...` 之后加：

```python
from commands import Command, parse as parse_command  # noqa: E402
from files import write_json_atomic  # noqa: E402
from screen import choose_z, is_fullscreen  # noqa: E402
```

在 `SETTINGS = ...` 之后加：

```python
COMMAND = os.path.join(RUN_DIR, 'command.json')   # 插件收到 /pet 子命令后写在这里
COMMAND_TTL_MS = 30_000                           # 比这更早的命令不执行（桌宠重启后不重放旧命令）
```

`save_settings` 替换为：

```python
def save_settings(s):
    try:
        write_json_atomic(SETTINGS, s)
    except Exception:
        log_error()
```

- [ ] **Step 3: `__init__` 里加状态**

在 `self.sprite_box = (0, 0, 0)` 之后加：

```python
        self.forced_hidden = False     # /pet hide 藏起来了
        self.fullscreen = False        # 她所在的那块屏正在全屏
        self.pending_break = None      # 全屏期间到点的休息提醒，等退出全屏再出
        self.z = None                  # 上一次设置的层级（'top' 或窗口句柄）
        self.last_command = None       # 处理过的最后一条 /pet 命令的 id
```

- [ ] **Step 4: 全屏和隐藏**

`watch_focus` 替换为：

```python
    def feet_point(self):
        if self.roam and self.motion:
            return round(self.motion.x), round(self.motion.y - 1)
        return self.root.winfo_x() + self.W // 2, self.root.winfo_y() + self.line_y - 1

    def check_fullscreen(self):
        fg = winapi.foreground_frame(os.getpid())
        if fg is None:
            return False
        _, rect, cls = fg
        return is_fullscreen(rect, cls, winapi.monitor_rect_at(*self.feet_point()))

    def watch_focus(self):
        try:
            self.fullscreen = self.check_fullscreen()
            auto_hide = (self.hide_var.get() and claude_is_foreground() and self.drag is None
                         and not self.break_state.level)  # 正在提醒休息的时候不躲
            should_hide = self.forced_hidden or self.fullscreen or auto_hide
            if should_hide and not self.hidden:
                self.root.withdraw()
                self.hidden = True
            elif not should_hide and self.hidden:
                self.root.deiconify()
                self.root.attributes('-topmost', True)
                self.hidden = False
                self.win_pos = None
                self.z = None   # 重新显示后层级要重新设
            if not self.fullscreen and self.pending_break is not None:
                ev, self.pending_break = self.pending_break, None
                self.on_break_event(ev)
        except Exception:
            log_error()
        finally:
            self.root.after(300, self.watch_focus)
```

在 `watch_break` 里，把 `if ev:\n                    self.on_break_event(ev)` 改为：

```python
                if ev and self.fullscreen:
                    self.pending_break = ev   # 全屏的时候不打扰，退出全屏再提醒
                elif ev:
                    self.on_break_event(ev)
```

- [ ] **Step 5: 层级**

在 `watch_surface` 的 `try` 块末尾（`self.check_dpi()` 之后）加：

```python
            self.apply_z()
```

在 `watch_surface` 之后加：

```python
    def apply_z(self):
        """坐在窗口上时贴着那个窗口（会被一起盖住），其余时候置顶。失败就退回置顶，只记一次日志。"""
        if self.hidden:
            return
        speaking = bool(self.speech and time.time() < self.speech[1])
        want = choose_z(self.motion if self.roam else None, self.break_state.level, speaking)
        if want == 'top':
            if self.z != 'top':
                winapi.set_topmost(self.layer.hwnd)
                self.z = 'top'
            return
        if not winapi.place_above(self.layer.hwnd, want):
            self.log_once(f'SetWindowPos 失败，退回置顶（窗口 {want}）')
            winapi.set_topmost(self.layer.hwnd)
            self.z = 'top'
            return
        self.z = want
```

- [ ] **Step 6: `/pet` 命令**

在 `poll` 里 `self.root.after(250, self.poll)` 之前加：

```python
        self.check_command()
```

在 `poll` 之后加：

```python
    def check_command(self):
        """读插件写来的 /pet 命令；同一条只执行一次，太旧的不执行。读到写了一半的文件就等下次。"""
        try:
            with open(COMMAND, encoding='utf-8') as f:
                data = json.load(f)
            cid = str(data.get('id', ''))
            ts = float(data.get('ts', 0))
            args = str(data.get('args', ''))
        except (FileNotFoundError, ValueError, TypeError, AttributeError):
            return
        if not cid or cid == self.last_command:
            return
        self.last_command = cid
        if time.time() * 1000 - ts > COMMAND_TTL_MS:
            return
        try:
            self.run_command(args)
        except Exception:
            log_error()

    def run_command(self, args):
        cmd = parse_command(args)
        if isinstance(cmd, str):
            self.forced_hidden = False
            self.say(cmd, 5.0)
            return
        name, value = cmd.name, cmd.value
        if name != 'hide':
            self.forced_hidden = False
        if name == 'show':
            self.say('我在这儿～', 3.0)
        elif name == 'hide':
            self.forced_hidden = True
        elif name == 'home':
            self.set_following(True)
            self.say('我回来啦～', 3.0)
        elif name == 'quit':
            self.root.destroy()
        elif name == 'rest':
            self.acknowledge_break()
        elif name == 'size':
            self.size_var.set(value)
            self.resize()
            self.say(f'变成{value}号啦', 3.0)
        elif name in ('follow', 'roam', 'sound', 'chat'):
            var, toggle, label = {
                'follow': (self.follow_var, self.toggle_follow, '自动跟着当前窗口'),
                'roam': (self.roam_var, self.toggle_roam, '跟着窗口走动'),
                'sound': (self.sound_var, self.toggle_sound, '提示音'),
                'chat': (self.chat_var, self.toggle_chat, '闲聊'),
            }[name]
            var.set(value)
            toggle()
            self.say(f'{label}已{"打开" if value else "关闭"}', 3.0)
        elif name == 'break':
            self.break_var.set(value)
            self.toggle_break()
            self.say(f'休息提醒已{"打开" if value else "关闭"}', 3.0)
        elif name == 'break-minutes':
            self.work_var.set(str(value))
            self.set_work_minutes()
            self.say(f'以后每 {value} 分钟提醒你休息', 3.0)
        elif name == 'break-test':
            self.preview_break(1)
```

- [ ] **Step 7: 检查**

Run: `python -m py_compile pet/pet.pyw pet/winapi.py` — Expected: 没有输出
Run: `python -m unittest discover -s tests` — Expected: 全部通过

- [ ] **Step 8: 手动冒烟（controller 做，实现者跳过）**

```bash
D="$TEMP/cdp_smoke_e"; mkdir -p "$D/sessions"
echo '{"state": "waiting", "text": "轮到你啦！", "project": "claude-desk-pet", "ts": 0}' > "$D/sessions/a.json"
DESK_PET_PORT=47399 python pet/pet.pyw "$D" &
python -c "import json,time;json.dump({'id':'t1','args':'size large','ts':time.time()*1000},open(r'$D/command.json','w'))"
```

确认：她变成大号并说「变成大号啦」；写 `hide` 后消失、写 `show`（新 id）后出现；写 `size huge` 时说看不懂；在她所在的屏上把一个视频或浏览器按 F11 全屏，她消失，退出全屏回来；她坐在一个窗口上时，把另一个窗口拖过来盖住，她被一起盖住。

- [ ] **Step 9: Commit**

```bash
git add pet/winapi.py pet/pet.pyw
git commit -m "feat: hide on fullscreen, follow the window's z-order, run /pet commands, write settings atomically"
```

---

### Task 3: 插件端 `/pet` 子命令

**Files:**
- Modify: `hooks/register.ts`
- Modify: `.claude-plugin/plugin.json`

- [ ] **Step 1: 常量和发命令的函数**

在 `const READING = new Set([...])` 之后加：

```ts
// /pet 的子命令（只认英文）；参数是否合法由桌宠检查，打错了它会在气泡里说
const PET_COMMANDS = new Set(['', 'show', 'hide', 'home', 'size', 'follow', 'roam', 'sound', 'chat', 'break', 'rest', 'quit'])

const PET_HELP = [
  '/pet 用法：',
  '/pet                      召唤桌宠；被藏起来了就显示出来',
  '/pet hide                 藏起来',
  '/pet home                 回到当前窗口，并重新开始自动跟随',
  '/pet size small|medium|large   调大小',
  '/pet follow on|off        自动跟着当前窗口',
  '/pet roam on|off          跟着窗口走动',
  '/pet sound on|off         提示音',
  '/pet chat on|off          闲聊',
  '/pet break on|off|30|45|50|60|90   休息提醒开关 / 间隔（分钟）',
  '/pet break test           试一下休息提醒',
  '/pet rest                 我去休息了',
  '/pet quit                 退出桌宠',
].join('\n')
```

在 `launchPet` 函数之后加：

```ts
// 把 /pet 的参数交给桌宠：写进 command.json，桌宠每 0.25 秒读一次，按 id 去重，30 秒以上的旧命令不执行
async function sendPetCommand($: EngineInterface, args: string) {
  const ts = await $.clock.now()
  const id = `${ts}-${Math.random().toString(36).slice(2, 8)}`
  await $.fs.write(`${runDir}/command.json`, JSON.stringify({ id, args, ts }))
}
```

- [ ] **Step 2: 注册命令时带参数提示**

把：

```ts
    await $.command.register({ name: 'pet', description: '重新召唤桌宠悬浮窗' })
```

替换为：

```ts
    await $.command.register({
      name: 'pet',
      description: '召唤和控制桌宠（/pet help 看用法）',
      argumentHint: '[hide|home|size|follow|roam|sound|chat|break|rest|quit|help]',
      immediate: true,
    })
```

- [ ] **Step 3: 命令处理**

把整个 `on('command.run', { command: 'pet' }, ...)` 替换为：

```ts
  on('command.run', { command: 'pet' }, async ($, e, next) => {
    const args = e.args.trim()
    const head = args.split(/\s+/)[0].toLowerCase()
    if (!PET_COMMANDS.has(head)) return { text: PET_HELP }
    try {
      await launchPet($) // 已经开着的话不会开第二个
      await sendPetCommand($, args)
    } catch (err) {
      $.ui.log(`桌宠命令失败：${String(err)}`, { to: 'debug' })
      return { text: '桌宠没有响应，看看 ~/.claude/desk-pet/mod-launch.log' }
    }
    if (args === '') {
      await pet($, 'waiting', '我在这儿～')
      return { text: '桌宠已召唤（如果它本来就开着，就不会再开第二个）。输入 /pet help 看还能做什么。' }
    }
    return { text: `已告诉桌宠：/pet ${args}` }
  })
```

（`/pet help` 和打错的第一个词都会返回 `PET_HELP`；`'help'` 不在 `PET_COMMANDS` 里正是为此。）

- [ ] **Step 4: 版本号**

`.claude-plugin/plugin.json` 的 `"version": "0.2.0"` 改为 `"version": "0.3.0"`。

- [ ] **Step 5: 校验插件**

Run: `claude plugin validate .`
Expected: 没有报错。如果这个子命令在本机的 Claude Code 版本里不存在，或者报的是与本次改动无关的旧问题，在报告里写明输出原文；报的是本次改动（类型、事件名、字段名）就修好再验。

- [ ] **Step 6: Commit**

```bash
git add hooks/register.ts .claude-plugin/plugin.json
git commit -m "feat: /pet subcommands with an argument hint, sent to the pet through command.json"
```

---

### Task 4: 文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README**

把「命令」一节里：

```markdown
- `/pet`：不小心关掉了桌宠？用它重新召唤
```

替换为：

```markdown
- `/pet`：召唤桌宠（不小心关掉、藏起来了都能叫回来）；后面还能跟子命令，`/pet help` 看全部：
  - `/pet hide` 藏起来，`/pet home` 回到当前窗口并重新自动跟随
  - `/pet size small|medium|large` 调大小
  - `/pet follow|roam|sound|chat on|off` 开关自动跟随、走动、提示音、闲聊
  - `/pet break on|off|30|45|50|60|90` 休息提醒开关和间隔，`/pet break test` 试一下，`/pet rest` 我去休息了
  - `/pet quit` 退出
```

在「🚶 走来走去」那一节末尾加：

```markdown
- 你在她所在的屏幕上全屏看视频、打游戏、放 PPT 时，她会自动躲起来，退出全屏再回来；这期间到点的休息提醒也会等你退出全屏再说
- 她坐在某个窗口上时，别的窗口盖过来会把她一起盖住，就像真的坐在那个窗口上一样
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: /pet subcommands, fullscreen hiding and window stacking"
```
