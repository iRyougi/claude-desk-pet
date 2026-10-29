# B 动画 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给桌宠加上眨眼、坐下/站起过渡、被拎着摇摆、下落、打瞌睡（带飘动的 z Z）。

**Architecture:** 素材由现有的 `tools/prep_sprites.py` 处理成透明立绘；眨眼只做"眼睛补丁"，运行时贴回原立绘。姿势选择全部是 `motion.py` 里的纯函数：`choose_pose` 认识新姿势，`settle` 负责坐下/站起过渡，`swing_step` 负责被拎着时的摇摆方向。眨眼节奏（`pet/blink.py`）和 z Z 的位置（`pet/effects.py`）也是纯函数；`render.draw_marks` 负责把 z Z 画上去。`pet.pyw` 只负责接线。

**Tech Stack:** Python 3.14、Pillow 12.2、tkinter，测试用 unittest。

**Spec:** `docs/superpowers/specs/2026-10-29-desk-pet-polish-design.md`（本计划实现其中的「B 动画」）

## Global Constraints

- 只支持 Windows；不新增第三方依赖（只有 Pillow）。
- 测试命令：`python -m unittest discover -s tests`（没有 pytest）；测试文件用 `sys.path.insert(0, .../pet)` 或 `.../tools` 导入，照现有测试的写法。测试输出不能有警告（Pillow 12.2 里 `getdata()` 已弃用，用 `tobytes()` 或 `get_flattened_data()`）。
- 新代码：中文注释、frozen dataclass、纯函数优先；不改动入参对象。
- 眨眼姿势只有 `sit-swing-1`、`sit-watch`、`typing`；每 2.5～6 秒一次，闭眼 0.12 秒，约 20% 连眨两下；走路、跳、下落、石化、睡觉时不眨。
- 坐下过渡 2 帧共约 0.25 秒（本计划取 0.24 秒，每帧 0.12 秒），站起倒着播；坐下/站起不再"蹦一下"，换状态时的小跳保留。
- 被拎着：拖得快就按拖动方向的反方向歪（立绘画的是"往左拖"，往右拖时翻转），速度回落后 0.3 秒回正；下落用 `fall`；跳去别的窗口继续用 `jump`。
- 睡觉：等你回复超过 10 分钟（`idle`）且坐着时打瞌睡，2 帧约 1.2 秒交替；z Z 由代码画，每 1.5 秒冒一个；睡着时不眨眼、不晃腿、不溜达。
- 素材源图在 `art/gpt-output/`（不进 git，见 Task 1 的 ruling）；成品立绘和眼睛补丁进 `pet/sprites/`。

### 与 spec 的差异（本计划的决定）

- spec B1 写眼睛补丁"用 `tone.adjust` 对齐原图色调"。实际编辑图和原图色调几乎一样，而一小块眼睛里没有头发、白色可供 `tone` 测量；改为**羽化补丁边缘**（2 像素）来消除接缝，不做色调调整。
- spec B2/B3/B4 把两帧素材写成两张图；用户实际让 GPT 把每组两帧画在一张图里（`下蹲两帧`、`被拎两帧`、`瞌睡两帧`），由 `prep_sprites` 的切帧功能切开。
- 过渡帧的"接触线"：`sit-down-1`（下蹲，脚还踩着边）取 1.0，`sit-down-2`（屁股刚碰到边、腿往前伸）取 0.85，坐稳后是原来的 0.70。
- 缩放系数是在写计划时用轮廓重合度量出来的（瞌睡对 `sit-swing-1` 重合度 0.95，被戳对 `smile` 0.91），写死在 `SHEETS` 里。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `tools/prep_sprites.py`（改） | 新素材登记进 `SHEETS`；找不到源图的立绘表跳过（不再要求所有源图都在） |
| `tools/blink_patch.py`（新） | 导出给 GPT 编辑的绿底原图；从编辑图里裁出眼睛补丁 |
| `pet/sprites/*.png`、`*.blink.png`、`patches.json`（新） | 成品立绘、眼睛补丁和补丁位置 |
| `pet/motion.py`（改） | 新姿势、`Swing`/`swing_step`、`Posture`/`settle` |
| `pet/blink.py`（新） | 眨眼节奏 |
| `pet/effects.py`（新） | z Z 的位置和透明度 |
| `pet/render.py`（改） | `draw_marks`；`_font` 加缓存 |
| `pet/pet.pyw`（改） | 接线 |
| `.gitignore`、`README.md`、spec（改） | 文档 |
| `tests/test_prep_sheets.py`、`test_blink_patch.py`、`test_blink.py`、`test_effects.py`（新）；`test_motion.py`、`test_render.py`（改） | 测试 |

---

### Task 1: 处理新立绘

**Files:**
- Modify: `tools/prep_sprites.py`（`SHEETS`、`find_source` → `available`、`main`）
- Modify: `.gitignore`
- Create: `tests/test_prep_sheets.py`
- Create（运行工具生成）: `pet/sprites/sit-down-1.png`、`sit-down-2.png`、`held.png`、`held-swing.png`、`fall.png`、`sleep-1.png`、`sleep-2.png`、`shy.png`、`poked.png`

**Interfaces:**
- Produces: `prep_sprites.available(folder: str, sheets=SHEETS) -> list[tuple[Sheet, str]]`；上面 9 张立绘文件。

- [ ] **Step 1: 写失败的测试 `tests/test_prep_sheets.py`**

