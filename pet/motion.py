"""桌宠的"身体"：站在哪、怎么走、怎么跳、该摆什么姿势。

不碰界面和系统接口：pet.pyw 告诉它"现在脚下的平面在哪"（前台窗口的顶边，或者任务栏），
它返回新的位置和模式。所有坐标是屏幕像素，y 向下，(x, y) 是她"脚底/屁股"落地点。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

WANDER_EVERY = (15.0, 40.0)   # 闲着的时候，隔多少秒晃悠到别的位置
WANDER_RANGE = (0.1, 0.9)     # 在窗口顶边的哪一段晃悠（比例）
WANDER_MIN_STEP = 0.15
LAND_POSE_S = 0.3             # 落地后摆多久的落地姿势
KNOCK_S = 8.0                 # Claude 刚回复完，她先敲 8 秒门，再坐下晃腿
WALK_FPS = 7.0
WALK_FRAMES = 6               # 走路立绘一个完整步伐的帧数：落地、下压、交叉经过，左右各一遍
SWING_S = 0.9                 # 晃腿每一帧的时长

# 原来的状态 → 立绘（不走动模式，以及"站起来"的事件姿势）
FIXED_SPRITES = {
    'thinking': 'smile-closed',
    'tool': 'typing',
    'reading': 'notes',
    'waiting': 'knock',
    'celebrate': 'confetti',
    'idle': 'smile',
    'error': 'panic',
    'aborted': 'guilty',
    'stone': 'stone',
}
EVENT_STANDING = {'celebrate': 'confetti', 'error': 'panic', 'aborted': 'guilty', 'stone': 'stone'}
# 立绘从上往下数，"屁股坐在窗口边上"那条线的位置（占立绘高度的比例）；站着的立绘是 1.0（脚底）
ANCHOR = {'sit-swing-1': 0.70, 'sit-swing-2': 0.70, 'sit-watch': 0.70, 'typing': 0.80}


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left


@dataclass(frozen=True)
class WinInfo:
    hwnd: int
    rect: Rect
    work: Rect              # 窗口所在显示器的工作区（不含任务栏）
    maximized: bool = False


@dataclass(frozen=True)
class Surface:
    """她能待的一条水平线：窗口的顶边，或者任务栏的上沿。"""
    key: object
    left: float
    right: float
    y: float
    kind: str  # 'window' | 'ground'


@dataclass(frozen=True)
class Jump:
    t0: float
    dur: float
    x0: float
    y0: float
    peak: float


@dataclass(frozen=True)
class Motion:
    mode: str                         # 'perch' 坐着/站着不动 | 'walk' 走 | 'jump' 跳
    x: float
    y: float
    frac: float                       # 在平面上的位置（0 最左，1 最右），平面移动时靠它跟着走
    surface: Surface
    face: int = 1                     # 1 朝右，-1 朝左
    target_frac: float | None = None
    jump: Jump | None = None
    landed_at: float = -1e9
    next_wander: float = 0.0


@dataclass(frozen=True)
class Pose:
    file: str      # pet/sprites/<file>.png
    flip: bool     # 是否水平翻转
    anchor: float  # 立绘里"接触平面"的那条线（占高度的比例）


def _ground(work: Rect) -> Surface:
    return Surface(key=('ground', work.left, work.top), left=float(work.left), right=float(work.right),
                   y=float(work.bottom), kind='ground')


def choose_surface(win: WinInfo | None, fallback_work: Rect, *, need_above: int, margin: int = 24,
                   min_width: int = 240) -> Surface:
    """前台窗口顶边上方放得下她就坐上去，否则（最大化、贴着屏幕顶、太窄、没有窗口）站在任务栏上。"""
    if win is None:
        return _ground(fallback_work)
    r = win.rect
    if win.maximized or r.top - need_above < win.work.top or r.width < min_width:
        return _ground(win.work)
    return Surface(key=win.hwnd, left=float(r.left + margin), right=float(r.right - margin), y=float(r.top),
                   kind='window')


def x_at(surface: Surface, frac: float) -> float:
    return surface.left + frac * (surface.right - surface.left)


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def _next_wander(now: float, rng) -> float:
    return now + rng.uniform(*WANDER_EVERY)


def spawn(surface: Surface, frac: float, now: float, face: int = 1, rng=None) -> Motion:
    rng = rng or random
    return Motion(mode='perch', x=x_at(surface, frac), y=surface.y, frac=frac, surface=surface, face=face,
                  next_wander=_next_wander(now, rng))


def _start_jump(m: Motion, surface: Surface, now: float, scale: float) -> Motion:
    frac = _clamp(m.frac, *WANDER_RANGE)
    dest_x, dest_y = x_at(surface, frac), surface.y
    dist = math.hypot(dest_x - m.x, dest_y - m.y)
    jump = Jump(t0=now, dur=min(1.0, 0.45 + dist / 2500), x0=m.x, y0=m.y, peak=40 * scale + 0.1 * dist)
    return replace(m, mode='jump', frac=frac, surface=surface, face=1 if dest_x >= m.x else -1,
                   target_frac=None, jump=jump)


def _fly(m: Motion, now: float, rng) -> Motion:
    j, s = m.jump, m.surface
    p = _clamp((now - j.t0) / j.dur, 0.0, 1.0)
    dest_x, dest_y = x_at(s, m.frac), s.y  # 终点跟着窗口走：落地前窗口动了也能落准
    if p >= 1.0:
        return replace(m, mode='perch', x=dest_x, y=dest_y, jump=None, landed_at=now,
                       next_wander=_next_wander(now, rng))
    return replace(m, x=j.x0 + (dest_x - j.x0) * p, y=j.y0 + (dest_y - j.y0) * p - 4 * j.peak * p * (1 - p))


def _pick_frac(cur: float, rng) -> float:
    for _ in range(10):
        f = rng.uniform(*WANDER_RANGE)
        if abs(f - cur) >= WANDER_MIN_STEP:
            return f
    return WANDER_RANGE[1] if cur < 0.5 else WANDER_RANGE[0]


def _perch(m: Motion, now: float, can_wander: bool, rng) -> Motion:
    s = m.surface
    m = replace(m, x=x_at(s, m.frac), y=s.y)
    if can_wander and now >= m.next_wander and s.right > s.left:
        f = _pick_frac(m.frac, rng)
        return replace(m, mode='walk', target_frac=f, face=1 if f > m.frac else -1)
    return m


def _walk(m: Motion, now: float, dt: float, speed: float, rng) -> Motion:
    s = m.surface
    tx, step = x_at(s, m.target_frac), speed * dt
    dx = tx - m.x
    if abs(dx) <= step:
        return replace(m, mode='perch', x=tx, y=s.y, frac=m.target_frac, target_frac=None,
                       next_wander=_next_wander(now, rng))
    x = m.x + math.copysign(step, dx)
    width = s.right - s.left
    return replace(m, x=x, y=s.y, frac=(x - s.left) / width if width > 0 else m.frac,
                   face=1 if dx > 0 else -1)


def tick(m: Motion, surface: Surface, now: float, dt: float, *, speed: float = 70.0, scale: float = 1.0,
         can_wander: bool = True, rng=None) -> Motion:
    """走一帧。surface 是她"现在应该待的平面"；平面换了她就跳过去，平面动了她就跟着。"""
    rng = rng or random
    m = _start_jump(m, surface, now, scale) if surface.key != m.surface.key else replace(m, surface=surface)
    if m.mode == 'jump':
        return _fly(m, now, rng)
    if m.mode == 'walk':
        return _walk(m, now, dt, speed, rng)
    return _perch(m, now, can_wander, rng)


def walk_to(m: Motion, frac: float, now: float) -> Motion:
    """命令她走到平面的某个位置（比如休息提醒时走到窗口中间）。跳到一半的时候忽略。"""
    if m.mode == 'jump':
        return m
    frac = _clamp(frac, 0.0, 1.0)
    if abs(frac - m.frac) < 1e-9:
        return m
    return replace(m, mode='walk', target_frac=frac, face=1 if frac > m.frac else -1)


def gait_progress(m: Motion, px_per_frame: float) -> float:
    """走了多远就是走到第几帧：往右走，x 变大帧数往前；往左走（立绘已翻转），x 变小帧数同样往前。"""
    return m.x * m.face / px_per_frame


def _fixed(state: str) -> str:
    return FIXED_SPRITES.get(state, 'smile')


def choose_pose(m: Motion | None, now: float, state: str, state_age: float, remind: int = 0,
                speech: str | None = None, roam: bool = True, px_per_frame: float | None = None) -> Pose:
    """根据"在干嘛"挑立绘。roam=False 是不走动模式：还是原来的状态立绘，全部贴着底边。

    px_per_frame：走路时脚步每前进多少像素换一帧。给了就按走过的距离换帧（脚才不会在地上打滑），
    不给就按时间换帧。
    """
    if not roam or m is None:
        file = _fixed(speech) if speech else f'remind-{remind}' if remind else _fixed(state)
        return Pose(file, False, 1.0)
    if m.mode == 'jump':
        return Pose('jump', m.face < 0, 1.0)
    if now - m.landed_at < LAND_POSE_S:
        return Pose('land', m.face < 0, 1.0)
    if m.mode == 'walk':
        u = gait_progress(m, px_per_frame) if px_per_frame else now * WALK_FPS
        return Pose(f'walk-{1 + math.floor(u) % WALK_FRAMES}', m.face < 0, 1.0)
    if speech:
        return Pose(_fixed(speech), False, 1.0)
    if remind:
        return Pose(f'remind-{remind}', False, 1.0)
    if state in EVENT_STANDING:
        return Pose(EVENT_STANDING[state], False, 1.0)
    if state == 'waiting' and state_age < KNOCK_S:
        return Pose('knock', False, 1.0)
    if state in ('thinking', 'reading'):
        return Pose('sit-watch', m.frac < 0.5, ANCHOR['sit-watch'])  # 在左半边就朝右看，朝着窗口里面
    if state == 'tool':
        return Pose('typing', False, ANCHOR['typing'])
    file = f'sit-swing-{1 + int(now / SWING_S) % 2}'
    return Pose(file, False, ANCHOR[file])
