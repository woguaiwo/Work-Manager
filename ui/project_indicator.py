"""
Floating project indicator widget
Always-on-top mini window showing current task / app / session duration.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu,
    QApplication, QDialog, QPushButton, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QAction, QCursor

from utils.logger import get_logger
from utils.i18n import trs

_log = get_logger("indicator")


class _TaskPickerDialog(QDialog):
    """Quick grid dialog for picking a task via click."""

    task_picked = pyqtSignal(int)  # task_id, -1 for unclassified

    def __init__(self, tasks, current_task_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(trs("select_current_task"))
        self.setMinimumWidth(300)
        layout = QGridLayout(self)
        layout.setSpacing(8)

        row, col = 0, 0
        # Unclassified button
        btn_none = QPushButton(f"🚫 {trs('unclassified')}")
        btn_none.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                color: white;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #757575; }
        """)
        btn_none.clicked.connect(lambda: self._pick(-1))
        layout.addWidget(btn_none, row, col)
        col += 1

        for task in tasks:
            btn = QPushButton(task.name)
            color = task.color or '#4CAF50'
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border-radius: 6px;
                    padding: 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {QColor(color).darker(120).name()};
                }}
            """)
            btn.clicked.connect(lambda checked, tid=task.id: self._pick(tid))
            layout.addWidget(btn, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

    def _pick(self, task_id: int):
        self.task_picked.emit(task_id)
        self.accept()


class ProjectIndicator(QWidget):
    """
    Always-on-top floating indicator showing current tracking state.
    """

    task_changed = pyqtSignal(int)   # -1 for unclassified
    show_main_window = pyqtSignal()

    def __init__(self, tracker, db, parent=None):
        super().__init__(parent)
        self.tracker = tracker
        self.db = db
        self._drag_pos: Optional[QPoint] = None

        self._init_ui()
        self._init_timer()
        self._load_position()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(180, 70)

        # Container with rounded background
        self.container = QWidget(self)
        self.container.setGeometry(0, 0, 180, 70)
        self.container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(50, 50, 50, 220);
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        # Top row: color bar + task name + focus button
        top = QHBoxLayout()
        top.setSpacing(6)

        self.lbl_color = QLabel()
        self.lbl_color.setFixedSize(8, 8)
        self.lbl_color.setStyleSheet("background-color: #9E9E9E; border-radius: 4px;")
        top.addWidget(self.lbl_color)

        self.lbl_task = QLabel(trs("unclassified"))
        self.lbl_task.setStyleSheet("color: white; font-size: 13px; font-weight: bold;")
        self.lbl_task.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        top.addWidget(self.lbl_task)
        top.addStretch()

        # Focus mode toggle button
        self.btn_focus = QPushButton("🎯")
        self.btn_focus.setFixedSize(18, 18)
        self.btn_focus.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                border-radius: 4px;
            }
        """)
        self.btn_focus.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_focus.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.btn_focus.clicked.connect(self._toggle_focus_mode)
        top.addWidget(self.btn_focus)

        layout.addLayout(top)

        # Bottom row: app name + duration
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        self.lbl_app = QLabel("--")
        self.lbl_app.setStyleSheet("color: #cccccc; font-size: 11px;")
        self.lbl_app.setFont(QFont("Microsoft YaHei", 9))
        bottom.addWidget(self.lbl_app)

        bottom.addStretch()

        self.lbl_duration = QLabel("0s")
        self.lbl_duration.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.lbl_duration.setFont(QFont("Microsoft YaHei", 9))
        bottom.addWidget(self.lbl_duration)

        layout.addLayout(bottom)

        # Ensure all child widgets pass mouse events up to ProjectIndicator,
        # except the focus button which needs to handle its own clicks.
        for child in self.findChildren(QWidget):
            if child is not self.btn_focus:
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _init_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)

    def _load_position(self):
        x, y = self.db.get_indicator_pos()
        if x == 0 and y == 0:
            # Default: top-right of primary screen
            screen = QApplication.primaryScreen().geometry()
            x = screen.width() - 200
            y = 40
        self.move(x, y)

    def _save_position(self):
        self.db.set_indicator_pos(self.x(), self.y())

    def _refresh(self):
        if not self.tracker._running:
            self.lbl_task.setText(trs("paused"))
            self.lbl_color.setStyleSheet("background-color: #9E9E9E; border-radius: 4px;")
            self.lbl_app.setText("--")
            self.lbl_duration.setText("")
            self._update_focus_ui()
            return

        summary = self.tracker.get_current_segment_summary()
        task_id = summary.get('task_id')
        app = summary.get('app_name', '--')
        window_title = summary.get('window_title', '')
        is_active = summary.get('is_active', False)
        session_sec = summary.get('session_seconds', 0)

        # Resolve task name & color
        if task_id:
            task = self.db.get_task_by_id(task_id)
            if task:
                task_name = task.name
                color = task.color or '#4CAF50'
            else:
                task_name = trs("unclassified")
                color = '#9E9E9E'
        else:
            task_name = trs("unclassified")
            color = '#9E9E9E'

        # Focus mode prefix
        if self.tracker.is_focus_mode():
            task_name = f"🎯 {task_name}"

        self.lbl_task.setText(task_name)
        self.lbl_color.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        self._update_focus_ui()

        # Show app name + window title snippet
        app_display = app if is_active else trs("idle")
        if window_title and is_active:
            # Extract a short meaningful snippet from title
            snippet = self._extract_snippet(app, window_title)
            if snippet:
                app_display = f"{app} | {snippet}"
        self.lbl_app.setText(app_display)
        self.lbl_duration.setText(self._fmt_duration(session_sec) if is_active else "")

    @staticmethod
    def _extract_snippet(app_name: str, title: str) -> str:
        """Extract a short meaningful snippet from window title."""
        if not title:
            return ""
        # VS Code: "file.py - Project - Visual Studio Code" → "Project"
        if app_name and 'code' in app_name.lower():
            import re
            m = re.search(r'\s-\s(.+?)\s-\sVisual Studio Code', title)
            if m:
                return m.group(1).strip()[:20]
        # WPS: "文件名.docx - WPS Office" → "文件名.docx"
        if app_name and 'wps' in app_name.lower():
            import re
            m = re.search(r'^(.+?)\s-\sWPS', title)
            if m:
                return m.group(1).strip()[:20]
        # Edge: use first part of title before common separators
        if app_name and 'edge' in app_name.lower():
            parts = title.split(' - ')
            if parts:
                return parts[0].strip()[:25]
        # Generic: first 20 chars
        return title.strip()[:20]

    @staticmethod
    def _fmt_duration(sec: int) -> str:
        if sec < 60:
            return f"{sec}s"
        return f"{sec // 60}m{sec % 60}s"

    # ------------------------------------------------------------------
    # Mouse events for dragging
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.tracker.pause_polling()
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.tracker.pause_polling()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            self._save_position()
            self.tracker.resume_polling()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            self.tracker.resume_polling()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_task_picker()
        else:
            event.ignore()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #555;
            }
        """)

        # Focus mode toggle (checkable)
        focus_action = QAction(f"🎯 {trs('focus_mode')}", self)
        focus_action.setCheckable(True)
        focus_action.setChecked(self.tracker.is_focus_mode())
        focus_action.triggered.connect(self._toggle_focus_mode)
        menu.addAction(focus_action)

        menu.addSeparator()

        # Task list
        tasks = self.db.get_all_tasks()
        for task in tasks:
            action = QAction(f"● {task.name}", self)
            action.triggered.connect(lambda checked, tid=task.id: self._set_task(tid))
            menu.addAction(action)

        menu.addSeparator()

        action_none = QAction(f"🚫 {trs('unclassified')}", self)
        action_none.triggered.connect(lambda: self._set_task(-1))
        menu.addAction(action_none)

        menu.addSeparator()

        action_show = QAction(f"🏠 {trs('open_main_window')}", self)
        action_show.triggered.connect(self.show_main_window.emit)
        menu.addAction(action_show)

        menu.exec(pos)

    def _retranslate_ui(self):
        # Labels are refreshed dynamically by _refresh()
        pass

    def _set_task(self, task_id: int):
        real_id = None if task_id == -1 else task_id
        self.tracker.set_current_task(real_id)
        self.task_changed.emit(task_id)
        self._refresh()

    def _toggle_focus_mode(self):
        new_state = not self.tracker.is_focus_mode()
        self.tracker.set_focus_mode(new_state)
        self._refresh()

    def _update_focus_ui(self):
        """Update focus button and container border based on focus mode state."""
        if self.tracker.is_focus_mode():
            self.btn_focus.setText("🎯")
            self.btn_focus.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 152, 0, 0.3);
                    border: 1px solid #FF9800;
                    border-radius: 4px;
                    font-size: 12px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 152, 0, 0.5);
                }
            """)
            self.container.setStyleSheet("""
                QWidget {
                    background-color: rgba(50, 50, 50, 220);
                    border-radius: 10px;
                    border: 1px solid #FF9800;
                }
            """)
        else:
            self.btn_focus.setText("🎯")
            self.btn_focus.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    font-size: 12px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.15);
                    border-radius: 4px;
                }
            """)
            self.container.setStyleSheet("""
                QWidget {
                    background-color: rgba(50, 50, 50, 220);
                    border-radius: 10px;
                }
            """)

    def _show_task_picker(self):
        tasks = self.db.get_all_tasks()
        current = self.tracker.get_current_segment_summary().get('task_id')
        dialog = _TaskPickerDialog(tasks, current, self)
        dialog.task_picked.connect(self._set_task)
        dialog.exec()
