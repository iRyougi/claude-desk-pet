# 桌宠打磨：画面、系统集成、动画、互动 —— 设计

日期：2026-10-29 · 分支：`feat/pet-polish`

这一轮讨论定下了四块：A 画面底层、E 系统集成、B 动画、C 互动。实现顺序 A → E → B → C：A、E 不需要新素材，可以在出图的同时做。
不在这一轮的：D 爬墙/挂边/探头，F 打包成 exe，托盘图标（用 `/pet` 命令代替）。

---

## A 画面底层

### A1 渲染：tk + Win32 分层窗口

- 现状：`-transparentcolor` 抠色，alpha < 110 的像素直接丢掉，靠深棕色描边遮洋红毛边。没有半透明、没有抗锯齿。
- 改为：tk 窗口保留（接鼠标事件、弹右键菜单），窗口加 `WS_EX_LAYERED`，每帧用 PIL 把「立绘 + 叠加效果（眨眼补丁、z Z）+ 气泡」合成一张 RGBA 图，预乘 alpha 后经 `UpdateLayeredWindow` 交给系统显示。tk 自己的绘制不再使用。
- alpha 为 0 的像素鼠标点穿（分层窗口的系统行为），不需要另做命中测试。
- 删除 `KEY`、`EDGE` 和 `prepare()` 里的抠色逻辑；立绘缓存改为缩放后的 RGBA `Image`。
- 新文件 `pet/render.py`：
  - `compose(frame: FrameSpec) -> Image`：纯函数，输入立绘、偏移、叠加层、气泡内容，输出整帧图。
  - `push(hwnd, image, x, y)`：唯一碰 Win32 的地方，负责 `CreateDIBSection` + `UpdateLayeredWindow`。
- 窗口位置由 `UpdateLayeredWindow` 的目标坐标给，不再调 `root.geometry()` 移动（避免两套坐标打架）。
- 性能目标：30 帧/秒，窗口约 300×700 像素，CPU 占用不明显上升（实测记录在实现计划里）。

### A2 DPI：按显示器感知

- `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`，失败退回 `SetProcessDpiAwareness(2)`，再失败退回现状。
- 缩放系数取她脚下落点所在显示器的 DPI（`MonitorFromPoint` + `GetDpiForMonitor`），不再用 `winfo_fpixels`。
- 她落在另一块屏、并且 DPI 不同的时候：清空立绘缓存，按新的系数重新生成；`motion` 里的速度、重力等按新系数换算。被拎着跨屏时，松手落地后再切换，避免拖动中途大小跳变。

### A3 气泡