```python
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from prep_sprites import SHEETS, available  # noqa: E402


def touch(folder, name):
    open(os.path.join(folder, name), 'wb').close()


class AvailableTest(unittest.TestCase):
    def test_only_sheets_with_a_source_are_returned(self):
        with tempfile.TemporaryDirectory() as d:
            touch(d, '瞌睡两帧.png')
            touch(d, '说明.txt')
            found = available(d)
            self.assertEqual([s.keyword for s, _ in found], ['瞌睡两帧'])
            self.assertEqual(found[0][1], os.path.join(d, '瞌睡两帧.png'))

    def test_two_sources_for_one_keyword_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            touch(d, '害羞.png')
            touch(d, '害羞-v2.png')
            with self.assertRaises(SystemExit):
                available(d)

    def test_empty_folder_gives_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(available(d), [])


class SheetsTest(unittest.TestCase):
    def test_new_sprites_are_registered(self):
        names = {n for s in SHEETS for n in s.names}
        for n in ('sit-down-1', 'sit-down-2', 'held', 'held-swing', 'fall', 'sleep-1', 'sleep-2', 'shy', 'poked'):
            self.assertIn(n, names)

    def test_keywords_do_not_overlap(self):
        keys = [s.keyword for s in SHEETS]
        for a in keys:
            for b in keys:
                if a != b:
                    self.assertNotIn(a, b)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_prep_sheets -v`
Expected: FAIL，`ImportError: cannot import name 'available'`

- [ ] **Step 3: 改 `tools/prep_sprites.py`**

在 `SHEETS` 末尾（`Sheet('落地', ('land',), 0.294),` 之后）加：

```python
    # 下面这批是 B 动画、C 互动的新素材（GPT 出图，art/gpt-output/）。两帧一组的画在一张横图里，人物比单张图小，
    # 所以系数大一些；系数是按轮廓和原立绘的重合度量出来的（瞌睡对 sit-swing-1、被戳对 smile）
    Sheet('下蹲两帧', ('sit-down-1', 'sit-down-2'), 0.48),
    Sheet('被拎两帧', ('held', 'held-swing'), 0.455),
    Sheet('下落', ('fall',), 0.31),
    Sheet('瞌睡两帧', ('sleep-1', 'sleep-2'), 0.485),
    Sheet('害羞', ('shy',), 0.30),
    Sheet('被戳', ('poked',), 0.30),
```

把整个 `find_source` 函数替换为：

```python
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
```

在 `main` 里，把：

```python
    keyed = [(s, key_green(Image.open(find_source(args[0], s.keyword)))) for s in SHEETS]
```

替换为：

```python
    found = available(args[0])
    if not found:
        print(f'{args[0]} 里没有找到任何源图（文件名里要带关键字）')
        return 1
    skipped = [s.keyword for s in SHEETS if s not in {f for f, _ in found}]
    if skipped:
        print('没有源图、跳过：' + '、'.join(skipped))
    keyed = [(s, key_green(Image.open(path))) for s, path in found]
```

同时更新文件开头的文档字符串里"用法"那一段，加一句：`只处理文件夹里找得到源图的立绘；没有源图的保持原样。`

确认别处没有用到 `find_source`：Run `grep -rn "find_source" tools tests` — Expected: 没有输出。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m unittest tests.test_prep_sheets -v`
Expected: 5 个测试 PASS

- [ ] **Step 5: `.gitignore` 加 `art/`**

在 `.gitignore` 末尾加一行 `art/`（GPT 源图和给 GPT 的导出图都很大，原有立绘的源图也一直没进 git）。

- [ ] **Step 6: 生成新立绘**

Run: `python tools/prep_sprites.py art/gpt-output`
Expected:
- 输出里列出被跳过的旧关键字（`六帧`、`双坐姿` 等）
- 打印「新立绘 / 原立绘 / 调整后」三行色调
- 写出 9 行：`sit-down-1`、`sit-down-2`、`held`、`held-swing`、`fall`、`sleep-1`、`sleep-2`、`shy`、`poked`，每张高度大约 380～440 像素

Run: `git status --short pet/sprites` — Expected: 只有这 9 个新文件（`??`），旧立绘没有被改动（没有 ` M`）。如果旧立绘被改了，说明跳过逻辑不对，`git checkout -- pet/sprites` 还原后排查。

- [ ] **Step 7: 跑全部测试**

Run: `python -m unittest discover -s tests`
Expected: 全部通过

- [ ] **Step 8: Commit**

```bash
git add tools/prep_sprites.py tests/test_prep_sheets.py .gitignore pet/sprites/sit-down-1.png pet/sprites/sit-down-2.png pet/sprites/held.png pet/sprites/held-swing.png pet/sprites/fall.png pet/sprites/sleep-1.png pet/sprites/sleep-2.png pet/sprites/shy.png pet/sprites/poked.png
git commit -m "feat: process the new sit-down, held, fall, sleep, shy and poked sprites"
```

---

### Task 2: 眼睛补丁

**Files:**
- Create: `tools/blink_patch.py`
- Create: `tests/test_blink_patch.py`
- Create（运行工具生成）: `pet/sprites/sit-swing-1.blink.png`、`sit-watch.blink.png`、`typing.blink.png`、`pet/sprites/patches.json`

**Interfaces:**
- Produces:
  - `blink_patch.Placement(k: float, x: int, y: int)`（frozen dataclass）
  - `blink_patch.placement(size: tuple[int, int]) -> Placement`
  - `blink_patch.export_image(sprite: Image.Image) -> Image.Image`（RGB，1024×1536 绿底）
  - `blink_patch.dense_mask(a: Image.Image, b: Image.Image) -> Image.Image`（L）
  - `blink_patch.build_patch(sprite, original_export, edited) -> tuple[Image.Image, tuple[int, int]]`
  - `pet/sprites/patches.json` 的格式：`{"<立绘名>": {"x": int, "y": int}}`，补丁文件是 `pet/sprites/<立绘名>.blink.png`

- [ ] **Step 1: 写失败的测试 `tests/test_blink_patch.py`**

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from PIL import Image, ImageDraw  # noqa: E402

from blink_patch import build_patch, export_image, placement  # noqa: E402

SKIN = (240, 210, 190, 255)


def sprite():
    """100×160 的假立绘：中间一块肤色身体，四周透明。"""
    im = Image.new('RGBA', (100, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((10, 10, 89, 149), fill=SKIN)
    return im


def to_export(p, x, y):
    return p.x + x * p.k, p.y + y * p.k


class PlacementTest(unittest.TestCase):
    def test_fits_into_the_canvas_with_feet_60px_above_bottom(self):
        p = placement((100, 160))
        self.assertAlmostEqual(p.k, 8.5)
        self.assertEqual((p.x, p.y), ((1024 - 850) // 2, 1536 - 60 - 1360))

    def test_export_is_green_outside_and_sprite_inside(self):
        im, p = export_image(sprite()), placement((100, 160))
        self.assertEqual(im.size, (1024, 1536))
        self.assertEqual(im.getpixel((0, 0)), (0, 255, 0))
        x, y = to_export(p, 50, 80)
        self.assertEqual(im.getpixel((round(x), round(y))), SKIN[:3])


class BuildPatchTest(unittest.TestCase):
    def edited(self, s, block=(40, 40, 60, 50)):
        a = export_image(s)
        b = a.copy()
        p = placement(s.size)
        d = ImageDraw.Draw(b)
        d.rectangle((*to_export(p, block[0], block[1]), *to_export(p, block[2], block[3])), fill=(40, 30, 30))
        # 压缩噪点：一条贯穿身体的 2 像素细线，不能被当成改动
        d.line([to_export(p, 10, 120), to_export(p, 89, 120)], fill=(0, 0, 0), width=2)
        return a, b

    def test_patch_covers_the_changed_block_only(self):
        s = sprite()
        a, b = self.edited(s)
        patch, (x, y) = build_patch(s, a, b)
        self.assertTrue(35 <= x <= 40 and 35 <= y <= 40, (x, y))
        self.assertTrue(60 <= x + patch.width <= 65 and 50 <= y + patch.height <= 55, (x, y, patch.size))

    def test_patch_center_is_opaque_and_dark(self):
        s = sprite()
        a, b = self.edited(s)
        patch, (x, y) = build_patch(s, a, b)
        r, g, bl, alpha = patch.getpixel((50 - x, 45 - y))
        self.assertEqual(alpha, 255)
        self.assertLess(r, 80)

    def test_patch_is_transparent_where_the_sprite_is(self):
        s = sprite()
        a, b = self.edited(s, block=(0, 40, 20, 50))  # 一半在身体外面
        patch, (x, y) = build_patch(s, a, b)
        self.assertEqual(patch.getpixel((5 - x, 45 - y))[3], 0)

    def test_no_change_is_an_error(self):
        s = sprite()
        a = export_image(s)
        with self.assertRaises(ValueError):
            build_patch(s, a, a.copy())


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_blink_patch -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'blink_patch'`

