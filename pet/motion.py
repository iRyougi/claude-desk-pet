"""桌宠的"身体"：站在哪、怎么走、怎么跳、会不会掉下去、该摆什么姿势。

参考 Shimeji 这类桌宠的做法：角色有位置，脚下有"地板"（任何窗口的顶边，或者屏幕底）就站着，没有就下落；
被拿起来就跟着光标走，松手后自由落体，落到下面第一块地板就停住，不会自己"回家"。
窗口只是地板：她站在哪个窗口上，窗口动她就跟着动，窗口没了她就掉下去。

不碰界面和系统接口：pet.pyw 每帧告诉它"现在有哪些地板"，它返回新的位置和模式。
所有坐标是屏幕像素，y 向下，(x, y) 是她"脚底/屁股"落地点。
"""
from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace

WANDER_EVERY = (15.0, 40.0)   # 闲着的时候，隔多少秒晃悠到别的位置
WANDER_RANGE = (0.1, 0.9)     # 在窗口顶边的哪一段晃悠（比例）
WANDER_MIN_STEP = 0.15
SWING_FOR = (3.0, 6.0)        # 一次晃腿持续多久
SWING_EVERY = (20.0, 45.0)    # 两次晃腿之间隔多久。坐着大部分时间是静止的，晃腿只是偶尔抽中的小行为
SWING_S = 0.7                 # 晃腿时每一帧停多久
LAND_POSE_S = 0.3             # 落地后摆多久的落地姿势
KNOCK_S = 8.0                 # Claude 刚回复完，她先敲 8 秒门，再坐下
WALK_FPS = 7.0
WALK_FRAMES = 6               # 走路立绘一个完整步伐的帧数：落地、下压、交叉经过，左右各一遍
GRAVITY = 2600.0              # 像素/秒²（100% 缩放）
TERMINAL = 2600.0             # 最大下落速度，像素/秒
AIR_X = 1.6                   # 被甩出去时水平速度的衰减，1/秒
LAND_TOL = 8.0                # 下落时，地板在这么近的范围内也算接住（窗口可能刚好动了一下）

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
    """她能站的一条水平线：窗口的顶边，或者屏幕底边（任务栏上沿）。"""
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
    mode: str                         # 'perch' 站/坐着 | 'walk' 走 | 'hop' 跳去别处 | 'fall' 下落 | 'held' 被拿着
    x: float
    y: float
    support: object | None            # 她脚下那块地板的 key；下落/被拿着时是 None，'hop' 时是要跳去的那块
    frac: float                       # 在地板上的位置（0 最左，1 最右），地板移动时靠它跟着走
    face: int = 1                     # 1 朝右，-1 朝左
    vx: float = 0.0
    vy: float = 0.0
    target_frac: float | None = None
    jump: Jump | None = None
    landed_at: float = -1e9
    next_wander: float = 0.0
    next_swing: float = 0.0           # 下一次晃腿的时刻
    swing_until: float = 0.0          # 晃腿到什么时候为止（过了就是静坐）


@dataclass(frozen=True)
class Pose:
    file: str      # pet/sprites/<file>.png
    flip: bool     # 是否水平翻转
    anchor: float  # 立绘里"接触地板"的那条线（占高度的比例）


def _ground(work: Rect, within: Rect | None = None, owner: object = None, margin: int = 24) -> Surface:
    """屏幕底边（任务栏上沿）。给了 within，她就只待在那个窗口的左右范围内，不满屏幕乱站。"""
    left, right = float(work.left), float(work.right)
    if within is not None:
        left, right = max(left, within.left + margin), min(right, within.right - margin)
    return Surface(key=('ground', work.left, work.top, owner), left=left, right=right, y=float(work.bottom),
                   kind='ground')


def choose_surface(win: WinInfo | None, fallback_work: Rect, *, need_above: int, margin: int = 24,
                   min_width: int = 240) -> Surface:
    """"跟着当前窗口"时她该去哪：窗口顶边上方放得下她就坐上去；放不下（最大化、贴着屏幕顶），就站在屏幕底边、
    待在这个窗口的左右范围内；窗口太窄或者没有窗口，站在整条屏幕底边。"""
    if win is None:
        return _ground(fallback_work)
    r = win.rect
    if r.width < min_width:
        return _ground(win.work)
    if win.maximized or r.top - need_above < win.work.top:
        return _ground(win.work, within=r, owner=win.hwnd, margin=margin)
    return Surface(key=win.hwnd, left=float(r.left + margin), right=float(r.right - margin), y=float(r.top),
                   kind='window')


