# Work Manager — 追踪功能设计报告

> 本文档详细描述当前应用程序使用追踪（Usage Tracking）功能的完整设计，包括底层 Windows API 调用、状态机算法、数据持久化策略、聚合统计逻辑，以及大量带时间线的具体例子。目标是让读者（包括未来的开发者或 AI）能够精确理解每一行代码背后的设计意图和实际行为。

---

## 1. 概述与目标

### 1.1 追踪系统解决什么问题

Work Manager 的核心价值是**自动记录用户在电脑上花费的时间**，无需手动开始/停止计时器。它要做到：

1. **自动检测**当前前台应用（你在用什么软件）
2. **自动判断**用户是否离开（idle / 锁屏）
3. **自动分段**——当应用切换或用户离开时，结束上一段、开始新的一段
4. **自动持久化**——数据实时写入本地 SQLite，程序崩溃不丢数据
5. **自动统计**——按日/周/月/年聚合，去重计算真实活跃时长

### 1.2 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        UI Layer                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ Timeline    │  │ Dashboard    │  │ Sidebar (实时状态)   │ │
│  │ 时间线可视化 │  │ 统计图表      │  │ 当前应用 / 今日活跃  │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ callbacks
┌─────────────────────────────────────────────────────────────┐
│                    Tracker Layer                             │
│              UsageTracker (后台线程)                         │
│         ┌──────────────────────────────────────┐            │
│         │  轮询循环 (每 2 秒)                   │            │
│         │  ├─ 获取用户状态 (monitor.py)         │            │
│         │  ├─ 检测状态变化                      │            │
│         │  ├─ 结束旧 Segment / 开始新 Segment   │            │
│         │  └─ 写入数据库                       │            │
│         └──────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Monitor Layer                             │
│  ┌──────────────────┐  ┌──────────────────────────────┐    │
│  │ Windows API      │  │ Windows API                  │    │
│  │ GetForegroundWin │  │ GetLastInputInfo             │    │
│  │ → 前台窗口 PID   │  │ → 键盘鼠标空闲毫秒数         │    │
│  └──────────────────┘  └──────────────────────────────┘    │
│  ┌──────────────────┐                                      │
│  │ psutil           │  → 将 PID 解析为进程名              │    │
│  │ Process(pid).name│                                      │    │
│  └──────────────────┘                                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer                             │
│              SQLite (data.db)                                │
│  ┌────────────────────────────────────────┐                 │
│  │ activity_segments                     │                 │
│  │  ├─ 原始追踪数据（秒级精度）            │                 │
│  │  ├─ 自动/手动 混合存储                 │                 │
│  │  └─ idle / active 标记                │                 │
│  ├───────────────────────────────────────┤                 │
│  │ tasks                                 │                 │
│  │  └─ 用户定义的工作分类（开发/会议等）   │                 │
│  ├───────────────────────────────────────┤                 │
│  │ quadrants / quadrant_tasks            │                 │
│  │  └─ 四象限时间管理                    │                 │
│  └────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 底层监控层：monitor.py

monitor.py 是追踪系统的"传感器"，负责从 Windows 操作系统采集原始输入。它**不**保存任何状态，也不启动线程——每次被调用时实时查询系统状态并返回一个字典。

### 2.1 空闲检测：键盘/鼠标多久没动了？

```python
def get_idle_time_ms() -> int:
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        tick_count = ctypes.windll.kernel32.GetTickCount()
        idle_ms = tick_count - lii.dwTime
        return max(0, int(idle_ms))
    return 0
```

**API 原理：**
- `GetLastInputInfo` 是 Windows user32 库提供的 API，返回系统最后一次接收到键盘或鼠标输入时的**系统启动 Tick 计数**（毫秒）
- `GetTickCount` 返回当前系统启动后的毫秒数
- 两者相减 = 用户空闲了多久

**精度限制：**
- `GetTickCount` 的精度约为 **10~16 毫秒**（Windows 定时器粒度）
- 如果用户一直在操作，`idle_ms` 会接近 0
- 如果用户离开 5 分钟，`idle_ms` ≈ 300,000

**API 失败回退：**
- 如果 `GetLastInputInfo` 调用失败（极少见），返回 0，即假设用户**一直在活跃**——这是一个"宁错勿漏"的设计，避免错误标记为 idle 导致丢数据

### 2.2 活跃判断

```python
def is_user_active(idle_threshold_ms: int = 180_000) -> bool:
    return get_idle_time_ms() < idle_threshold_ms
```

- 默认阈值：**180 秒 = 3 分钟**
- 意味着：只要 3 分钟内有过键盘或鼠标操作，就认为是"活跃"
- 这个阈值是可配置的（`UsageTracker` 构造函数传入）

**实际例子：**

| 时间 | 用户行为 | idle_ms | is_active |
|------|---------|---------|-----------|
| 09:00:00 | 正在打字 | 200 ms | True |
| 09:01:00 | 阅读文档，偶尔滚动 | 5,000 ms | True |
| 09:03:30 | 去倒水了 | 210,000 ms | **False** (超过 180s) |
| 09:05:00 | 回来继续工作 | 0 ms | True |

### 2.3 锁屏检测

```python
def is_screen_locked() -> bool:
    hwnd = win32gui.GetForegroundWindow()
    if hwnd == 0:
        return True
    title = win32gui.GetWindowText(hwnd)
    lock_titles = ['Windows Default Lock Screen', '锁屏界面', '登录']
    if any(t in title for t in lock_titles):
        return True
    return False
```

**设计说明：**
- Windows 没有公开的直接"是否锁屏"API
- 采用**启发式检测**：如果前台窗口标题包含"锁屏"或"登录"等关键词，认为已锁屏
- `hwnd == 0` 也是锁屏的一个信号（因为锁屏时没有正常的前台窗口）
- 如果检测失败（异常），返回 `False`（假设未锁屏）——同样"宁错勿漏"

**实际例子：**

| 场景 | GetForegroundWindow | WindowText | 检测结果 |
|------|---------------------|-----------|---------|
| 正常使用 Chrome | hwnd=123456 | "GitHub - Chrome" | False |
| Win+L 锁屏 | hwnd=0 | "" | True |
| 锁屏界面 | hwnd=654321 | "锁屏界面" | True |
| 登录界面 | hwnd=111111 | "登录" | True |

### 2.4 前台应用检测

```python
def get_foreground_window_info() -> dict:
    hwnd = win32gui.GetForegroundWindow()
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    window_title = win32gui.GetWindowText(hwnd)
    
    if pid == _OWN_PID:  # 检测到的是本程序自己
        return {'process_name': '工作管理系统', ...}
    
    process = psutil.Process(pid)
    process_name = process.name()
    
    return {'process_name': process_name, 'window_title': window_title, ...}
```