- [ ] **Step 3: 实现 `tools/blink_patch.py`**

```python
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
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m unittest tests.test_blink_patch -v`
Expected: 6 个测试 PASS。如果 `test_patch_covers_the_changed_block_only` 的范围差一两个像素，先打印 `(x, y, patch.size)` 看是扩边算多了还是少了，调整的是测试注释里的推理，不是随意放宽断言；确实需要放宽时在报告里写清原因。

- [ ] **Step 5: 生成三张眼睛补丁**

Run:

```bash
python tools/blink_patch.py build sit-swing-1 art/gpt-output/眨眼-静坐.png
python tools/blink_patch.py build sit-watch art/gpt-output/眨眼-托腮.png
python tools/blink_patch.py build typing art/gpt-output/眨眼-打字.png
```

Expected: 每条打印一行补丁尺寸和位置，补丁大约 40～120 像素宽、15～60 像素高，位置在立绘上部（y 小于立绘高度的一半）。`pet/sprites/patches.json` 有三个条目。如果某张报"改动太分散"，不要调参数绕过，把报错原文写进报告（状态 DONE_WITH_CONCERNS），继续做其他两张。

- [ ] **Step 6: 跑全部测试**

Run: `python -m unittest discover -s tests`
Expected: 全部通过

- [ ] **Step 7: Commit**

```bash
git add tools/blink_patch.py tests/test_blink_patch.py pet/sprites/sit-swing-1.blink.png pet/sprites/sit-watch.blink.png pet/sprites/typing.blink.png pet/sprites/patches.json
git commit -m "feat: eye patches for blinking, cut from GPT edits of the original sprites"
```

---

### Task 3: 新姿势、摇摆、坐下过渡（motion.py）

**Files:**
- Modify: `pet/motion.py`
- Modify: `tests/test_motion.py`

**Interfaces:**
- Produces（pet.pyw 和 C 计划会用）:
  - 常量 `TRANSITION_S = 0.24`、`SLEEP_S = 1.2`、`SWING_HOLD_S = 0.3`、`SITTING`、`AIRBORNE`
  - `ANCHOR` 新增 `'sit-down-1': 1.0, 'sit-down-2': 0.85, 'sleep-1': 0.70, 'sleep-2': 0.70`
  - `Swing(direction: int = 0, until: float = 0.0)`，`swing_step(s: Swing, vx: float, now: float, threshold: float) -> Swing`
  - `Posture(sitting: bool = False, since: float = -1e9)`，`settle(p: Posture, target: Pose, now: float) -> tuple[Posture, Pose]`
  - `choose_pose(..., swing: int = 0)`：新增关键字参数

- [ ] **Step 1: 改测试 `tests/test_motion.py`**

导入行改为：

```python
from motion import (  # noqa: E402
    Motion, Pose, Posture, Rect, Surface, Swing, WinInfo, build_surfaces, choose_pose, choose_surface, drop, hold,
    hop_to, release, settle, spawn, swing_step, tick, walk_to,
)
```

