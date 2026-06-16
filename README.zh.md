# Work Manager — Windows 自动时间追踪工具

<p align="center">
  <img src="icon.png" width="96" alt="Work Manager 图标">
</p>

<p align="center">
  一款免费开源的 Windows <strong>自动时间追踪</strong>与<strong>工作时长统计</strong>工具。
  自动记录应用使用、管理任务标签、可视化 productivity — 全部数据本地存储。
</p>

<p align="center">
  <a href="README.md">🇺🇸 English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey.svg" alt="Windows">
</p>

---

## Work Manager 是什么？

**Work Manager** 是一款轻量级、隐私优先的**桌面端时间追踪应用**，静默运行在系统托盘中。它会自动检测当前活跃的应用窗口，并记录你在每个任务上花费的时长 —— 无需手动点击开始/停止计时。

与云端时间追踪工具不同，所有数据都保存在你电脑的本地 SQLite 数据库中，完全不上传。

## 功能特性

- **自动时间追踪** — 每 2 秒检测前台窗口，自动记录各应用使用时长
- **任务标签系统** — 自定义工作任务并分配颜色；自动按窗口记住上次选择的任务
- **专注时段（Focus Session）** — 自动合并连续活跃片段为专注块，展示任务分布
- **24 小时时间轴** — 垂直纵览全天，双击任意时段查看详情
- **生产力仪表盘** — 柱状图 + 环形图展示今日 / 本周 / 本月 / 本年数据
- **日历回顾** — 按月查看历史记录，快速跳转到任意日期
- **多语言支持** — 一键切换中文 / 英文界面
- **系统托盘集成** — 最小化后台持续追踪；支持桌面快捷方式
- **本地优先** — 所有数据保存在本地 SQLite，无需联网或注册账号

## 为什么选择 Work Manager？

| 功能 | Work Manager | 浏览器插件 | 手动计时器 |
|------|-------------|-----------|-----------|
| **自动追踪** | ✅ 是 | ⚠️ 有限 | ❌ 否 |
| **隐私保护** | ✅ 纯本地 | ❌ 云端 | ✅ 本地 |
| **按窗口记忆任务** | ✅ 是 | ❌ 否 | ❌ 否 |
| **专注时段分析** | ✅ 是 | ❌ 否 | ❌ 否 |
| **免费开源** | ✅ MIT | ❌ 付费/限制 | 混合 |

## 安装与运行

### 环境要求

- Windows 10 / 11
- Python 3.10+

### 安装依赖

```bash
pip install PyQt6 matplotlib pywin32 psutil Pillow
```

### 启动程序

```bash
python main.py
```

或在 Windows 上直接双击：
- `start.bat` — 带控制台窗口启动
- `start.vbs` — 静默后台启动

### VS Code 扩展（可选）

如需追踪 VS Code 内置终端的当前工作目录（包括远程 SSH 会话），请安装配套扩展：

[![从 Marketplace 安装](https://img.shields.io/badge/VS_Code_Marketplace-Work%20Manager%20for%20VS%20Code-blue.svg)](https://marketplace.visualstudio.com/items?itemName=woguaiwo.workmanager-vscode)

[Work Manager for VS Code](https://marketplace.visualstudio.com/items?itemName=woguaiwo.workmanager-vscode)

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
│   ├── settings_dialog.py       # 设置对话框
│   ├── calendar_widget.py       # 日历组件
│   ├── project_indicator.py     # 项目/任务指示器
│   └── theme.py                 # 主题与样式常量
├── utils/
│   ├── i18n.py                  # 国际化翻译模块
│   ├── focus_session.py         # Focus Session 合并算法
│   ├── helpers.py               # 时间格式化等辅助函数
│   └── logger.py                # 日志模块
├── icon.png / icon.ico          # 应用图标
└── docs/                        # 设计文档（仅本地）
```

## 使用说明

1. **启动** — 运行 `main.py`，程序自动最小化到系统托盘并在后台追踪
2. **分配任务** — 打开主界面，在底部项目指示器中为当前应用选择任务标签
3. **查看仪表盘** — 切换至"仪表盘"页，查看柱状图与环形图展示的时间分布
4. **查看时间轴** — 切换至"今日详情"页，纵览全天窗口切换与任务分配
5. **管理任务** — 在"任务管理"中添加、编辑、删除工作分类（如开发、会议、文档）
6. **切换语言** — 点击侧边栏底部 ⚙ 设置按钮，切换中文 / 英文

## 数据与隐私

所有追踪数据保存在程序目录下的本地 SQLite 数据库 `data.db` 中。

- ✅ **不上传云端**
- ✅ **无需注册账号**
- ✅ **无网络请求**
- ✅ **备份迁移方便** — 直接复制 `data.db` 即可

## 关键词 / 标签

`时间追踪` · `工作时长统计` · `自动计时器` · `生产力工具` · `专注计时` · `Windows 桌面应用` · `任务管理` · `工作效率` · `time-tracking` · `productivity-app`

## 协议

本项目采用 [MIT License](LICENSE) 开源协议。

---

<p align="center">
  Made with ❤️ for focused work.
</p>
