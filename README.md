# Work Manager — Automatic Time Tracker for Windows

<p align="center">
  <img src="icon.png" width="96" alt="Work Manager - automatic time tracking app icon">
</p>

<p align="center">
  A free, open-source <strong>automatic time tracker</strong> and <strong>work hours tracker</strong> for Windows.
  Track app usage, manage tasks, and visualize your productivity — all stored locally.
</p>

<p align="center">
  <a href="README.zh.md">🇨🇳 中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey.svg" alt="Windows">
</p>

---

## What is Work Manager?

**Work Manager** is a lightweight, privacy-first **desktop time tracking app** that runs silently in your system tray. It automatically detects which application window is active and records how long you spend on each task — no manual start/stop timers needed.

Unlike cloud-based time trackers, all your data stays on your machine in a local SQLite database.

## Features

- **Automatic Time Tracking** — Detects the foreground window every 2 seconds; records app usage duration automatically
- **Task Tagging System** — Define custom tasks with colors; auto-remembers the last task per window
- **Focus Sessions** — Merges contiguous active segments into focused work blocks with task breakdown
- **24-Hour Timeline** — Vertical timeline overview of your entire day; double-click any session for details
- **Productivity Dashboard** — Bar + donut charts for today / this week / this month / this year
- **Calendar Review** — Browse historical records by month; jump to any date instantly
- **Multi-Language Support** — One-click switch between English and Chinese (i18n)
- **System Tray Integration** — Minimize to tray and track silently; desktop shortcut support
- **Local-First Data** — All data stored in a local SQLite database; no internet or account required

## Why Use Work Manager?

| Feature | Work Manager | Browser Trackers | Manual Timers |
|---------|-------------|------------------|---------------|
| **Auto tracking** | ✅ Yes | ⚠️ Limited | ❌ No |
| **Privacy** | ✅ Local only | ❌ Cloud | ✅ Local |
| **Per-app task memory** | ✅ Yes | ❌ No | ❌ No |
| **Focus session analysis** | ✅ Yes | ❌ No | ❌ No |
| **Free & open source** | ✅ MIT | ❌ Paid / Freemium | Mixed |

## Installation

### Requirements

- Windows 10 / 11
- Python 3.10 or newer

### Install Dependencies

```bash
pip install PyQt6 matplotlib pywin32 psutil Pillow
```

### Launch

```bash
python main.py
```

Or on Windows, double-click:
- `start.bat` — launches with a console window
- `start.vbs` — launches silently in the background

### VS Code Extension (Optional)

For tracking the current working directory of your VS Code integrated terminal (including remote SSH sessions), install the companion extension:

[![Install from Marketplace](https://img.shields.io/badge/VS_Code_Marketplace-Work%20Manager%20for%20VS%20Code-blue.svg)](https://marketplace.visualstudio.com/items?itemName=woguaiwo.workmanager-vscode)

[Work Manager for VS Code](https://marketplace.visualstudio.com/items?itemName=woguaiwo.workmanager-vscode)

### Create Desktop Shortcut

```bash
python create_desktop_shortcut.py
```

## Project Structure

```
Work-Manager/
├── main.py                      # Entry point
├── start.bat / start.vbs        # Windows launch scripts
├── core/
│   ├── monitor.py               # Foreground window detection (Windows API)
│   ├── tracker.py               # Background tracking engine
│   └── database.py              # SQLite persistence layer
├── ui/
│   ├── main_window.py           # Main window & sidebar navigation
│   ├── dashboard.py             # Stats dashboard (bar + donut charts)
│   ├── timeline_view.py         # 24h vertical timeline
│   ├── timeline_container.py    # Timeline page container
│   ├── task_dialog.py           # Task management dialog
│   ├── focus_session_dialog.py  # Focus Session detail popup
│   ├── settings_dialog.py       # Settings (language, etc.)
│   ├── calendar_widget.py       # Calendar component
│   ├── project_indicator.py     # Project / task indicator bar
│   └── theme.py                 # Theme & style constants
├── utils/
│   ├── i18n.py                  # Internationalization (EN / ZH)
│   ├── focus_session.py         # Session grouping algorithm
│   ├── helpers.py               # Time formatting helpers
│   └── logger.py                # Logging module
├── icon.png / icon.ico          # App icons
└── docs/                        # Design docs (local only)
```

## Usage

1. **Launch** — Run `main.py`; the app auto-minimizes to the system tray and starts tracking
2. **Assign Tasks** — Open the main window and use the bottom project indicator to assign a task tag to the current app
3. **Dashboard** — View bar + donut charts showing your time distribution across today / week / month / year
4. **Timeline** — See the full day's window switches and task assignments on a 24h vertical timeline
5. **Manage Tasks** — Add, edit, or delete your work categories (e.g., Development, Meeting, Documentation)
6. **Switch Language** — Click the ⚙ Settings button in the sidebar to toggle English / Chinese

## Data & Privacy

All tracking data is saved in a local SQLite database (`data.db`) in the program directory.

- ✅ **No cloud upload**
- ✅ **No account required**
- ✅ **No network calls**
- ✅ **Easy to back up or migrate** — just copy `data.db`

## Keywords / Tags

`time-tracking` · `work-hours-tracker` · `automatic-time-tracker` · `productivity-app` · `focus-timer` · `windows-desktop-app` · `pyqt6` · `python` · `activity-monitor` · `task-tracker` · `work-time-manager`

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Made with ❤️ for focused work.
</p>