把 `ChoosePoseTest.test_in_the_air_she_uses_the_jump_pose` 整个替换为：

```python
    def test_in_the_air_each_situation_has_its_own_pose(self):
        self.assertEqual(self.pose(drop(500.0, 0.0, 0.0)).file, 'fall')
        self.assertEqual(self.pose(hold(self.perched(), 5.0, 5.0)).file, 'held')
        self.assertEqual(self.pose(hop_to(self.perched(), G, 1.0)).file, 'jump')

    def test_held_and_swung_she_leans_against_the_drag(self):
        held = hold(self.perched(), 5.0, 5.0)
        left, right = self.pose(held, swing=-1), self.pose(held, swing=1)
        self.assertEqual((left.file, left.flip), ('held-swing', False))   # 立绘画的就是往左拖
        self.assertEqual((right.file, right.flip), ('held-swing', True))

    def test_idle_she_dozes_on_two_alternating_frames(self):
        files = [self.pose(self.perched(), state='idle', now=t * 0.3).file for t in range(20)]
        self.assertEqual(set(files), {'sleep-1', 'sleep-2'})
        self.assertEqual(self.pose(self.perched(), state='idle').anchor, 0.70)

    def test_dozing_ignores_the_leg_swing(self):
        m = replace(self.perched(), swing_until=100.0)
        self.assertTrue(self.pose(m, state='idle', now=50.0).file.startswith('sleep'))
```

在 `test_while_swinging_the_two_frames_alternate_slowly` 和 `test_swing_ends_when_the_timer_runs_out` 里，把 `state='idle'` 改成 `state='waiting'`（晃腿是醒着时的小动作；默认 `age=100.0` 已经过了敲门的 8 秒）。

在文件末尾（`if __name__` 之前）加：

```python
SIT = Pose('sit-swing-1', False, 0.70)
STAND = Pose('knock', False, 1.0)
AIR = Pose('held', False, 1.0)


class SwingTest(unittest.TestCase):
    def test_fast_drag_leans_and_holds_briefly_after_stopping(self):
        s = swing_step(Swing(), -400.0, 1.0, 250.0)
        self.assertEqual(s.direction, -1)
        self.assertEqual(swing_step(s, 0.0, 1.2, 250.0).direction, -1)   # 停下后 0.3 秒内还歪着
        self.assertEqual(swing_step(s, 0.0, 1.31, 250.0).direction, 0)

    def test_slow_drag_does_not_lean(self):
        self.assertEqual(swing_step(Swing(), 100.0, 1.0, 250.0), Swing())

    def test_reversing_the_drag_flips_the_lean(self):
        s = swing_step(Swing(), -400.0, 1.0, 250.0)
        self.assertEqual(swing_step(s, 500.0, 1.1, 250.0).direction, 1)


class SettleTest(unittest.TestCase):
    def seated(self):
        p, _ = settle(Posture(), SIT, 0.0)
        p, _ = settle(p, SIT, 1.0)
        return p

    def test_sitting_down_plays_two_frames_then_the_target(self):
        p, a = settle(Posture(), SIT, 10.0)
        _, b = settle(p, SIT, 10.15)
        _, c = settle(p, SIT, 10.3)
        self.assertEqual((a.file, b.file, c.file), ('sit-down-1', 'sit-down-2', 'sit-swing-1'))
        self.assertEqual((a.anchor, b.anchor), (1.0, 0.85))

    def test_standing_up_plays_them_backwards(self):
        p, a = settle(self.seated(), STAND, 5.0)
        _, b = settle(p, STAND, 5.15)
        _, c = settle(p, STAND, 5.3)
        self.assertEqual((a.file, b.file, c.file), ('sit-down-2', 'sit-down-1', 'knock'))

    def test_picked_up_while_sitting_skips_the_transition(self):
        p, a = settle(self.seated(), AIR, 2.0)
        self.assertEqual(a.file, 'held')
        self.assertFalse(p.sitting)

    def test_switching_between_sitting_poses_needs_no_transition(self):
        _, a = settle(self.seated(), Pose('typing', False, 0.80), 2.0)
        self.assertEqual(a.file, 'typing')

    def test_standing_stays_standing_without_transition(self):
        _, a = settle(Posture(), STAND, 0.0)
        self.assertEqual(a.file, 'knock')

    def test_transition_keeps_the_target_flip(self):
        _, a = settle(Posture(), Pose('sit-watch', True, 0.70), 0.0)
        self.assertEqual((a.file, a.flip), ('sit-down-1', True))
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_motion -v`
Expected: FAIL，`ImportError: cannot import name 'Posture'`

- [ ] **Step 3: 改 `pet/motion.py`**

在常量区（`LAND_TOL = 8.0 ...` 那一行之后）加：

```python
TRANSITION_S = 0.24           # 坐下/站起的过渡一共多久（两帧各一半）
SLEEP_S = 1.2                 # 打瞌睡两帧交替的间隔
SWING_HOLD_S = 0.3            # 被拎着甩动停下后，身体还歪着多久才回正
```

把 `ANCHOR` 那一行替换为：

```python
ANCHOR = {'sit-swing-1': 0.70, 'sit-swing-2': 0.70, 'sit-watch': 0.70, 'typing': 0.80,
          'sit-down-1': 1.0, 'sit-down-2': 0.85, 'sleep-1': 0.70, 'sleep-2': 0.70}
SITTING = frozenset({'sit-swing-1', 'sit-swing-2', 'sit-watch', 'typing', 'sleep-1', 'sleep-2'})
AIRBORNE = frozenset({'jump', 'fall', 'held', 'held-swing', 'land'})   # 这些姿势切换时不播坐下/站起过渡
```

在 `Pose` dataclass 之后加：