**三个关键 API：**
1. `GetForegroundWindow()` —— 获取当前拥有焦点的窗口句柄
2. `GetWindowThreadProcessId(hwnd)` —— 通过窗口句柄反查进程 PID
3. `psutil.Process(pid).name()` —— 通过 PID 获取进程可执行文件名

**排除自身：**
- `_OWN_PID = os.getpid()` 在模块导入时记录
- 如果检测到前台应用就是自己（Work Manager），显示为"工作管理系统"，避免循环自引用

**错误处理：**
- `psutil.NoSuchProcess` —— 进程在检测瞬间已退出
- `psutil.AccessDenied` —— 权限不足（如系统进程）
- 两种情况都回退到 `'Unknown'`

**实际例子：**

| 时间 | 前台窗口 | PID | psutil 结果 | process_name |
|------|---------|-----|------------|--------------|
| 09:00 | VS Code 编辑代码 | 4521 | code.exe | code.exe |
| 09:15 | Chrome 查文档 | 8812 | chrome.exe | chrome.exe |
| 09:30 | 本程序窗口 | 1234 | python.exe | 工作管理系统 |
| 09:45 | 系统设置 | 999 | 权限不足 | Unknown |

### 2.5 综合状态：get_user_state()

这是 monitor.py 对外暴露的唯一主 API，tracker 每轮询调用一次：

```python
def get_user_state(idle_threshold_ms: int = 180_000) -> dict:
    app_info = get_foreground_window_info()
    idle_ms = get_idle_time_ms()
    locked = is_screen_locked()
    
    if locked:
        is_active = False  # 锁屏强制空闲
    else:
        is_active = idle_ms < idle_threshold_ms
    
    return {
        'app_name': app_info['process_name'],
        'window_title': app_info['window_title'],
        'idle_ms': idle_ms,
        'is_active': is_active,
        'is_locked': locked,
        'timestamp': time.time(),
    }
```

**优先级设计：**
1. 先检测锁屏 —— 锁屏是最高优先级的"强制空闲"
2. 再检测 idle —— 3 分钟无输入标记为空闲
3. 两者都通过才算活跃

**返回字典的完整字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `app_name` | str | 前台进程名（如 "code.exe"） |
| `window_title` | str | 窗口标题（如 "tracker.py - Work Manager"） |
| `idle_ms` | int | 空闲毫秒数 |
| `is_active` | bool | 是否活跃（综合锁屏+idle） |
| `is_locked` | bool | 是否锁屏 |
| `timestamp` | float | Unix 时间戳（秒） |


---

## 3. 追踪引擎层：tracker.py

tracker.py 是追踪系统的"大脑"，它在一个独立的后台线程中每 2 秒轮询一次 monitor，决定何时创建/结束/更新时间段（Segment）。

### 3.1 核心数据模型：Segment

```python
class Segment:
    def __init__(self, date_str, start_time, app_name,
                 is_idle=False, task_id=None, source='auto', description=''):
        self.date_str = date_str      # 日期，如 "2026-05-14"
        self.start_time = start_time  # 开始时间，如 "09:30:15"
        self.end_time = start_time    # 动态更新，初始=start_time
        self.app_name = app_name      # 应用名，如 "code.exe"
        self.is_idle = is_idle        # 是否空闲
        self.task_id = task_id        # 关联的任务分类 ID
        self.source = source          # 'auto' 自动追踪 | 'manual' 手动添加
        self.description = description
        self.db_id = None             # 写入 DB 后填充
```

**关键设计：start_time = end_time 的初始化**
- Segment 创建时，`end_time` 被设为和 `start_time` 相同
- 随着时间推移，`end_time` 被不断更新（"滑动窗口"）
- 当状态变化时，`end_time` 定格为变化时刻，Segment 被写入数据库

### 3.2 UsageTracker 状态机

Tracker 内部维护的核心状态：

```python
self._current_segment  # 当前正在进行的 Segment（内存中）
self._last_state       # 上一轮询的状态字典（用于比较变化）
self._last_flush_time  # 上次写入 DB 的时间戳
```

**状态转换图：**

```
                    ┌──────────────────────────────┐
                    │   _current_segment = None    │
                    │      (未开始或刚关闭)          │
                    └──────────────┬───────────────┘
                                   │ 第一次轮询
                                   ▼
                    ┌──────────────────────────────┐
                    │   创建新 Segment             │
                    │   start_time = now           │
                    │   end_time = now             │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
        ┌──────────┐       ┌──────────┐         ┌──────────┐
        │ 应用切换  │       │ 用户离开  │         │ 跨天了   │
        │ 或       │       │ (idle)   │         │          │
        │ active↔idle│      │          │         │          │
        └────┬─────┘       └────┬─────┘         └────┬─────┘
             │                  │                    │
             ▼                  ▼                    ▼
        ┌─────────────────────────────────────────────────┐
        │ 1. 设置 end_time = 当前时间                      │
        │ 2. _flush_segment() 写入数据库                   │
        │ 3. 创建新 Segment，start_time = 当前时间          │
        └─────────────────────────────────────────────────┘
              │
              ▼
        ┌──────────────────────────────┐
        │   无变化（每 2 秒）           │
        │   只更新 end_time = now      │
        │   每 60 秒强制刷盘           │
        └──────────────────────────────┘
```

### 3.3 核心轮询循环详解

```python
def _loop(self):
    while self._running:
        time.sleep(self.poll_interval)  # 睡 2 秒
        if not self._running:
            break
        
        state = get_user_state(self.idle_threshold_ms)
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        
        with self._lock:
            # --- 分支 1: 跨天处理 ---
            if self._current_segment and self._current_segment.date_str != date_str:
                self._close_current_segment()
                self._start_new_segment(state, date_str, time_str)
                self._notify_state_change(state)
                self._last_state = state
                continue
            
            # --- 分支 2: 首次启动 ---
            if self._current_segment is None:
                self._start_new_segment(state, date_str, time_str)
                self._notify_state_change(state)
                self._last_state = state
                continue
            
            # --- 分支 3: 检测状态变化 ---
            last = self._last_state
            app_changed = state['app_name'] != last['app_name']
            active_changed = state['is_active'] != last['is_active']
            changed = app_changed or active_changed
            
            if changed:
                # 结束旧段，开始新段
                self._current_segment.end_time = time_str
                self._flush_segment(self._current_segment)
                self._start_new_segment(state, date_str, time_str)
                self._notify_state_change(state)
            else:
                # 无变化，滑动 end_time
                self._current_segment.end_time = time_str
                # 每 60 秒强制刷盘
                if time.time() - self._last_flush_time > 60:
                    self._flush_segment(self._current_segment)
                    self._last_flush_time = time.time()
            
            self._last_state = state
```

### 3.4 用大量例子说明轮询行为

**例子 1：正常办公场景（应用切换）**

假设 09:00:00 启动追踪，用户在 VS Code 中工作：

