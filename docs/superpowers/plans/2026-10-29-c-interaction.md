# C 互动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 摸头、戳她、偶尔闲聊、同时开多个会话时不丢"在等你"。

**Architecture:** 三个纯函数模块：`pet/interact.py`（摸头手势、单击/双击区分、连戳计数）、`pet/chatter.py`（闲聊调度 + 台词文件）、`pet/sessions.py`（多会话汇总）。`motion.choose_pose` 认识互动反应的立绘。`pet.pyw` 只把鼠标事件、时间、会话文件交给它们，再用已有的 `say()` 说话。

**Tech Stack:** Python 3.14、tkinter、Pillow 12.2，测试用 unittest。

**Spec:** `docs/superpowers/specs/2026-10-29-desk-pet-polish-design.md`（本计划实现其中的「C 互动」）

**前置:** B 动画（`plans/2026-10-29-b-animation.md`）已完成：`shy.png`、`poked.png` 已在 `pet/sprites/`；`Pet.say(text, seconds, sprite)`、`motion.choose_pose(..., speech=...)`、`render`/`bubble.layout(..., sub=...)` 可用。

## Global Constraints

- 只支持 Windows；不新增第三方依赖；测试 `python -m unittest discover -s tests`，输出不能有警告；中文注释、frozen dataclass、纯函数、不改动入参。
- 摸头：鼠标不按键，在立绘上部 1/4 来回划，1.5 秒内水平反转 3 次；`shy` 约 2 秒；冷却 5 秒。
- 戳：单击后等 0.3 秒没有第二下才算戳（双击仍是叫出 Claude 窗口）；`poked` 约 1.5 秒；5 秒内戳 4 下及以上生气，用 `remind-3` 约 3 秒；之后 5 秒内再戳只说"哼"不换姿势。
- 优先级：提醒休息时单击 = 我去休息了；睡着（`idle`）时戳、摸、拎起都会把她叫醒。
- 闲聊：每 15～30 分钟一句，只在 Claude 等你回复（`waiting`）、没有临时说话、没提醒休息、没隐藏时开口；每句约 5 秒；同一句不连续出现；当天第一次出现时问候；12:00、18:00 各提醒一次吃饭；右键菜单「闲聊」开关，设置项 `chat`（默认开）。台词在 `pet/lines.json`，读不出来用内置的兜底并记一次日志。
- 多会话：进行中 = 最近 30 分钟内有更新；姿势和第一行跟着最新会话；进行中会话 ≥ 2 个时显示第二行小字 `<当前项目> · <其他会话摘要>`，摘要优先级 出错 > 在等你 > 在忙。

### 与 spec 的差异（本计划的决定）

- spec C3 的"跟工作有关"台词用插件写入的 `todayMs`（当天累计时长）。这要改 `hooks/register.ts`，而项目没有 TS 测试；本计划只用项目名（`{project}` 占位符），不改插件。以后需要时长再加。
- `/pet chat on|off` 属于 E 的 `/pet` 命令，留给 E 计划；本计划只做右键菜单开关和设置项。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `pet/interact.py`（新） | 摸头手势、单击/双击、连戳 → 反应 |
| `pet/chatter.py`（新） | 闲聊调度、读台词文件 |
| `pet/lines.json`（新） | 台词 |
| `pet/sessions.py`（新） | 多会话汇总 |
| `pet/motion.py`（改） | `REACTION_SPRITES`：反应 → 立绘 |
| `pet/pet.pyw`（改） | 接线 |
| `tests/test_interact.py`、`test_chatter.py`、`test_sessions.py`（新）；`test_motion.py`（改） | 测试 |
| `README.md`（改） | 文档 |

---

### Task 1: 互动、闲聊、多会话三个纯函数模块

**Files:**
- Create: `pet/interact.py`、`pet/chatter.py`、`pet/lines.json`、`pet/sessions.py`
- Modify: `pet/motion.py`
- Create: `tests/test_interact.py`、`tests/test_chatter.py`、`tests/test_sessions.py`
- Modify: `tests/test_motion.py`

**Interfaces:**
- Produces:
  - `interact.Touch`（frozen dataclass，全部字段有默认值）；`interact.on_move(s, t, x, in_head) -> (Touch, str | None)`；`interact.on_click(s, t) -> Touch`；`interact.on_double(s) -> Touch`；`interact.on_tick(s, t) -> (Touch, str | None)`。反应是 `'pet' | 'poke' | 'angry' | 'huff'`。常量 `HEAD_SHARE = 0.25`、`REACT_S = {'pet': 2.0, 'poke': 1.5, 'angry': 3.0, 'huff': 1.5}`
  - `chatter.Chatter`、`chatter.Context(now: float, date: str, hour: int, quiet: bool, project: str)`；`chatter.start(now, rng) -> Chatter`；`chatter.next_line(c, ctx, lines, rng) -> (Chatter, str | None)`；`chatter.pick(pool, last, rng) -> str`；`chatter.load_lines(path) -> (dict, str | None)`；`chatter.DEFAULT_LINES`；常量 `CHAT_SHOW_S = 5.0`
  - `sessions.Session(mtime: float, state: str, text: str, project: str)`；`sessions.Summary(latest: Session | None, sub: str | None)`；`sessions.summarize(items, now) -> Summary`；常量 `ACTIVE_S = 1800`
  - `motion.REACTION_SPRITES = {'pet': 'shy', 'poke': 'poked', 'angry': 'remind-3'}`；`choose_pose(..., speech='pet')` 返回 `shy` 等

