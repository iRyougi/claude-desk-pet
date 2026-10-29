"""绿幕抠图和切帧的小工具：给 AI 生成的绿底立绘去背景，只依赖 Pillow。"""
from __future__ import annotations

from collections.abc import Sequence

from PIL import Image

RGB = tuple[int, int, int]

# 绿色"过量"（g 比 r、b 里较大的那个多出多少）达到这个值，才算背景绿
BG_MIN_EXCESS = 150
# 过量低于这个值的像素当作完全不透明的角色
SUBJECT_MAX_EXCESS = 20
# 过量达到"背景过量"的这个比例，就肯定是背景（容忍绿底的明暗噪点）
BG_CERTAIN = 0.8
# 透明度低于这个值的残影直接抹掉
ALPHA_FLOOR = 24


def _excess(r: int, g: int, b: int) -> int:
    return g - max(r, b)


def pixels(im: Image.Image) -> list:
    """按行展开所有像素（Pillow 14 起 getdata 改名为 get_flattened_data）。"""
    return list(getattr(im, 'get_flattened_data', im.getdata)())


def estimate_bg(im: Image.Image) -> RGB:
    """取画布四周"绿色"像素的平均色。角色碰到边缘的那几个像素不是绿色，会被自动忽略。"""
    w, h = im.size
    px = im.convert('RGB').load()
    edge = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    edge += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    greens = [px[p] for p in edge if _excess(*px[p]) >= BG_MIN_EXCESS]
    if not greens:
        raise ValueError('画布边缘找不到绿色背景')
    n = len(greens)
    return (
        round(sum(c[0] for c in greens) / n),
        round(sum(c[1] for c in greens) / n),
        round(sum(c[2] for c in greens) / n),
    )


def _key_pixel(c: RGB, bg: RGB, bg_excess: int) -> tuple[int, int, int, int]:
    r, g, b = c
    certain = SUBJECT_MAX_EXCESS + BG_CERTAIN * (bg_excess - SUBJECT_MAX_EXCESS)
    t = (_excess(r, g, b) - SUBJECT_MAX_EXCESS) / (certain - SUBJECT_MAX_EXCESS)
    t = min(1.0, max(0.0, t))  # 这个像素里有多少是背景
    alpha = round(255 * (1 - t))
    if alpha < ALPHA_FLOOR:
        return (0, 0, 0, 0)
    if alpha < 255:
        # 抗锯齿边缘：把混进去的绿色减掉，还原角色本来的颜色
        a = alpha / 255
        r, g, b = (min(255, max(0, round((v - (1 - a) * k) / a))) for v, k in zip(c, bg))
    return (r, min(g, max(r, b)), b, alpha)  # 去绿：g 不许超过 r、b，消掉发丝里的绿色反光


def key_green(im: Image.Image) -> Image.Image:
    """返回新的 RGBA 图：背景（包括头发缝隙里被围住的绿色）变透明，边缘去绿。不修改原图。"""
    src = im.convert('RGB')
    bg = estimate_bg(src)
    bg_excess = _excess(*bg)
    out = Image.new('RGBA', src.size)
    out.putdata([_key_pixel(c, bg, bg_excess) for c in pixels(src)])
    return out


def split_valleys(coverage: Sequence[int], n: int) -> list[tuple[int, int]]:
    """把一条横向精灵图切成 n 帧。coverage[x] 是第 x 列有多少角色像素。

    每条切线选在等分位置附近"角色最少"的那一列，这样相邻帧的发梢连在一起也不会被削掉。
    返回 n 个 (左, 右) 半开区间，相邻两帧共用同一条切线。
    """
    width = len(coverage)
    window = max(1, width // (n * 3))
    cuts = [0]
    for i in range(1, n):
        target = round(i * width / n)
        lo, hi = max(1, target - window), min(width - 1, target + window)
        cuts.append(min(range(lo, hi + 1), key=lambda x: (coverage[x], abs(x - target))))
    cuts.append(width)
    return list(zip(cuts, cuts[1:]))
