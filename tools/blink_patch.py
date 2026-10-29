"""眨眼补丁：只把 GPT 改过的眼睛那一块贴回原立绘。身体永远用原图，眨眼时才不会整个人抖一下。

用法：
  python tools/blink_patch.py export <立绘名>...           把原立绘放大、叠到绿底上，导出到 art/gpt-input/（给 GPT 编辑）
  python tools/blink_patch.py build <立绘名> <编辑后的图>   生成 pet/sprites/<立绘名>.blink.png，位置写进 patches.json，
                                                           并在 art/ 下写一张 blink-preview-<立绘名>.png 方便检查
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITES = os.path.join(ROOT, 'pet', 'sprites')
PATCHES = os.path.join(SPRITES, 'patches.json')
ART = os.path.join(ROOT, 'art')
CANVAS = (1024, 1536)
FIT = (940, 1360)     # 立绘放大后最多这么宽、这么高
BOTTOM = 60           # 脚底离画布底边的距离
GREEN = (0, 255, 0)
DIFF_MIN = 40         # 颜色差超过这个才算"改过"
DENSE_R = 12          # 在 (2r+1)² 的范围里数改过的像素
DENSE_MIN = 0.3       # 改过的像素占比超过这个才算成片（眼睛）；压缩噪点只是沿轮廓的细线，到不了
GROW = 6              # 补丁四周多留几像素（导出图的像素）
FEATHER = 2           # 补丁边缘羽化半径（立绘像素），贴回去才看不出接缝
MAX_SHARE = 0.4       # 补丁高度超过立绘高度的这个比例，多半是没对齐，直接报错


@dataclass(frozen=True)
class Placement:
    k: float  # 立绘放大的倍数
    x: int    # 放大后的立绘左上角在导出图里的位置
    y: int


def placement(size: tuple) -> Placement:
    w, h = size
    k = min(FIT[1] / h, FIT[0] / w)
    return Placement(k, (CANVAS[0] - round(w * k)) // 2, CANVAS[1] - BOTTOM - round(h * k))


def export_image(sprite: Image.Image) -> Image.Image:
    """导出给 GPT 编辑的图：立绘放大、叠在纯绿底上。"""
    p = placement(sprite.size)
    big = sprite.convert('RGBA').resize((round(sprite.width * p.k), round(sprite.height * p.k)), Image.LANCZOS)
    canvas = Image.new('RGBA', CANVAS, GREEN + (255,))
    canvas.alpha_composite(big, (p.x, p.y))
    return canvas.convert('RGB')


def _grow(mask: Image.Image, r: int) -> Image.Image:
    """把白色区域向外扩 r 像素（用盒式模糊代替大核的最大值滤波，快得多）。"""
    return mask.filter(ImageFilter.BoxBlur(r)).point(lambda v: 255 if v > 0 else 0)


def dense_mask(a: Image.Image, b: Image.Image) -> Image.Image:
    """两张图里"成片"改动的地方（白色）。零星的压缩噪点不算。"""
    diff = ImageChops.difference(a.convert('RGB'), b.convert('RGB')).convert('L')
    changed = diff.point(lambda v: 255 if v > DIFF_MIN else 0)
    density = changed.filter(ImageFilter.BoxBlur(DENSE_R))
    return density.point(lambda v: 255 if v >= 255 * DENSE_MIN else 0)


def build_patch(sprite: Image.Image, original_export: Image.Image, edited: Image.Image) -> tuple:
    """从编辑后的图里裁出改动的那一块，缩回立绘的像素网格。返回 (补丁 RGBA, 补丁左上角在立绘里的位置)。"""
    if edited.size != original_export.size:
        edited = edited.resize(original_export.size, Image.LANCZOS)
    p = placement(sprite.size)
    area = _grow(dense_mask(original_export, edited), DENSE_R + GROW)
    box = area.getbbox()
    if box is None:
        raise ValueError('没找到改动：编辑后的图和导出的原图一样？')
    x0, y0, x1, y1 = box
    sx0, sy0 = max(0, math.floor((x0 - p.x) / p.k)), max(0, math.floor((y0 - p.y) / p.k))
    sx1, sy1 = min(sprite.width, math.ceil((x1 - p.x) / p.k)), min(sprite.height, math.ceil((y1 - p.y) / p.k))
    if sx1 <= sx0 or sy1 <= sy0:
        raise ValueError('改动不在立绘范围内')
    if (sy1 - sy0) > MAX_SHARE * sprite.height:
        raise ValueError(f'改动太分散（{sy1 - sy0} 像素高），检查编辑图是不是只改了眼睛、有没有被挪动')
    src_box = (p.x + sx0 * p.k, p.y + sy0 * p.k, p.x + sx1 * p.k, p.y + sy1 * p.k)
    size = (sx1 - sx0, sy1 - sy0)
    rgb = edited.convert('RGB').resize(size, Image.LANCZOS, box=src_box)
    soft = area.resize(size, Image.BILINEAR, box=src_box).filter(ImageFilter.GaussianBlur(FEATHER))
    alpha = ImageChops.multiply(soft, sprite.convert('RGBA').getchannel('A').crop((sx0, sy0, sx1, sy1)))
    return Image.merge('RGBA', (*rgb.split(), alpha)), (sx0, sy0)


def _load_patches() -> dict:
    try:
        with open(PATCHES, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _export(names: list) -> int:
    os.makedirs(os.path.join(ART, 'gpt-input'), exist_ok=True)
    for name in names:
        out = os.path.join(ART, 'gpt-input', f'眨眼原图-{name}.png')
        export_image(Image.open(os.path.join(SPRITES, name + '.png'))).save(out)
        print('导出', out)
    return 0


def _build(name: str, edited_path: str) -> int:
    sprite = Image.open(os.path.join(SPRITES, name + '.png')).convert('RGBA')
    patch, (x, y) = build_patch(sprite, export_image(sprite), Image.open(edited_path))
    patch.save(os.path.join(SPRITES, name + '.blink.png'), optimize=True)
    patches = {**_load_patches(), name: {'x': x, 'y': y}}
    with open(PATCHES, 'w', encoding='utf-8') as f:
        json.dump(patches, f, ensure_ascii=False, indent=2, sort_keys=True)
    blinked = sprite.copy()
    blinked.alpha_composite(patch, (x, y))
    preview = Image.new('RGBA', (sprite.width * 2 + 10, sprite.height), (90, 90, 110, 255))
    preview.alpha_composite(sprite, (0, 0))
    preview.alpha_composite(blinked, (sprite.width + 10, 0))
    os.makedirs(ART, exist_ok=True)
    preview.convert('RGB').save(os.path.join(ART, f'blink-preview-{name}.png'))
    print(f'{name}: 补丁 {patch.width}x{patch.height}，位置 ({x}, {y})')
    return 0


def main(argv: list) -> int:
    if len(argv) >= 3 and argv[1] == 'export':
        return _export(argv[2:])
    if len(argv) == 4 and argv[1] == 'build':
        return _build(argv[2], argv[3])
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