- [ ] **Step 1: 写失败的测试**

`tests/test_interact.py`：

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from interact import Touch, on_click, on_double, on_move, on_tick  # noqa: E402


def rub(s, t0, xs, dt=0.1, in_head=True):
    """在头上按 xs 依次移动；返回 (最后的状态, 所有反应)。"""
    out = []
    for i, x in enumerate(xs):
        s, r = on_move(s, t0 + i * dt, x, in_head)
        if r:
            out.append(r)
    return s, out


class PetTest(unittest.TestCase):
    def test_three_turns_on_the_head_is_a_pet(self):
        _, rs = rub(Touch(), 0.0, [0, 20, 0, 20, 0])
        self.assertEqual(rs, ['pet'])

    def test_moving_one_way_is_not_a_pet(self):
        _, rs = rub(Touch(), 0.0, [0, 20, 40, 60, 80, 100])
        self.assertEqual(rs, [])

    def test_too_slow_does_not_count(self):
        _, rs = rub(Touch(), 0.0, [0, 20, 0, 20, 0], dt=1.0)
        self.assertEqual(rs, [])

    def test_not_on_the_head_does_not_count(self):
        _, rs = rub(Touch(), 0.0, [0, 20, 0, 20, 0], in_head=False)
        self.assertEqual(rs, [])

    def test_tiny_jitter_is_ignored(self):
        _, rs = rub(Touch(), 0.0, [0, 1, 0, 1, 0, 1, 0])
        self.assertEqual(rs, [])

    def test_cooldown_after_a_pet(self):
        s, rs = rub(Touch(), 0.0, [0, 20, 0, 20, 0])
        s, rs2 = rub(s, 1.0, [0, 20, 0, 20, 0])
        self.assertEqual(rs2, [])
        _, rs3 = rub(s, 6.0, [0, 20, 0, 20, 0])
        self.assertEqual(rs3, ['pet'])


class PokeTest(unittest.TestCase):
    def test_single_click_becomes_a_poke_after_the_wait(self):
        s = on_click(Touch(), 1.0)
        s, r = on_tick(s, 1.2)
        self.assertIsNone(r)
        s, r = on_tick(s, 1.31)
        self.assertEqual(r, 'poke')
        self.assertEqual(on_tick(s, 2.0)[1], None)  # 只算一次

    def test_double_click_is_not_a_poke(self):
        s = on_click(Touch(), 1.0)
        s = on_double(s)
        s = on_click(s, 1.15)   # 双击的第二下松开也会来一次，要忽略
        _, r = on_tick(s, 2.0)
        self.assertIsNone(r)

    def test_four_pokes_in_five_seconds_makes_her_angry(self):
        s, rs = Touch(), []
        for i in range(4):
            s = on_click(s, i * 1.0)
            s, r = on_tick(s, i * 1.0 + 0.5)
            rs.append(r)
        self.assertEqual(rs, ['poke', 'poke', 'poke', 'angry'])

    def test_after_angry_pokes_only_get_a_huff(self):
        s = Touch()
        for i in range(4):
            s, _ = on_tick(on_click(s, i * 1.0), i * 1.0 + 0.5)
        s, r = on_tick(on_click(s, 5.0), 5.5)
        self.assertEqual(r, 'huff')
        s, r = on_tick(on_click(s, 20.0), 20.5)
        self.assertEqual(r, 'poke')

    def test_slow_pokes_never_anger(self):
        s, rs = Touch(), []
        for i in range(6):
            s, r = on_tick(on_click(s, i * 3.0), i * 3.0 + 0.5)
            rs.append(r)
        self.assertNotIn('angry', rs)


if __name__ == '__main__':
    unittest.main()
