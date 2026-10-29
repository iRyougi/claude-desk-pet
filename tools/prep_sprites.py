"""把 AI 生成的绿幕立绘处理成透明 PNG，放进 pet/sprites/。

用法：python tools/prep_sprites.py <绿幕图所在文件夹> [--raw]

默认会把新立绘的发色和白色调到和原来的立绘一致；加 --raw 则保持 AI 出图的原色。

源文件按文件名里的关键字匹配（见 SHEETS）。只处理文件夹里找得到源图的立绘；没有源图的保持原样。SCALE 是"源图一个像素 → 成品多少像素"，
按头的大小对齐，让各个姿势在桌面上看起来一样大。
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass

from PIL import Image

from chroma import key_green, pixels, split_valleys
from fragments import drop_fragments, split_by_components
from outline import add_outline
from tone import Tone, adjust, measure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'pet', 'sprites')
PAD = 6
ALPHA_SOLID = 40  # 透明度超过这个值才算"有角色"
# 色调基准：原来的立绘（stone 是灰石头、confetti 带彩带，都不参与）
ORIGINALS = ('smile', 'smile-closed', 'typing', 'notes', 'knock', 'panic', 'confident', 'guilty')


@dataclass(frozen=True)
class Sheet:
    keyword: str          # 源文件名里的关键字
    names: tuple          # 成品文件名（不含 .png），多帧时按从左到右
    scale: float          # 源图像素 → 成品像素


# 单张图大约 1086x1448，角色约 1360 高 → 成品约 400 高
SHEETS = (
    Sheet('六帧', ('walk-1', 'walk-2', 'walk-3', 'walk-4', 'walk-5', 'walk-6'), 0.72),
    Sheet('双坐姿', ('sit-swing-1', 'sit-swing-2'), 0.436),
    Sheet('悠然', ('sit-watch',), 0.294),
    Sheet('品茶', ('remind-1',), 0.294),
    Sheet('温柔恳请', ('remind-2',), 0.294),
    Sheet('叉腰', ('remind-3',), 0.294),
    Sheet('跃起', ('jump',), 0.294),
    Sheet('落地', ('land',), 0.294),
    # 下面这批是 B 动画、C 互动的新素材（GPT 出图，art/gpt-output/）。两帧一组的画在一张横图里，人物比单张图小，
    # 所以系数大一些；系数是按轮廓和原立绘的重合度量出来的（瞌睡对 sit-swing-1、被戳对 smile）
    Sheet('下蹲两帧', ('sit-down-1', 'sit-down-2'), 0.48),
    Sheet('被拎两帧', ('held', 'held-swing'), 0.455),
    Sheet('下落', ('fall',), 0.31),
    Sheet('瞌睡两帧', ('sleep-1', 'sleep-2'), 0.485),
    Sheet('害羞', ('shy',), 0.30),
    Sheet('被戳', ('poked',), 0.30),
)


def available(folder: str, sheets=SHEETS) -> list:
    """文件夹里找得到源图的立绘表，和各自的源图路径。没有源图的表跳过；一个关键字匹配到多个文件就报错。"""
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith('.png'))
    found = []
    for sheet in sheets:
        hits = [f for f in files if sheet.keyword in f]
        if len(hits) > 1:
            raise SystemExit(f'「{sheet.keyword}」应该最多匹配 1 个文件，实际 {len(hits)} 个：{hits}')
        if hits:
            found.append((sheet, os.path.join(folder, hits[0])))
    return found


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


def head_x(im: Image.Image) -> float:
    """头的水平位置：角色最上面四分之一那部分的中心。头发摆动会改变整个身体的外框，但头基本不动。"""
    left, top, right, bottom = solid_bbox(im)
    limit = top + max(1, (bottom - top) // 4)
    data = pixels(im.getchannel('A'))
    xs = [x for y in range(top, limit) for x in range(im.width) if data[y * im.width + x] > ALPHA_SOLID]
    return sum(xs) / len(xs)


def align_on_head(frames: list) -> list:
    """把几帧放进同样大小的画布，并让每一帧的头落在同一个水平位置（走路时头才不会左右抖）。"""
    boxes = [solid_bbox(f) for f in frames]
    anchors = [head_x(f) for f in frames]
    left = math.ceil(max(a - b[0] for a, b in zip(anchors, boxes)))
    right = math.ceil(max(b[2] - a for a, b in zip(anchors, boxes)))
    out = []
    for f, b, a in zip(frames, boxes, anchors):
        canvas = Image.new('RGBA', (left + right, f.height))
        offset = math.floor(left - (a - b[0]) + 0.5)  # 不用 round：它对 .5 取偶数，会让两帧差 1 像素
        canvas.paste(f.crop((b[0], 0, b[2], f.height)), (offset, 0))
        out.append(canvas)
    return out


def cut_frames(rgba: Image.Image, count: int) -> list:
    """切成 count 帧：先按连通的人形分（不会切到靴尖、发梢），分不开再按列切；上下用所有帧的并集（保持脚底对齐），左右让每一帧的头对齐。"""
    frames = split_by_components(rgba, count)
    if frames is None:  # 相邻帧的头发连在一起，分不开：退回按列切，再清掉带进来的碎片
        cells = [rgba.crop((x0, 0, x1, rgba.height)) for x0, x1 in split_valleys(column_coverage(rgba), count)]
        frames = [drop_fragments(c) for c in cells]
    boxes = [solid_bbox(f) for f in frames]
    top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
    return align_on_head([f.crop((0, top, f.width, bottom)) for f in frames])


def pad(im: Image.Image) -> Image.Image:
    out = Image.new('RGBA', (im.width + 2 * PAD, im.height + 2 * PAD))
    out.paste(im, (PAD, PAD))
    return out


def render(sheet: Sheet, rgba: Image.Image) -> list:
    if len(sheet.names) == 1:
        frames = [rgba.crop(solid_bbox(rgba))]
    else:
        frames = cut_frames(rgba, len(sheet.names))
    written = []
    for name, frame in zip(sheet.names, frames):
        out = add_outline(pad(resize_premultiplied(frame, sheet.scale)))  # 先留边距，勾边才不会被切掉
        out.save(os.path.join(OUT_DIR, name + '.png'), optimize=True)
        written.append((name, out.size))
    return written


def reference_tone() -> Tone:
    """原来那 10 张立绘（去掉石头和撒花）的色调，新立绘要向它看齐。"""
    return measure(Image.open(os.path.join(OUT_DIR, n + '.png')) for n in ORIGINALS)


def describe(tone: Tone) -> str:
    w = tuple(round(c) for c in tone.white)
    dark = f'{tone.dark_s:.2f}' if tone.dark_s is not None else '-'
    skin = f'{tone.skin_s:.2f}' if tone.skin_s is not None else '-'
    return f'头发 H{tone.hair_h:.3f} S{tone.hair_s:.3f} V{tone.hair_v:.3f}，白色 {w}，深色S {dark}，肤色S {skin}'


def main(argv: list) -> int:
    raw = '--raw' in argv
    args = [a for a in argv[1:] if a != '--raw']
    if len(args) != 1:
        print(__doc__)
        return 2
    os.makedirs(OUT_DIR, exist_ok=True)
    found = available(args[0])
    if not found:
        print(f'{args[0]} 里没有找到任何源图（文件名里要带关键字）')
        return 1
    skipped = [s.keyword for s in SHEETS if s not in {f for f, _ in found}]
    if skipped:
        print('没有源图、跳过：' + '、'.join(skipped))
    keyed = [(s, key_green(Image.open(path))) for s, path in found]
    if not raw:
        src, ref = measure(k for _, k in keyed), reference_tone()
        print('新立绘', describe(src))
        print('原立绘', describe(ref))
        keyed = [(s, adjust(k, src, ref)) for s, k in keyed]
        print('调整后', describe(measure(k for _, k in keyed)))
    for sheet, rgba in keyed:
        for name, size in render(sheet, rgba):
            print(f'{name:12s} {size[0]}x{size[1]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
