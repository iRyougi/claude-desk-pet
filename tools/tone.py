"""色调迁移：让新生成的立绘和原来的立绘用同样的发色、白色、深色和肤色。

只调整下面几类颜色，其他颜色（棕色、靴子的红色鞋带等）保持原样：
- 橙色头发：色相按平均值平移；饱和度和明度按整条分布对齐（只对平均值不够：
  原图头发是一大块明度 0.97 的平涂橙，新图的主色只有 0.92，平均值一样但看起来更深更艳）
- 深色（描边、黑色装饰）：新图的深色偏红橙，要降低饱和度
- 肤色：新图偏粉，降低饱和度
- 近白色（裙子、袖子的奶油白）：按三个通道的平均值之比来调
"""
from __future__ import annotations

import bisect
import colorsys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from PIL import Image

from chroma import pixels

HAIR_H = (0.015, 0.11)   # 橙色的色相范围
HAIR_MIN_S = 0.55        # 统计时，饱和度达到这个值才算头发
HAIR_MIN_V = 0.50        # 太暗的是描边和阴影，不算
WHITE_MAX_S = 0.12       # 白色、奶油白；再往上是肤色
DARK_MAX_V = 0.25        # 统计"深色"用
SKIN_S = (0.12, 0.35)
OPAQUE = 200
STRIDE = 2               # 统计时隔一个像素取一个，够准也更快
MIN_SAMPLES = 20         # 深色/肤色的像素少于这个数，就当这套图里没有，不去调
QUANTILES = 101


@dataclass(frozen=True)
class Tone:
    hair_h: float
    hair_s: float
    hair_v: float
    white: tuple                 # (r, g, b) 平均值
    hair_s_q: tuple = ()         # 头发饱和度的 101 个分位数
    hair_v_q: tuple = ()         # 头发明度的 101 个分位数
    dark_s: float | None = None  # 深色的平均饱和度；这套图里没有深色就是 None
    skin_s: float | None = None


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _is_hair(h: float, s: float, v: float) -> bool:
    return HAIR_H[0] <= h <= HAIR_H[1] and s >= HAIR_MIN_S and v >= HAIR_MIN_V


def _is_white(s: float, v: float) -> bool:
    return s < WHITE_MAX_S and v > 0.85


def _is_skin(h: float, s: float, v: float) -> bool:
    return 0.0 <= h <= 0.12 and SKIN_S[0] <= s < SKIN_S[1] and v > 0.8


def _quantiles(values: Sequence[float]) -> tuple:
    v = sorted(values)
    return tuple(v[min(len(v) - 1, round(i / (QUANTILES - 1) * (len(v) - 1)))] for i in range(QUANTILES))


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def measure(images: Iterable[Image.Image]) -> Tone:
    """统计一批 RGBA 图里（不透明像素）头发、白色、深色、肤色的色调。"""
    hair, white, dark, skin = [], [], [], []
    for im in images:
        for r, g, b, a in pixels(im.convert('RGBA'))[::STRIDE]:
            if a < OPAQUE:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if _is_hair(h, s, v):
                hair.append((h, s, v))
            elif _is_white(s, v):
                white.append((r, g, b))
            elif v < DARK_MAX_V:
                dark.append(s)
            elif _is_skin(h, s, v):
                skin.append(s)
    if not hair or not white:
        raise ValueError('图里找不到橙色头发或白色，没法统计色调')
    return Tone(
        hair_h=_mean([p[0] for p in hair]), hair_s=_mean([p[1] for p in hair]), hair_v=_mean([p[2] for p in hair]),
        white=tuple(_mean([p[i] for p in white]) for i in range(3)),
        hair_s_q=_quantiles([p[1] for p in hair]), hair_v_q=_quantiles([p[2] for p in hair]),
        dark_s=_mean(dark) if len(dark) >= MIN_SAMPLES else None,
        skin_s=_mean(skin) if len(skin) >= MIN_SAMPLES else None,
    )


def _qmap(x: float, src: Sequence[float], ref: Sequence[float], src_mean: float, ref_mean: float) -> float:
    """分位数映射：x 在 src 分布里排第几，就换成 ref 分布里同样位置的值。超出范围的按两端的差平移。"""
    if not src or not ref:
        return x * ref_mean / src_mean  # 没有分布信息（手工构造的 Tone），退回按平均值之比
    i = bisect.bisect_left(src, x)
    if i <= 0:
        return x + (ref[0] - src[0])
    if i >= len(src):
        return x + (ref[-1] - src[-1])
    lo, hi = src[i - 1], src[i]
    t = 0.0 if hi == lo else (x - lo) / (hi - lo)
    return ref[i - 1] + t * (ref[i] - ref[i - 1])


def _ratio(src: float | None, ref: float | None) -> float:
    return ref / src if src and ref is not None else 1.0


def _hsv_to_rgb255(h: float, s: float, v: float) -> tuple:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, _clamp01(s), _clamp01(v))
    return (round(r * 255), round(g * 255), round(b * 255))


def _adjust_pixel(rgb: tuple, src: Tone, ref: Tone) -> tuple:
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if HAIR_H[0] <= h <= HAIR_H[1]:
        w = _clamp01((s - 0.40) / 0.20) * _clamp01((v - 0.35) / 0.15)
        if w > 0:
            s2 = s + w * (_qmap(s, src.hair_s_q, ref.hair_s_q, src.hair_s, ref.hair_s) - s)
            v2 = v + w * (_qmap(v, src.hair_v_q, ref.hair_v_q, src.hair_v, ref.hair_v) - v)
            return _hsv_to_rgb255(h + w * (ref.hair_h - src.hair_h), s2, v2)
    k_dark = _ratio(src.dark_s, ref.dark_s)
    if k_dark != 1.0 and v < 0.32:
        w = _clamp01((0.32 - v) / 0.08)
        return _hsv_to_rgb255(h, s * (1 + w * (k_dark - 1)), v)
    k_skin = _ratio(src.skin_s, ref.skin_s)
    if k_skin != 1.0 and 0.0 <= h <= 0.12 and v > 0.8:
        w = _clamp01((s - SKIN_S[0]) / 0.04)  # 从肤色范围的下沿渐变进来，和下面的白色渐变互补
        if w > 0:
            r, g, b = _hsv_to_rgb255(h, s * (1 + w * (k_skin - 1)), v)
    w = _clamp01((v - 0.80) / 0.10) * _clamp01((WHITE_MAX_S + 0.04 - s) / 0.04)
    if w > 0:
        return tuple(
            min(255, max(0, round(c * (1 + w * (k_ref / k_src - 1)))))
            for c, k_src, k_ref in zip((r, g, b), src.white, ref.white)
        )
    return (r, g, b)


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