```

`tests/test_chatter.py`：

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from chatter import (  # noqa: E402
    CHAT_EVERY, DEFAULT_LINES, Chatter, Context, load_lines, next_line, pick, start,
)


class FixedRng:
    def __init__(self, u=None):
        self.u = u

    def uniform(self, a, b):
        return a if self.u is None else self.u

    def choice(self, seq):
        return seq[0]


LINES = {
    'greet': {'morning': ['早'], 'afternoon': ['午'], 'evening': ['晚']},
    'meal': ['吃饭'], 'chat': ['一', '二'], 'work': ['在写 {project}'],
    'pet': ['嘿嘿'], 'poke': ['呀'], 'angry': ['哼！'], 'huff': ['哼'],
}


def ctx(now=0.0, date='2026-10-29', hour=10, quiet=False, project='p'):
    return Context(now=now, date=date, hour=hour, quiet=quiet, project=project)


class NextLineTest(unittest.TestCase):
    def test_first_line_of_the_day_is_a_greeting(self):
        c, line = next_line(start(0.0, FixedRng()), ctx(hour=9), LINES, FixedRng())
        self.assertEqual(line, '早')
        self.assertEqual(next_line(c, ctx(now=1.0, hour=9), LINES, FixedRng())[1], None)

    def test_greeting_depends_on_the_hour(self):
        self.assertEqual(next_line(start(0.0, FixedRng()), ctx(hour=14), LINES, FixedRng())[1], '午')
        self.assertEqual(next_line(start(0.0, FixedRng()), ctx(hour=21), LINES, FixedRng())[1], '晚')

    def test_quiet_means_no_line_at_all(self):
        self.assertEqual(next_line(start(0.0, FixedRng()), ctx(quiet=True), LINES, FixedRng())[1], None)

    def test_meal_reminder_once_per_meal(self):
        c, _ = next_line(start(0.0, FixedRng()), ctx(hour=11), LINES, FixedRng())   # 先问候
        c, line = next_line(c, ctx(now=10.0, hour=12), LINES, FixedRng())
        self.assertEqual(line, '吃饭')
        self.assertIsNone(next_line(c, ctx(now=20.0, hour=12), LINES, FixedRng())[1])

    def test_chat_after_the_interval_and_not_before(self):
        c, _ = next_line(start(0.0, FixedRng()), ctx(), LINES, FixedRng())
        self.assertIsNone(next_line(c, ctx(now=CHAT_EVERY[0] - 1), LINES, FixedRng())[1])
        _, line = next_line(c, ctx(now=CHAT_EVERY[0] + 1), LINES, FixedRng())
        self.assertIn(line, ['一', '二', '在写 p'])

    def test_project_fills_the_work_placeholder(self):
        lines = {**LINES, 'chat': []}
        c, _ = next_line(start(0.0, FixedRng()), ctx(), lines, FixedRng())
        _, line = next_line(c, ctx(now=CHAT_EVERY[1] + 1, project='claude-desk-pet'), lines, FixedRng())
        self.assertEqual(line, '在写 claude-desk-pet')

    def test_no_project_skips_work_lines(self):
        lines = {**LINES, 'chat': ['一']}
        c, _ = next_line(start(0.0, FixedRng()), ctx(), lines, FixedRng())
        _, line = next_line(c, ctx(now=CHAT_EVERY[1] + 1, project=''), lines, FixedRng())
        self.assertEqual(line, '一')


class PickTest(unittest.TestCase):
    def test_does_not_repeat_the_last_line(self):
        self.assertEqual(pick(['一', '二'], '一', FixedRng()), '二')

    def test_single_line_may_repeat(self):
        self.assertEqual(pick(['一'], '一', FixedRng()), '一')


class LoadLinesTest(unittest.TestCase):
    def test_missing_file_gives_defaults_and_an_error(self):
        lines, err = load_lines(os.path.join(tempfile.gettempdir(), 'no-such-lines.json'))
        self.assertEqual(lines, DEFAULT_LINES)
        self.assertIsNotNone(err)

    def test_file_overrides_defaults_key_by_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'lines.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'chat': ['自定义']}, f, ensure_ascii=False)
            lines, err = load_lines(p)
        self.assertIsNone(err)
        self.assertEqual(lines['chat'], ['自定义'])
        self.assertEqual(lines['poke'], DEFAULT_LINES['poke'])

    def test_bundled_file_loads_cleanly(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet', 'lines.json')
        lines, err = load_lines(path)
        self.assertIsNone(err)
        for key in ('greet', 'meal', 'chat', 'work', 'pet', 'poke', 'angry', 'huff'):
            self.assertTrue(lines[key])


if __name__ == '__main__':
    unittest.main()
```

`tests/test_sessions.py`：

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from sessions import ACTIVE_S, Session, Summary, summarize  # noqa: E402

NOW = 10_000.0


def s(age, state='tool', project='a', text=''):
    return Session(mtime=NOW - age, state=state, text=text, project=project)


