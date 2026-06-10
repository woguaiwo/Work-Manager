"""
Windows startup folder management.
Adds/removes a shortcut to start.vbs in the user's Startup folder
so Work Manager launches automatically on Windows login.
"""
import os


def _startup_folder() -> str:
    """Return the path to the Windows user startup folder."""
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )


def _shortcut_path() -> str:
    return os.path.join(_startup_folder(), "WorkManager.lnk")


def is_autostart_enabled() -> bool:
    """Check whether the startup shortcut exists."""
    return os.path.exists(_shortcut_path())


def set_autostart(enabled: bool) -> bool:
    """
    Enable or disable autostart by creating/deleting a shortcut
    in the Windows Startup folder.
    Returns True on success, False on failure.
    """
    shortcut = _shortcut_path()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vbs_path = os.path.join(base_dir, "start.vbs")
    icon_path = os.path.join(base_dir, "icon.ico")

    if enabled:
        try:
            from win32com.client import Dispatch
            shell = Dispatch("WScript.Shell")
            sc = shell.CreateShortCut(shortcut)
            sc.TargetPath = "wscript.exe"
            sc.Arguments = f'"{vbs_path}"'
            sc.WorkingDirectory = base_dir
            sc.Description = "Work Manager - Auto Start"
            if os.path.exists(icon_path):
                sc.IconLocation = icon_path
            sc.save()
            return True
        except Exception:
            return False
    else:
        try:
            if os.path.exists(shortcut):
                os.remove(shortcut)
            return True
        except Exception:
            return False