def build_surfaces(windows: Sequence[WinInfo], work_areas: Sequence[Rect], margin: int = 24,
                   min_width: int = 240) -> list:
    """所有能站的地板：每块显示器一条屏幕底边，加上每个普通窗口的顶边（最大化的、太窄的不算）。"""
    out = [_ground(work) for work in work_areas]
    for win in windows:
        r = win.rect
        if win.maximized or r.width < min_width:
            continue
        out.append(Surface(key=win.hwnd, left=float(r.left + margin), right=float(r.right - margin),
                           y=float(r.top), kind='window'))
    return out


def x_at(surface: Surface, frac: float) -> float:
    return surface.left + frac * (surface.right - surface.left)


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def _later(now: float, span: tuple, rng) -> float:
    return now + rng.uniform(*span)


def spawn(surface: Surface, frac: float, now: float, face: int = 1, rng=None) -> Motion:
    """直接站在某块地板上。"""
    rng = rng or random
    return Motion(mode='perch', x=x_at(surface, frac), y=surface.y, support=surface.key, frac=frac, face=face,
                  next_wander=_later(now, WANDER_EVERY, rng), next_swing=_later(now, SWING_EVERY, rng))


def drop(x: float, y: float, now: float, vx: float = 0.0, vy: float = 0.0, face: int = 1, rng=None) -> Motion:
    """从半空开始下落。"""
    rng = rng or random
    return Motion(mode='fall', x=x, y=y, support=None, frac=0.5, face=face, vx=vx, vy=vy,
                  next_wander=_later(now, WANDER_EVERY, rng), next_swing=_later(now, SWING_EVERY, rng))


def hold(m: Motion, x: float, y: float) -> Motion:
    """被用户拿起来：位置完全由光标决定，她自己不动。"""
    return replace(m, mode='held', x=x, y=y, support=None, vx=0.0, vy=0.0, jump=None, target_frac=None)


def release(m: Motion, vx: float = 0.0, vy: float = 0.0) -> Motion:
    """用户松手：带着甩出去的速度自由落体。不是被拿着的就什么都不做。"""
    if m.mode != 'held':
        return m
    return replace(m, mode='fall', vx=vx, vy=vy)


def hop_to(m: Motion, surface: Surface, now: float, scale: float = 1.0) -> Motion:
    """起跳，去另一块地板（比如跟着切换过来的前台窗口）。终点跟着那块地板走，落地前它动了也能落准。"""
    frac = _clamp(m.frac, *WANDER_RANGE)
    dist = math.hypot(x_at(surface, frac) - m.x, surface.y - m.y)
    jump = Jump(t0=now, dur=min(1.0, 0.45 + dist / 2500), x0=m.x, y0=m.y, peak=40 * scale + 0.1 * dist)
    return replace(m, mode='hop', support=surface.key, frac=frac, face=1 if x_at(surface, frac) >= m.x else -1,
                   target_frac=None, jump=jump, vx=0.0, vy=0.0)


def walk_to(m: Motion, frac: float, now: float) -> Motion:
    """命令她走到地板的某个位置（比如休息提醒时走到窗口中间）。在空中、被拿着的时候忽略。"""
    if m.mode not in ('perch', 'walk'):
        return m
    frac = _clamp(frac, 0.0, 1.0)
    if abs(frac - m.frac) < 1e-9:
        return m
    return replace(m, mode='walk', target_frac=frac, face=1 if frac > m.frac else -1)


def _land(m: Motion, s: Surface, x: float, now: float, rng) -> Motion:
    width = s.right - s.left
    frac = _clamp((x - s.left) / width, 0.0, 1.0) if width > 0 else 0.5
    return replace(m, mode='perch', x=x, y=s.y, support=s.key, frac=frac, vx=0.0, vy=0.0, jump=None,
                   target_frac=None, landed_at=now, next_wander=_later(now, WANDER_EVERY, rng),
                   next_swing=_later(now, SWING_EVERY, rng))