```python
@dataclass(frozen=True)
class Swing:
    """被拎着时身体往哪边甩：-1 是往左拖（身体落在右边），1 是往右拖，0 不甩。"""
    direction: int = 0
    until: float = 0.0


@dataclass(frozen=True)
class Posture:
    """她现在算坐着还是站着，从什么时候开始的；用来播坐下/站起的过渡。"""
    sitting: bool = False
    since: float = -1e9
```

在 `gait_progress` 之前加：

```python
def swing_step(s: Swing, vx: float, now: float, threshold: float) -> Swing:
    """拖得比 threshold 快就按拖动方向歪；慢下来以后再歪 SWING_HOLD_S 秒才回正。"""
    if abs(vx) >= threshold:
        return Swing(1 if vx > 0 else -1, now + SWING_HOLD_S)
    return s if now < s.until else Swing()


def settle(p: Posture, target: Pose, now: float) -> tuple:
    """坐下/站起的过渡：目标姿势从站变坐（或反过来）时，先播 TRANSITION_S 秒的过渡帧，站起就倒着播。
    在空中的姿势（被拎着、下落、跳）直接切，不过渡。"""
    if target.file in AIRBORNE:
        return Posture(False), target
    want = target.file in SITTING
    if want != p.sitting:
        p = Posture(want, now)
    age = now - p.since
    if age >= TRANSITION_S:
        return p, target
    frames = ('sit-down-1', 'sit-down-2') if p.sitting else ('sit-down-2', 'sit-down-1')
    file = frames[min(1, int(age / (TRANSITION_S / 2)))]
    return p, Pose(file, target.flip, ANCHOR[file])
```

`choose_pose` 的签名加 `swing: int = 0`：

```python
def choose_pose(m: Motion | None, now: float, state: str, state_age: float, remind: int = 0,
                speech: str | None = None, roam: bool = True, px_per_frame: float | None = None,
                swing: int = 0) -> Pose:
```

文档字符串末尾加一行：`swing：被拎着时身体往哪边甩（见 Swing）。`

把：

```python
    if m.mode in ('held', 'fall', 'hop'):
        return Pose('jump', m.face < 0, 1.0)  # 被拎着、掉下去、跳过去，都是四肢悬空的这一张
```

替换为：

```python
    if m.mode == 'held':
        if swing:
            return Pose('held-swing', swing > 0, 1.0)  # 立绘画的是往左拖（身体落在右边）；往右拖就翻过来
        return Pose('held', False, 1.0)
    if m.mode == 'fall':
        return Pose('fall', m.face < 0, 1.0)
    if m.mode == 'hop':
        return Pose('jump', m.face < 0, 1.0)
```

在 `if state == 'waiting' and state_age < KNOCK_S:` 那两行之后加：

```python
    if state == 'idle':  # 等你回复太久：坐着打瞌睡，头一点一点
        file = f'sleep-{1 + int(now / SLEEP_S) % 2}'
        return Pose(file, False, ANCHOR[file])
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m unittest tests.test_motion -v`
Expected: 全部 PASS（原有测试 + 新增的 4 个 ChoosePose、3 个 Swing、6 个 Settle）

- [ ] **Step 5: 跑全部测试并 Commit**

Run: `python -m unittest discover -s tests` — Expected: 全部通过

```bash
git add pet/motion.py tests/test_motion.py
git commit -m "feat: held, fall and dozing poses, drag lean and sit-down transitions"
```

---

### Task 4: 眨眼节奏、z Z 位置、画记号

**Files:**
- Create: `pet/blink.py`、`pet/effects.py`
- Modify: `pet/render.py`（`_font` 加缓存、新增 `draw_marks`）
- Create: `tests/test_blink.py`、`tests/test_effects.py`
- Modify: `tests/test_render.py`

**Interfaces:**
- Produces:
  - `blink.Blink(next_at: float, closed_until: float = 0.0, again_at: float | None = None)`；`blink.start(now: float, rng) -> Blink`；`blink.step(b: Blink, now: float, rng) -> Blink`；`blink.closed(b: Blink, now: float) -> bool`；常量 `BLINK_EVERY = (2.5, 6.0)`、`BLINK_CLOSED = 0.12`、`BLINK_GAP = 0.18`、`BLINK_DOUBLE = 0.2`
  - `effects.Mark(text: str, dx: float, dy: float, alpha: int, size: int)`；`effects.zz_marks(t: float, scale: float) -> list[Mark]`；常量 `ZZ_EVERY = 1.5`、`ZZ_LIFE = 3.0`
  - `render.draw_marks(image: Image.Image, marks: list, x: float, y: float) -> None`（就地修改 image）
  - rng 只需要 `uniform(a, b)` 和 `random()` 两个方法（`random` 模块本身就满足）

- [ ] **Step 1: 写失败的测试**

`tests/test_blink.py`：

```python
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from blink import BLINK_CLOSED, closed, start, step  # noqa: E402


class FixedRng:
    """uniform 永远返回 u，random 永远返回 r。"""
    def __init__(self, u=3.0, r=0.5):
        self.u, self.r = u, r

    def uniform(self, a, b):
        return self.u

    def random(self):
        return self.r


class BlinkTest(unittest.TestCase):
    def test_eyes_open_until_the_first_blink(self):
        b = start(0.0, FixedRng())
        self.assertFalse(closed(step(b, 2.9, FixedRng()), 2.9))

    def test_a_blink_closes_the_eyes_briefly(self):
        b = step(start(0.0, FixedRng()), 3.0, FixedRng())
        self.assertTrue(closed(b, 3.05))
        self.assertFalse(closed(b, 3.0 + BLINK_CLOSED + 0.01))
        self.assertAlmostEqual(b.next_at, 3.0 + BLINK_CLOSED + 3.0)

    def test_sometimes_blinks_twice(self):
        rng = FixedRng(r=0.1)
        b = step(start(0.0, rng), 3.0, rng)
        self.assertIsNotNone(b.again_at)
        b2 = step(b, b.again_at, rng)
        self.assertTrue(closed(b2, b.again_at + 0.05))
        self.assertIsNone(b2.again_at)

    def test_single_blink_when_the_dice_say_so(self):
        b = step(start(0.0, FixedRng(r=0.9)), 3.0, FixedRng(r=0.9))
        self.assertIsNone(b.again_at)

    def test_rate_over_a_long_time(self):
        rng, b, t, blinks, was = random.Random(7), None, 0.0, 0, False
        b = start(0.0, rng)
        while t < 1000.0:
            b = step(b, t, rng)
            now = closed(b, t)
            blinks += now and not was
            was, t = now, t + 1 / 30
        self.assertTrue(150 < blinks < 450, blinks)


if __name__ == '__main__':
    unittest.main()
```

