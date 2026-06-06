"""
Windows foreground window monitor + idle detection
Uses win32gui, win32process, psutil for app detection
Uses GetLastInputInfo for keyboard/mouse idle detection
"""

import ctypes
from ctypes import wintypes
import os
import time

import win32gui
import win32process
import psutil

from utils.logger import get_logger

_log = get_logger("monitor")


# PID of the current process (our own tracker app)
_OWN_PID = os.getpid()


# Windows API structures for GetLastInputInfo
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


def get_idle_time_ms() -> int:
    """
    Returns milliseconds since last keyboard or mouse input.
    If the API fails, returns 0 (assume active).
    """
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            tick_count = ctypes.windll.kernel32.GetTickCount()
            idle_ms = tick_count - lii.dwTime
            return max(0, int(idle_ms))
    except Exception:
        _log.exception("GetLastInputInfo failed")
    return 0


def is_user_active(idle_threshold_ms: int = 180_000) -> bool:
    """
    Returns True if the user has interacted with keyboard/mouse
    within the last `idle_threshold_ms` milliseconds (default 3 min).
    """
    return get_idle_time_ms() < idle_threshold_ms


def is_screen_locked() -> bool:
    """
    Attempt to detect if the Windows session is locked.
    Returns False if detection fails (assume unlocked).
    """
    try:
        # Simple heuristic: if foreground window is the lock screen
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            return True
        title = win32gui.GetWindowText(hwnd)
        # Common lock screen window titles
        lock_titles = ['Windows Default Lock Screen', '锁屏界面', '登录']
        if any(t in title for t in lock_titles):
            _log.debug("Screen locked detected | title=%r", title)
            return True
    except Exception:
        _log.exception("is_screen_locked() failed")
    return False


def get_foreground_window_info() -> dict:
    """
    Get information about the currently focused window
    Returns dict with: hwnd, pid, process_name, window_title
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            return {'hwnd': 0, 'pid': 0, 'process_name': 'Unknown', 'window_title': ''}

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        window_title = win32gui.GetWindowText(hwnd)

        try:
            process = psutil.Process(pid)
            process_name = process.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            _log.debug("psutil access denied for pid=%d: %s", pid, e)
            process_name = 'Unknown'

        return {
            'hwnd': hwnd,
            'pid': pid,
            'process_name': process_name,
            'window_title': window_title
        }
    except Exception:
        _log.exception("get_foreground_window_info() failed")
        return {'hwnd': 0, 'pid': 0, 'process_name': 'Unknown', 'window_title': ''}


def get_current_app_name() -> str:
    """Get just the process name of the active window"""
    info = get_foreground_window_info()
    return info['process_name']


def get_user_state(idle_threshold_ms: int = 180_000) -> dict:
    """
    Returns a comprehensive state dict combining app info and idle detection.
    This is the primary API for the tracker.
    """
    app_info = get_foreground_window_info()
    idle_ms = get_idle_time_ms()
    locked = is_screen_locked()

    # If screen is locked, force idle
    if locked:
        is_active = False
    else:
        is_active = idle_ms < idle_threshold_ms

    state = {
        'app_name': app_info['process_name'],
        'window_title': app_info['window_title'],
        'idle_ms': idle_ms,
        'is_active': is_active,
        'is_locked': locked,
        'timestamp': time.time(),
    }
    _log.debug("get_user_state -> %s", state)
    return state
