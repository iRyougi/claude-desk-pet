"""把 AI 生成的绿幕立绘处理成透明 PNG，放进 pet/sprites/。

用法：python tools/prep_sprites.py <绿幕图所在文件夹>

源文件按文件名里的关键字匹配（见 SHEETS）。SCALE 是"源图一个像素 → 成品多少像素"，
按头的大小对齐，让各个姿势在桌面上看起来一样大。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from PIL import Image

from chroma import key_green, pixels, split_valleys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'pet', 'sprites')
PAD = 6
ALPHA_SOLID = 40  # 透明度超过这个值才算"有角色"


@dataclass(frozen=True)
class Sheet:
    keyword: str          # 源文件名里的关键字
    names: tuple          # 成品文件名（不含 .png），多帧时按从左到右
    scale: float          # 源图像素 → 成品像素


# 单张图大约 1086x1448，角色约 1360 高 → 成品约 400 高
SHEETS = (
    Sheet('行走', ('walk-1', 'walk-2', 'walk-3', 'walk-4'), 0.58),
    Sheet('双坐姿', ('sit-swing-1', 'sit-swing-2'), 0.436),
    Sheet('悠然', ('sit-watch',), 0.294),
    Sheet('品茶', ('remind-1',), 0.294),
    Sheet('温柔恳请', ('remind-2',), 0.294),
    Sheet('叉腰', ('remind-3',), 0.294),
    Sheet('跃起', ('jump',), 0.294),
    Sheet('落地', ('land',), 0.294),
)


def find_source(folder: str, keyword: str) -> str:
    hits = [f for f in os.listdir(folder) if keyword in f and f.lower().endswith('.png')]
    if len(hits) != 1:
        raise SystemExit(f'「{keyword}」应该恰好匹配 1 个文件，实际 {len(hits)} 个：{hits}')
    return os.path.join(folder, hits[0])


def column_coverage(rgba: Image.Image) -> list:
    w, h = rgba.size
    data = pixels(rgba.getchannel('A'))
    return [sum(1 for v in data[x::w] if v > ALPHA_SOLID) for x in range(w)]


def solid_bbox(rgba: Image.Image) -> tuple:
    box = rgba.getchannel('A').point(lambda a: 255 if a > ALPHA_SOLID else 0).getbbox()
    if box is None:
        raise SystemExit('抠完以后是一张空图，检查背景色')
    return box


def resize_premultiplied(im: Image.Image, scale: float) -> Image.Image:
    """先转成预乘 alpha 再缩放，避免半透明边缘出现脏边。"""
    size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
    return im.convert('RGBa').resize(size, Image.LANCZOS).convert('RGBA')


def cut_frames(rgba: Image.Image, count: int) -> list:
    """切成 count 帧：每帧按自己的左右范围裁，上下用所有帧的并集（保持脚底对齐），再居中放进同宽画布。"""
    cells = [rgba.crop((x0, 0, x1, rgba.height)) for x0, x1 in split_valleys(column_coverage(rgba), count)]
    boxes = [solid_bbox(c) for c in cells]
    top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
    tight = [c.crop((b[0], top, b[2], bottom)) for c, b in zip(cells, boxes)]
    width = max(t.width for t in tight)
    frames = []
    for t in tight:
        canvas = Image.new('RGBA', (width, t.height))
        canvas.paste(t, ((width - t.width) // 2, 0))
        frames.append(canvas)
    return frames


def pad(im: Image.Image) -> Image.Image:
    out = Image.new('RGBA', (im.width + 2 * PAD, im.height + 2 * PAD))
    out.paste(im, (PAD, PAD))
    return out


def process(sheet: Sheet, folder: str) -> list:
    src = find_source(folder, sheet.keyword)
    rgba = key_green(Image.open(src))
    if len(sheet.names) == 1:
        frames = [rgba.crop(solid_bbox(rgba))]
    else:
        frames = cut_frames(rgba, len(sheet.names))
    written = []
    for name, frame in zip(sheet.names, frames):
        out = pad(resize_premultiplied(frame, sheet.scale))
        path = os.path.join(OUT_DIR, name + '.png')
        out.save(path, optimize=True)
        written.append((name, out.size))
    return written


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    folder = argv[1]
    os.makedirs(OUT_DIR, exist_ok=True)
    for sheet in SHEETS:
        for name, size in process(sheet, folder):
            print(f'{name:12s} {size[0]}x{size[1]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