| 轮询 # | 时间 | 前台应用 | is_active | 变化？ | Segment 行为 |
|--------|------|---------|-----------|--------|-------------|
| 1 | 09:00:02 | VS Code | True | 首次启动 | 创建 Seg#1: [09:00:02→09:00:02] code.exe |
| 2 | 09:00:04 | VS Code | True | 无变化 | 更新 Seg#1: end=09:00:04 |
| 3 | 09:00:06 | VS Code | True | 无变化 | 更新 Seg#1: end=09:00:06 |
| ... | ... | ... | ... | ... | ... |
| 150 | 09:05:00 | VS Code | True | 无变化 | 更新 Seg#1: end=09:05:00，同时 60s 刷盘 |
| 151 | 09:05:02 | **Chrome** | True | **app_changed!** | 1. 关闭 Seg#1: end=09:05:02 → 写入 DB<br>2. 创建 Seg#2: [09:05:02→09:05:02] chrome.exe |
| 152 | 09:05:04 | Chrome | True | 无变化 | 更新 Seg#2: end=09:05:04 |

**最终数据库中的两条记录：**
```
Seg#1: date=2026-05-14, start=09:00:02, end=09:05:02, app=code.exe, is_idle=0
Seg#2: date=2026-05-14, start=09:05:02, end=09:05:04, app=chrome.exe, is_idle=0
```

**例子 2：用户离开（进入 Idle）**

| 轮询 # | 时间 | 前台应用 | is_active | 变化？ | Segment 行为 |
|--------|------|---------|-----------|--------|-------------|
| 1 | 10:00:00 | VS Code | True | 首次启动 | 创建 Seg#1: [10:00:00→10:00:00] code.exe |
| ... | ... | VS Code | True | 无变化 | 持续滑动 end_time |
| 90 | 10:03:00 | VS Code | True | 无变化 | 60s 刷盘 |
| 91 | 10:03:02 | VS Code | **False** | **active_changed!** | 1. 关闭 Seg#1: end=10:03:02 → 写入 DB<br>2. 创建 Seg#2: [10:03:02→10:03:02] **Idle**, is_idle=1 |
| 92 | 10:03:04 | VS Code | False | 无变化 | 更新 Seg#2: end=10:03:04 |
| ... | ... | VS Code | False | 无变化 | 持续滑动（用户在 idle） |
| 120 | 10:04:00 | VS Code | False | 无变化 | 60s 刷盘 |
| 121 | 10:04:02 | VS Code | **True** | **active_changed!** | 1. 关闭 Seg#2: end=10:04:02 → 写入 DB<br>2. 创建 Seg#3: [10:04:02→10:04:02] code.exe |

**注意：** 即使进入了 idle，前台应用仍然是 VS Code（因为 `get_user_state` 依然会返回当前前台窗口），但 Segment 的 `app_name` 被强制设为 `'Idle'`（见 `_start_new_segment`）

**例子 3：锁屏场景**

| 轮询 # | 时间 | is_locked | is_active | 变化？ | Segment 行为 |
|--------|------|-----------|-----------|--------|-------------|
| 1 | 11:00:00 | False | True | 首次启动 | 创建 Seg#1: [11:00:00→11:00:00] code.exe |
| ... | ... | False | True | 无变化 | 持续滑动 |
| 50 | 11:01:40 | **True** | **False** | **active_changed!** | 1. 关闭 Seg#1: end=11:01:40<br>2. 创建 Seg#2: [11:01:40→11:01:40] **Idle** |

锁屏会立即触发 active_changed（从 True → False），因为 `is_user_active` 在 locked 时强制返回 False。

**例子 4：跨天（Day Rollover）**

| 轮询 # | 时间 | date_str | 变化？ | Segment 行为 |
|--------|------|----------|--------|-------------|
| 1 | 23:59:58 | 2026-05-14 | 首次启动 | 创建 Seg#1: [23:59:58→23:59:58] code.exe |
| 2 | 00:00:00 | **2026-05-15** | **date 变了！** | 1. 关闭 Seg#1: end=00:00:00 → 写入 DB (date=2026-05-14)<br>2. 创建 Seg#2: [00:00:00→00:00:00] code.exe (date=2026-05-15) |

**关键细节：** 跨天时，旧的 Segment 的 `date` 字段保持前一天，`end_time` 设为 00:00:00。新的 Segment 使用新日期，`start_time` 设为 00:00:00。

**例子 5：短促切换（< 2 秒）**

| 轮询 # | 时间 | 前台应用 | 变化？ | 行为 |
|--------|------|---------|--------|------|
| 1 | 14:00:00 | VS Code | 首次启动 | 创建 Seg#1 |
| 2 | 14:00:02 | **Notepad** | app_changed! | 关闭 Seg#1 (end=14:00:02)，创建 Seg#2 |
| 3 | 14:00:04 | **VS Code** | app_changed! | 关闭 Seg#2 (end=14:00:04)，创建 Seg#3 |

这里 Seg#2 只持续了 2 秒。在 `_flush_segment` 中：
```python
duration = self._segment_duration_seconds(seg)
if duration < 2:
    return  # 忽略超短段
```

**结果：** Seg#2 不会被写入数据库。但 Seg#1 和 Seg#3 都会被写入。Seg#1 的 end_time 是 14:00:02（虽然实际上用户在 14:00:02~14:00:04 期间在用 Notepad，但这段被过滤掉了）。

**这是一个精度损失：** 短于 2 秒的应用切换完全丢失。

### 3.5 写入策略详解

```python
def _flush_segment(self, seg: Segment):
    duration = self._segment_duration_seconds(seg)
    if duration < 2:
        return  # 过滤噪声
    
    if seg.db_id is None:
        seg.db_id = self.db.add_segment(...)  # INSERT
    else:
        self.db.update_segment_end_time(seg.db_id, seg.end_time)  # UPDATE
```

**INSERT vs UPDATE 的判断：**
- `db_id is None` → 这段从未写入过数据库 → 执行 INSERT
- `db_id is not None` → 这段已经在数据库中 → 只 UPDATE end_time

**何时 UPDATE：**
- 每 60 秒的定期刷盘
- 程序正常退出时的 `_close_current_segment`
- 用户手动暂停/恢复追踪时的状态切换

**这带来一个重要的性能优化：**
- 活跃期间（如连续在 VS Code 工作 1 小时），数据库只会被写入约 60 次（每 60 秒一次 UPDATE），而不是 1800 次（每 2 秒一次）
- 只有在**状态变化**时才会 INSERT 新记录

### 3.6 回调机制

```python
def _notify_state_change(self, state: dict):
    app = state['app_name'] if state['is_active'] else 'Idle'
    for cb in self._callbacks:
        try:
            cb(app)
        except Exception:
            pass
```

Tracker 维护一个回调列表。每次状态变化时，调用所有回调函数并传入当前应用名。