class SummarizeTest(unittest.TestCase):
    def test_nothing(self):
        self.assertEqual(summarize([], NOW), Summary(None, None))

    def test_one_session_has_no_second_line(self):
        a = s(5)
        self.assertEqual(summarize([a], NOW), Summary(a, None))

    def test_latest_wins_and_others_are_summarised(self):
        a, b = s(5, project='a'), s(60, state='tool', project='b')
        self.assertEqual(summarize([b, a], NOW), Summary(a, 'a · 另有 1 个在忙'))

    def test_waiting_beats_busy(self):
        a, b, c = s(5, project='a'), s(60, project='b'), s(90, state='waiting', project='c')
        self.assertEqual(summarize([a, b, c], NOW).sub, 'a · c 在等你')

    def test_several_waiting(self):
        a, b, c = s(5, project='a'), s(60, state='waiting', project='b'), s(90, state='waiting', project='c')
        self.assertEqual(summarize([a, b, c], NOW).sub, 'a · 2 个会话在等你')

    def test_error_beats_waiting(self):
        a, b, c = s(5), s(60, state='waiting', project='b'), s(90, state='error', project='c')
        self.assertEqual(summarize([a, b, c], NOW).sub, 'a · c 出错了')

    def test_stale_sessions_are_ignored(self):
        a, old = s(5), s(ACTIVE_S + 1, state='waiting', project='old')
        self.assertEqual(summarize([a, old], NOW).sub, None)

    def test_unnamed_project(self):
        a, b = s(5, project=''), s(60, state='waiting', project='')
        self.assertEqual(summarize([a, b], NOW).sub, '当前会话 · 另一个会话 在等你')


if __name__ == '__main__':
    unittest.main()
```

在 `tests/test_motion.py` 的 `ChoosePoseTest` 里加：

```python
    def test_reactions_use_their_own_sprites(self):
        self.assertEqual(self.pose(self.perched(), speech='pet').file, 'shy')
        self.assertEqual(self.pose(self.perched(), speech='poke').file, 'poked')
        self.assertEqual(self.pose(self.perched(), speech='angry').file, 'remind-3')
        self.assertEqual(choose_pose(None, 0.0, 'tool', 0.0, speech='poke', roam=False).file, 'poked')
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_interact tests.test_chatter tests.test_sessions tests.test_motion -v`
Expected: FAIL（三个新模块 `ModuleNotFoundError`；`test_reactions_use_their_own_sprites` 拿到 `smile`）

- [ ] **Step 3: 实现 `pet/interact.py`**

```python
"""摸头、戳她：把鼠标事件变成"反应"。纯函数，时间和坐标由调用方给。

反应：'pet' 摸头、'poke' 戳一下、'angry' 连戳生气、'huff' 生完气后再戳只哼一声。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

HEAD_SHARE = 0.25     # 立绘上部这么多算"头"
MIN_STEP = 3          # 鼠标一次至少动这么多像素才算方向（防抖）
PET_TURNS = 3         # 来回反转几次算摸头
PET_WINDOW = 1.5      # 这几次反转要在多少秒内
PET_COOLDOWN = 5.0    # 摸完一次，多久之内不再触发
CLICK_WAIT = 0.3      # 单击后等多久没有第二下，才算戳（不是双击）
POKE_ANGRY = 4        # 多少下算连戳
POKE_WINDOW = 5.0     # 连戳要在多少秒内
CALM_S = 5.0          # 生完气（3 秒）以后，再过多久才消气
REACT_S = {'pet': 2.0, 'poke': 1.5, 'angry': 3.0, 'huff': 1.5}   # 每种反应维持多久


@dataclass(frozen=True)
class Touch:
    last_x: float | None = None     # 头上上一次的鼠标横坐标
    last_dir: int = 0               # 上一次移动的方向（1 右、-1 左）
    turns: tuple = ()               # 最近几次方向反转的时刻
    pet_cool_until: float = 0.0
    click_at: float | None = None   # 还没确认是不是戳的那次单击
    ignore_click: bool = False      # 双击之后紧跟的那次松开不算单击
    pokes: tuple = ()               # 最近几次戳的时刻
    calm_until: float = 0.0         # 生气期间到这个时刻为止，再戳只哼一声


def on_move(s: Touch, t: float, x: float, in_head: bool):
    """鼠标（没按键）移动了一下。返回 (新状态, 'pet' 或 None)。"""
    if not in_head:
        return replace(s, last_x=None, last_dir=0, turns=()), None
    if s.last_x is None:
        return replace(s, last_x=x), None
    dx = x - s.last_x
    if abs(dx) < MIN_STEP:
        return s, None
    d = 1 if dx > 0 else -1
    turns = s.turns
    if s.last_dir and d != s.last_dir:
        turns = tuple(tt for tt in turns + (t,) if t - tt <= PET_WINDOW)
    s = replace(s, last_x=x, last_dir=d, turns=turns)
    if len(turns) >= PET_TURNS and t >= s.pet_cool_until:
        return replace(s, turns=(), pet_cool_until=t + PET_COOLDOWN), 'pet'
    return s, None


def on_click(s: Touch, t: float) -> Touch:
    """一次没拖动的松开。先记下来，等 CLICK_WAIT 秒确认不是双击。"""
    if s.ignore_click:
        return replace(s, ignore_click=False)
    return replace(s, click_at=t)


def on_double(s: Touch) -> Touch:
    """双击：取消等待中的单击，并忽略紧跟着的那次松开。"""
    return replace(s, click_at=None, ignore_click=True)


def on_tick(s: Touch, t: float):
    """定时调用：单击等够了就变成一次戳。返回 (新状态, 'poke' / 'angry' / 'huff' 或 None)。"""
    if s.click_at is None or t - s.click_at < CLICK_WAIT:
        return s, None
    at = s.click_at
    pokes = tuple(p for p in s.pokes + (at,) if at - p <= POKE_WINDOW)
    s = replace(s, click_at=None, pokes=pokes)
    if at < s.calm_until:
        return s, 'huff'
    if len(pokes) >= POKE_ANGRY:
        return replace(s, pokes=(), calm_until=at + REACT_S['angry'] + CALM_S), 'angry'
    return s, 'poke'
```

- [ ] **Step 4: 实现 `pet/chatter.py` 和 `pet/lines.json`**

`pet/chatter.py`：

```python
"""闲聊：当天第一次见面问候、饭点提醒吃饭、平时每 15～30 分钟随口一句。纯函数，时间、随机数由调用方给。

