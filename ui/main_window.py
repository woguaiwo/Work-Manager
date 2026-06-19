"""
Main Application Window
"""

import sys
import os
from datetime import date

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame,
    QSystemTrayIcon, QMenu, QApplication,
    QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont

from core.tracker import UsageTracker
from core.database import Database
from utils.helpers import format_duration_short, get_app_display_name
from utils.logger import get_logger
from utils.i18n import trs, language_changed
from ui.dashboard import DashboardWidget
from ui.settings_dialog import SettingsDialog
from ui.task_dialog import TaskManagerDialog
from ui.timeline_container import TimelineContainer
from ui.calendar_widget import CalendarWidget
from ui.project_indicator import ProjectIndicator
from ui.projects_widget import ProjectsWidget

_log = get_logger("mainwindow")


class MainWindow(QMainWindow):
    app_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("工作管理系统 - Work Manager")
        self.setMinimumSize(1200, 800)

        # Set application icon (window + taskbar)
        self._ensure_app_icon()

        self.db = Database()

        # Load language preference
        from utils.i18n import set_language
        lang = self.db.get_setting('language', 'zh')
        set_language(lang)

        self.tracker = UsageTracker(poll_interval=2.0)
        self.tracker.add_callback(self._on_app_change)
        self.tracker.start()

        self._init_ui()
        self._init_tray_icon()
        self._init_timer()
        self._init_indicator()
        self._init_shortcuts()

        # Listen for language changes
        language_changed.connect(self._retranslate_ui)

        # Initial translation of all UI text
        self._retranslate_ui()

        # Restore tracking state from settings
        tracking_enabled = self.db.get_setting('tracking_enabled', 'true')
        if tracking_enabled == 'false':
            self.tracker.stop()
            self.btn_toggle.setText(f"▶ {trs('start_recording')}")
            self.lbl_current_app.setText(trs("current_app_paused"))
            if self.tray_icon:
                self.tray_icon.setToolTip(trs("app_paused").format(trs("app_title")))

    def _ensure_app_icon(self):
        """Create icon.ico if not exists, then set as window and app icon."""
        import struct, io
        self._icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.ico")
        if not os.path.exists(self._icon_path):
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
                # Build multi-resolution ICO manually (Pillow doesn't support append_images for ICO)
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
                with open(self._icon_path, "wb") as f:
                    f.write(header + dirs + data)
            except Exception:
                # Fallback: create a simple ICO with Qt (single size)
                px = QPixmap(64, 64)
                px.fill(QColor("#5B8DB8"))
                p = QPainter(px)
                p.setPen(QColor("white"))
                font = QFont("Microsoft YaHei", 32, QFont.Weight.Bold)
                p.setFont(font)
                p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "工")
                p.end()
                px.save(self._icon_path)
        self.setWindowIcon(QIcon(self._icon_path))

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #E8D5C4;
                color: #4a3f35;
            }
            QPushButton {
                background-color: transparent;
                color: #5a4f45;
                border: none;
                border-radius: 8px;
                padding: 14px 16px;
                text-align: left;
                font-size: 14px;
                margin: 2px 6px;
            }
            QPushButton:hover {
                background-color: #D4C4B5;
                color: #3a2f25;
            }
            QPushButton:checked {
                background-color: #C4B4A5;
                color: #3a2f25;
                font-weight: bold;
            }
            QLabel {
                color: #7a6f65;
                padding: 8px 12px;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(5)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 12px 10px 18px 10px; color: #4a3f35;")
        sidebar_layout.addWidget(self.title_label)

        self.btn_timeline = QPushButton()
        self.btn_timeline.setCheckable(True)
        self.btn_timeline.setChecked(True)
        self.btn_timeline.clicked.connect(lambda: self._switch_page(0))

        self.btn_dashboard = QPushButton()
        self.btn_dashboard.setCheckable(True)
        self.btn_dashboard.clicked.connect(lambda: self._switch_page(1))

        self.btn_weekly = QPushButton()
        self.btn_weekly.setCheckable(True)
        self.btn_weekly.clicked.connect(lambda: self._switch_page(2))

        self.btn_calendar = QPushButton()
        self.btn_calendar.setCheckable(True)
        self.btn_calendar.clicked.connect(lambda: self._switch_page(3))

        self.btn_projects = QPushButton()
        self.btn_projects.setCheckable(True)
        self.btn_projects.clicked.connect(lambda: self._switch_page(4))

        self.btn_tasks = QPushButton()
        self.btn_tasks.setCheckable(True)
        self.btn_tasks.clicked.connect(self._open_task_manager)

        self.btn_settings = QPushButton()
        self.btn_settings.clicked.connect(self._open_settings)

        sidebar_layout.addWidget(self.btn_timeline)
        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.btn_weekly)
        sidebar_layout.addWidget(self.btn_calendar)
        sidebar_layout.addWidget(self.btn_projects)
        sidebar_layout.addWidget(self.btn_tasks)
        sidebar_layout.addWidget(self.btn_settings)
        sidebar_layout.addStretch()

        # Tracking toggle button
        self.btn_toggle = QPushButton()
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background-color: #5B8DB8;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                text-align: center;
                font-size: 13px;
                font-weight: bold;
                margin: 2px 6px;
            }
            QPushButton:hover {
                background-color: #4a7aa5;
            }
        """)
        self.btn_toggle.clicked.connect(self._toggle_tracking)
        sidebar_layout.addWidget(self.btn_toggle)

        # Current state monitor
        self.lbl_current_app = QLabel()
        self.lbl_current_app.setStyleSheet("font-size: 12px; color: #7a6f65; line-height: 1.5;")
        sidebar_layout.addWidget(self.lbl_current_app)

        self.lbl_today_total = QLabel()
        self.lbl_today_total.setStyleSheet("font-size: 15px; color: #5B8DB8; font-weight: bold; padding-top: 4px;")
        sidebar_layout.addWidget(self.lbl_today_total)

        main_layout.addWidget(sidebar)

        # Main content
        self.stack = QStackedWidget()

        # Page 0: Timeline (primary view)
        self.timeline_container = TimelineContainer(self.db)
        self.timeline_container.date_changed.connect(self._on_timeline_date_changed)
        self.stack.addWidget(self.timeline_container)

        # Page 1: Dashboard
        self.dashboard = DashboardWidget(self.db)
        self.stack.addWidget(self.dashboard)

        # Page 2: Weekly Plan (placeholder)
        self.weekly_widget = QWidget()
        weekly_layout = QVBoxLayout(self.weekly_widget)
        weekly_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weekly_placeholder = QLabel()
        self.weekly_placeholder.setStyleSheet("font-size: 18px; color: #7a6f65;")
        self.weekly_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        weekly_layout.addWidget(self.weekly_placeholder)
        self.stack.addWidget(self.weekly_widget)

        # Page 3: Calendar
        self.calendar_widget = CalendarWidget(self.db)
        self.stack.addWidget(self.calendar_widget)

        # Page 4: Projects
        self.projects_widget = ProjectsWidget(self.db)
        self.stack.addWidget(self.projects_widget)

        main_layout.addWidget(self.stack, 1)

    def _switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        self.btn_timeline.setChecked(index == 0)
        self.btn_dashboard.setChecked(index == 1)
        self.btn_weekly.setChecked(index == 2)
        self.btn_calendar.setChecked(index == 3)
        self.btn_projects.setChecked(index == 4)
        if index == 0:
            self.timeline_container.refresh()
        elif index == 1:
            self.dashboard.refresh()
        elif index == 3:
            self.calendar_widget.refresh()
        elif index == 4:
            self.projects_widget._ensure_loaded()

    def _open_task_manager(self):
        dialog = TaskManagerDialog(self.db, self)
        dialog.exec()
        self.btn_tasks.setChecked(False)
        self.timeline_container.refresh()
        self.dashboard.refresh()

    def _on_timeline_date_changed(self, date_str: str):
        # Update sidebar summary when timeline date changes
        total = self.db.get_daily_summary(date_str)
        self.lbl_today_total.setText(trs("day_active").format(format_duration_short(total)))

    def _init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return

        # Use the generated ICO if available, otherwise fallback to in-memory
        icon_path = getattr(self, '_icon_path', None)
        if icon_path and os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            # Fallback in-memory icon
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor("#5B8DB8"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("white"))
            font = QFont("Microsoft YaHei", 32, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "工")
            painter.end()
            self.tray_icon.setIcon(QIcon(pixmap))

        self.tray_icon.setToolTip(trs("app_running").format(trs("app_title")))

        tray_menu = QMenu()
        self.show_action = QAction(self)
        self.show_action.triggered.connect(self.show_normal)
        self.quit_action = QAction(self)
        self.quit_action.triggered.connect(self._quit)

        tray_menu.addAction(self.show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(self.quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _init_timer(self):
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._update_ui)
        self.ui_timer.start(1000)

    def _toggle_tracking(self):
        if self.tracker._running:
            _log.info("User clicked PAUSE tracking")
            self.tracker.stop()
            self.btn_toggle.setText("▶ 开始记录")
            self.lbl_current_app.setText(trs("current_app_paused"))
            if self.tray_icon:
                self.tray_icon.setToolTip("工作管理系统 - 已暂停")
            self.db.set_setting('tracking_enabled', 'false')
        else:
            _log.info("User clicked START tracking")
            try:
                self.tracker.start()
                self.btn_toggle.setText(f"⏸ {trs('pause_recording')}")
                if self.tray_icon:
                    self.tray_icon.setToolTip(trs("app_running").format(trs("app_title")))
                self.db.set_setting('tracking_enabled', 'true')
            except Exception:
                _log.exception("Failed to start tracker")
                QMessageBox.critical(self, trs("error"), trs("start_tracking_failed"))

    def _update_ui(self):
        if not self.tracker._running:
            self.lbl_current_app.setText(trs("current_app_paused"))
            return

        try:
            summary = self.tracker.get_current_segment_summary()
        except Exception:
            _log.exception("get_current_segment_summary() failed")
            return

        app = summary['app_name']
        is_active = summary['is_active']
        session_sec = summary['session_seconds']
        is_idle = summary['is_idle']

        display = get_app_display_name(app)
        if is_idle:
            status = trs("status_idle")
        elif is_active:
            status = trs("status_active").format(format_duration_short(session_sec))
        else:
            status = trs("status_detecting")

        self.lbl_current_app.setText(f"{trs('current_app')}: {display}\n{status}")

        # Today total (live: DB total + current session if active)
        try:
            today_str = date.today().isoformat()
            total = self.db.get_daily_summary(today_str)
            if is_active and not is_idle:
                total += session_sec
            if self.timeline_container.timeline.date_str == today_str:
                self.lbl_today_total.setText(trs("today_active").format(format_duration_short(total)))
        except Exception:
            _log.exception("_update_ui DB query failed")

    def _on_app_change(self, app_name: str):
        self.app_changed.emit(app_name)
        # Tracker callback runs in background thread -> schedule UI update on main thread
        if hasattr(self, 'timeline_container'):
            QTimer.singleShot(0, self.timeline_container.refresh)
        if hasattr(self, 'dashboard'):
            QTimer.singleShot(0, self.dashboard.refresh)

    def show_normal(self):
        self.showNormal()
        self.activateWindow()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_normal()

    def closeEvent(self, event):
        if self.tray_icon:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                trs("tray_minimized_title"),
                trs("tray_minimized_msg"),
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            self._quit()

    def _retranslate_ui(self):
        self.setWindowTitle(f"{trs('app_title')} - Work Manager")
        self.title_label.setText(f"📊 {trs('app_title')}")
        self.btn_timeline.setText(f"⏰ {trs('timeline')}")
        self.btn_dashboard.setText(f"📈 {trs('dashboard')}")
        self.btn_weekly.setText(f"📋 {trs('weekly_plan')}")
        self.btn_calendar.setText(f"📅 {trs('calendar')}")
        self.btn_projects.setText(f"📁 {trs('projects')}")
        self.btn_tasks.setText(f"📝 {trs('task_management')}")
        self.btn_settings.setText(f"⚙ {trs('settings')}")

        if hasattr(self, 'show_action'):
            self.show_action.setText(trs("show_main_window"))
        if hasattr(self, 'quit_action'):
            self.quit_action.setText(trs("quit"))

        if hasattr(self, 'weekly_placeholder'):
            self.weekly_placeholder.setText(f"📋 {trs('weekly_plan')}\n\n{trs('feature_in_development')}")

        if self.tracker._running:
            self.btn_toggle.setText(f"⏸ {trs('pause_recording')}")
            if self.tray_icon:
                self.tray_icon.setToolTip(trs("app_running").format(trs("app_title")))
        else:
            self.btn_toggle.setText(f"▶ {trs('start_recording')}")
            if self.tray_icon:
                self.tray_icon.setToolTip(trs("app_paused").format(trs("app_title")))

        # Propagate to child widgets
        if hasattr(self, 'timeline_container'):
            self.timeline_container._retranslate_ui()
        if hasattr(self, 'dashboard'):
            self.dashboard._retranslate_ui()
        if hasattr(self, 'calendar_widget'):
            self.calendar_widget._retranslate_ui()
        if hasattr(self, 'projects_widget'):
            self.projects_widget._retranslate_ui()
        if hasattr(self, 'indicator'):
            self.indicator._retranslate_ui()

        # Force refresh of dynamic labels
        self._update_ui()

    def _open_settings(self):
        dialog = SettingsDialog(self.db, self)
        dialog.exec()
        self.btn_settings.setChecked(False)

    def _init_indicator(self):
        # parent=None so the indicator stays visible when main window is minimized
        self.indicator = ProjectIndicator(self.tracker, self.db, parent=None)
        self._indicator_shown = False
        self.indicator.show_main_window.connect(self.show_normal)
        self.indicator.task_changed.connect(self._on_indicator_task_changed)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'indicator') and not getattr(self, '_indicator_shown', False):
            self._indicator_shown = True
            QTimer.singleShot(300, self.indicator.show)

    def _on_indicator_task_changed(self, task_id: int):
        # Refresh dashboard and timeline when task changes via indicator
        self.timeline_container.refresh()
        self.dashboard.refresh()

    def _init_shortcuts(self):
        from PyQt6.QtGui import QKeySequence, QShortcut
        tasks = self.db.get_all_tasks()
        for i, task in enumerate(tasks[:9]):
            seq = QKeySequence(f"Ctrl+Shift+{i+1}")
            sc = QShortcut(seq, self)
            sc.activated.connect(lambda tid=task.id: self._set_task_shortcut(tid))
        # Ctrl+Shift+0 = unclassified
        sc0 = QShortcut(QKeySequence("Ctrl+Shift+0"), self)
        sc0.activated.connect(lambda: self._set_task_shortcut(None))

    def _set_task_shortcut(self, task_id):
        self.tracker.set_current_task(task_id)
        self.indicator._refresh()
        self.timeline_container.refresh()
        self.dashboard.refresh()

    def _quit(self):
        _log.info("Application quitting...")
        if hasattr(self, 'indicator'):
            self.indicator.close()
        if self.tray_icon:
            self.tray_icon.hide()
        try:
            self.tracker.stop()
        except Exception:
            _log.exception("Error during tracker stop")
        try:
            self.db.close()
        except Exception:
            _log.exception("Error during database close")
        _log.info("Application quit complete")
        QApplication.instance().quit()
