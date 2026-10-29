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
