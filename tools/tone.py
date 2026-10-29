"""色调迁移：让新生成的立绘和原来的立绘用同样的发色、白色。

只调整两类颜色，其他颜色（黑色描边、棕色、靴子的红色鞋带等）保持原样：
- 橙色头发：色相、饱和度、明度各按两套图的平均值之比/差来调
- 近白色（裙子、袖子的奶油白）：按三个通道的平均值之比来调
"""
from __future__ import annotations

import colorsys
from collections.abc import Iterable
from dataclasses import dataclass

from PIL import Image

from chroma import pixels

HAIR_H = (0.015, 0.11)   # 橙色的色相范围
HAIR_MIN_S = 0.55        # 统计时，饱和度达到这个值才算头发
HAIR_MIN_V = 0.50        # 太暗的是描边和阴影，不算
OPAQUE = 200
STRIDE = 2               # 统计时隔一个像素取一个，够准也更快


@dataclass(frozen=True)
class Tone:
    hair_h: float
    hair_s: float
    hair_v: float
    white: tuple  # (r, g, b) 平均值


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _is_hair(h: float, s: float, v: float) -> bool:
    return HAIR_H[0] <= h <= HAIR_H[1] and s >= HAIR_MIN_S and v >= HAIR_MIN_V


def _is_white(s: float, v: float) -> bool:
    return s < 0.2 and v > 0.85


def measure(images: Iterable[Image.Image]) -> Tone:
    """统计一批 RGBA 图里（不透明像素）头发和白色的平均色调。"""
    hair, white = [], []
    for im in images:
        for r, g, b, a in pixels(im.convert('RGBA'))[::STRIDE]:
            if a < OPAQUE:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if _is_hair(h, s, v):
                hair.append((h, s, v))
            elif _is_white(s, v):
                white.append((r, g, b))
    if not hair or not white:
        raise ValueError('图里找不到橙色头发或白色，没法统计色调')
    mean = lambda xs, i: sum(x[i] for x in xs) / len(xs)  # noqa: E731
    return Tone(
        hair_h=mean(hair, 0), hair_s=mean(hair, 1), hair_v=mean(hair, 2),
        white=(mean(white, 0), mean(white, 1), mean(white, 2)),
    )


def _adjust_pixel(rgb: tuple, src: Tone, ref: Tone) -> tuple:
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if HAIR_H[0] <= h <= HAIR_H[1]:
        w = _clamp01((s - 0.40) / 0.20) * _clamp01((v - 0.35) / 0.15)
        if w > 0:
            h2 = h + w * (ref.hair_h - src.hair_h)
            s2 = _clamp01(s + w * (s * ref.hair_s / src.hair_s - s))
            v2 = _clamp01(v + w * (v * ref.hair_v / src.hair_v - v))
            r2, g2, b2 = colorsys.hsv_to_rgb(h2, s2, v2)
            return (round(r2 * 255), round(g2 * 255), round(b2 * 255))
    w = _clamp01((v - 0.80) / 0.10) * _clamp01((0.25 - s) / 0.10)
    if w > 0:
        return tuple(
            min(255, max(0, round(c * (1 + w * (k_ref / k_src - 1)))))
            for c, k_src, k_ref in zip(rgb, src.white, ref.white)
        )
    return rgb


def adjust(im: Image.Image, src: Tone, ref: Tone) -> Image.Image:
    """返回新的 RGBA 图：把 src 的色调迁移到 ref。透明度不变，不修改原图。"""
    cache: dict = {}
    out = []
    for r, g, b, a in pixels(im.convert('RGBA')):
        if a == 0:
            out.append((r, g, b, a))
            continue
        rgb = (r, g, b)
        if rgb not in cache:
            cache[rgb] = _adjust_pixel(rgb, src, ref)
        out.append(cache[rgb] + (a,))
    result = Image.new('RGBA', im.size)
    result.putdata(out)
    return result