**当前唯一的回调：** `MainWindow._on_app_change()`
- 更新侧边栏的"当前应用"标签
- 更新托盘 tooltip

```python
def _on_app_change(self, app_name):
    self.lbl_current_app.setText(f"当前应用: {app_name}\n状态: 运行中")
    self.tray_icon.setToolTip(f"工作管理系统 - 运行中 ({app_name})")
```

**回调被调用的时机：**
1. 首次启动 tracker
2. 应用切换
3. 活跃/idle 切换
4. 跨天

**注意：** 回调在 `self._lock` 保护内被调用（见 `_loop`），因此 UI 更新和 Segment 操作是同步的。

### 3.7 暂停/恢复追踪

```python
def _toggle_tracking(self):
    if self.tracker._running:
        self.tracker.stop()
        # UI 更新为"已暂停"
    else:
        self.tracker.start()
        # UI 更新为"运行中"
```

`tracker.stop()` 的行为：
1. 设置 `_running = False`
2. 等待后台线程在最多 4 秒内退出（`poll_interval + 2`）
3. 调用 `_close_current_segment()` —— 强制关闭当前 Segment 并写入 DB
4. 关闭数据库连接

**暂停时的 Segment 处理：**
- 暂停会立即触发 `_close_current_segment`，当前 Segment 被定格并写入
- 恢复时会重新进入 `_loop` 的"首次启动"分支，创建新的 Segment
- 这意味着**暂停期间的时间不会被记录**（正确行为）


---

## 4. 数据持久化层：database.py

### 4.1 表结构设计

#### activity_segments（核心追踪表）

```sql
CREATE TABLE activity_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,              -- 日期，格式 "YYYY-MM-DD"
    start_time TEXT NOT NULL,        -- 开始时间，格式 "HH:MM:SS"
    end_time TEXT NOT NULL,          -- 结束时间，格式 "HH:MM:SS"
    app_name TEXT,                   -- 进程名（如 "code.exe"）
    task_id INTEGER,                 -- 关联 tasks 表，可 NULL
    is_idle INTEGER DEFAULT 0,       -- 0=活跃, 1=空闲
    source TEXT DEFAULT 'auto',      -- 'auto'=自动追踪, 'manual'=手动添加
    description TEXT DEFAULT '',     -- 备注/描述
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
```

**索引：**
```sql
CREATE INDEX idx_seg_date ON activity_segments(date)
CREATE INDEX idx_seg_start ON activity_segments(date, start_time)
CREATE INDEX idx_seg_task ON activity_segments(task_id)
```

**索引设计理由：**
- `idx_seg_date`：仪表盘按日查询（最频繁）
- `idx_seg_start`：时间线按日期+时间排序显示
- `idx_seg_task`：按任务分类聚合统计

#### tasks（工作分类表）

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,       -- "开发", "会议", "文档" 等
    color TEXT DEFAULT '#4CAF50',    -- 用于时间线着色
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

默认存在一个"未分类"任务：
```sql
INSERT INTO tasks (name, color) VALUES ('未分类', '#9E9E9E')
```

**用途：** 用户可以为时间段打标签（如"开发"），之后按任务类型统计时间占比。

### 4.2 数据写入流程

**INSERT（新 Segment）：**
```python
def add_segment(self, date_str, start_time, end_time, app_name, is_idle, task_id, source, description):
    cursor.execute('''
        INSERT INTO activity_segments
        (date, start_time, end_time, app_name, is_idle, task_id, source, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (date_str, start_time, end_time, app_name,
          1 if is_idle else 0, task_id, source, description))
    self.conn.commit()
    return cursor.lastrowid
```

**UPDATE（滑动 end_time）：**
```python
def update_segment_end_time(self, seg_id, end_time):
    cursor.execute(
        "UPDATE activity_segments SET end_time = ? WHERE id = ?",
        (end_time, seg_id)
    )
    self.conn.commit()
```

### 4.3 核心聚合算法：去重计算

#### 问题背景

 tracker 按 2 秒轮询，如果用户在 VS Code 和 Chrome 之间频繁切换，会产生大量重叠或相邻的 Segment。直接对 Segment 时长求和会**重复计算同一时间**。

**例子：**

```
09:00:00 - 09:05:00  VS Code    (5 min)
09:02:00 - 09:03:00  Chrome     (1 min)  ← 和上一段重叠！
09:05:00 - 09:10:00  VS Code    (5 min)
```

直接求和 = 5 + 1 + 5 = 11 分钟
真实活跃 = 5 + 5 = 10 分钟（Chrome 那段完全在 VS Code 段内，不应重复计算）

#### _merge_intervals_seconds 算法

```python
def _merge_intervals_seconds(self, segments):
    # 1. 提取非 idle 段的时间区间（转为分钟数）
    intervals = []
    for s in segments:
        if s.is_idle:
            continue
        sm = int(s.start_time[:2]) * 60 + int(s.start_time[3:5])
        em = int(s.end_time[:2]) * 60 + int(s.end_time[3:5])
        if em > sm:
            intervals.append((sm, em))
    
    # 2. 按开始时间排序
    intervals.sort(key=lambda x: x[0])
    
    # 3. 合并重叠/相邻区间
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            # 重叠或相邻，扩展
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    
    # 4. 求和（转回秒）
    return sum((end - start) * 60 for start, end in merged)
```

**步骤拆解（以上面的例子为例）：**

原始 Segment：
```
[09:00:00, 09:05:00] VS Code  → (540, 545)
[09:02:00, 09:03:00] Chrome   → (542, 543)
[09:05:00, 09:10:00] VS Code  → (545, 550)
```

Step 1：提取 intervals（忽略 idle，转分钟）
```
[(540, 545), (542, 543), (545, 550)]
```

Step 2：排序（已经有序）

Step 3：合并
```
merged = [(540, 545)]

处理 (542, 543):
  start=542 <= last_end=545 → 重叠！
  merged[-1] = (540, max(545, 543)) = (540, 545)
  
处理 (545, 550):
  start=545 <= last_end=545 → 相邻（=也算重叠）
  merged[-1] = (540, max(545, 550)) = (540, 550)
```

Step 4：求和
```
(550 - 540) * 60 = 10 * 60 = 600 秒 = 10 分钟
```

**正确！**

**另一个例子（不重叠）：**

```
[09:00, 09:05] VS Code   → (540, 545)
[09:06, 09:10] Chrome    → (546, 550)  ← 间隔 1 分钟
```

合并：
```
(546, 550): start=546 > last_end=545 → 不重叠，追加
merged = [(540, 545), (546, 550)]
```

总和 = (545-540)*60 + (550-546)*60 = 300 + 240 = 540 秒 = 9 分钟

**注意：** 中间空缺的 1 分钟（09:05~09:06）不会被计入。这是正确行为——用户确实没有在电脑前。

