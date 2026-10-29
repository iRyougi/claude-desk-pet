"""一帧画面：立绘 + 气泡，合成一张带透明度的图（RGBA）。纯 PIL，不碰窗口。"""
from __future__ import annotations

import functools
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from bubble import BubbleLayout

ORANGE = (232, 116, 59, 255)
PAPER = (255, 250, 243, 255)
INK = (58, 42, 26, 255)
SUB_INK = (150, 136, 122, 255)
SS = 3                      # 气泡的形状按 3 倍画再缩小，边缘才平滑；文字直接按原尺寸画（字体自带抗锯齿）
FONT_FILE, FONT_INDEX = 'msyh.ttc', 1   # Microsoft YaHei UI


@functools.lru_cache(maxsize=16)
def _font(px: int):
    try:
        return ImageFont.truetype(FONT_FILE, px, index=FONT_INDEX)
    except OSError:
        return ImageFont.load_default(px)


@dataclass(frozen=True)
class BubbleStyle:
    font: object     # 正文字体（PIL FreeTypeFont）
    small: object    # 第二行小字
    scale: float

    @classmethod
    def make(cls, scale: float) -> 'BubbleStyle':
        # 和原来 tk 的 10 号、8 号字一样大：1 磅 = 96/72 像素
        return cls(font=_font(round(10 * 96 / 72 * scale)), small=_font(round(8 * 96 / 72 * scale)), scale=scale)

    def px(self, v: float) -> int:
        return round(v * self.scale)

    def measure(self, text: str) -> float:
        return self.font.getlength(text)


def _shape(w: int, box_h: int, tail: int, s: BubbleStyle, k: int) -> Image.Image:
    """气泡的外形（圆角框 + 底部正中的小尖角），按 k 倍画。"""
    W, H, B = w * k, (box_h + tail) * k, max(2, s.px(2)) * k
    r, bottom, cx = s.px(12) * k, box_h * k, w * k // 2
    left, right, tip = cx - s.px(4) * k, cx + s.px(8) * k, bottom + tail * k
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, bottom - 1), radius=r, fill=ORANGE)
    d.polygon([(left, bottom - B), (cx, tip), (right, bottom - B)], fill=ORANGE)
    d.rounded_rectangle((B, B, W - 1 - B, bottom - 1 - B), radius=max(1, r - B), fill=PAPER)
    d.polygon([(left + B, bottom - 2 * B), (cx, tip - 2 * B), (right - B, bottom - 2 * B)], fill=PAPER)
    return im


def bubble_image(layout: BubbleLayout, style: BubbleStyle) -> Image.Image:
    s = style
    pad_x, pad_y, line_h, sub_h, tail = s.px(10), s.px(7), s.px(19), s.px(16), s.px(10)
    widths = [s.font.getlength(t) for t in layout.lines]
    if layout.sub:
        widths.append(s.small.getlength(layout.sub))
    w = round(max(widths + [0])) + 2 * pad_x
    box_h = 2 * pad_y + line_h * len(layout.lines) + (sub_h if layout.sub else 0)
    shape = _shape(w, box_h, tail, s, SS)
    im = shape.resize((w, box_h + tail), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    y = pad_y
    for text, tw in zip(layout.lines, widths):
        d.text(((w - tw) / 2, y), text, font=s.font, fill=INK)
        y += line_h
    if layout.sub:
        d.text(((w - widths[-1]) / 2, y + s.px(1)), layout.sub, font=s.small, fill=SUB_INK)
    return im


def paste(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """把 src 按透明度叠到 dst 的 (x, y)；超出 dst 的部分裁掉（alpha_composite 不接受负坐标）。"""
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(src.width, dst.width - x), min(src.height, dst.height - y)
    if right <= left or bottom <= top:
        return
    dst.alpha_composite(src, (x + left, y + top), (left, top, right, bottom))


def compose(sprite: Image.Image, sprite_bottom: int, bubble: Image.Image | None, bubble_bottom: int,
            min_w: int, height: int) -> Image.Image:
    """整帧：立绘底边中点落在 (宽/2, sprite_bottom)；气泡水平居中、底边（尖角）落在 bubble_bottom。
    宽度取 min_w 和气泡宽里大的那个。"""
    w = max(min_w, bubble.width if bubble else 0)
    out = Image.new('RGBA', (w, height), (0, 0, 0, 0))
    paste(out, sprite, w // 2 - sprite.width // 2, sprite_bottom - sprite.height)
    if bubble is not None:
        paste(out, bubble, w // 2 - bubble.width // 2, bubble_bottom - bubble.height)
    return out


def draw_marks(image: Image.Image, marks: list, x: float, y: float) -> None:
    """把 z Z 这类小记号画到 image 上（就地修改）。(x, y) 是记号飘出来的起点，marks 来自 effects。
    浅色字、深色描边，什么背景上都看得清。"""
    layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for m in marks:
        if m.alpha > 0:
            d.text((x + m.dx, y + m.dy), m.text, font=_font(m.size), fill=PAPER[:3] + (m.alpha,),
                   stroke_width=max(1, round(m.size / 10)), stroke_fill=INK[:3] + (m.alpha,))
    image.alpha_composite(layer)