`tests/test_effects.py`：

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from effects import ZZ_LIFE, zz_marks  # noqa: E402


class ZzMarksTest(unittest.TestCase):
    def test_a_fresh_mark_is_fully_visible_at_the_start(self):
        marks = zz_marks(3.0, 1.0)
        newest = min(marks, key=lambda m: -m.alpha)
        self.assertEqual((newest.alpha, newest.dx, newest.dy), (255, 0.0, 0.0))

    def test_only_marks_younger_than_their_life_are_shown(self):
        self.assertEqual(len(zz_marks(4.0, 1.0)), 2)   # 1.5 秒和 3.0 秒冒出的两个；0 秒那个已经飘走了

    def test_older_marks_are_higher_and_fainter(self):
        a, b = sorted(zz_marks(4.0, 1.0), key=lambda m: m.alpha)
        self.assertLess(a.dy, b.dy)       # 更老的飘得更高（dy 更负）
        self.assertGreater(a.dx, b.dx)    # 也更往右

    def test_scale_multiplies_distance_and_size(self):
        a = zz_marks(4.0, 1.0)
        b = zz_marks(4.0, 2.0)
        self.assertAlmostEqual(b[0].dy, 2 * a[0].dy)
        self.assertEqual(b[0].size, 2 * a[0].size)

    def test_big_and_small_alternate(self):
        texts = {m.text for m in zz_marks(4.0, 1.0)}
        self.assertEqual(texts, {'Z', 'z'})

    def test_nothing_older_than_life(self):
        self.assertTrue(all(m.alpha > 0 for m in zz_marks(100.0, 1.0)))
        self.assertLessEqual(len(zz_marks(100.0, 1.0)), int(ZZ_LIFE / 1.5) + 1)


if __name__ == '__main__':
    unittest.main()
```

在 `tests/test_render.py` 的导入里加 `draw_marks`，从 `effects` 导入 `Mark`（在 `from render import ...` 那一行之后加 `from effects import Mark  # noqa: E402`），并在文件末尾（`if __name__` 之前）加：

```python
class DrawMarksTest(unittest.TestCase):
    def test_draws_near_the_origin(self):
        im = Image.new('RGBA', (80, 80), (0, 0, 0, 0))
        draw_marks(im, [Mark('Z', 0.0, 0.0, 255, 20)], 30, 30)
        box = im.getchannel('A').getbbox()
        self.assertIsNotNone(box)
        self.assertTrue(25 <= box[0] <= 40 and 25 <= box[1] <= 45, box)

    def test_invisible_mark_draws_nothing(self):
        im = Image.new('RGBA', (80, 80), (0, 0, 0, 0))
        draw_marks(im, [Mark('Z', 0.0, 0.0, 0, 20)], 30, 30)
        self.assertIsNone(im.getchannel('A').getbbox())
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python -m unittest tests.test_blink tests.test_effects tests.test_render -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'blink'` / `'effects'`，以及 `cannot import name 'draw_marks'`

- [ ] **Step 3: 实现 `pet/blink.py`**

```python
"""眨眼的节奏：每隔 2.5～6 秒眨一次，闭眼 0.12 秒，偶尔连眨两下。

纯函数：时间和随机数（有 uniform、random 两个方法的对象，random 模块就行）由调用方给。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

BLINK_EVERY = (2.5, 6.0)   # 两次眨眼之间隔多久（秒）
BLINK_CLOSED = 0.12        # 一次闭眼多久
BLINK_GAP = 0.18           # 连眨时两下之间睁开多久
BLINK_DOUBLE = 0.2         # 连眨两下的概率


@dataclass(frozen=True)
class Blink:
    next_at: float                  # 下一次眨眼的时刻
    closed_until: float = 0.0       # 眼睛闭到什么时候
    again_at: float | None = None   # 连眨时第二下的时刻


def start(now: float, rng) -> Blink:
    return Blink(next_at=now + rng.uniform(*BLINK_EVERY))


def step(b: Blink, now: float, rng) -> Blink:
    if b.again_at is not None and now >= b.again_at:
        return replace(b, closed_until=now + BLINK_CLOSED, again_at=None)
    if now >= b.next_at:
        again = now + BLINK_CLOSED + BLINK_GAP if rng.random() < BLINK_DOUBLE else None
        return Blink(next_at=now + BLINK_CLOSED + rng.uniform(*BLINK_EVERY), closed_until=now + BLINK_CLOSED,
                     again_at=again)
    return b


def closed(b: Blink, now: float) -> bool:
    return now < b.closed_until
```

- [ ] **Step 4: 实现 `pet/effects.py`**

```python
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
```

- [ ] **Step 5: 改 `pet/render.py`**

文件开头的导入加 `import functools`。给 `_font` 加缓存（每帧都会按字号取字体，不能每次都从磁盘读）：

```python
@functools.lru_cache(maxsize=16)
def _font(px: int):
```

在文件末尾加：