def _fall(m: Motion, surfaces: Sequence[Surface], now: float, dt: float, scale: float, rng) -> Motion:
    vy = min(m.vy + GRAVITY * scale * dt, TERMINAL * scale)
    vx = m.vx * max(0.0, 1 - AIR_X * dt)
    x1, y1 = m.x + vx * dt, m.y + vy * dt
    tol = LAND_TOL * scale
    # 这一帧从 m.y 落到 y1，中间穿过的地板都算（帧再长也不会穿过去）；取最高的那块
    reachable = [s for s in surfaces if s.left <= x1 <= s.right and m.y - tol <= s.y <= y1 + tol]
    if reachable:
        return _land(m, min(reachable, key=lambda s: s.y), x1, now, rng)
    if surfaces and y1 >= max(s.y for s in surfaces):
        # 掉到所有地板的下面了（比如被甩出了屏幕）：落在最低的那块上，x 夹进它的范围
        lowest = max(s.y for s in surfaces)
        s = min((s for s in surfaces if s.y == lowest), key=lambda s: max(s.left - x1, 0.0, x1 - s.right))
        return _land(m, s, _clamp(x1, s.left, s.right), now, rng)
    return replace(m, x=x1, y=y1, vx=vx, vy=vy)


def _fly(m: Motion, s: Surface, now: float, rng) -> Motion:
    j = m.jump
    p = _clamp((now - j.t0) / j.dur, 0.0, 1.0)
    dest_x, dest_y = x_at(s, m.frac), s.y
    if p >= 1.0:
        return _land(m, s, dest_x, now, rng)
    return replace(m, x=j.x0 + (dest_x - j.x0) * p, y=j.y0 + (dest_y - j.y0) * p - 4 * j.peak * p * (1 - p))


def _pick_frac(cur: float, rng) -> float:
    for _ in range(10):
        f = rng.uniform(*WANDER_RANGE)
        if abs(f - cur) >= WANDER_MIN_STEP:
            return f
    return WANDER_RANGE[1] if cur < 0.5 else WANDER_RANGE[0]


def _perch(m: Motion, s: Surface, now: float, can_wander: bool, rng) -> Motion:
    m = replace(m, x=x_at(s, m.frac), y=s.y)
    if not can_wander or m.swing_until > now:  # 忙着（Claude 在干活、提醒休息）或者正在晃腿：不另起行为
        return m
    if now >= m.next_wander and s.right > s.left:
        f = _pick_frac(m.frac, rng)
        return replace(m, mode='walk', target_frac=f, face=1 if f > m.frac else -1)
    if now >= m.next_swing:
        dur = rng.uniform(*SWING_FOR)
        return replace(m, swing_until=now + dur, next_swing=now + dur + rng.uniform(*SWING_EVERY))
    return m


def _walk(m: Motion, s: Surface, now: float, dt: float, speed: float, rng) -> Motion:
    tx, step = x_at(s, m.target_frac), speed * dt
    dx = tx - m.x
    if abs(dx) <= step:
        return replace(m, mode='perch', x=tx, y=s.y, frac=m.target_frac, target_frac=None,
                       next_wander=_later(now, WANDER_EVERY, rng), next_swing=_later(now, SWING_EVERY, rng))
    x = m.x + math.copysign(step, dx)
    width = s.right - s.left
    return replace(m, x=x, y=s.y, frac=(x - s.left) / width if width > 0 else m.frac, face=1 if dx > 0 else -1)


def tick(m: Motion, surfaces: Sequence[Surface], now: float, dt: float, *, speed: float = 70.0,
         scale: float = 1.0, can_wander: bool = True, rng=None) -> Motion:
    """走一帧。surfaces 是此刻所有的地板：她脚下那块动了她就跟着动，没了她就掉下去。"""
    rng = rng or random
    if m.mode == 'held':
        return m
    if m.mode == 'fall':
        return _fall(m, surfaces, now, dt, scale, rng)
    s = {surface.key: surface for surface in surfaces}.get(m.support)
    if s is None:  # 脚下的窗口关了、最小化了，或者要跳去的那块没了
        return replace(m, mode='fall', support=None, jump=None, target_frac=None, vx=0.0, vy=0.0)
    if m.mode == 'hop':
        return _fly(m, s, now, rng)
    if m.mode == 'walk':
        return _walk(m, s, now, dt, speed, rng)
    return _perch(m, s, now, can_wander, rng)


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
    if m.mode in ('held', 'fall', 'hop'):
        return Pose('jump', m.face < 0, 1.0)  # 被拎着、掉下去、跳过去，都是四肢悬空的这一张
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
    # 平时静静地坐着；只有"晃腿"这个小行为进行的时候，两帧才慢慢交替
    file = f'sit-swing-{1 + int(now / SWING_S) % 2}' if m.swing_until > now else 'sit-swing-1'
    return Pose(file, False, ANCHOR[file])