**边界情况：跨午夜段**

```
[23:50, 00:10] 某应用
```

这段在数据库中存储为 `date=2026-05-14, start=23:50:00, end=00:10:00`。`_merge_intervals_seconds` 直接解析 `end_time` 为 0*60+10=10 分钟，会得到 `end < start`，`if em > sm` 判断失败，**这段会被完全丢弃！**

这是当前算法的一个已知 bug：跨午夜的 Segment（如 23:50 → 00:10）在按日聚合时会被错误地忽略，因为算法假设 `end_time > start_time`。

### 4.4 聚合查询接口

#### 日汇总（get_daily_summary）

```python
def get_daily_summary(self, date_str: str) -> int:
    segs = self.get_segments_by_date(date_str)
    return self._merge_intervals_seconds(segs)
```

返回当天**去重后的总活跃秒数**。

#### 月汇总（get_monthly_summary）

```python
def get_monthly_summary(self, year, month) -> Dict[str, int]:
    # 返回 {date_str: total_seconds, ...}
    # 每天独立去重
```

**关键点：** 按天分组后每天分别调用 `_merge_intervals_seconds`。这意味着：
- 同一天的 overlapping segments 会被去重
- 不同天的数据互不影响

#### 周汇总（get_weekly_summary）

```python
def get_weekly_summary(self, monday_date: date) -> Dict[str, int]:
    # 查询周一到周日共 7 天
    # 每天独立去重
```

#### 年汇总（get_yearly_summary）

```python
def get_yearly_summary(self, year: int) -> Dict[str, int]:
    # 返回 {month: total_seconds, ...}
    # 每月独立去重
```

#### 应用排行（get_top_apps_by_date）

```python
def get_top_apps_by_date(self, date_str, limit=10):
    cursor.execute('''
        SELECT app_name,
               COALESCE(SUM((julianday(end_time) - julianday(start_time)) * 86400), 0)
        FROM activity_segments
        WHERE date = ? AND is_idle = 0 AND app_name IS NOT NULL
        GROUP BY app_name
        ORDER BY total_sec DESC
        LIMIT ?
    ''')
```

**注意：** 这个查询**没有去重**！它直接对同一应用的所有 Segment 求和。如果用户在 VS Code 和 Chrome 之间频繁切换，VS Code 的 Segment 可能包含大量被 Chrome 段覆盖的时间，这部分会被重复计算到 VS Code 的总时长中。

**例子：**
```
09:00-09:05 VS Code (5 min)
09:02-09:03 Chrome (1 min)  ← 在 VS Code 段内
09:05-09:10 VS Code (5 min)
```

VS Code 直接求和 = 10 分钟（正确，因为 VS Code 确实在前台 10 分钟）
Chrome 直接求和 = 1 分钟
总应用时长 = 11 分钟 > 实际活跃 10 分钟

这是设计上的取舍：应用排行允许"超过 100%"的总和，因为用户可能同时看到多个应用的数据（虽然实际上只有一个前台应用，但切换会造成时间重叠）。

#### 任务分布（get_task_distribution）

```python
def get_task_distribution(self, date_str=None, year=None, month=None):
    # LEFT JOIN tasks，未分配 task_id 的显示为 "未分类"
    # 同样没有去重
```

### 4.5 数据模型：ActivitySegment

```python
@dataclass
class ActivitySegment:
    id: int
    date: str
    start_time: str
    end_time: str
    app_name: Optional[str]
    task_id: Optional[int]
    is_idle: int          # 0 or 1
    source: str           # 'auto' | 'manual'
    description: str
```

**source 字段的意义：**
- `'auto'`：由 UsageTracker 自动创建的追踪数据
- `'manual'`：用户在时间线上手动拖拽创建的时间段

这允许自动追踪和手动规划共存，在时间线上用不同颜色或样式区分。


---

## 5. UI 展示层：仪表盘中的数据消费

### 5.1 仪表盘数据流

```
SQLite activity_segments
         │
         ▼
  Database.get_daily_summary()
  Database.get_top_apps_by_date()
  Database.get_task_distribution()
  Database.get_weekly_summary()
         │
         ▼
  DashboardWidget.refresh_data()
         │
         ▼
  饼图（任务分布）  柱状图（周趋势）  统计卡片
```

### 5.2 统计卡片

仪表盘左上角显示四个核心指标：

| 指标 | 数据来源 | 计算方式 |
|------|---------|---------|
| 今日活跃 | `get_daily_summary(today)` | `_merge_intervals_seconds` 去重后秒数 |
| 专注时长 | `get_daily_summary(today)` 过滤 is_idle=0 | 同上去重 |
| 应用切换 | `get_segments_by_date(today)` 的 app_name 变化次数 | 段数 - 1 |
| 空闲占比 | `idle_time / total_time` | idle 段总和 / (idle + active) 总和 |

**例子：**

假设今日数据库中有：
```
Seg#1: [09:00, 09:05] VS Code, active
Seg#2: [09:05, 09:10] VS Code, active  
Seg#3: [09:10, 09:15] Idle, idle
Seg#4: [09:15, 09:20] Chrome, active
```

**今日活跃：** `_merge_intervals_seconds` 处理所有 active 段 → (540,545)+(545,550)+(555,560)
  - (540,550) 合并（相邻）
  - (555,560) 独立
  - 总计 = 10*60 + 5*60 = 900 秒 = 15 分钟

**专注时长：** 同上（因为没有 idle 段被计入）

**应用切换：** 4 段 - 1 = 3 次切换（严格来说是 3 个"边界"：Seg1→Seg2, Seg2→Seg3, Seg3→Seg4）

**空闲占比：** idle = 5 分钟，总 = 20 分钟 → 25%

### 5.3 饼图：任务分布

```python
task_data = self.db.get_task_distribution(date_str=today)
# 返回 [(task_name, duration_seconds), ...]
```

使用 matplotlib 绘制：
```python
ax.pie(durations, labels=task_names, autopct='%1.1f%%', ...)
```

**颜色来源：** tasks 表的 `color` 字段。未分类任务使用默认灰色 `#9E9E9E`。

**注意：** 如果一个 Segment 没有关联 task_id，它默认归入"未分类"。

### 5.4 柱状图：周趋势

```python
week_data = self.db.get_weekly_summary(monday)
# 返回 {'2026-05-12': 28800, '2026-05-13': 32400, ...}
```

绘制 7 天的柱状图，X 轴为"周一"~"周日"，Y 轴为小时数。

**数据去重：** 每天的数值已经过 `_merge_intervals_seconds` 去重。

### 5.5 实时托盘信息

```python
def get_current_segment_summary(self):
    with self._lock:
        if not self._current_segment:
            return "无"
        duration = time.time() - self._current_segment_start_ts
        return f"{self._current_segment.app_name} ({int(duration)}s)"
```