- 用 PIL 画：圆角矩形、橙色描边、底部小尖角，样式与现在一致；字体仍为 Microsoft YaHei UI。
- 最大宽度 260 px（100% 缩放下），自动换行，最多 2 行，第 2 行放不下末尾加「…」。
- 路径从中间省略、保留文件名：`在改 pet/…/motion.py`。规则：识别文字里含 `/` 或 `\` 的片段，先省略中间目录，仍放不下再按普通文字截断。
- 第二行（多会话信息，见 C4）用灰色小字，占掉换行的第 2 行；此时正文只有 1 行。
- 窗口宽度 = max(气泡宽, 角色宽)，气泡内容变化时窗口跟着变宽变窄，脚底中心点不动。
- 「思考中…」的点点动画保留。
- 新文件 `pet/bubble.py`：`layout(text, sub, font, max_w) -> BubbleLayout`，纯函数（测量文字宽度的函数作为参数传进去，测试时用假的等宽测量）。

### A 的测试

- `bubble.layout`：换行、2 行截断、路径中间省略、有第二行时正文只剩 1 行。
- `render.compose`：边缘确实有 0 < alpha < 255 的像素；透明区域 alpha 为 0；气泡和立绘的相对位置。
- 原有 `test_motion.py`、`test_breaks.py` 不改、照常通过。

---

## E 系统集成

### E1 全屏避让

- 判断全屏：前台窗口不是桌面（`Progman`/`WorkerW`）、不是她自己，窗口矩形覆盖整块显示器（`rcMonitor`，包括任务栏）。
- 只看她所在的那块屏；别的屏全屏不影响。
- 全屏时窗口隐藏，退出全屏后恢复。休息提醒在全屏期间不触发，等退出全屏后再出（计时照常累计）。
- 纯函数 `is_fullscreen(fg: WinInfo, monitor: Rect) -> bool`，放进 `winapi.py` 旁边的新文件 `pet/screen.py`（不碰 Win32 的判断逻辑），Win32 取数仍在 `winapi.py`。

### E2 层级：跟着她坐的窗口

- 坐在某个窗口顶边上（`motion.support` 是窗口句柄）：取消置顶，层级放在那个窗口的正上方（插在 `GetWindow(target, GW_HWNDPREV)` 之后），被盖住时她跟着一起被盖住。
- 以下情况置顶：站在屏幕底边、被拎着、下落/跳跃中、提醒休息、气泡在临时说话（`speech`）。
- 每 0.25 秒（随 `watch_surface`）校正一次；层级已经对了就不调用，减少闪烁。
- 纯函数 `choose_z(motion, remind, speaking) -> 'topmost' | ('above', hwnd)`。

### E3 `/pet` 命令

- 子命令全用英文，不认中文；参数打错或 `/pet help` 时列出用法。
- 注册时带 `argumentHint`，并设为 Claude 干活时也能立即执行（`immediate`）。

| 命令 | 作用 |
|---|---|
| `/pet` | 召唤；被隐藏了就显示 |
| `/pet hide` | 隐藏 |
| `/pet home` | 放回当前窗口，并重新打开自动跟随 |
| `/pet size small\|medium\|large` | 调大小 |
| `/pet follow on\|off` | 自动跟着当前窗口 |
| `/pet roam on\|off` | 跟着窗口走动 |
| `/pet sound on\|off` | 提示音 |
| `/pet chat on\|off` | 闲聊（C3） |
| `/pet break on\|off\|<分钟>` | 休息提醒开关 / 间隔（30、45、50、60、90） |
| `/pet break test` | 试一下提醒（温柔档） |
| `/pet rest` | 我去休息了 |
| `/pet quit` | 退出桌宠 |
| `/pet help` | 列出用法 |

- 传话：插件把 `{ id, cmd, args, ts }` 写进 `<运行目录>/command.json`（先写临时文件再改名）。桌宠在 `poll()` 里顺手读取，`id` 没处理过就执行，执行后在气泡里回一句；处理过的 `id` 记在内存里，重复读到不重复执行。
- 桌宠没在运行时：`/pet`（无参数）照旧启动它；其他子命令先启动再写命令，桌宠启动后读到 30 秒内的命令仍会执行，更早的忽略。
- 插件端：命令解析写成纯函数 `parsePetCommand(args) -> { cmd, value } | { error }`，用 `claude plugin test` 测。
- 桌宠端：`pet/commands.py` 的 `apply(cmd, value) -> list[Action]` 纯函数，`pet.pyw` 执行动作；与右键菜单共用同一套设置函数。
- 不做托盘图标；右键菜单保留。

### E4 设置防写坏

- `save_settings` 先写 `settings.json.tmp`，再 `os.replace` 替换。

### E 的测试

- `is_fullscreen`：盖满显示器 / 只盖工作区 / 桌面 / 另一块屏。
- `choose_z`：各模式下的结果。
- `parsePetCommand` 与 `commands.apply`：每个子命令、大小写、错误参数、缺参数。
- 设置写入：写到一半抛异常时原文件不变。

---

## B 动画

### B1 眨眼（局部补丁）

- 姿势：`sit-swing-1`、`sit-watch`、`typing`。
- 素材做法：把原图交给 GPT 的图片编辑，只改眼睛为闭眼，其他不动。
- 新工具 `tools/blink_patch.py`：
  1. 去绿幕（复用 `chroma.key_green`），按原图尺寸对齐（复用 `prep_sprites` 的缩放/对齐逻辑）。
  2. 与原图逐像素比较，找出眼睛附近变化最大的连通区域，外扩几个像素，裁成补丁。
  3. 补丁色调用 `tone.adjust` 对齐原图。
  4. 输出 `pet/sprites/<名字>.blink.png` 和偏移量（写进 `pet/sprites/patches.json`）。
- 运行时：原图不变，眨眼时把补丁贴到偏移位置。
- 节奏：每 2.5～6 秒随机一次，闭眼约 0.12 秒，约 20% 的概率连眨两下。走路、跳、下落、石化、睡觉时不眨。
- 纯函数 `blink_at(now, seed_state) -> bool`，调度状态放进不可变的 dataclass。

### B2 坐下 / 站起过渡

- 2 张过渡帧 `sit-down-1`、`sit-down-2`：弯膝下蹲 → 屁股快碰到窗口边 → 坐稳。整段约 0.25 秒（每帧约 0.12 秒）。
- 站起 = 倒着播。
- 每张过渡帧在 `motion.ANCHOR` 里登记"屁股高度"，过渡期间 anchor 逐帧变化，身体平滑下沉。
- 触发：站立类姿势（`knock`、事件姿势、提醒、`land`、走完路）↔ 坐姿类（`sit-*`、`typing`、`sleep-*`）切换时。
- 坐下/站起不再触发"蹦一下"；换状态时的小跳保留。
- `Motion` 新增 `posture: 'stand' | 'sit'` 和 `posture_since`，`choose_pose` 根据目标姿势和 `posture_since` 选过渡帧。

### B3 被拎着 / 下落

- `held`：静止悬空，手脚下垂。
- `held-swing`：身体往一侧歪；往另一侧歪时翻转。拖动的水平速度超过阈值时，按拖动方向的反方向歪；速度回落后 0.3 秒回到 `held`。
- `fall`：双手张开、头发和裙摆往上飘。用于下落（`mode == 'fall'`）。
- `hop`（跳去别的窗口）继续用 `jump`。
- `choose_pose` 新增参数 `drag_vx`（像素/秒），由 `pet.pyw` 用已有的 `drag_samples` 算出来传入。

### B4 睡觉

- 触发：`claude_state() == 'idle'`（等你回复超过 10 分钟）且她在坐着。
- 2 帧 `sleep-1`、`sleep-2`：坐着打瞌睡，头一点一点，约 1.2 秒交替一次。anchor 与 `sit-swing-1` 相同（0.70）。
- z Z 由 `render.py` 画：从头顶右侧冒出，往上飘、逐渐变淡，每 1.5 秒一个。
- 醒来：Claude 状态变化、休息提醒到点、被戳、被拎起。醒来时小跳一下。
- 睡着时不眨眼、不闲聊、不晃腿。

### B 的测试

- `choose_pose`：坐下第 0.05 / 0.15 / 0.3 秒用哪一帧；站起倒序；拖动速度对应的姿势和翻转；睡觉帧交替；睡着时不出眨眼。
- `blink_patch`：用合成的测试图（原图 + 改了一小块的图）验证补丁位置、大小和色调对齐。

---

## C 互动

### C1 摸头

- 鼠标不按键，在立绘上部约 1/4（头部）来回划，1.5 秒内水平方向反转 3 次即为摸头。
- 反应：`shy` 立绘约 2 秒，说一句（台词见 `lines.json` 的 `pet`）。
- 冷却 5 秒，冷却期间不重复触发。

### C2 戳她

- 单击：等 0.3 秒，没有第二下才算戳（双击仍是叫出 Claude 窗口）。
- 反应：`poked` 立绘约 1.5 秒，说一句（`lines.json` 的 `poke`）。
- 5 秒内戳 4 下及以上：生气，用 `remind-3` 约 3 秒，说一句（`angry`），之后 5 秒内再戳只说"哼"不换姿势。
- 优先级：提醒休息时单击 = 我去休息了；睡着时戳 = 醒来 + 被戳反应。
- Claude 在干活时也能互动；表情维持后回到干活的姿势。
- 新文件 `pet/interact.py`：`feed(state, event) -> (state, reaction | None)`，事件是 `('move', t, x, y)`、`('press', t)`、`('release', t, moved)`、`('double', t)`，纯函数、不可变状态。

### C3 闲聊

- 每 15～30 分钟随机一句，只在 Claude 等你回复（`waiting`，未进入 `idle`）、没有临时说话、未提醒休息、未全屏时开口；每句约 5 秒；同一句不连续出现。
- 时间问候：当天第一次出现时按时段问候；12:00、18:00 各提醒一次吃饭（当天已提醒过就不再提）。深夜沿用 `breaks.is_night` 的逻辑。
- 跟工作有关：用会话文件里的项目名和本日累计时长（插件写入状态文件时多带一个 `todayMs` 字段），例如「今天陪你写了 2 小时 claude-desk-pet 了」。
- 台词放在 `pet/lines.json`：`greet.morning/afternoon/evening`、`meal`、`chat`、`work`（带 `{project}`、`{hours}` 占位符）、`pet`、`poke`、`angry`。文件读不出来时用内置的几句兜底，并写一次 `pet-error.log`。
- 开关：右键菜单「闲聊」、`/pet chat on|off`，设置项 `chat`（默认开）。
- 新文件 `pet/chatter.py`：`next_line(state, now, ctx) -> (state, line | None)`，纯函数。

### C4 多会话

- 进行中的会话：会话文件最近 30 分钟内有更新。
- 姿势和气泡第一行：跟着最新更新的会话（与现在一致）。
- 第二行：进行中的会话 ≥ 2 个时出现，灰色小字：`<当前项目名> · <其他会话摘要>`。摘要优先级：出错 > 在等你 > 在忙；例如 `claude-desk-pet · sts2-ai 在等你`、`claude-desk-pet · 另有 2 个在忙`。
- 新文件 `pet/sessions.py`：`summarize(sessions, now) -> Summary(latest, sub_line)`，纯函数；`read_latest()` 改为读出全部会话再交给它。

### C 的测试

- `interact.feed`：摸头手势（反转次数、时间窗、只在头部）、单击/双击区分、连戳计数和生气冷却、提醒和睡觉时的优先级。
- `chatter.next_line`：频率区间、静默条件、饭点只提醒一次、不连续重复、占位符替换、`lines.json` 缺失时兜底。
- `sessions.summarize`：单会话没有第二行、多会话摘要优先级、30 分钟过期。

---

## 素材清单（12 张）

所有整图都按现有流程出：**纯绿幕背景（#00FF00）**，交给 `tools/prep_sprites.py` 去绿幕、对齐头部、调色、描边，再放进 `pet/sprites/`。实现时在 `SHEETS` 里给新素材加条目。

通用要求（每张提示词都带上）：

- 角色参考：附上 `pet/sprites/smile.png`（站姿）或 `sit-swing-1.png`（坐姿）作为同一角色的参考图。
- 画风：Q 版、与参考图同样的线条粗细和上色方式、同样的发色和服装，不加阴影投影、不加背景物件。
- 构图：单个角色，全身入画，四周留白，背景为纯 #00FF00 绿色、没有渐变和地面阴影。
- 坐姿类：角色坐在一条看不见的水平边上，屁股所在高度与参考图 `sit-swing-1.png` 一致（约在角色高度 70% 处），双腿垂在边下面。

| # | 文件名 | 类型 | 内容 | 参考图 |
|---|---|---|---|---|
| 1 | `sit-swing-1.blink` | 编辑原图 | 只把眼睛改成自然闭眼，其他像素不动 | `sit-swing-1.png`（叠绿底） |
| 2 | `sit-watch.blink` | 编辑原图 | 同上 | `sit-watch.png`（叠绿底） |
| 3 | `typing.blink` | 编辑原图 | 同上 | `typing.png`（叠绿底） |
| 4 | `sit-down-1` | 新整图 | 从站立开始下蹲，膝盖弯曲，屁股约在站立时腰的高度 | `smile.png` + `sit-swing-1.png` |
| 5 | `sit-down-2` | 新整图 | 屁股快碰到边，双腿开始往前伸 | 同上 |
| 6 | `held` | 新整图 | 被人从后领提起，身体自然下垂，手脚垂着，表情无奈 | `smile.png` |
| 7 | `held-swing` | 新整图 | 同上，但身体向画面左侧倾斜约 20°，头发和裙摆向右飘 | `held` 成品 |
| 8 | `fall` | 新整图 | 正在下落，双手向上张开，头发和裙摆向上飘，表情惊讶 | `smile.png` |
| 9 | `sleep-1` | 新整图 | 坐着打瞌睡，头微微低下，闭眼，嘴角放松 | `sit-swing-1.png` |
| 10 | `sleep-2` | 新整图 | 同上，头低得更多一点（点头的下一刻），身体位置不变 | `sleep-1` 成品 |
| 11 | `shy` | 新整图 | 站着、被摸头时害羞，脸红，眯眼笑，双手放在胸前 | `smile.png` |
| 12 | `poked` | 新整图 | 站着、被戳脸，一边脸颊被戳得微鼓，眼睛一大一小，有点委屈 | `smile.png` |

编辑原图（1～3）的做法：实现阶段先提供一个小命令，把原图叠到绿底上导出给你，例如 `python tools/blink_patch.py export sit-swing-1`；你把导出的图交给 GPT 编辑后放回来，再跑 `python tools/blink_patch.py build sit-swing-1 <编辑后的图>`。

---

## 文件变化一览

| 文件 | 变化 |
|---|---|
| `pet/render.py` | 新：整帧合成 + `UpdateLayeredWindow` |
| `pet/bubble.py` | 新：气泡排版 |
| `pet/screen.py` | 新：全屏判断、层级选择 |
| `pet/commands.py` | 新：`/pet` 命令执行 |
| `pet/interact.py` | 新：摸头、戳 |
| `pet/chatter.py` | 新：闲聊调度 |
| `pet/sessions.py` | 新：多会话汇总 |
| `pet/lines.json` | 新：台词 |
| `pet/motion.py` | 改：`choose_pose` 增加过渡、被拎着、下落、睡觉；`Motion` 增加姿态字段 |
| `pet/winapi.py` | 改：DPI、显示器信息、层级调整、全屏取数 |
| `pet/pet.pyw` | 改：绘制换成 `render`，事件交给 `interact`，命令读取，设置原子写入；预计瘦身到 500 行以内 |
| `hooks/register.ts` | 改：`/pet` 子命令、`argumentHint`、`immediate`、`command.json`、状态文件加 `todayMs` |
| `tools/blink_patch.py` | 新：眨眼补丁的导出和生成 |
| `tools/prep_sprites.py` | 改：`SHEETS` 加新素材 |
| `README.md` | 改：新功能、`/pet` 用法、换素材的说明 |
| `tests/` | 新增对应测试文件 |

## 风险

- `UpdateLayeredWindow` 与 tk 的窗口过程共存：tk 可能在重绘时覆盖分层内容。缓解：A 的第一步就是最小验证（一张静态图 + 拖动 + 右键菜单），不行再评估其他做法。
- 层级跟随可能和某些窗口（UWP、管理员权限窗口）不兼容：`SetWindowPos` 失败时退回置顶，并只记一次日志。
- GPT 出图的一致性：坐姿的屁股高度、过渡帧的比例可能不准。缓解：`ANCHOR` 按成品实测登记；比例由 `prep_sprites` 按头部大小统一。
