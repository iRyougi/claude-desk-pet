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