Tray icon 的 tooltip 显示当前 Segment 的应用名和已持续时间。这不是来自数据库，而是内存中的实时计算。


---

## 6. 设计决策与权衡

### 6.1 轮询 vs 事件驱动

**当前方案：轮询（Polling）**
- 每 2 秒主动查询系统状态
- 优点：实现简单、跨平台兼容性好、不会遗漏事件
- 缺点：固定开销（2 秒一次的 CPU/IO）、精度上限为 2 秒

**替代方案：事件驱动（Hook）**
- 使用 Windows `SetWinEventHook` 监听前台窗口变化事件
- 优点：零开销等待、毫秒级精度、事件发生时立即响应
- 缺点：实现复杂、需要处理消息泵、可能错过某些边缘情况

**决策理由：**
- 轮询的 2 秒间隔对"工作时间统计"场景来说精度足够（用户不会在意 2 秒误差）
- 事件驱动需要维护一个消息循环，与 PyQt 的主事件循环可能冲突
- 轮询还可以同时检测 idle 状态（鼠标/键盘无输入），这是单纯窗口事件无法提供的

### 6.2 内存 Segment + 延迟写入 vs 实时写入

**当前方案：**
- Segment 先在内存中"滑动"（只更新 end_time）
- 状态变化或 60 秒超时才写入数据库

**替代方案：** 每 2 秒 INSERT/UPDATE

**当前方案的优点：**
- 大幅减少数据库写入次数（从每 2 秒一次降到每分钟一次或更少）
- 减少磁盘磨损（对 SSD 友好）
- 事务更小，降低数据库锁定时间

**风险：**
- 程序崩溃时丢失最多 60 秒的数据
- 但在"工作统计"场景下，60 秒的数据丢失是可接受的

### 6.3 SQLite vs 其他数据库

**选择 SQLite 的理由：**
- 零配置、单文件、内嵌在应用中
- 用户的个人工作数据量很小（一年数据通常 < 100MB）
- 不需要多用户并发、网络访问
- Python 内置支持

**如果未来数据量增长：**
- 可以透明地迁移到 PostgreSQL（SQLAlchemy ORM 层抽象）
- 但当前单用户桌面应用场景下没有必要

### 6.4 时间存储格式

**当前格式：**
- `date`: TEXT "YYYY-MM-DD"
- `start_time/end_time`: TEXT "HH:MM:SS"

**为什么不使用 DATETIME/TIMESTAMP？**
- SQLite 的日期时间函数（如 `julianday()`）对 TEXT 格式支持良好
- 字符串格式便于直接阅读和调试
- 分离 date 和 time 字段便于按天查询（`WHERE date = '2026-05-14'`）

**代价：**
- 跨午夜段（如 23:50 → 00:10）在按日聚合时会有问题（见第 7.1 节）
- 需要手动解析字符串进行时间运算

### 6.5 idle 检测阈值

**默认值：3 分钟（180,000 毫秒）**

**权衡：**
- 太短（如 30 秒）：用户可能只是停下来思考，就被标记为 idle
- 太长（如 10 分钟）：用户去喝水、上厕所的时间被错误计为工作

**3 分钟的经验依据：**
- 大多数"短暂离开"（拿杯水、去洗手间）在 1-2 分钟内
- "停下来思考"通常不会超过 2 分钟（会动鼠标或键盘）
- 3 分钟是一个合理的分界点

**注意：** 这个阈值存储在 settings 表中，用户可以自行调整：
```python
idle_threshold = int(self.db.get_setting('idle_threshold_ms', '180000'))
```


---

## 7. 已知问题与边缘情况

### 7.1 跨午夜段的去重 Bug

**问题描述：**

当用户在接近午夜时工作，产生跨午夜的 Segment：
```
date=2026-05-14, start_time=23:50:00, end_time=00:10:00
```

`_merge_intervals_seconds` 解析这段：
```python
sm = 23*60 + 50 = 1430
em = 0*60 + 10 = 10
```

`if em > sm` → `10 > 1430` → **False！这段被完全丢弃。**

**影响：**
- 跨午夜工作的用户（如夜班开发者）会丢失 23:50~00:00 这段时间的统计
- 日汇总显示的时间会少于实际工作时间

**修复方案：**

方案 A：拆分存储
```
Segment A: date=2026-05-14, start=23:50:00, end=23:59:59
Segment B: date=2026-05-15, start=00:00:00, end=00:10:00
```

方案 B：使用 24 小时制分钟数
```python
sm = 23*60 + 50 = 1430
em = 24*60 + 10 = 1450  # 跨天加 1440
# 计算后取模
```

方案 C：使用分钟时间戳（当天第几分钟）
存储时允许 end_minutes > 1440，聚合时处理。

**当前状态：** 未修复。由于大多数用户不会在午夜工作，优先级较低。

### 7.2 应用切换精度损失

**问题描述：**

如果用户在 2 秒轮询间隔内快速切换多个应用：
```
T+0s:   切换到 Chrome（用户操作）
T+0.5s: 切换到 VS Code（用户操作）
T+1s:   切换到 Notepad（用户操作）
T+2s:   轮询检测到 Notepad
```

结果：Chrome 和 VS Code 的使用完全丢失，只记录了 Notepad。

**影响：**
- 应用切换频率极高的用户（<2 秒）的统计会不准确
- 但这类场景非常罕见

**缓解：**
- 降低轮询间隔到 1 秒可以提高精度，但会增加 CPU 使用率
- 事件驱动方案可以从根本上解决这个问题

### 7.3 短于 2 秒的段被过滤

**_flush_segment 的过滤逻辑：**
```python
if duration < 2:
    return  # 不写入
```

**问题场景：**
用户不小心点到了桌面（1 秒），然后马上回到 VS Code：
```
[09:00:00, 09:00:02] VS Code
[09:00:02, 09:00:03] explorer.exe  ← 1 秒，被过滤
[09:00:03, 09:00:05] VS Code
```

结果：
```
DB 记录：
Seg#1: [09:00:00, 09:00:02] VS Code  (2 秒)
Seg#3: [09:00:03, 09:00:05] VS Code  (2 秒)
```

注意：中间有 1 秒（09:00:02~09:00:03）没有被任何 Segment 覆盖。在 `_merge_intervals_seconds` 中：
```
(540, 542) 和 (543, 545)
start=543 > last_end=542 → 不重叠，两段独立
```

总时长 = 2 + 2 = 4 秒，但实际 VS Code 使用时间约为 4 秒（09:00:00~09:00:03 减去 1 秒桌面），误差 1 秒。

**影响：** 极小，因为短于 2 秒的误触通常不重要。

### 7.4 屏幕锁定的误判

**当前检测方式：**
```python
def is_screen_locked():
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    return title in ["Windows 锁定屏幕", "Windows Lock Screen", "Windows 安全登录"]
```

