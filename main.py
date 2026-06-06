"""
Work Manager - Main Entry Point

A Windows desktop application that tracks your active application usage,
stores daily/monthly/yearly work logs, and provides visual statistics.

Usage:
    python main.py
"""

import sys
import os

# Ensure we can find our own modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Logging setup (must be first, before anything else) ──
from utils.logger import setup_logging, get_logger
setup_logging()
_log = get_logger("main")

# Set Windows AppUserModelID BEFORE creating QApplication so taskbar groups correctly
# and uses our custom icon instead of the generic python.exe icon.
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WorkManager.App.1")
    _log.info("AppUserModelID set")
except Exception as e:
    _log.warning("Failed to set AppUserModelID: %s", e)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow


def _ensure_desktop_shortcut():
    """Auto-create desktop shortcut once. Uses a marker file to avoid duplicates."""
    try:
        import struct, io
        from win32com.client import Dispatch

        base_dir = os.path.dirname(os.path.abspath(__file__))
        marker_path = os.path.join(base_dir, ".shortcut_created")

        # Already created in a previous run; never create again automatically.
        if os.path.exists(marker_path):
            return

        shell = Dispatch("WScript.Shell")
        desktop = shell.SpecialFolders("Desktop")
        shortcut_path = os.path.join(desktop, "WorkManager.lnk")
        icon_path = os.path.join(base_dir, "icon.ico")

        # Ensure icon.ico exists
        if not os.path.exists(icon_path):
            try:
                from PIL import Image, ImageDraw, ImageFont
                images = []
                for sz in (16, 32, 48, 64, 128, 256):
                    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(img)
                    r = int(sz * 0.2)
                    draw.rounded_rectangle([0, 0, sz - 1, sz - 1], radius=r, fill="#5B8DB8")
                    try:
                        font = ImageFont.truetype("msyh.ttc", int(sz * 0.5))
                    except Exception:
                        font = ImageFont.load_default()
                    bbox = draw.textbbox((0, 0), "工", font=font)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    x = (sz - tw) // 2 - bbox[0]
                    y = (sz - th) // 2 - bbox[1]
                    draw.text((x, y), "工", font=font, fill="white")
                    images.append(img)
                count = len(images)
                header = struct.pack("<HHH", 0, 1, count)
                dirs = b""
                data = b""
                offset = 6 + 16 * count
                for img in images:
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    png_data = buf.getvalue()
                    w = img.width if img.width < 256 else 0
                    h = img.height if img.height < 256 else 0
                    dirs += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png_data), offset)
                    data += png_data
                    offset += len(png_data)
                with open(icon_path, "wb") as f:
                    f.write(header + dirs + data)
            except Exception:
                pass

        # Use start.vbs as the launcher (proven reliable, no console window)
        vbs_path = os.path.join(base_dir, "start.vbs")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.TargetPath = "wscript.exe"
        shortcut.Arguments = f'"{vbs_path}"'
        shortcut.WorkingDirectory = base_dir
        shortcut.Description = "工作管理系统 - Work Manager"
        if os.path.exists(icon_path):
            shortcut.IconLocation = icon_path
        shortcut.save()

        # Write marker so we never auto-create again
        with open(marker_path, "w") as f:
            f.write("1")
    except Exception:
        pass


def main():
    # Enable high DPI scaling
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Auto-create desktop shortcut on first run
    _ensure_desktop_shortcut()

    # Global stylesheet
    # Global Material-inspired stylesheet
    app.setStyleSheet("""
        QWidget {
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        }
        QPushButton {
            border-radius: 6px;
            padding: 8px 16px;
            background-color: #2196F3;
            color: white;
            border: none;
            font-size: 13px;
        }
        QPushButton:hover {
            background-color: #1976D2;
        }
        QPushButton:pressed {
            background-color: #1565C0;
        }
        QPushButton:disabled {
            background-color: #bdbdbd;
            color: #757575;
        }
        QLineEdit, QTextEdit {
            border-radius: 6px;
            border: 1px solid #e0e0e0;
            padding: 8px;
            background-color: white;
            font-size: 13px;
        }
        QLineEdit:focus, QTextEdit:focus {
            border: 1px solid #2196F3;
        }
        QComboBox {
            border-radius: 6px;
            border: 1px solid #e0e0e0;
            padding: 6px 10px;
            background-color: white;
            font-size: 13px;
            min-height: 24px;
        }
        QComboBox:focus {
            border: 1px solid #2196F3;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 1px solid #e0e0e0;
        }
        QComboBox QAbstractItemView {
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            background-color: white;
            selection-background-color: #e3f2fd;
            selection-color: #1565C0;
        }
        QDialog {
            background-color: #f5f7fa;
        }
        QFrame {
            background-color: transparent;
        }
        QScrollBar:vertical {
            background: #f5f5f5;
            width: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #c0c0c0;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #a0a0a0;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background: #f5f5f5;
            height: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:horizontal {
            background: #c0c0c0;
            border-radius: 4px;
            min-width: 30px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #a0a0a0;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        QMenu {
            background-color: white;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 6px;
        }
        QMenu::item {
            padding: 6px 20px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #e3f2fd;
            color: #1565C0;
        }
        QMessageBox {
            background-color: white;
        }
    """)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
