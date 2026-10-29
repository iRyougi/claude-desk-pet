# Claude 娘桌宠悬浮窗
# mod 把每个会话的状态写进 <运行目录>/sessions/<会话id>.json，这里读最新的那个来换表情和气泡。
# 她会坐在你当前窗口的顶边上陪你，窗口一换她就跳过去；提醒休息时走到窗口中间。
# 用法：pythonw pet.pyw <运行目录>
import ctypes
import ctypes.wintypes as wt
import glob
import json
import math
import os
import random
import socket
import subprocess
import sys
import time
import tkinter as tk
import traceback
import winsound
from dataclasses import replace

from PIL import Image, ImageOps, ImageTk

from breaks import ACK_LINES, BreakConfig, BreakEvent, BreakState, acknowledge, is_night, pick_line, step
from motion import (
    FIXED_SPRITES, Motion, Surface, choose_pose, choose_surface, spawn, tick, walk_bounce, walk_to,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS = os.path.join(os.path.dirname(HERE), 'sounds')
RUN_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser('~'), '.claude', 'desk-pet')
SESSIONS = os.path.join(RUN_DIR, 'sessions')
SETTINGS = os.path.join(RUN_DIR, 'settings.json')

# 只允许开一个桌宠：占住一个本地端口，占不到说明已经有一个在跑
try:
    _lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _lock.bind(('127.0.0.1', int(os.environ.get('DESK_PET_PORT', 47321))))  # 环境变量只给调试用
except OSError:
    sys.exit(0)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import winapi  # noqa: E402  要等 DPI 感知设好以后再导入，窗口坐标才是真实像素

# 用到的全部立绘（pet/sprites/<名字>.png）
SPRITE_FILES = sorted(set(FIXED_SPRITES.values()) | {
    'remind-1', 'remind-2', 'remind-3', 'jump', 'land', 'sit-watch', 'sit-swing-1', 'sit-swing-2',
    'walk-1', 'walk-2', 'walk-3', 'walk-4',
})
SIZES = {'小': 140, '中': 190, '大': 250}  # 角色高度（100% 缩放下的像素）
BASE_H = 400          # 立绘源图里一个站着的角色大约有多高；缩放按这个算，各姿势才能保持相对大小
IDLE_AFTER = 10 * 60  # 等你回复超过 10 分钟就开始发呆
SETTLE_S = 0.8        # 前台窗口稳定这么久，她才跳过去（Alt+Tab 路过的不算）
STRIDE_PX = 250       # 走路立绘 4 帧走完一个整步，脚向前迈多远（立绘像素；量出来的，别随便改）
STRIDES_PER_S = 1.2   # 每秒走几个整步；速度由它和步幅算出来，脚步和地面速度才对得上，不会打滑
KEY = '#ff00fe'       # 透明色：画布上这个颜色的像素会被挖空
EDGE = (58, 36, 26)   # 半透明边缘和这个深棕色混合，避免边缘发出洋红色的毛边
ORANGE = '#e8743b'

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

_logged = set()


def log_error():
    """把异常写进 pet-error.log；同一种只记一次，免得每帧都报错时把磁盘写满。"""
    text = traceback.format_exc()
    if text in _logged:
        return
    _logged.add(text)
    try:
        os.makedirs(RUN_DIR, exist_ok=True)
        with open(os.path.join(RUN_DIR, 'pet-error.log'), 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + text + '\n')
    except Exception:
        pass


