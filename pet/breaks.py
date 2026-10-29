"""休息提醒的逻辑：连续工作多久、什么时候催、催到第几级。

这里不碰界面和系统接口：pet.pyw 每隔一会儿告诉它"现在几点、你多久没碰键鼠了"，
它返回新的状态，必要时附带一个提醒事件。所有时间单位：状态里是秒，配置里是分钟。
"""
from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace

ACTIVE_IDLE_S = 120.0  # 最近 2 分钟内有键鼠操作，才算"在工作"
MAX_DT = 120.0         # 两次检查隔得比这更久（睡眠、卡住），这段时间不计入工作时长
MAX_LEVEL = 3
NIGHT_FROM, NIGHT_TO = 23, 5  # 23:00–04:59 算深夜

# 每一级的台词：白天 / 深夜
# 每句控制在 9 个字以内：气泡宽度有限，长了会被画布切掉
LINES = {
    1: (
        ('喝口茶休息一下吧～', '站起来动一动吧～', '看看远处歇歇眼～'),
        ('很晚啦，该睡觉啦～', '夜深了，明天再说～'),
    ),
    2: (
        ('拜托，休息一下嘛…', '再不休息我担心了…', '求你了，歇一会儿～'),
        ('拜托，早点睡吧…', '熬夜对身体不好…'),
    ),
    3: (
        ('再不休息我生气啦！', '哼！快去休息！', '不许写了！去休息！'),
        ('这么晚了！快去睡！', '哼！再不睡我生气！'),
    ),
}
ACK_LINES = ('好耶，去休息吧～', '回来记得喝水哦～', '乖～我等你回来')


@dataclass(frozen=True)
class BreakConfig:
    work_min: float = 50.0      # 连续工作多久开始提醒
    escalate_min: float = 10.0  # 没理她，每隔多久升一级
    repeat_min: float = 5.0     # 最高一级之后，每隔多久再催一次
    away_min: float = 5.0       # 离开多久算"已经休息过了"
    enabled: bool = True

    @classmethod
    def from_settings(cls, s: dict) -> BreakConfig:
        """从 settings.json 读取；任何一项不合法就用默认值（配置文件是用户手写的，不能信）。"""
        d = cls()

        def minutes(key: str, default: float) -> float:
            v = s.get(key)
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0
            return v if ok else default

        enabled = s.get('breakEnabled')
        return cls(
            work_min=minutes('breakWork', d.work_min),
            escalate_min=minutes('breakEscalate', d.escalate_min),
            repeat_min=minutes('breakRepeat', d.repeat_min),
            away_min=minutes('breakAway', d.away_min),
            enabled=enabled if isinstance(enabled, bool) else d.enabled,
        )


@dataclass(frozen=True)
class BreakState:
    active_s: float = 0.0                # 已连续工作的秒数
    level: int = 0                       # 0 没在提醒，1 温柔，2 催促，3 急了
    last_tick: float | None = None
    reminded_at: float | None = None     # 第一次提醒的时刻
    last_event: float | None = None      # 最近一次发出事件的时刻


@dataclass(frozen=True)
class BreakEvent:
    level: int
    repeat: bool = False  # True 表示是最高一级的"再催一次"


def step(state: BreakState, now: float, idle_s: float, cfg: BreakConfig) -> tuple:
    """走一步：返回 (新状态, 事件或 None)。不修改传进来的状态。"""
    if not cfg.enabled or idle_s >= cfg.away_min * 60:
        return BreakState(last_tick=now), None  # 关掉了，或者人已经走开休息过了：全部清零

    dt = 0.0 if state.last_tick is None else now - state.last_tick
    dt = dt if 0 <= dt <= MAX_DT else 0.0
    active = state.active_s + (dt if idle_s < ACTIVE_IDLE_S else 0.0)
    st = replace(state, active_s=active, last_tick=now)

    if st.level == 0:
        if active >= cfg.work_min * 60:
            return replace(st, level=1, reminded_at=now, last_event=now), BreakEvent(1)
        return st, None

    target = min(MAX_LEVEL, 1 + int((now - st.reminded_at) // (cfg.escalate_min * 60)))
    if target > st.level:
        return replace(st, level=target, last_event=now), BreakEvent(target)
    if st.level == MAX_LEVEL and now - st.last_event >= cfg.repeat_min * 60:
        return replace(st, last_event=now), BreakEvent(MAX_LEVEL, repeat=True)
    return st, None


def acknowledge(state: BreakState, now: float) -> BreakState:
    """用户表示"我去休息了"：重新开始计时。"""
    return BreakState(last_tick=now)


def is_night(hour: int) -> bool:
    return hour >= NIGHT_FROM or hour < NIGHT_TO


def pick_line(level: int, night: bool, rng: random.Random | None = None, last: str | None = None) -> str:
    if level not in LINES:
        raise ValueError(f'未知的提醒级别：{level}')
    pool: Sequence[str] = LINES[level][1 if night else 0]
    choices = [x for x in pool if x != last] or list(pool)
    return (rng or random).choice(choices)
