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

from PIL import Image, ImageOps

from breaks import ACK_LINES, BreakConfig, BreakEvent, BreakState, acknowledge, is_night, pick_line, step
from motion import (
    FIXED_SPRITES, WALK_FRAMES, Posture, Swing, build_surfaces, choose_pose, choose_surface, hold, hop_to, release,
    settle, spawn, swing_step, tick, walk_to,
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

import dpi  # noqa: E402

dpi.enable()

import winapi  # noqa: E402  要等 DPI 感知设好以后再导入，窗口坐标才是真实像素
from bubble import layout  # noqa: E402
from layered import LayeredWindow  # noqa: E402
from render import BubbleStyle, bubble_image, compose, draw_marks  # noqa: E402
from blink import closed as eyes_closed, start as start_blink, step as step_blink  # noqa: E402
from effects import zz_marks  # noqa: E402

# 用到的全部立绘（pet/sprites/<名字>.png）
SPRITE_FILES = sorted(set(FIXED_SPRITES.values()) | {
    'remind-1', 'remind-2', 'remind-3', 'jump', 'land', 'sit-watch', 'sit-swing-1', 'sit-swing-2',
    'walk-1', 'walk-2', 'walk-3', 'walk-4', 'walk-5', 'walk-6',
    'sit-down-1', 'sit-down-2', 'held', 'held-swing', 'fall', 'sleep-1', 'sleep-2',
})
SIZES = {'小': 140, '中': 190, '大': 250}  # 角色高度（100% 缩放下的像素）
BASE_H = 400          # 立绘源图里一个站着的角色大约有多高；缩放按这个算，各姿势才能保持相对大小
IDLE_AFTER = 10 * 60  # 等你回复超过 10 分钟就开始发呆
SETTLE_S = 0.8        # 前台窗口稳定这么久，她才跳过去（Alt+Tab 路过的不算）
STRIDE_PX = 280       # 走路立绘 6 帧走完一个整步，脚向前迈多远（立绘像素；量出来的，别随便改）
STRIDES_PER_S = 1.2   # 每秒走几个整步；速度由它和步幅算出来，脚步和地面速度才对得上，不会打滑
BUBBLE_MAX_W = 260    # 气泡最宽多少像素（100% 缩放）；放不下就换行，最多两行
BUBBLE_AREA = 66      # 角色头顶留给气泡的高度（两行正文 + 尖角）
BUBBLE_CACHE = 64     # 最多缓存多少张气泡图（文件名一直在变，不能无限存）
SWING_V = 250         # 拖得比这快（像素/秒，100% 缩放），被拎着的她就往反方向歪
PATCHES = os.path.join(HERE, 'sprites', 'patches.json')   # 眨眼补丁的位置（tools/blink_patch.py 生成）

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


class Pet:
    def __init__(self):
        self.settings = load_settings()
        self.root = tk.Tk()
        self.root.title('Claude 桌宠')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.scale = dpi.scale_at(self.settings.get('x', 0), self.settings.get('y', 0))

        # 画布只用来接鼠标事件；看得见的画面每帧由 render 合成、交给分层窗口
        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0, bd=0)
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
        self.following = self.settings.get('follow', True) is not False  # 自动跟着当前窗口；被你拖走后暂停
        self.target_hwnd = None        # 当前窗口（前台窗口稳定之后才算），"跟着当前窗口"时她要去它那儿
        self.candidate = None          # (窗口, 开始当前台的时刻)：稳定了才换
        self.work_areas = winapi.monitor_work_areas()
        self.surfaces = []             # 此刻所有的地板（每 0.25 秒刷新）
        self.drag_samples = []         # 拖动时最近几次的 (时刻, x, y)，松手时用来算甩出去的速度
        self.win_pos = None
        self.last_frame = time.time()
        self.bubble_dy = 0
        self.pose_key = None
        self.anchor = 1.0
        self.patches = load_patches()
        self.posture = Posture()       # 坐着还是站着（播坐下/站起的过渡用）
        self.swing = Swing()           # 被拎着时身体往哪边甩
        self.blink = start_blink(time.time(), random)

        self.build()
        self.place_window()
        self.root.update_idletasks()
        self.layer = LayeredWindow(user32.GetParent(self.root.winfo_id()))
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
        self.bubble_cache = {}
        self.style = BubbleStyle.make(s)
        sizes = []
        for name in SPRITE_FILES:
            with Image.open(os.path.join(HERE, 'sprites', name + '.png')) as im:
                sizes.append(im.size)
        self.char_h = round(max(h for _, h in sizes) * self.k)
        self.char_w = round(max(w for w, _ in sizes) * self.k)
        self.bubble_h = round(BUBBLE_AREA * s)
        self.min_w = max(self.char_w, round(190 * s))
        self.W = self.min_w
        self.line_y = self.bubble_h + round(8 * s) + self.char_h   # 站着时脚底、坐着时屁股落在窗口边上的那条线
        self.leg_room = round(0.32 * self.char_h)                  # 线下面留给垂下来的两条腿
        self.H = self.line_y + self.leg_room + round(6 * s)
        self.px_per_frame = STRIDE_PX / WALK_FRAMES * self.k  # 脚步每前进这么多像素，走路动画换一帧
        self.speed = STRIDES_PER_S * STRIDE_PX * self.k  # 像素/秒
        self.canvas.config(width=self.W, height=self.H)
        self.pose_key = None
        self.bubble_dy = 0

    def sprite_image(self, file, flip, blink=False):
        key = (file, flip, blink)
        if key not in self.cache:
            patch = None
            if blink:
                x, y = self.patches[file]
                patch = (os.path.join(HERE, 'sprites', file + '.blink.png'), x, y)
            self.cache[key] = prepare(os.path.join(HERE, 'sprites', file + '.png'), self.k, flip, patch)
        return self.cache[key]

    def bubble_for(self, text):
        """这句话的气泡图；同一句话只画一次。"""
        if text not in self.bubble_cache:
            if len(self.bubble_cache) >= BUBBLE_CACHE:
                self.bubble_cache = {}
            # 10 是气泡左右内边距（见 render.bubble_image），扣掉它，气泡外宽才不会超过 BUBBLE_MAX_W
            max_w = round(BUBBLE_MAX_W * self.scale) - 2 * self.style.px(10)
            lay = layout(text, self.style.measure, max_w)
            self.bubble_cache[text] = bubble_image(lay, self.style)
        return self.bubble_cache[text]

    def fit_width(self, width):
        """气泡变宽变窄时窗口跟着变，脚底的中心点不动。"""
        if width == self.W:
            return
        x = self.root.winfo_x() + self.W // 2 - width // 2  # 和 rebuild() 一样按中心点算，来回变宽不会慢慢挪位置
        self.W = width
        self.canvas.config(width=width)
        self.root.geometry(f'{width}x{self.H}+{x}+{self.root.winfo_y()}')
        self.win_pos = None

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
                           px_per_frame=self.px_per_frame, swing=self.swing.direction)

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

    def refresh(self):
        self.apply_pose()  # 画面每帧都会重新合成，这里只需要更新姿势

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
        self.follow_var = tk.BooleanVar(value=self.following)
        self.menu.add_checkbutton(label='自动跟着当前窗口', variable=self.follow_var, command=self.toggle_follow)
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
        self.rebuild()

    def rebuild(self):
        """换大小或换缩放后重建立绘；脚底位置不变。"""
        bottom_x = self.root.winfo_x() + self.W // 2
        bottom_y = self.root.winfo_y() + self.line_y
        self.build()
        self.win_pos = None  # 走动模式下，下一帧会按她的位置重新摆
        self.root.geometry(f'{self.W}x{self.H}+{bottom_x - self.W // 2}+{bottom_y - self.line_y}')

    def check_dpi(self):
        """她落在缩放不同的另一块屏上了：按那块屏的缩放重建。拖着、在空中的时候不换，免得大小一路跳。"""
        if self.drag is not None:
            return
        if self.roam and self.motion:
            if self.motion.mode not in ('perch', 'walk'):
                return
            x, y = self.motion.x, self.motion.y - 1
        else:
            x, y = self.root.winfo_x() + self.W // 2, self.root.winfo_y() + self.line_y - 1
        scale = dpi.scale_at(round(x), round(y))
        if abs(scale - self.scale) > 0.01:
            self.scale = scale
            self.rebuild()

    def toggle_roam(self):
        self.roam = self.roam_var.get()
        self.settings['roam'] = self.roam
        if not self.roam:  # 不走动了：就停在她现在的位置
            self.motion = None
            self.settings['x'], self.settings['y'] = self.root.winfo_x(), self.root.winfo_y()
        save_settings(self.settings)
        self.win_pos = None
        self.refresh()

    def set_following(self, on, announce=False):
        self.following = on
        self.settings['follow'] = on
        save_settings(self.settings)
        self.follow_var.set(on)
        if announce:
            self.say('我就待在这儿啦～', 3.0)

    def toggle_follow(self):
        self.set_following(self.follow_var.get())

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
        self.drag_samples = []

    def on_drag(self, e):
        if not self.drag:
            return
        if abs(e.x_root - self.press_at[0]) + abs(e.y_root - self.press_at[1]) > 4:
            self.moved = True
        x, y = e.x_root - self.drag[0], e.y_root - self.drag[1]
        self.root.geometry(f'+{x}+{y}')
        if self.moved and self.roam and self.motion:
            feet = (x + self.W / 2, y + self.line_y)
            self.motion = hold(self.motion, *feet)  # 她被你拎起来了：位置完全跟着光标走
            self.drag_samples = (self.drag_samples + [(time.time(), *feet)])[-6:]

    def throw_velocity(self):
        """松手那一刻甩出去的速度（像素/秒）：看最近一小段拖动。"""
        samples = [s for s in self.drag_samples if time.time() - s[0] < 0.12]
        if len(samples) < 2 or samples[-1][0] - samples[0][0] < 0.02:
            return 0.0, 0.0
        dt = samples[-1][0] - samples[0][0]
        limit = 1600 * self.scale
        clamp = lambda v: max(-limit, min(limit, v))  # noqa: E731
        return clamp((samples[-1][1] - samples[0][1]) / dt), clamp((samples[-1][2] - samples[0][2]) / dt)

    def on_release(self, e):
        self.drag = None
        if self.roam:
            if self.moved and self.motion and self.motion.mode == 'held':
                self.motion = release(self.motion, *self.throw_velocity())  # 松手：自由落体，落在下面第一块地板上
                if self.following:
                    self.set_following(False, announce=True)  # 你把她放在哪儿，她就待在哪儿，不会自己跑回去
            self.win_pos = None
        else:
            self.settings['x'], self.settings['y'] = self.root.winfo_x(), self.root.winfo_y()
            save_settings(self.settings)
        if not self.moved and self.break_state.level:
            self.acknowledge_break()  # 提醒的时候点她一下，就是"我去休息了"

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
        """每 0.25 秒：刷新所有地板，并找出"当前窗口"——前台窗口稳定 SETTLE_S 秒才算，Alt+Tab 路过的不算。"""
        try:
            now = time.time()
            self.work_areas = winapi.monitor_work_areas()
            self.surfaces = build_surfaces(winapi.visible_windows(os.getpid()), self.work_areas)
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
                self.target_hwnd = win.hwnd if win else None  # 当前窗口关了/最小化了
            self.check_dpi()
        except Exception:
            log_error()
        finally:
            self.root.after(250, self.watch_surface)

    def follow_surface(self):
        """"跟着当前窗口"时她该去的地方：当前窗口的顶边；上方放不下就是屏幕底边（限在这个窗口的左右范围内）。"""
        win = winapi.window_info(self.target_hwnd) if self.target_hwnd else None
        return choose_surface(win, self.work_areas[0], need_above=self.line_y)

    def fresh_surfaces(self, follow):
        """地板列表。她脚下这块每帧都重新量一次，拖动窗口时她才不会慢半拍；窗口最大化、最小化了就从列表里消失，
        她就掉下去。"""
        surfaces = [s for s in self.surfaces if s.key != follow.key]
        support = self.motion.support if self.motion else None
        if isinstance(support, int) and support != follow.key:
            info = winapi.window_info(support)
            surfaces = [s for s in surfaces if s.key != support] + (build_surfaces([info], []) if info else [])
        return surfaces + [follow]

    def can_wander(self):
        return (self.drag is None and not self.break_state.level and not self.speech_state()
                and self.claude_state() == 'waiting')  # 发呆久了就睡着了，不溜达

    def update_motion(self, now, dt):
        follow = self.follow_surface()
        if self.motion is None:
            ground = choose_surface(None, self.work_areas[0], need_above=self.line_y)
            self.motion = spawn(follow if self.following else ground, 0.8, now)  # 一开始待在当前窗口靠右的位置
        else:
            m = self.motion
            if self.following and m.mode in ('perch', 'walk') and m.support != follow.key:
                m = hop_to(m, follow, now, self.scale)  # 你切到了别的窗口：她跳过去
            self.motion = tick(m, self.fresh_surfaces(follow), now, dt, speed=self.speed, scale=self.scale,
                               can_wander=self.can_wander())

    def bob_for(self, file, t):
        if file in ('stone', 'jump', 'land', 'fall', 'held', 'held-swing') or file.startswith(('walk', 'sit-down')):
            return 0  # 走路、过渡、悬空的立绘自带动作，不能再叠加起伏
        if file.startswith('sleep'):
            return 1.0 * math.sin(t * 1.6)          # 打瞌睡：慢慢地呼吸
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
        if self.roam:
            self.update_motion(t, dt)
        if self.hidden:
            return  # 藏起来的时候不用合成画面
        self.blink = step_blink(self.blink, t, random)
        held = self.roam and self.motion is not None and self.motion.mode == 'held'
        self.swing = swing_step(self.swing, self.throw_velocity()[0], t, SWING_V * self.scale) if held else Swing()
        pose, img = self.apply_pose()
        since = t - self.hop_at
        hop = -14 * math.sin(since / 0.28 * math.pi) if since < 0.28 else 0  # 换状态时小跳一下
        sprite_bottom = (self.line_y + round((1 - pose.anchor) * img.height)
                         + round((self.bob_for(pose.file, t) + hop) * self.scale))
        text = self.display_text()
        if (self.claude_state() == 'thinking' and self.text.endswith('中')
                and not self.break_state.level and not self.speech_state()):
            text = self.text + '.' * (int(t * 2.5) % 3 + 1)  # “思考中” 后面的点点点一跳一跳
        image = compose(img, sprite_bottom, self.bubble_for(text), self.bubble_h + self.bubble_dy,
                        self.min_w, self.H)
        if pose.file.startswith('sleep'):  # z Z 从头顶右上方冒出来（离开头发，免得压在黑色蝴蝶结上看不见）
            top = sprite_bottom - img.height
            draw_marks(image, zz_marks(t, self.scale), image.width // 2 + round(img.width * 0.36),
                       top + round(img.height * 0.02))
        self.fit_width(image.width)
        if self.roam and self.motion and self.drag is None:
            self.put_window(self.motion.x, self.motion.y)
        if not self.layer.show(image):
            raise OSError('UpdateLayeredWindow 失败')  # animate() 会记一次日志

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
        pet = Pet()
        pet.root.mainloop()
        pet.layer.close()
    except Exception:
        os.makedirs(RUN_DIR, exist_ok=True)
        with open(os.path.join(RUN_DIR, 'pet-error.log'), 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
