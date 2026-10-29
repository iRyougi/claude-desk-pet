"""清掉切帧时混进来的碎片：相邻帧的发梢、靴尖被切分线带进这一帧，还有零星的小斑点。"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter

from chroma import pixels

ALPHA_SOLID = 40         # 透明度超过这个值才算"有东西"
EDGE_FRAGMENT_MAX = 0.03  # 贴着左右边缘、面积不到主体 3% 的，当成邻居帧的碎片
SPECK_MAX = 0.001        # 面积不到主体千分之一的，当成斑点（流苏耳坠这类独立小件比这大得多）
HALO = 3                 # 抹掉碎片时，向外多抹几像素，清掉抗锯齿留下的淡边


def components(mask: list, w: int, h: int) -> list:
    """8 连通的连通块；返回 [(像素下标列表, 是否碰到左右边缘), ...]。"""
    seen = bytearray(w * h)
    comps = []
    for start, on in enumerate(mask):
        if not on or seen[start]:
            continue
        seen[start] = 1
        stack, members, edge = [start], [], False
        while stack:
            i = stack.pop()
            members.append(i)
            x, y = i % w, i // w
            edge = edge or x == 0 or x == w - 1
            for ny in (y - 1, y, y + 1):
                if not 0 <= ny < h:
                    continue
                for nx in (x - 1, x, x + 1):
                    j = ny * w + nx
                    if 0 <= nx < w and mask[j] and not seen[j]:
                        seen[j] = 1
                        stack.append(j)
        comps.append((members, edge))
    return comps


def _mask_image(size: tuple, indices: list) -> Image.Image:
    data = bytearray(size[0] * size[1])
    for i in indices:
        data[i] = 255
    return Image.frombytes('L', size, bytes(data))


def drop_fragments(im: Image.Image) -> Image.Image:
    """返回新的 RGBA 图：抹掉贴着左右边缘的小碎片和孤立的小斑点；主体和有一定大小的独立小件不动。"""
    im = im.convert('RGBA')
    w, h = im.size
    alpha = im.getchannel('A')
    comps = components([v > ALPHA_SOLID for v in pixels(alpha)], w, h)
    if not comps:
        return im.copy()
    main = max(len(members) for members, _ in comps)
    dropped, kept = [], []
    for members, edge in comps:
        area = len(members)
        if area < main and (area < SPECK_MAX * main or (edge and area < EDGE_FRAGMENT_MAX * main)):
            dropped.extend(members)
        else:
            kept.extend(members)
    if not dropped:
        return im.copy()
    drop_zone = _mask_image(im.size, dropped).filter(ImageFilter.MaxFilter(2 * HALO + 1))
    keep_zone = _mask_image(im.size, kept).filter(ImageFilter.MaxFilter(3))  # 保住主体边缘的抗锯齿像素
    out = im.copy()
    out.putalpha(ImageChops.subtract(alpha, ImageChops.subtract(drop_zone, keep_zone)))
    return out


def split_by_components(im: Image.Image, count: int, min_ratio: float = 0.05):
    """把横向精灵图按"连通的人形"分成 count 帧，返回和原图同样大小的 count 张图，从左到右。

    相邻帧的头发、靴尖在横向上常有重叠，按列切会切到别人身上；按连通块分，每一帧都是完整的。
    如果相邻帧连在一起、或者人形的个数不对，就分不开，返回 None，调用方改用按列切。
    """
    im = im.convert('RGBA')
    w, h = im.size
    alpha = im.getchannel('A')
    comps = components([v > ALPHA_SOLID for v in pixels(alpha)], w, h)
    if not comps:
        return None
    largest = max(len(members) for members, _ in comps)
    bodies = [members for members, _ in comps if len(members) >= min_ratio * largest]
    if len(bodies) != count:
        return None
    bodies.sort(key=lambda members: sum(i % w for i in members) / len(members))
    frames = []
    for members in bodies:
        zone = _mask_image(im.size, members).filter(ImageFilter.MaxFilter(2 * HALO + 1))  # 连同抗锯齿的淡边一起
        frame = im.copy()
        frame.putalpha(ImageChops.darker(alpha, zone))
        frames.append(frame)
    return frames
