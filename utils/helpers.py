"""
Helper utilities
"""

from datetime import datetime, timedelta
from utils.i18n import trs


def format_duration(seconds: int) -> str:
    """Format seconds into HH:MM:SS or MM:SS"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_duration_short(seconds: int) -> str:
    """Format seconds into Xh Xm or Xm"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0 and minutes > 0:
        return f"{hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h"
    return f"{minutes}m"


def get_app_display_name(process_name: str) -> str:
    """Map common process names to friendly names"""
    mapping = {
        'code.exe': 'VS Code',
        'devenv.exe': 'Visual Studio',
        'chrome.exe': 'Chrome',
        'msedge.exe': 'Edge',
        'firefox.exe': 'Firefox',
        'explorer.exe': trs('file_explorer'),
        'notepad.exe': trs('notepad'),
        'notepad++.exe': 'Notepad++',
        'cmd.exe': trs('command_prompt'),
        'powershell.exe': 'PowerShell',
        'pycharm64.exe': 'PyCharm',
        'idea64.exe': 'IntelliJ IDEA',
        'wechat.exe': trs('wechat'),
        'qq.exe': 'QQ',
        'dingtalk.exe': trs('dingtalk'),
        'feishu.exe': trs('feishu'),
        'lark.exe': 'Lark',
        'outlook.exe': 'Outlook',
        'winword.exe': 'Word',
        'excel.exe': 'Excel',
        'powerpnt.exe': 'PowerPoint',
        'python.exe': trs('work_manager'),
        'pythonw.exe': trs('work_manager'),
    }
    return mapping.get(process_name.lower(), process_name)


# ---------------------------------------------------------------------------
# Time math helpers for timeline view
# ---------------------------------------------------------------------------


def time_to_minutes(time_str: str) -> int:
    """Convert 'HH:MM' or 'HH:MM:SS' to minutes from midnight."""
    parts = time_str.split(':')
    h = int(parts[0])
    m = int(parts[1])
    return h * 60 + m


def minutes_to_time(minutes: int) -> str:
    """Convert minutes from midnight to 'HH:MM'."""
    minutes = max(0, min(minutes, 24 * 60 - 1))
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def snap_to_grid(minutes: int, grid_minutes: int = 5) -> int:
    """Snap minutes to nearest grid point (default 5 min)."""
    return round(minutes / grid_minutes) * grid_minutes


def duration_between(start_time: str, end_time: str) -> int:
    """Return duration in seconds between two HH:MM:SS strings."""
    fmt = "%H:%M:%S"
    try:
        start_dt = datetime.strptime(start_time, fmt)
        end_dt = datetime.strptime(end_time, fmt)
        delta = end_dt - start_dt
        return int(delta.total_seconds())
    except ValueError:
        return 0


def add_minutes_to_time(time_str: str, delta_minutes: int) -> str:
    """Add minutes to a HH:MM time string, clamped to 00:00–23:59."""
    base = datetime.strptime(time_str, "%H:%M")
    result = base + timedelta(minutes=delta_minutes)
    # Clamp
    day_start = base.replace(hour=0, minute=0)
    day_end = base.replace(hour=23, minute=59)
    if result < day_start:
        result = day_start
    if result > day_end:
        result = day_end
    return result.strftime("%H:%M")
