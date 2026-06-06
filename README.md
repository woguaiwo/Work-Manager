# Work Manager — 工作管理系统

<p align="center">
  <img src="icon.png" width="96" alt="Work Manager Icon">
</p>

<p align="center">
  一款 Windows 桌面应用，自动追踪你的每日工作时间与应用程序使用，助你了解时间去向、提升专注效率。
</p>

<p align="center">
  <a href="#功能特性">功能特性</a> •
  <a href="#安装与运行">安装与运行</a> •
  <a href="#项目结构">项目结构</a> •
  <a href="#截图">截图</a> •
  <a href="#协议">协议</a>
</p>

---

## 功能特性

- **后台自动追踪** — 每 2 秒检测前台窗口，自动记录各应用使用时长
- **任务标签系统** — 自定义工作任务，为不同工作类型分配颜色；自动按窗口记住上次选择的任务
- **智能时段合并（Focus Session）** — 自动将连续活跃片段合并为专注时段，直观展示每次专注的时长与任务分布
- **24 小时时间轴** — 垂直时间轴纵览全天，支持双击查看 Focus Session 详情
- **多维度仪表盘** — 柱状图 + 环形图展示今日 / 本周 / 本月 / 本年的时间分布
- **日历回顾** — 按月查看历史记录，快速跳转到任意日期
- **多语言支持** — 中文 / 英文一键切换（i18n）
- **系统托盘** — 最小化到后台持续运行，不打扰工作；支持桌面快捷方式一键启动
- **本地数据存储** — 所有数据保存在 SQLite 数据库中，无需联网，隐私安全

## 安装与运行

### 环境要求

- Windows 10/11
- Python 3.10+

### 安装依赖

```bash
pip install PyQt6 matplotlib pywin32 psutil Pillow
```

### 启动程序

```bash
python main.py
```

或在 Windows 上直接双击 `start.bat`（有控制台窗口）或 `start.vbs`（静默启动）。

### 创建桌面快捷方式

```bash
python create_desktop_shortcut.py
```

## 项目结构

```
Work-Manager/
├── main.py                      # 程序入口
├── start.bat / start.vbs        # Windows 启动脚本
├── core/
│   ├── monitor.py               # Windows 前台窗口检测
│   ├── tracker.py               # 后台时长追踪引擎
│   └── database.py              # SQLite 数据库操作
├── ui/
│   ├── main_window.py           # 主窗口与侧边栏导航
│   ├── dashboard.py             # 统计仪表盘（柱状图 + 环形图）
│   ├── timeline_view.py         # 24 小时垂直时间轴
│   ├── timeline_container.py    # 时间轴页面容器
│   ├── task_dialog.py           # 任务管理对话框
│   ├── focus_session_dialog.py  # Focus Session 详情弹窗
│   ├── settings_dialog.py       # 设置对话框（语言切换等）
│   ├── calendar_widget.py       # 日历组件
│   ├── project_indicator.py     # 项目/任务指示器
│   └── theme.py                 # 主题与样式常量
├── utils/
│   ├── i18n.py                  # 国际化翻译模块
│   ├── focus_session.py         # Focus Session 合并算法
│   ├── helpers.py               # 时间格式化等辅助函数
│   └── logger.py                # 日志模块
├── icon.png / icon.ico          # 应用图标
└── docs/                        # 设计文档
```

## 使用说明

1. **启动** — 运行 `main.py`，程序自动最小化到系统托盘并在后台追踪
2. **分配任务** — 点击托盘图标打开主界面，在底部项目指示器中为当前应用选择任务标签
3. **查看仪表盘** — 切换到"仪表盘"页，查看今日 / 本周 / 本月 / 本年的时间分布图表
4. **查看时间轴** — 切换到"今日详情"页，在时间轴上查看全天的窗口切换与任务分配
5. **管理任务** — 在"任务管理"中添加、编辑、删除你的工作分类（如开发、会议、文档等）
6. **切换语言** — 点击侧边栏底部的 ⚙ 设置按钮，切换界面语言（中文/英文）

## 数据存储

所有数据保存在程序目录下的 `data.db` SQLite 数据库中，无需额外配置。你可以随时备份或迁移该文件。

## 截图

> （欢迎在此补充应用截图）

## 协议

本项目采用 [MIT License](LICENSE) 开源协议。

---

<p align="center">
  Made with ❤️ for focused work.
</p>
