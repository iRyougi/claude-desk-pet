"""给立绘补一圈深棕色外轮廓线：原来的立绘都有 1 到 2 像素的深色勾边，AI 新出的图没有，边缘是软的。"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter

OUTLINE = (30, 18, 14)  # 量出来的：原立绘最外圈深色像素的平均色
SOFT_ALPHA = 110        # 第二圈的不透明度（原图的线粗细约 1.5 像素）
CHARACTER_ALPHA = 20    # 透明度超过这个值才算角色的一部分


def add_outline(im: Image.Image) -> Image.Image:
    """返回新的 RGBA 图：在角色外面加一圈实线和半圈淡线。尺寸不变，不修改原图；调用方要自己留够边距。"""
    im = im.convert('RGBA')
    alpha = im.getchannel('A')
    near = alpha.filter(ImageFilter.MaxFilter(3)).point(lambda v: 255 if v > CHARACTER_ALPHA else 0)
    far = alpha.filter(ImageFilter.MaxFilter(5)).point(lambda v: SOFT_ALPHA if v > CHARACTER_ALPHA else 0)
    under = Image.new('RGBA', im.size, OUTLINE + (0,))
    under.putalpha(ImageChops.lighter(near, far))
    out = Image.new('RGBA', im.size, (0, 0, 0, 0))
    out.alpha_composite(under)
    out.alpha_composite(im)
    return out