**问题：**
- 某些第三方锁屏软件可能使用不同的窗口标题
- 如果锁屏窗口不是前台窗口（某些企业策略），检测会失败
- 远程桌面会话最小化时，`GetForegroundWindow` 返回 0

**后果：**
- 误判为"用户活跃"，记录大量虚假 active 时间
- 或者误判为"锁定"，记录大量 idle 时间

**修复方向：** 使用 `WTSGetActiveConsoleSessionId` + `WTSQuerySessionInformation` 检测会话状态。

### 7.5 多显示器环境下的精度

`GetLastInputInfo` 检测的是**整个会话**的输入时间，不区分显示器。这意味着：
- 用户在显示器 A 工作，然后去显示器 B 操作，idle 计时器仍然重置
- 这在多显示器环境下是正确的行为（用户确实在活跃）

但有一个边缘情况：
- 用户在看副显示器的参考资料，长时间不动鼠标/键盘
- 主显示器的前台应用仍然被记录为 active
- 实际上用户没有和该应用交互

**这是设计上的局限：** tracker 只能知道"前台窗口是什么"，无法知道"用户实际在和哪个窗口交互"。

### 7.6 崩溃恢复

**场景：** 程序在运行中崩溃（未调用 `tracker.stop()`）。

**当前 Segment 状态：**
- 内存中的 `_current_segment` 丢失了最后的 `end_time` 更新
- 上一次 `_flush_segment`（最多 60 秒前）的数据已经写入数据库

**结果：**
- 丢失最多 60 秒的数据（上一次刷盘到崩溃之间）
- 数据库中已有的 Segment 是完整的（因为定期 UPDATE）

**改善：** 可以引入更频繁的刷盘（如每 30 秒），或使用 WAL 模式提高写入性能。

### 7.7 系统休眠/睡眠

**场景：** 用户合上笔记本盖子，系统进入睡眠。

**检测：**
- Windows 睡眠前会发送 `WM_POWERBROADCAST` 消息，但 tracker 没有监听
- 睡眠期间，轮询线程被冻结
- 醒来后，轮询继续

**可能的问题：**
- 睡眠前的 Segment 的 `end_time` 可能不是精确的睡眠时刻
- 醒来后，`GetLastInputInfo` 的 `dwTime` 可能与系统运行时间不一致

**当前处理：** 依赖 idle 检测。如果醒来后用户长时间不动，`is_active` 会变为 False，触发新的 Idle Segment。

### 7.8 同一应用多窗口

**场景：** 用户同时打开了多个 Chrome 窗口（工作和个人）。

**tracker 的行为：**
- 只记录前台窗口的进程名 "chrome.exe"
- 无法区分是哪个窗口
- 所有 Chrome 窗口的时间都汇总到 "chrome.exe"

**如果要区分：** 需要使用 `window_title` 做更细粒度的分类，但这会大幅增加复杂度。


---

## 8. 性能分析

### 8.1 轮询开销估算

每 2 秒轮询一次，每次轮询执行的操作：

| 操作 | 耗时估算 | 说明 |
|------|---------|------|
| `GetLastInputInfo` | ~0.1 ms | Windows API，极快 |
| `GetTickCount` | ~0.01 ms | Windows API，极快 |
| `GetForegroundWindow` | ~0.1 ms | Windows API |
| `GetWindowThreadProcessId` | ~0.1 ms | Windows API |
| `psutil.Process(pid).name()` | ~1-5 ms | 首次较慢，有缓存后更快 |
| 状态比较 + Segment 更新 | ~0.01 ms | Python 内存操作 |
| `time.sleep(2)` | 2000 ms | 大部分时间在这里 |

**单次轮询总耗时（无状态变化）：** ~2-6 ms
**CPU 占用率：** ~0.1% - 0.3%（非常轻量）

### 8.2 数据库写入开销

**INSERT（状态变化时）：**
```
INSERT INTO activity_segments (...) VALUES (...)
```
- 耗时：~1-3 ms（SQLite 内存 + 磁盘写入）

**UPDATE（每 60 秒刷盘）：**
```
UPDATE activity_segments SET end_time = ? WHERE id = ?
```
- 耗时：~0.5-2 ms

**日常写入频率估算：**

假设一个典型工作日（8 小时）：
- 应用切换：约 100 次（平均每 5 分钟切换一次应用）
- INSERT 次数：~100 次（状态变化）
- UPDATE 次数：~480 次（每 60 秒刷盘 × 8 小时）
- 总写入操作：~580 次/天

**磁盘写入量：** 每次操作几百字节，总计每天 < 1MB 的写入量。

### 8.3 仪表盘查询性能

**日汇总查询：**
```sql
SELECT * FROM activity_segments WHERE date = '2026-05-14'
```
- 数据量：~100-200 条/天
- 查询时间：< 1 ms（有索引）
- 去重计算：~1-3 ms（Python 端）

**月汇总查询：**
- 数据量：~3000-6000 条/月
- 查询时间：< 10 ms
- 去重计算：~10-30 ms（30 天 × 每天去重）

**结论：** 所有查询都在毫秒级完成，UI 响应流畅。

### 8.4 内存占用

| 组件 | 内存估算 |
|------|---------|
| Python 解释器 + PyQt | ~80-120 MB |
| UsageTracker（内存中的 Segment）| ~1 KB |
| Database 连接 + 缓存 | ~5-10 MB |
| 仪表盘图表（matplotlib）| ~20-30 MB |
| **总计** | **~110-160 MB** |

这是一个非常轻量的桌面应用。

### 8.5 长期数据增长

**数据量估算：**

每条 Segment 记录大小：
```
id(8) + date(11) + start_time(9) + end_time(9) + app_name(avg 15) + task_id(8) + is_idle(4) + source(5) + description(avg 20) = ~89 bytes
```

每天约 100-200 条 Segment：
```
200 × 89 bytes = ~17.8 KB/天
```

一年数据量：
```
17.8 KB × 365 = ~6.5 MB/年
```

加上索引开销，实际约 **10-15 MB/年**。

**十年数据量：** ~100-150 MB。

SQLite 单文件支持到 TB 级别，所以数据量完全不是瓶颈。


---

## 9. 未来优化方向

### 9.1 事件驱动架构（高精度追踪）

**当前局限：** 2 秒轮询导致短于 2 秒的应用切换丢失。

**方案：** 使用 `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` 监听前台窗口变化事件。

```python
import ctypes
from ctypes import wintypes

# 注册事件钩子
callback = ctypes.WINFUNCTYPE(None, ...)
hook = ctypes.windll.user32.SetWinEventHook(
    EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
    None, callback_ptr, 0, 0, WINEVENT_OUTOFCONTEXT
)
```

**优点：**
- 毫秒级精度
- 零 CPU 开销（等待事件）
- 不会遗漏任何切换

