"""
Create a desktop shortcut (.lnk) for Work Manager.
Run this once:  python create_desktop_shortcut.py
"""
import os
import sys
import struct
import io


def ensure_icon():
    """Generate icon.ico if it doesn't exist."""
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(icon_path):
        return icon_path

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
        # Build multi-resolution ICO manually
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
    return icon_path


def create_shortcut():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = ensure_icon()

    # Find pythonw.exe
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        alt = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(alt):
            pythonw = alt

    main_py = os.path.join(base_dir, "main.py")
    try:
        from win32com.client import Dispatch
        shell = Dispatch("WScript.Shell")
        desktop = shell.SpecialFolders("Desktop")
        shortcut_path = os.path.join(desktop, "WorkManager.lnk")
        shortcut = shell.CreateShortCut(shortcut_path)

        needs_save = False
        if not os.path.exists(shortcut_path):
            shortcut.TargetPath = pythonw
            shortcut.Arguments = f'"{main_py}"'
            shortcut.WorkingDirectory = base_dir
            shortcut.Description = "工作管理系统 - Work Manager"
            needs_save = True

        if os.path.exists(icon_path):
            current_icon = getattr(shortcut, 'IconLocation', '')
            if icon_path not in current_icon:
                shortcut.IconLocation = icon_path
                needs_save = True

        if needs_save:
            shortcut.save()
            print(f"[OK] Desktop shortcut updated: {shortcut_path}")
        else:
            print(f"[OK] Desktop shortcut already up-to-date: {shortcut_path}")
    except Exception as e:
        print(f"[ERROR] Failed to create shortcut: {e}")
        print("Make sure pywin32 is installed:  pip install pywin32")


if __name__ == '__main__':
    create_shortcut()
