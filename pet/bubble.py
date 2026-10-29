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