def process_name(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ''
    finally:
        kernel32.CloseHandle(h)


def window_pid(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def claude_is_foreground():
    hwnd = user32.GetForegroundWindow()
    return bool(hwnd) and process_name(window_pid(hwnd)) == 'claude.exe'


def find_claude_window():
    found = []
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0 \
                and process_name(window_pid(hwnd)) == 'claude.exe':
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(PROC(cb), 0)
    return found[0] if found else None


def claude_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq claude.exe', '/NH'], capture_output=True,
                             text=True, timeout=10, creationflags=0x08000000).stdout
        return 'claude.exe' in out.lower()
    except Exception:
        return True


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [('cbSize', wt.UINT), ('dwTime', wt.DWORD)]


kernel32.GetTickCount.restype = wt.DWORD


def idle_seconds():
    """距离上一次键盘/鼠标操作过了多少秒；系统接口失败时当作"刚操作过"。"""
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def load_settings():
    try:
        with open(SETTINGS, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(s):
    try:
        os.makedirs(RUN_DIR, exist_ok=True)
        with open(SETTINGS, 'w', encoding='utf-8') as f:
            json.dump(s, f, ensure_ascii=False)
    except Exception:
        pass


def read_latest():
    """读所有会话里最新的状态；顺手清掉两天前的旧文件。"""
    best, now = None, time.time()
    for p in glob.glob(os.path.join(SESSIONS, '*.json')):
        try:
            mtime = os.path.getmtime(p)
            if now - mtime > 2 * 86400:
                os.remove(p)
                continue
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
            if best is None or mtime > best[0]:
                best = (mtime, data)
        except Exception:
            continue
    return best


def prepare(path, k, flip=False):
    """按 k 倍缩放立绘（可水平翻转），并把透明部分处理成透明色。"""
    im = Image.open(path).convert('RGBA')
    if flip:
        im = ImageOps.mirror(im)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    bg = Image.new('RGBA', im.size, EDGE + (255,))
    solid = Image.alpha_composite(bg, im)
    key = Image.new('RGBA', im.size, KEY)
    mask = im.getchannel('A').point(lambda a: 255 if a >= 110 else 0)
    key.paste(solid, (0, 0), mask)
    return key.convert('RGB')


class Pet:
    def __init__(self):
        self.settings = load_settings()
        self.root = tk.Tk()
        self.root.title('Claude 桌宠')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', KEY)
        self.root.configure(bg=KEY)
        self.scale = self.root.winfo_fpixels('1i') / 96

        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.font = ('Microsoft YaHei UI', 10)
        self.small = ('Microsoft YaHei UI', 8)

        self.state, self.text, self.project = 'waiting', '我来啦～', ''
        self.state_since = time.time()
        self.last_mtime = 0
        self.last_mtime_seen = 0
        self.hop_at = time.time()
        self.hidden = False
        self.drag = None
        self.moved = False
        self.press_at = (0, 0)
        self.last_alive = time.time()
        self.break_cfg = BreakConfig.from_settings(self.settings)
        self.break_state = BreakState()
        self.remind_text = ''
        self.speech = None  # (气泡文字, 截止时刻, 立绘状态或 None)：临时插话，盖过其他文字

        self.roam = self.settings.get('roam', True) is not False
        self.motion = None             # 走动模式下她的位置和动作
        self.target_hwnd = None        # 她现在坐着的窗口
        self.candidate = None          # (窗口, 开始当前台的时刻)：稳定了才换
        self.work_area = winapi.primary_work_area()
        self.win_pos = None
        self.last_frame = time.time()
        self.bubble_dy = 0
        self.pose_key = None
        self.anchor = 1.0

        self.build()
        self.place_window()
        self.make_menu()

        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Double-Button-1>', self.on_double)
        self.canvas.bind('<Button-3>', lambda e: self.menu.tk_popup(e.x_root, e.y_root))

        self.poll()
        self.watch_surface()
        self.animate()
        self.watch_focus()
        self.watch_claude()
        self.watch_break()

    # ---------- 布局 ----------
    def build(self):
        s = self.scale
        self.k = SIZES.get(self.settings.get('size', '中'), 190) * s / BASE_H
        self.cache = {}
        sizes = []
        for name in SPRITE_FILES:
            with Image.open(os.path.join(HERE, 'sprites', name + '.png')) as im:
                sizes.append(im.size)
        self.char_h = round(max(h for _, h in sizes) * self.k)
        self.char_w = round(max(w for w, _ in sizes) * self.k)
        self.bubble_h = round(52 * s)
        self.W = max(self.char_w, round(190 * s))
        self.line_y = self.bubble_h + round(8 * s) + self.char_h   # 站着时脚底、坐着时屁股落在窗口边上的那条线
        self.leg_room = round(0.32 * self.char_h)                  # 线下面留给垂下来的两条腿
        self.H = self.line_y + self.leg_room + round(6 * s)
        self.px_per_frame = STRIDE_PX / 4 * self.k      # 脚步每前进这么多像素，走路动画换一帧
        self.speed = STRIDES_PER_S * STRIDE_PX * self.k  # 像素/秒
        self.canvas.config(width=self.W, height=self.H)
        self.canvas.delete('all')
        self.pose_key = None
        self.bubble_dy = 0
        pose = self.current_pose()
        self.sprite = self.canvas.create_image(self.W // 2, self.line_y, anchor='s',
                                               image=self.sprite_image(pose.file, pose.flip))
        self.draw_bubble()

    def sprite_image(self, file, flip):
        key = (file, flip)
        if key not in self.cache:
            self.cache[key] = ImageTk.PhotoImage(prepare(os.path.join(HERE, 'sprites', file + '.png'), self.k, flip))
        return self.cache[key]

    def draw_bubble(self):
        c, s, dy = self.canvas, self.scale, self.bubble_dy
        c.delete('bubble')
        text = self.display_text()
        tid = c.create_text(self.W // 2, round(20 * s) + dy, text=text, font=self.font, fill='#3a2a1a', tags='bubble')
        x0, y0, x1, y1 = c.bbox(tid)
        pad = round(10 * s)
        x0, x1 = max(1, x0 - pad), min(self.W - 2, x1 + pad)
        y0, y1 = 2 + dy, round(38 * s) + dy
        r = round(12 * s)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               self.W // 2 + round(8 * s), y1, self.W // 2, y1 + round(10 * s), self.W // 2 - round(4 * s), y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        c.create_polygon(pts, smooth=True, fill='#fffaf3', outline=ORANGE, width=max(2, round(2 * s)), tags='bubble')
        c.tag_raise(tid)
        self.bubble_text = tid

    def display_text(self):
        if self.speech and time.time() < self.speech[1]:
            return self.speech[0]
        if self.break_state.level:
            return self.remind_text
        if self.claude_state() == 'idle':
            return '在发呆～ zZ'
        return self.text

    def claude_state(self):
        if self.state == 'waiting' and time.time() - self.state_since > IDLE_AFTER:
            return 'idle'
        return self.state

    def speech_state(self):
        if self.speech and time.time() < self.speech[1]:
            return self.speech[2]
        return None

    def current_pose(self):
        now = time.time()
        return choose_pose(self.motion if self.roam else None, now, self.claude_state(), now - self.state_since,
                           remind=self.break_state.level, speech=self.speech_state(), roam=self.roam,
                           px_per_frame=self.px_per_frame)

    def apply_pose(self):
        """按当前情况换立绘；坐着的时候气泡跟着往下挪，贴着头顶。返回 (姿势, 立绘高度)。"""
        pose = self.current_pose()
        key = (pose.file, pose.flip)
        img = self.sprite_image(*key)
        if key != self.pose_key:
            self.canvas.itemconfig(self.sprite, image=img)
            if self.pose_key and pose.anchor != self.anchor:
                self.hop_at = time.time()  # 站起来/坐下去：身体落点差了一截，蹦一下盖过那一下突兀的跳变
            self.pose_key, self.anchor = key, pose.anchor
        dy = round((1 - pose.anchor) * img.height())
        if dy != self.bubble_dy:
            self.bubble_dy = dy
            self.draw_bubble()
        return pose, img.height()

    def refresh(self):
        self.apply_pose()
        self.draw_bubble()

    def say(self, text, seconds, sprite=None):
        self.speech = (text, time.time() + seconds, sprite)
        self.hop_at = time.time()
        self.refresh()

    def place_window(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = self.settings.get('x', sw - self.W - round(40 * self.scale))
        y = self.settings.get('y', sh - self.H - round(70 * self.scale))
        x, y = min(max(0, x), sw - 40), min(max(0, y), sh - 40)
        self.root.geometry(f'{self.W}x{self.H}+{x}+{y}')

    def put_window(self, x, y):
        """把窗口摆到"脚底落在 (x, y)"的位置。"""
        pos = (round(x - self.W / 2), round(y - self.line_y))
        if pos != self.win_pos:
            self.win_pos = pos
            self.root.geometry(f'{self.W}x{self.H}+{pos[0]}+{pos[1]}')

    def make_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0, font=self.font)
        size_menu = tk.Menu(self.menu, tearoff=0, font=self.font)
        self.size_var = tk.StringVar(value=self.settings.get('size', '中'))
        for name in SIZES:
            size_menu.add_radiobutton(label=name, variable=self.size_var, value=name, command=self.resize)
        self.menu.add_cascade(label='大小', menu=size_menu)
        self.roam_var = tk.BooleanVar(value=self.roam)
        self.menu.add_checkbutton(label='跟着窗口走动', variable=self.roam_var, command=self.toggle_roam)
        self.hide_var = tk.BooleanVar(value=self.settings.get('hideOnFocus', False))
        self.menu.add_checkbutton(label='切到 Claude 时自动隐藏', variable=self.hide_var, command=self.toggle_hide)
        self.sound_var = tk.BooleanVar(value=self.settings.get('sound', True))
        self.menu.add_checkbutton(label='提示音', variable=self.sound_var, command=self.toggle_sound)
        self.menu.add_separator()
        self.break_var = tk.BooleanVar(value=self.break_cfg.enabled)
        self.menu.add_checkbutton(label='休息提醒', variable=self.break_var, command=self.toggle_break)
        work_menu = tk.Menu(self.menu, tearoff=0, font=self.font)
        self.work_var = tk.StringVar(value=f'{self.break_cfg.work_min:g}')
        for minutes in (30, 45, 50, 60, 90):
            work_menu.add_radiobutton(label=f'{minutes} 分钟', variable=self.work_var, value=str(minutes),
                                      command=self.set_work_minutes)
        self.menu.add_cascade(label='多久提醒一次', menu=work_menu)
        preview_menu = tk.Menu(self.menu, tearoff=0, font=self.font)
        for level, name in ((1, '温柔'), (2, '催促'), (3, '急了')):
            preview_menu.add_command(label=name, command=lambda lv=level: self.preview_break(lv))
        self.menu.add_cascade(label='试一下提醒', menu=preview_menu)
        self.menu.add_command(label='我去休息了', command=self.acknowledge_break)
        self.menu.add_separator()
        self.menu.add_command(label='退出桌宠', command=self.root.destroy)

    def resize(self):
        self.settings['size'] = self.size_var.get()
        save_settings(self.settings)
        bottom_x = self.root.winfo_x() + self.W // 2
        bottom_y = self.root.winfo_y() + self.line_y
        self.build()
        self.win_pos = None  # 走动模式下，下一帧会按她的位置重新摆
        self.root.geometry(f'{self.W}x{self.H}+{bottom_x - self.W // 2}+{bottom_y - self.line_y}')

    def toggle_roam(self):
        self.roam = self.roam_var.get()
        self.settings['roam'] = self.roam
        if not self.roam:  # 不走动了：就停在她现在的位置
            self.motion = None
            self.settings['x'], self.settings['y'] = self.root.winfo_x(), self.root.winfo_y()
        save_settings(self.settings)
        self.win_pos = None
        self.refresh()

    def toggle_hide(self):
        self.settings['hideOnFocus'] = self.hide_var.get()
        save_settings(self.settings)

    def toggle_sound(self):
        self.settings['sound'] = self.sound_var.get()
        save_settings(self.settings)

    def toggle_break(self):
        self.settings['breakEnabled'] = self.break_var.get()
        save_settings(self.settings)
        self.break_cfg = BreakConfig.from_settings(self.settings)
        self.break_state = BreakState()  # 开关一下就重新计时；正在提醒的话也就此作罢
        self.refresh()

    def set_work_minutes(self):
        self.settings['breakWork'] = float(self.work_var.get())
        save_settings(self.settings)
        self.break_cfg = BreakConfig.from_settings(self.settings)

    # ---------- 休息提醒 ----------
    def play(self, name):
        if not self.sound_var.get():
            return
        try:
            winsound.PlaySound(os.path.join(SOUNDS, name + '.wav'),
                               winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass

    def on_break_event(self, ev):
        self.remind_text = pick_line(ev.level, is_night(time.localtime().tm_hour), last=self.remind_text)
        self.speech = None
        self.hop_at = time.time()
        if self.roam and self.motion:
            self.motion = walk_to(self.motion, 0.5, time.time())  # 走到窗口中间，来找你
        self.refresh()
        self.play('error' if ev.level >= 3 else 'done')

    def acknowledge_break(self):
        self.break_state = acknowledge(self.break_state, time.time())
        self.say(random.choice(ACK_LINES), 3.5, 'idle')

    def preview_break(self, level):
        now = time.time()
        self.break_state = replace(self.break_state, level=level, reminded_at=now, last_event=now)
        self.on_break_event(BreakEvent(level))

    def watch_break(self):
        try:
            if self.break_cfg.enabled:  # 关掉的时候不检查；"试一下提醒"的预览会留到你点她为止
                had = self.break_state.level
                self.break_state, ev = step(self.break_state, time.time(), idle_seconds(), self.break_cfg)
                if ev:
                    self.on_break_event(ev)
                elif had and not self.break_state.level:
                    self.refresh()  # 你走开休息了，她就不催了
        except Exception:
            log_error()
        finally:
            self.root.after(2000, self.watch_break)

    # ---------- 鼠标 ----------
    def on_press(self, e):
        self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self.press_at, self.moved = (e.x_root, e.y_root), False

    def on_drag(self, e):
        if self.drag:
            if abs(e.x_root - self.press_at[0]) + abs(e.y_root - self.press_at[1]) > 4:
                self.moved = True
            self.root.geometry(f'+{e.x_root - self.drag[0]}+{e.y_root - self.drag[1]}')

    def on_release(self, e):
        self.drag = None
        if self.roam:
            if self.moved and self.motion:
                self.motion = self.dropped()  # 被你拎到别处了：松手后她跳回窗口上
            self.win_pos = None
        else:
            self.settings['x'], self.settings['y'] = self.root.winfo_x(), self.root.winfo_y()
            save_settings(self.settings)
        if not self.moved and self.break_state.level:
            self.acknowledge_break()  # 提醒的时候点她一下，就是"我去休息了"

    def dropped(self):
        x, y = self.root.winfo_x() + self.W / 2, self.root.winfo_y() + self.line_y
        nowhere = Surface(key=None, left=x, right=x, y=y, kind='dropped')  # 平面对不上，下一帧就会起跳
        return Motion(mode='perch', x=x, y=y, frac=self.motion.frac, surface=nowhere, face=self.motion.face,
                      next_wander=time.time() + 15)

    def on_double(self, e):
        # 双击：把 Claude 窗口叫到前台
        hwnd = find_claude_window()
        if hwnd:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)

    # ---------- 循环 ----------
    def poll(self):
        latest = read_latest()
        if latest and latest[0] != self.last_mtime:
            self.last_mtime_seen, self.last_mtime = self.last_mtime, latest[0]
            data = latest[1]
            state = data.get('state', 'waiting')
            if state not in FIXED_SPRITES:
                state = 'waiting'
            changed = state != self.state
            self.state, self.text = state, data.get('text', '')
            self.project = data.get('project', '')
            self.state_since = time.time()
            sound = data.get('sound')
            if sound in ('done', 'error') and self.last_mtime_seen:  # 刚启动时不重播旧提示音
                self.play(sound)
            if changed:
                self.hop_at = time.time()
            self.refresh()
        self.root.after(250, self.poll)

    def watch_surface(self):
        """决定她该坐哪个窗口：前台窗口稳定 SETTLE_S 秒才换；坐着的窗口没了就立刻换。"""
        try:
            now = time.time()
            self.work_area = winapi.primary_work_area()
            win = winapi.foreground_window(os.getpid())
            if win is None:
                self.candidate = None
            elif self.target_hwnd is None or win.hwnd == self.target_hwnd:
                self.candidate = None
                self.target_hwnd = win.hwnd
            elif self.candidate is None or self.candidate[0] != win.hwnd:
                self.candidate = (win.hwnd, now)
            elif now - self.candidate[1] >= SETTLE_S:
                self.target_hwnd, self.candidate = win.hwnd, None
            if self.target_hwnd and winapi.window_info(self.target_hwnd) is None:
                self.target_hwnd = win.hwnd if win else None  # 她坐的窗口关了/最小化了
        except Exception:
            log_error()
        finally:
            self.root.after(250, self.watch_surface)

    def surface_now(self):
        win = winapi.window_info(self.target_hwnd) if self.target_hwnd else None
        return choose_surface(win, self.work_area, need_above=self.line_y)

    def can_wander(self):
        return (self.drag is None and not self.break_state.level and not self.speech_state()
                and self.claude_state() in ('waiting', 'idle'))

    def move(self, now, dt):
        surface = self.surface_now()
        if self.motion is None:
            self.motion = spawn(surface, 0.8, now)  # 一开始就坐在窗口靠右的位置
        else:
            self.motion = tick(self.motion, surface, now, dt, speed=self.speed, scale=self.scale,
                               can_wander=self.can_wander())
        if self.drag is None and not self.hidden:
            self.put_window(self.motion.x, self.motion.y)

    def bob_for(self, file, t):
        if file in ('stone', 'jump', 'land'):
            return 0
        if file.startswith('walk'):
            # 走路：跟着脚步一起一伏（两腿交叉经过时最高），不是按时间晃
            return -2.5 * walk_bounce(self.motion, self.px_per_frame) if self.motion else 0
        if file == 'remind-3':
            return -7 * abs(math.sin(t * 4))        # 急了：原地一下一下跺脚
        if file == 'remind-2':
            return 2.5 * math.sin(t * 7)            # 催促：着急地晃
        if file == 'typing':
            return 1.5 * math.sin(t * 9)            # 敲键盘：快速小幅抖动
        if file == 'panic':
            return 2 * math.sin(t * 25)             # 慌张：发抖
        if file.startswith('sit'):
            return 1.2 * math.sin(t * 2.2)          # 坐着：轻轻晃
        return 3 * math.sin(t * 2.2)                # 平时：慢慢呼吸

    def frame(self):
        t = time.time()
        dt = min(0.1, max(0.0, t - self.last_frame))
        self.last_frame = t
        if self.speech and t >= self.speech[1]:
            self.speech = None
            self.draw_bubble()
        if self.roam:
            self.move(t, dt)
        pose, h = self.apply_pose()
        since = t - self.hop_at
        hop = -14 * math.sin(since / 0.28 * math.pi) if since < 0.28 else 0  # 换状态时小跳一下
        y = self.line_y + round((1 - pose.anchor) * h) + round((self.bob_for(pose.file, t) + hop) * self.scale)
        self.canvas.coords(self.sprite, self.W // 2, y)
        if (self.claude_state() == 'thinking' and self.text.endswith('中')
                and not self.break_state.level and not self.speech_state()):
            # “思考中” 后面的点点点一跳一跳
            self.canvas.itemconfig(self.bubble_text, text=self.text + '.' * (int(t * 2.5) % 3 + 1))

    def animate(self):
        try:
            self.frame()
        except Exception:
            log_error()
        finally:
            self.root.after(33, self.animate)

    def watch_focus(self):
        should_hide = (self.hide_var.get() and claude_is_foreground() and self.drag is None
                       and not self.break_state.level)  # 正在提醒休息的时候不躲
        if should_hide and not self.hidden:
            self.root.withdraw()
            self.hidden = True
        elif not should_hide and self.hidden:
            self.root.deiconify()
            self.root.attributes('-topmost', True)
            self.hidden = False
            self.win_pos = None
        self.root.after(300, self.watch_focus)

    def watch_claude(self):
        # Claude 关掉两分钟后，桌宠也自己退出
        if claude_running():
            self.last_alive = time.time()
        elif time.time() - self.last_alive > 120:
            self.root.destroy()
            return
        self.root.after(30000, self.watch_claude)


if __name__ == '__main__':
    try:
        Pet().root.mainloop()
    except Exception:
        os.makedirs(RUN_DIR, exist_ok=True)
        with open(os.path.join(RUN_DIR, 'pet-error.log'), 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
