"""一次性验证：tk 窗口 + UpdateLayeredWindow 能不能共存。

用法：python tools/spike_layered.py [立绘名，默认 smile]
看四件事：边缘半透明没有锯齿和毛边；透明的地方鼠标能点穿；按住能拖动；右键能弹出菜单（菜单里"退出"）。
"""
import ctypes
import math
import os
import sys
import time
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'pet'))

import dpi  # noqa: E402

print('DPI 感知：', dpi.enable())

from PIL import Image  # noqa: E402

from layered import LayeredWindow  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else 'smile'
sprite = Image.open(os.path.join(ROOT, 'pet', 'sprites', name + '.png')).convert('RGBA')
W, H = sprite.width + 40, sprite.height + 40

root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
canvas = tk.Canvas(root, width=W, height=H, bg='black', highlightthickness=0, bd=0)
canvas.pack()
root.geometry(f'{W}x{H}+300+300')
root.update_idletasks()
layer = LayeredWindow(ctypes.windll.user32.GetParent(root.winfo_id()))
print('缩放：', dpi.scale_at(300, 300))

drag = None


def press(e):
    global drag
    drag = (e.x_root - root.winfo_x(), e.y_root - root.winfo_y())


def motion(e):
    if drag:
        root.geometry(f'+{e.x_root - drag[0]}+{e.y_root - drag[1]}')


def release(e):
    global drag
    drag = None


menu = tk.Menu(root, tearoff=0, font=('Microsoft YaHei UI', 10))
menu.add_command(label='退出', command=root.destroy)
canvas.bind('<ButtonPress-1>', press)
canvas.bind('<B1-Motion>', motion)
canvas.bind('<ButtonRelease-1>', release)
canvas.bind('<Button-3>', lambda e: menu.tk_popup(e.x_root, e.y_root))


def tick():
    frame = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    frame.alpha_composite(sprite, (20, 20 + round(4 * math.sin(time.time() * 2.2))))
    if not layer.show(frame):
        print('UpdateLayeredWindow 失败')
    root.after(33, tick)


tick()
root.mainloop()
layer.close()
