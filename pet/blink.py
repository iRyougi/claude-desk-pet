"""眨眼的节奏：每隔 2.5～6 秒眨一次，闭眼 0.12 秒，偶尔连眨两下。

纯函数：时间和随机数（有 uniform、random 两个方法的对象，random 模块就行）由调用方给。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

BLINK_EVERY = (2.5, 6.0)   # 两次眨眼之间隔多久（秒）
BLINK_CLOSED = 0.12        # 一次闭眼多久
BLINK_GAP = 0.18           # 连眨时两下之间睁开多久
BLINK_DOUBLE = 0.2         # 连眨两下的概率


@dataclass(frozen=True)
class Blink:
    next_at: float                  # 下一次眨眼的时刻
    closed_until: float = 0.0       # 眼睛闭到什么时候
    again_at: float | None = None   # 连眨时第二下的时刻


def start(now: float, rng) -> Blink:
    return Blink(next_at=now + rng.uniform(*BLINK_EVERY))


def step(b: Blink, now: float, rng) -> Blink:
    if b.again_at is not None and now >= b.again_at:
        return replace(b, closed_until=now + BLINK_CLOSED, again_at=None)
    if now >= b.next_at:
        again = now + BLINK_CLOSED + BLINK_GAP if rng.random() < BLINK_DOUBLE else None
        return Blink(next_at=now + BLINK_CLOSED + rng.uniform(*BLINK_EVERY), closed_until=now + BLINK_CLOSED,
                     again_at=again)
    return b


def closed(b: Blink, now: float) -> bool:
    return now < b.closed_until
