"""头上飘的 z Z：每 1.5 秒冒一个，3 秒内往右上方飘走、慢慢变淡。纯函数，只算位置和透明度，不画。"""
from __future__ import annotations

import math
from dataclasses import dataclass

ZZ_EVERY = 1.5         # 隔多久冒一个
ZZ_LIFE = 3.0          # 一个飘多久
ZZ_RISE = 40           # 一生往上飘多远（100% 缩放的像素）
ZZ_DRIFT = 15          # 一生往右飘多远
ZZ_SIZES = (15, 11)    # 大 Z、小 z 的字号（像素）


@dataclass(frozen=True)
class Mark:
    text: str
    dx: float      # 相对起点的偏移（像素）
    dy: float
    alpha: int     # 0～255
    size: int      # 字号（像素）


def zz_marks(t: float, scale: float) -> list:
    """t 时刻所有还看得见的 z Z。大小交替：第偶数个是大 Z。"""
    newest = math.floor(t / ZZ_EVERY)
    out = []
    for i in range(newest - math.ceil(ZZ_LIFE / ZZ_EVERY), newest + 1):
        age = t - i * ZZ_EVERY
        if not 0 <= age < ZZ_LIFE:
            continue
        p = age / ZZ_LIFE
        big = i % 2 == 0
        out.append(Mark('Z' if big else 'z', ZZ_DRIFT * p * scale, -ZZ_RISE * p * scale, round(255 * (1 - p)),
                        round((ZZ_SIZES[0] if big else ZZ_SIZES[1]) * scale)))
    return out