台词在 pet/lines.json，可以随便改；读不出来就用这里的 DEFAULT_LINES。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace

CHAT_EVERY = (15 * 60.0, 30 * 60.0)   # 两句闲聊之间隔多久（秒）
MEAL_HOURS = (12, 18)                 # 这两个整点提醒吃饭
CHAT_SHOW_S = 5.0                     # 一句话显示多久

DEFAULT_LINES = {
    'greet': {'morning': ['早上好～'], 'afternoon': ['下午好～'], 'evening': ['晚上好～']},
    'meal': ['到饭点啦，先去吃饭吧～'],
    'chat': ['今天也辛苦啦', '要不要喝口水？'],
    'work': ['今天也在写 {project} 呀'],
    'pet': ['嘿嘿…'],
    'poke': ['呀！'],
    'angry': ['不许再戳了！'],
    'huff': ['哼'],
}


@dataclass(frozen=True)
class Chatter:
    next_at: float              # 下一次随口闲聊的时刻
    greeted_on: str = ''        # 已经问候过的日期（YYYY-MM-DD）
    meals_on: tuple = ()        # 已经提醒过的 (日期, 整点)
    last: str = ''              # 上一句说的话，免得连着说同一句


@dataclass(frozen=True)
class Context:
    now: float
    date: str        # 本地日期 YYYY-MM-DD
    hour: int        # 本地小时 0～23
    quiet: bool      # 现在不该说话（Claude 在忙、在提醒休息、正在说别的、藏起来了、闲聊关了）
    project: str     # 当前会话的项目名，可以是空的


def start(now: float, rng) -> Chatter:
    return Chatter(next_at=now + rng.uniform(*CHAT_EVERY))


def _period(hour: int) -> str:
    if 5 <= hour < 11:
        return 'morning'
    if 11 <= hour < 18:
        return 'afternoon'
    return 'evening'


def pick(pool: list, last: str, rng) -> str:
    """随机挑一句；有得选的时候不挑上一句。"""
    options = [p for p in pool if p != last] or list(pool)
    return rng.choice(options)


def next_line(c: Chatter, ctx: Context, lines: dict, rng):
    """现在要不要说一句。返回 (新状态, 这句话或 None)。"""
    if ctx.quiet:
        return c, None
    if c.greeted_on != ctx.date:
        line = pick(lines['greet'][_period(ctx.hour)], c.last, rng)
        return replace(c, greeted_on=ctx.date, last=line), line
    if ctx.hour in MEAL_HOURS and (ctx.date, ctx.hour) not in c.meals_on:
        line = pick(lines['meal'], c.last, rng)
        return replace(c, meals_on=c.meals_on + ((ctx.date, ctx.hour),), last=line), line
    if ctx.now >= c.next_at:
        pool = list(lines['chat'])
        if ctx.project:
            pool += [w.format(project=ctx.project) for w in lines['work']]
        if pool:
            line = pick(pool, c.last, rng)
            return replace(c, next_at=ctx.now + rng.uniform(*CHAT_EVERY), last=line), line
        return replace(c, next_at=ctx.now + rng.uniform(*CHAT_EVERY)), None
    return c, None


def load_lines(path: str):
    """读台词文件，按键覆盖 DEFAULT_LINES。返回 (台词, 出错信息或 None)；出错时台词就是 DEFAULT_LINES。"""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError('台词文件最外层应该是一个对象')
        return {**DEFAULT_LINES, **data}, None
    except Exception as err:  # 文件缺了、格式坏了，都退回内置台词
        return DEFAULT_LINES, f'{path}: {err}'
