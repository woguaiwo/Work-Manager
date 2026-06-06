# Work Manager

<p align="center">
  <img src="icon.png" width="96" alt="Work Manager Icon">
</p>

<p align="center">
  A Windows desktop app that automatically tracks your daily work time and application usage, helping you understand where your time goes and boost focus.
</p>

<p align="center">
  <a href="README.zh.md">🇨🇳 中文</a>
</p>

---

## Features

- **Auto Background Tracking** — Detects the foreground window every 2 seconds and records app usage duration
- **Task Tag System** — Define your own tasks with colors; automatically remembers the last task per window
- **Focus Session** — Automatically merges contiguous active segments into focused sessions, showing duration and task breakdown
- **24h Timeline** — Vertical timeline overview of the whole day; double-click to view Focus Session details
- **Multi-dimensional Dashboard** — Bar + donut charts for today / this week / this month / this year
- **Calendar Review** — Browse historical records by month, quickly jump to any date
- **i18n Support** — One-click language switch between Chinese and English
- **System Tray** — Minimize to tray and keep tracking silently; desktop shortcut support
- **Local Data Storage** — All data stored in a local SQLite database, no internet required, privacy-safe

## Installation & Run

### Requirements

- Windows 10/11
- Python 3.10+

### Install Dependencies

```bash
pip install PyQt6 matplotlib pywin32 psutil Pillow
```

### Launch

```bash
python main.py
```

Or on Windows, simply double-click `start.bat` (with console) or `start.vbs` (silent).

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
│   ├── monitor.py               # Foreground window detection
│   ├── tracker.py               # Background tracking engine
│   └── database.py              # SQLite operations
├── ui/
│   ├── main_window.py           # Main window & sidebar navigation
│   ├── dashboard.py             # Stats dashboard (bar + donut charts)
│   ├── timeline_view.py         # 24h vertical timeline
│   ├── timeline_container.py    # Timeline page container
│   ├── task_dialog.py           # Task management dialog
│   ├── focus_session_dialog.py  # Focus Session detail popup
│   ├── settings_dialog.py       # Settings dialog (language switch, etc.)
│   ├── calendar_widget.py       # Calendar component
│   ├── project_indicator.py     # Project / task indicator
│   └── theme.py                 # Theme & style constants
├── utils/
│   ├── i18n.py                  # Internationalization module
│   ├── focus_session.py         # Focus Session grouping algorithm
│   ├── helpers.py               # Time formatting & helpers
│   └── logger.py                # Logging module
├── icon.png / icon.ico          # App icons
└── docs/                        # Design docs (local only, not in repo)
```

## Usage

1. **Launch** — Run `main.py`; the app auto-minimizes to the system tray and starts tracking
2. **Assign Tasks** — Open the main window and use the bottom project indicator to assign a task tag to the current app
3. **Dashboard** — Switch to the "Dashboard" page to see time distribution charts for today / week / month / year
4. **Timeline** — Switch to "Today's Details" to view the full day's window switches and task assignments
5. **Manage Tasks** — In "Task Management", add, edit, or delete your work categories (e.g. Development, Meeting, Docs)
6. **Switch Language** — Click the ⚙ Settings button in the sidebar to switch UI language (Chinese / English)

## Data Storage

All data is saved in a local SQLite database `data.db` in the program directory. No extra configuration needed — feel free to back up or migrate this file anytime.

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Made with ❤️ for focused work.
</p>