```python
def draw_marks(image: Image.Image, marks: list, x: float, y: float) -> None:
    """把 z Z 这类小记号画到 image 上（就地修改）。(x, y) 是记号飘出来的起点，marks 来自 effects。"""
    layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for m in marks:
        if m.alpha > 0:
            d.text((x + m.dx, y + m.dy), m.text, font=_font(m.size), fill=INK[:3] + (m.alpha,))
    image.alpha_composite(layer)
```

- [ ] **Step 6: 跑测试，确认通过**

Run: `python -m unittest tests.test_blink tests.test_effects tests.test_render -v`
Expected: 全部 PASS，没有警告

- [ ] **Step 7: 跑全部测试并 Commit**

Run: `python -m unittest discover -s tests` — Expected: 全部通过

```bash
git add pet/blink.py pet/effects.py pet/render.py tests/test_blink.py tests/test_effects.py tests/test_render.py
git commit -m "feat: blink timing, floating zZ marks and a helper to draw them"
```

---

### Task 5: 接到桌宠上

**Files:**
- Modify: `pet/pet.pyw`

**Interfaces:**
- Consumes: Task 2 的 `patches.json` 和 `<名字>.blink.png`；Task 3 的 `Posture`、`Swing`、`settle`、`swing_step`、`choose_pose(swing=...)`；Task 4 的 `blink.start/step/closed`、`effects.zz_marks`、`render.draw_marks`
- Produces（C 计划会用）: `Pet.sprite_image(file, flip, blink=False)`、`Pet.posture`、`Pet.swing`、`Pet.blink`

没有新的单元测试（界面接线），靠全部测试 + 手动冒烟。

- [ ] **Step 1: 导入和常量**

把 `from motion import (...)` 那一段替换为：

```python
from motion import (
    FIXED_SPRITES, WALK_FRAMES, Posture, Swing, build_surfaces, choose_pose, choose_surface, hold, hop_to, release,
    settle, spawn, swing_step, tick, walk_to,
)
```

在 `from render import ...` 那一行改为：

```python
from render import BubbleStyle, bubble_image, compose, draw_marks  # noqa: E402
from blink import closed as eyes_closed, start as start_blink, step as step_blink  # noqa: E402
from effects import zz_marks  # noqa: E402
```

`SPRITE_FILES` 里加上新立绘：

```python
SPRITE_FILES = sorted(set(FIXED_SPRITES.values()) | {
    'remind-1', 'remind-2', 'remind-3', 'jump', 'land', 'sit-watch', 'sit-swing-1', 'sit-swing-2',
    'walk-1', 'walk-2', 'walk-3', 'walk-4', 'walk-5', 'walk-6',
    'sit-down-1', 'sit-down-2', 'held', 'held-swing', 'fall', 'sleep-1', 'sleep-2',
})
```

在 `BUBBLE_CACHE = ...` 之后加：

```python
SWING_V = 250         # 拖得比这快（像素/秒，100% 缩放），被拎着的她就往反方向歪
PATCHES = os.path.join(HERE, 'sprites', 'patches.json')   # 眨眼补丁的位置（tools/blink_patch.py 生成）
```

- [ ] **Step 2: 读补丁位置、`prepare` 支持贴补丁**

在 `read_latest` 函数之后加：

```python
def load_patches():
    """眨眼补丁：{立绘名: (x, y)}。文件坏了就当没有补丁（不眨眼），记一次日志。"""
    try:
        with open(PATCHES, encoding='utf-8') as f:
            return {name: (int(v['x']), int(v['y'])) for name, v in json.load(f).items()}
    except FileNotFoundError:
        return {}
    except Exception:
        log_error()
        return {}
```

`prepare` 整个替换为：

```python
def prepare(path, k, flip=False, patch=None):
    """按 k 倍缩放立绘（可水平翻转），保留透明度。patch=(补丁路径, x, y) 时先把补丁贴上去（眨眼）。
    按预乘透明度缩放，边缘才不会发黑。"""
    im = Image.open(path).convert('RGBA')
    if patch:
        im.alpha_composite(Image.open(patch[0]).convert('RGBA'), patch[1:])
    if flip:
        im = ImageOps.mirror(im)
    size = (max(1, round(im.width * k)), max(1, round(im.height * k)))
    return im.convert('RGBa').resize(size, Image.LANCZOS).convert('RGBA')
```

- [ ] **Step 3: `__init__` 里加状态**

在 `self.anchor = 1.0` 那一行之后加：

```python
        self.patches = load_patches()
        self.posture = Posture()       # 坐着还是站着（播坐下/站起的过渡用）
        self.swing = Swing()           # 被拎着时身体往哪边甩
        self.blink = start_blink(time.time(), random)
```

- [ ] **Step 4: `sprite_image` 支持眨眼版本**

替换为：

```python
    def sprite_image(self, file, flip, blink=False):
        key = (file, flip, blink)
        if key not in self.cache:
            patch = None
            if blink:
                x, y = self.patches[file]
                patch = (os.path.join(HERE, 'sprites', file + '.blink.png'), x, y)
            self.cache[key] = prepare(os.path.join(HERE, 'sprites', file + '.png'), self.k, flip, patch)
        return self.cache[key]
```

- [ ] **Step 5: `current_pose` 传摇摆方向，`apply_pose` 加过渡和眨眼**

`current_pose` 里的 `choose_pose(...)` 调用末尾加 `swing=self.swing.direction`：

```python
        return choose_pose(self.motion if self.roam else None, now, self.claude_state(), now - self.state_since,
                           remind=self.break_state.level, speech=self.speech_state(), roam=self.roam,
                           px_per_frame=self.px_per_frame, swing=self.swing.direction)
```

`apply_pose` 整个替换为：