```

`pet/lines.json`：

```json
{
  "greet": {
    "morning": ["早上好～今天也一起加油！", "早安！睡得好吗？"],
    "afternoon": ["下午好～", "下午也要元气满满哦"],
    "evening": ["晚上好～今天辛苦啦", "晚上也在忙呀？别太晚哦"]
  },
  "meal": ["到饭点啦，先去吃饭吧～", "肚子饿了没？吃完再写～"],
  "chat": ["今天也辛苦啦", "要不要喝口水？", "坐久了起来伸个懒腰吧", "我一直在这儿陪你哦", "眼睛累了就看看远处～"],
  "work": ["今天也在写 {project} 呀", "{project} 进展怎么样啦？"],
  "pet": ["嘿嘿…", "再摸就要长不高了！", "好舒服～"],
  "poke": ["呀！", "干嘛啦～", "戳我做什么？"],
  "angry": ["不许再戳了！", "生气了！哼！"],
  "huff": ["哼", "不理你了"]
}
```

- [ ] **Step 5: 实现 `pet/sessions.py`**

```python
"""多个会话同时开着时，桌宠跟着最新的那个，再用一行小字说说别的会话：有出错的先报出错，其次在等你的，最后在忙的。"""
from __future__ import annotations

from dataclasses import dataclass

ACTIVE_S = 30 * 60.0   # 最近这么久有更新的会话才算"进行中"


@dataclass(frozen=True)
class Session:
    mtime: float
    state: str
    text: str
    project: str


@dataclass(frozen=True)
class Summary:
    latest: Session | None   # 最新的会话（不管进行中与否），姿势和第一行跟着它
    sub: str | None          # 第二行小字；只有一个会话在进行时是 None


def summarize(items: list, now: float) -> Summary:
    if not items:
        return Summary(None, None)
    latest = max(items, key=lambda s: s.mtime)
    others = [s for s in items if s is not latest and now - s.mtime <= ACTIVE_S]
    if now - latest.mtime > ACTIVE_S or not others:
        return Summary(latest, None)
    head = latest.project or '当前会话'
    errors = [s for s in others if s.state in ('error', 'stone')]
    waiting = [s for s in others if s.state == 'waiting']
    if errors:
        tail = f'{errors[0].project or "另一个会话"} 出错了'
    elif len(waiting) == 1:
        tail = f'{waiting[0].project or "另一个会话"} 在等你'
    elif waiting:
        tail = f'{len(waiting)} 个会话在等你'
    else:
        tail = f'另有 {len(others)} 个在忙'
    return Summary(latest, f'{head} · {tail}')
```

- [ ] **Step 6: 改 `pet/motion.py`**

在 `EVENT_STANDING = {...}` 那一行之后加：

```python
REACTION_SPRITES = {'pet': 'shy', 'poke': 'poked', 'angry': 'remind-3'}   # 摸头、戳、连戳生气时的立绘
```

`_fixed` 替换为：

```python
def _fixed(state: str) -> str:
    return REACTION_SPRITES.get(state) or FIXED_SPRITES.get(state, 'smile')
```

- [ ] **Step 7: 跑测试，确认通过**

Run: `python -m unittest tests.test_interact tests.test_chatter tests.test_sessions tests.test_motion -v`
Expected: 全部 PASS
Run: `python -m unittest discover -s tests` — Expected: 全部通过，没有警告

- [ ] **Step 8: Commit**

```bash
git add pet/interact.py pet/chatter.py pet/lines.json pet/sessions.py pet/motion.py tests/test_interact.py tests/test_chatter.py tests/test_sessions.py tests/test_motion.py
git commit -m "feat: petting and poking gestures, idle chatter and a multi-session summary"
```

---

### Task 2: 接到桌宠上

**Files:**
- Modify: `pet/pet.pyw`

**Interfaces:**
- Consumes: Task 1 的全部接口；B 的 `Pet.say`、`Pet.apply_pose`、`frame` 里的 `sprite_bottom`；`bubble.layout(text, measure, max_w, sub)`
- Produces（E 计划会用）: `Pet.react(kind)`、`Pet.chat_var`、`Pet.sub`

没有新的单元测试（界面接线），靠全部测试 + 手动冒烟。

- [ ] **Step 1: 导入、常量、立绘**

在 `from effects import zz_marks` 之后加：

```python
from chatter import CHAT_SHOW_S, Context, load_lines, next_line, pick, start as start_chatter  # noqa: E402
from interact import HEAD_SHARE, REACT_S, Touch, on_click, on_double as touch_double, on_move, on_tick  # noqa: E402
from sessions import Session, summarize  # noqa: E402
```

`SPRITE_FILES` 的集合里再加 `'shy', 'poked'`。

在 `PATCHES = ...` 之后加：

```python
LINES = os.path.join(HERE, 'lines.json')   # 台词，可以随便改
```

- [ ] **Step 2: 读全部会话**

把 `read_latest` 整个替换为：

```python
def read_sessions():
    """读所有会话的状态；顺手清掉两天前的旧文件。"""
    out, now = [], time.time()
    for p in glob.glob(os.path.join(SESSIONS, '*.json')):
        try:
            mtime = os.path.getmtime(p)
            if now - mtime > 2 * 86400:
                os.remove(p)
                continue
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
            out.append(Session(mtime=mtime, state=str(data.get('state', 'waiting')), text=str(data.get('text', '')),
                               project=str(data.get('project', ''))))
        except Exception:
            continue
    return out