**挑战：**
- 需要在 PyQt 事件循环中集成 Windows 消息泵
- 事件回调可能在非主线程中执行，需要线程安全处理
- 仍然需要轮询来检测 idle 状态（GetLastInputInfo）

**混合方案：**
- 窗口切换：事件驱动（即时响应）
- Idle 检测：轮询（每 5-10 秒）

### 9.2 跨午夜段修复

**方案：** 在 `_flush_segment` 或 `_start_new_segment` 中自动拆分跨午夜段。

```python
def _split_overnight_segment(self, seg):
    """将跨午夜段拆分为两段"""
    if seg.start_time < "00:00:00" and seg.end_time > "00:00:00":
        # 创建第一段（前一天）
        seg1 = Segment(
            date_str=seg.date_str,
            start_time=seg.start_time,
            end_time="23:59:59",
            ...
        )
        # 创建第二段（后一天）
        next_date = (datetime.strptime(seg.date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        seg2 = Segment(
            date_str=next_date,
            start_time="00:00:00",
            end_time=seg.end_time,
            ...
        )
        return [seg1, seg2]
    return [seg]
```

### 9.3 应用分类规则引擎

**当前：** 按进程名（如 "code.exe"）统计。

**优化：** 允许用户定义规则，将多个进程归类到同一个"工作类型"。

```python
RULES = [
    {"name": "开发", "patterns": ["code.exe", "idea64.exe", "pycharm64.exe"]},
    {"name": "浏览器", "patterns": ["chrome.exe", "firefox.exe", "msedge.exe"]},
    {"name": "沟通", "patterns": ["wechat.exe", "slack.exe", "teams.exe"]},
]
```

**好处：**
- 减少应用排行的碎片化（20 个不同的编辑器合并为"开发"）
- 更准确的任务时间占比

### 9.4 机器学习能力

**空闲阈值自适应：**

不同用户的"思考时间"不同。可以通过机器学习自动调整 idle 阈值：

```python
# 分析用户历史数据
# 如果用户在某个应用停留 5 分钟后通常继续工作（非 idle）
# 则提高该应用的 idle 阈值
```

**应用分类自动学习：**
- 根据窗口标题关键词自动分类（如包含 "GitHub" → 开发）
- 根据使用时间段分类（如晚上 22:00 后的娱乐应用）

### 9.5 数据导出与备份

**当前：** 数据存储在本地 SQLite 文件中。

**优化：**
- CSV/Excel 导出（便于用户做年度总结）
- 自动云备份（OneDrive/Google Drive 同步）
- 数据加密（保护隐私）

### 9.6 多设备同步

**场景：** 用户在台式机和笔记本上都使用 Work Manager。

**方案：**
- 每个设备独立追踪
- 通过云同步合并数据（需要处理时间重叠）
- 或者使用中央服务器统一存储

### 9.7 更细粒度的追踪

**当前：** 只记录"前台应用"。

**可能的扩展：**
- 记录当前文档/项目名称（从窗口标题提取）
- 记录浏览器当前 URL（需要浏览器扩展配合）
- 记录代码编辑器当前文件（需要 IDE 插件）

### 9.8 可视化增强

- **热力图：** 一周 7 天 × 24 小时的活跃热力图
- **桑基图（Sankey）：** 展示时间在不同应用/任务间的流转
- **趋势预测：** 基于历史数据预测本周/本月总工作时间


---

## 10. 总结

### 10.1 架构回顾

Work Manager 的追踪系统采用三层架构：

```
┌─────────────────────────────────────────────────────────────┐
│                    UI 展示层（仪表盘）                         │
│  饼图 · 柱状图 · 统计卡片 · 托盘实时提示 · 时间线可视化         │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ 查询聚合数据
┌─────────────────────────────────────────────────────────────┐
│                  数据持久化层（database.py）                   │
│  SQLite 数据库 · 去重合并算法 · 日/周/月/年聚合查询              │
│  activity_segments · tasks · settings                        │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ INSERT / UPDATE
┌─────────────────────────────────────────────────────────────┐
│                   追踪引擎层（tracker.py）                     │
│  后台线程 · 2 秒轮询 · Segment 状态机 · 滑动窗口 · 60 秒刷盘     │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ 调用
┌─────────────────────────────────────────────────────────────┐
│                   系统监控层（monitor.py）                     │
│  GetLastInputInfo（idle 检测）· GetForegroundWindow（前台窗口）│
│  psutil（进程名解析）· 锁屏检测 · 自进程过滤                    │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 核心设计哲学

1. **简单可靠优先**：轮询方案虽然不够"优雅"，但实现简单、行为可预测、极少出错

2. **延迟写入策略**：内存中滑动更新 + 定期刷盘，在数据安全和性能之间取得平衡

3. **去重计算**：在查询阶段而非存储阶段做去重，保持原始数据完整，便于后续分析

4. **低开销**：2 秒轮询 + 每分钟一次数据库写入，CPU 占用 < 0.3%，对用户系统几乎无感知

5. **可扩展性**：清晰的模块分层（monitor → tracker → database → UI），每个层都可以独立替换或升级

### 10.3 关键数字

| 指标 | 数值 | 说明 |
|------|------|------|
| 轮询间隔 | 2 秒 | 精度与开销的平衡点 |
| Idle 阈值 | 3 分钟 | 区分"思考"和"离开" |
| 刷盘间隔 | 60 秒 | 崩溃时最多丢失 60 秒 |
| 最小有效段 | 2 秒 | 过滤噪声和误触 |
| 日数据量 | ~17 KB | 约 200 条 Segment |
| 年数据量 | ~6.5 MB | 单用户典型值 |
| CPU 占用 | < 0.3% | 后台追踪时 |
| 内存占用 | ~110-160 MB | 完整应用 |
| 查询耗时 | < 10 ms | 日/周汇总 |

### 10.4 适用场景

✅ **非常适合：**
- 个人工作时间追踪与复盘
- 按任务分类统计时间占比
- 发现时间黑洞（哪个应用占用最多时间）
- 生成周报/月报的数据支撑

⚠️ **有限制：**
- 需要精确到秒级的应用切换追踪（建议改用事件驱动）
- 跨午夜工作的用户（跨天统计有 bug）
- 多用户共享一台电脑（数据会混合）
- 需要追踪"实际交互"而非"前台窗口"（需要更深度的 OS 集成）

### 10.5 一句话总结

> Work Manager 的追踪系统通过"2 秒轮询 + 内存滑动窗口 + 每分钟刷盘 + 查询时去重"的简单但高效的设计，在极低的系统开销下实现了可靠的个人工作时间追踪，适合绝大多数日常办公场景。

---

*文档版本：1.0*  
*最后更新：2026-05-13*  
*适用代码版本：core/monitor.py, core/tracker.py, core/database.py, ui/dashboard_widget.py*