```python
    def apply_pose(self):
        """按当前情况挑立绘：站坐之间先播过渡帧，有眼睛补丁的姿势按节奏眨眼；坐着的时候气泡跟着往下挪。
        返回 (姿势, 立绘图)。"""
        now = time.time()
        pose = self.current_pose()
        if self.roam:
            self.posture, pose = settle(self.posture, pose, now)
        blink = pose.file in self.patches and eyes_closed(self.blink, now)
        img = self.sprite_image(pose.file, pose.flip, blink)
        self.pose_key, self.anchor = (pose.file, pose.flip, blink), pose.anchor
        self.bubble_dy = round((1 - pose.anchor) * img.height)
        return pose, img
```

（原来"换了落点就蹦一下"的逻辑删掉：坐下/站起现在有过渡帧。换状态时的小跳在 `poll()` 里，不受影响。）

- [ ] **Step 6: 睡着了不溜达**

`can_wander` 里把 `self.claude_state() in ('waiting', 'idle')` 改成 `self.claude_state() == 'waiting'`，并在行尾注释 `# 发呆久了就睡着了，不溜达`。

- [ ] **Step 7: `bob_for` 认识新立绘**

把第一行判断：

```python
        if file in ('stone', 'jump', 'land') or file.startswith('walk'):
            return 0  # 走路立绘自带身体的起伏，不能再叠加
```

替换为：

```python
        if file in ('stone', 'jump', 'land', 'fall', 'held', 'held-swing') or file.startswith(('walk', 'sit-down')):
            return 0  # 走路、过渡、悬空的立绘自带动作，不能再叠加起伏
        if file.startswith('sleep'):
            return 1.0 * math.sin(t * 1.6)          # 打瞌睡：慢慢地呼吸
```

- [ ] **Step 8: `frame` 里推进眨眼和摇摆、画 z Z**

在 `frame` 里 `if self.hidden: return` 之后、`pose, img = self.apply_pose()` 之前加：

```python
        self.blink = step_blink(self.blink, t, random)
        held = self.roam and self.motion is not None and self.motion.mode == 'held'
        self.swing = swing_step(self.swing, self.throw_velocity()[0], t, SWING_V * self.scale) if held else Swing()
```

在 `image = compose(...)` 之后、`self.fit_width(image.width)` 之前加：

```python
        if pose.file.startswith('sleep'):  # z Z 从头顶右边冒出来
            top = sprite_bottom - img.height
            draw_marks(image, zz_marks(t, self.scale), image.width // 2 + round(img.width * 0.22),
                       top + round(img.height * 0.12))
```

- [ ] **Step 9: 检查**

Run: `python -m py_compile pet/pet.pyw` — Expected: 没有输出
Run: `grep -n "hop_at = time.time()  # 站起来" pet/pet.pyw` — Expected: 没有输出（旧的蹦一下已删）
Run: `python -m unittest discover -s tests` — Expected: 全部通过

- [ ] **Step 10: 手动冒烟（由 controller 和用户一起做，实现者跳过）**

用独立测试实例运行（不影响正在用的桌宠）：

```bash
D="$TEMP/cdp_smoke_b"; mkdir -p "$D/sessions"
echo '{"state": "waiting", "text": "轮到你啦！", "project": "claude-desk-pet", "ts": 0}' > "$D/sessions/a.json"
DESK_PET_PORT=47399 python pet/pet.pyw "$D"
```

确认：
1. 她坐下时先下蹲再坐稳，没有"蹦一下"；被拎起再放回窗口上，又会坐下；走路前会先站起来。
2. 坐着时隔几秒眨一下眼，偶尔连眨两下；托腮和打字时也会眨。
3. 拎起来不动是下垂的样子；左右快速甩，身体往拖动的反方向歪；停下一会儿回正。
4. 松手往下掉时是张手、头发上飘的下落姿势，落地后正常。
5. 睡觉：把测试会话改成发呆状态——`echo '{"state": "idle", "text": "", "project": "claude-desk-pet", "ts": 1}' > "$D/sessions/a.json"`（桌宠 0.25 秒内会读到）——她坐着打瞌睡，头一点一点，头顶右边飘 z Z；不溜达、不眨眼。再改回 `"state": "tool"`，她醒过来开始打字。

- [ ] **Step 11: Commit**

```bash
git add pet/pet.pyw
git commit -m "feat: blink, sit-down transitions, drag lean, falling and dozing in the pet"
```

---

### Task 6: 文档

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-29-desk-pet-polish-design.md`（B1 的色调对齐那一条）

- [ ] **Step 1: README**

在「🚶 走来走去，坐在你的窗口上」那一节的列表末尾（"不喜欢的话，右键关掉…"那一条之前）加：

```markdown
- 坐着的时候会眨眼，偶尔连眨两下；坐下、站起会先蹲一下，不会一下子跳过去
- 被你拎起来时手脚垂着；甩得快，身体会往反方向歪；松手掉下去时会张手、头发往上飘
- 等你回复太久（10 分钟），她会坐着打瞌睡，头顶飘 z Z；Claude 一开始干活她就醒了
```

在「自定义」一节"换立绘"那一条后面加：

```markdown
- **换眨眼**：用 `python tools/blink_patch.py export sit-swing-1` 导出绿底原图，让 AI 只把眼睛改成闭眼，再用 `python tools/blink_patch.py build sit-swing-1 <改好的图>` 生成补丁
```

- [ ] **Step 2: spec B1**

把：

```markdown
  3. 补丁色调用 `tone.adjust` 对齐原图。
```

改为：

```markdown
  3. 补丁边缘羽化 2 像素、透明度跟随原立绘，贴回去看不出接缝（编辑图和原图色调几乎一致，一小块眼睛里也没有头发、白色可供 `tone` 测量，所以不做色调调整）。
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-29-desk-pet-polish-design.md
git commit -m "docs: describe blinking, transitions, drag lean and dozing"
```