```

`poll` 整个替换为：

```python
    def poll(self):
        summary = summarize(read_sessions(), time.time())
        self.sub = summary.sub
        latest = summary.latest
        if latest and latest.mtime != self.last_mtime:
            self.last_mtime_seen, self.last_mtime = self.last_mtime, latest.mtime
            state = latest.state if latest.state in FIXED_SPRITES else 'waiting'
            changed = state != self.state
            self.state, self.text, self.project = state, latest.text, latest.project
            self.state_since = time.time()
            self.on_state_file(latest)
            if changed:
                self.hop_at = time.time()
            self.refresh()
        self.root.after(250, self.poll)

    def on_state_file(self, latest):
        """会话文件里带的提示音（刚启动时不重播旧的）。"""
        try:
            with open(max(glob.glob(os.path.join(SESSIONS, '*.json')), key=os.path.getmtime), encoding='utf-8') as f:
                sound = json.load(f).get('sound')
        except Exception:
            return
        if sound in ('done', 'error') and self.last_mtime_seen:
            self.play(sound)
```

（`Session` 不带 `sound` 字段，提示音单独从最新的文件里读，保持原有行为。）

- [ ] **Step 3: `__init__` 里加状态、绑定鼠标移动**

在 `self.blink = start_blink(time.time(), random)` 之后加：

```python
        self.sub = None                # 多会话时气泡里的第二行小字
        self.touch = Touch()           # 摸头、戳的识别状态
        self.lines, err = load_lines(LINES)
        if err:
            self.log_once(err)
        self.chatter = start_chatter(time.time(), random)
        self.sprite_box = (0, 0, 0)    # 上一帧立绘在窗口里的 (左, 上, 高)，判断鼠标是不是在头上
```

在 `self.canvas.bind('<Double-Button-1>', self.on_double)` 之后加：

```python
        self.canvas.bind('<Motion>', self.on_motion)
```

在 `self.watch_break()` 之后加：

```python
        self.watch_chat()
```

在 `log_error` 函数之后（模块级）不用改；在 `Pet` 类里 `display_text` 之前加：

```python
    def log_once(self, message):
        """记一条不是异常的错误（比如台词文件坏了）。"""
        try:
            raise RuntimeError(message)
        except RuntimeError:
            log_error()
```

- [ ] **Step 4: 菜单加「闲聊」**

在 `self.menu.add_checkbutton(label='提示音', ...)` 那一行之后加：

```python
        self.chat_var = tk.BooleanVar(value=self.settings.get('chat', True) is not False)
        self.menu.add_checkbutton(label='闲聊', variable=self.chat_var, command=self.toggle_chat)
```

在 `toggle_sound` 之后加：

```python
    def toggle_chat(self):
        self.settings['chat'] = self.chat_var.get()
        save_settings(self.settings)
```

- [ ] **Step 5: 反应和闲聊**

在 `acknowledge_break` 之前加：

```python
    def wake(self):
        """她睡着了（等你太久）的话把她叫醒：当作你刚回来，重新开始计时。"""
        if self.claude_state() == 'idle':
            self.state_since = time.time()

    def react(self, kind):
        """摸头、戳、连戳生气、哼：说一句，换上对应的立绘（'huff' 不换）。"""
        self.wake()
        line = pick(self.lines.get(kind) or [''], '', random)
        self.say(line, REACT_S[kind], None if kind == 'huff' else kind)

    def watch_chat(self):
        try:
            now = time.time()
            local = time.localtime(now)
            quiet = (not self.chat_var.get() or self.hidden or self.claude_state() != 'waiting'
                     or self.break_state.level or self.speech_state() is not None
                     or (self.speech and now < self.speech[1]))
            ctx = Context(now=now, date=time.strftime('%Y-%m-%d', local), hour=local.tm_hour, quiet=bool(quiet),
                          project=self.project)
            self.chatter, line = next_line(self.chatter, ctx, self.lines, random)
            if line:
                self.say(line, CHAT_SHOW_S)
        except Exception:
            log_error()
        finally:
            self.root.after(5000, self.watch_chat)
```

- [ ] **Step 6: 鼠标事件**

在 `on_drag` 里，`if self.moved and self.roam and self.motion:` 这一行之前加：

```python
        if self.moved:
            self.wake()  # 拎起来就醒了
