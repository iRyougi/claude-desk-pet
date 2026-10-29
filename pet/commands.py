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
