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