```

`on_release` 里，把：

```python
        if not self.moved and self.break_state.level:
            self.acknowledge_break()  # 提醒的时候点她一下，就是"我去休息了"
```

替换为：

```python
        if not self.moved:
            if self.break_state.level:
                self.acknowledge_break()  # 提醒的时候点她一下，就是"我去休息了"
            else:
                self.touch = on_click(self.touch, time.time())  # 等一下，确认不是双击再算戳
```

`on_double` 的第一行（注释之后）加：

```python
        self.touch = touch_double(self.touch)
```

在 `on_double` 之后加：

```python
    def on_motion(self, e):
        """鼠标在她身上（没按键）移动：在头上来回划就是摸头。"""
        if self.drag is not None:
            return
        left, top, h = self.sprite_box
        in_head = h > 0 and top <= e.y <= top + HEAD_SHARE * h
        self.touch, r = on_move(self.touch, time.time(), e.x, in_head)
        if r:
            self.react(r)
```

- [ ] **Step 7: `frame` 里推进戳的判定、记下立绘位置、把第二行交给气泡**

在 `frame` 里 `self.blink = step_blink(...)` 之前加：

```python
        self.touch, r = on_tick(self.touch, t)
        if r:
            self.react(r)
```

在 `sprite_bottom = (...)` 计算之后加：

```python
        self.sprite_box = (0, sprite_bottom - img.height, img.height)
```

把 `image = compose(img, sprite_bottom, self.bubble_for(text), ...)` 里的 `self.bubble_for(text)` 改成 `self.bubble_for(text, self.bubble_sub())`，并在 `display_text` 之后加：

```python
    def bubble_sub(self):
        """第二行小字：只在显示 Claude 的状态时出现（临时说话、提醒休息时不出现）。"""
        if self.speech_state() is not None or (self.speech and time.time() < self.speech[1]) or self.break_state.level:
            return None
        return self.sub
```

`bubble_for` 替换为：

```python
    def bubble_for(self, text, sub=None):
        """这句话（和第二行小字）的气泡图；同样的内容只画一次。"""
        key = (text, sub)
        if key not in self.bubble_cache:
            if len(self.bubble_cache) >= BUBBLE_CACHE:
                self.bubble_cache = {}
            # 10 是气泡左右内边距（见 render.bubble_image）
            lay = layout(text, self.style.measure, round(BUBBLE_MAX_W * self.scale) - 2 * self.style.px(10), sub)
            self.bubble_cache[key] = bubble_image(lay, self.style)
        return self.bubble_cache[key]
```

（保留现有 `bubble_for` 里关于内边距的那行注释的意思；如果现有代码的写法和这里不同，按现有写法只加 `sub` 参数和缓存键。）

- [ ] **Step 8: 检查**

Run: `python -m py_compile pet/pet.pyw` — Expected: 没有输出
Run: `grep -n "read_latest" pet/pet.pyw` — Expected: 没有输出
Run: `python -m unittest discover -s tests` — Expected: 全部通过

- [ ] **Step 9: 手动冒烟（controller 做，实现者跳过）**

```bash
D="$TEMP/cdp_smoke_c"; mkdir -p "$D/sessions"
echo '{"state": "waiting", "text": "轮到你啦！", "project": "claude-desk-pet", "ts": 0}' > "$D/sessions/a.json"
echo '{"state": "waiting", "text": "轮到你啦！", "project": "sts2-ai", "ts": 0}' > "$D/sessions/b.json"
touch "$D/sessions/a.json"
DESK_PET_PORT=47399 python pet/pet.pyw "$D"
```

确认：一出现就问候一句；气泡第二行是「claude-desk-pet · sts2-ai 在等你」；单击她 0.3 秒后露出被戳的表情；连戳 4 下生气；在头上来回划露出害羞表情；双击不算戳。

- [ ] **Step 10: Commit**

```bash
git add pet/pet.pyw
git commit -m "feat: pet and poke her, idle chatter, and a second line for other sessions"
```

---

### Task 3: 文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README**

在「**双击**桌宠：把 Claude 窗口叫到前台」那一条之前加：

```markdown
- **单击**她：戳一下，她会有反应；连着戳会生气哦
- 鼠标在她**头上来回划**：摸头，她会害羞
- 她偶尔会主动说话：早上问好、饭点提醒吃饭、平时随口聊两句（右键菜单可以关掉「闲聊」）
- 同时开着好几个会话时，气泡下面会多一行小字，告诉你别的会话在等你或者出错了
```

在「自定义」一节"改台词"那一条改为：

```markdown
- **改台词**：Claude 状态的气泡文字写在 `hooks/register.ts` 里；闲聊、摸头、戳她的台词写在 `pet/lines.json` 里
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: petting, poking, chatter and the multi-session line"
```
