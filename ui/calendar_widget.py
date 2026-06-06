"""
Calendar page with month view and quadrant planning dialog.
"""

from datetime import date
from calendar import monthcalendar

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QFrame, QDialog, QLineEdit,
    QCheckBox, QMessageBox, QSizePolicy, QScrollArea, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QAction

from core.database import Database
from utils.i18n import trs, tr_quadrant_name, current_lang


EVENT_PRESET_COLORS = [
    ("#e74c3c", "red"), ("#f39c12", "orange"), ("#f1c40f", "yellow"),
    ("#2ecc71", "green"), ("#3498db", "blue"), ("#9b59b6", "purple"),
    ("#e91e63", "pink"), ("#00bcd4", "cyan"),
]



class QuadrantPlannerDialog(QDialog):
    """Dialog for planning quadrant tasks and calendar events for a specific date."""

    events_changed = pyqtSignal()

    def __init__(self, db: Database, date_str: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.date_str = date_str
        self.setWindowTitle(f"{trs('quadrant_plan')} - {date_str}")
        self.setMinimumSize(520, 560)
        self._build_ui()
        self._load_tasks()
        self._load_events()

    # ------------------------------------------------------------------
    # UI builders
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QLabel(f"📅 {self.date_str} {trs('quadrant_plan')}")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #4a3f35;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # --- Quadrant tasks ---
        self.quadrants = self.db.get_quadrants()
        self.task_widgets = {}
        self._quadrant_task_layouts = {}

        for idx, q in enumerate(self.quadrants):
            base = QColor(q.color)
            bg_rgba = f"rgba({base.red()}, {base.green()}, {base.blue()}, 40)"
            border_rgba = f"rgba({base.red()}, {base.green()}, {base.blue()}, 130)"
            q_frame = QFrame()
            q_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_rgba};
                    border-radius: 8px;
                    border: 1px solid {border_rgba};
                }}
            """)
            q_layout = QVBoxLayout(q_frame)
            q_layout.setContentsMargins(10, 10, 10, 10)
            q_layout.setSpacing(6)

            q_title = QLabel(f"{tr_quadrant_name(q.name)} ({q.start_time[:5]} - {q.end_time[:5]})")
            q_title.setStyleSheet(f"font-weight: bold; color: #7a6f65;")
            q_layout.addWidget(q_title)

            tasks_layout = QVBoxLayout()
            tasks_layout.setSpacing(4)
            self.task_widgets[q.id] = []
            self._quadrant_task_layouts[q.id] = tasks_layout
            q_layout.addLayout(tasks_layout)

            # Add task button
            add_btn = QPushButton(trs("add_task"))
            add_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #5B8DB8;
                    border: 1px dashed #5B8DB8;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #5B8DB8;
                    color: white;
                    border-style: solid;
                }
            """)
            add_btn.clicked.connect(lambda checked, qid=q.id: self._on_add_quadrant_task(qid))
            q_layout.addWidget(add_btn)

            content_layout.addWidget(q_frame)

        # --- Calendar event markers ---
        event_frame = QFrame()
        event_frame.setStyleSheet("""
            QFrame {
                background-color: #faf8f5;
                border-radius: 8px;
                border: 1px solid #e8e0d8;
            }
        """)
        event_layout = QVBoxLayout(event_frame)
        event_layout.setContentsMargins(10, 10, 10, 10)
        event_layout.setSpacing(8)

        ev_title = QLabel(f"📌 {trs('calendar_markers')}")
        ev_title.setStyleSheet("font-weight: bold; color: #7a6f65;")
        event_layout.addWidget(ev_title)

        self.events_list_layout = QVBoxLayout()
        self.events_list_layout.setSpacing(6)
        event_layout.addLayout(self.events_list_layout)

        # Add new event row
        add_row = QHBoxLayout()
        add_row.setSpacing(6)

        self.event_input = QLineEdit()
        self.event_input.setPlaceholderText(trs("enter_marker_placeholder"))
        self.event_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px 8px;
                background: white;
            }
        """)

        self._event_color_btns = []
        self._selected_event_color = EVENT_PRESET_COLORS[0][0]
        for color, name in EVENT_PRESET_COLORS:
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setToolTip(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 2px solid {'#333' if color == self._selected_event_color else 'transparent'};
                    border-radius: 10px;
                }}
                QPushButton:hover {{
                    border: 2px solid #555;
                }}
            """)
            btn.clicked.connect(lambda checked, c=color: self._on_event_color_clicked(c))
            add_row.addWidget(btn)
            self._event_color_btns.append((btn, color))

        add_btn = QPushButton(trs("add"))
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #5B8DB8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a7aa5; }
        """)
        add_btn.clicked.connect(self._on_add_event)

        add_row.addWidget(self.event_input, 1)
        add_row.addWidget(add_btn)
        event_layout.addLayout(add_row)

        content_layout.addWidget(event_frame)
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(trs("save"))
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #5B8DB8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a7aa5; }
        """)
        save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton(trs("cancel"))
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #ddd;
                color: #555;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
            }
            QPushButton:hover { background-color: #ccc; }
        """)
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # Event color picker
    # ------------------------------------------------------------------

    def _on_event_color_clicked(self, color: str):
        self._selected_event_color = color
        for btn, c in self._event_color_btns:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c};
                    border: 2px solid {'#333' if c == color else 'transparent'};
                    border-radius: 10px;
                }}
                QPushButton:hover {{
                    border: 2px solid #555;
                }}
            """)

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _add_task_row(self, qid: int, content: str = "", completed: bool = False, task_id=None):
        tasks_layout = self._quadrant_task_layouts[qid]
        row = QHBoxLayout()
        row.setSpacing(6)
        cb = QCheckBox()
        cb.setFixedSize(18, 18)
        cb.setChecked(completed)
        le = QLineEdit()
        le.setPlaceholderText("输入任务...")
        le.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px 8px;
                background: white;
            }
        """)
        le.setText(content)
        le.setProperty("task_id", task_id)
        row.addWidget(cb)
        row.addWidget(le, 1)
        tasks_layout.addLayout(row)
        self.task_widgets[qid].append((cb, le))

    def _load_tasks(self):
        tasks = self.db.get_all_quadrant_tasks(self.date_str)
        for qid, widgets in self.task_widgets.items():
            layout = self._quadrant_task_layouts[qid]
            while layout.count():
                item = layout.takeAt(0)
                if item.layout():
                    while item.layout().count():
                        sub = item.layout().takeAt(0)
                        if sub.widget():
                            sub.widget().deleteLater()
                    item.layout().deleteLater()
                elif item.widget():
                    item.widget().deleteLater()
            widgets.clear()

            q_tasks = [t for t in tasks if t.quadrant_id == qid]
            for t in q_tasks:
                self._add_task_row(qid, t.content, t.completed, t.id)

    def _load_events(self):
        """Load calendar events into the UI."""
        self._events_data = self.db.get_calendar_events(self.date_str)
        # Clear existing rows thoroughly
        while self.events_list_layout.count():
            item = self.events_list_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget:
                widget.deleteLater()
            layout = item.layout()
            if layout:
                while layout.count():
                    sub = layout.takeAt(0)
                    if sub and sub.widget():
                        sub.widget().deleteLater()
                layout.deleteLater()

        for ev in self._events_data:
            ev_id, ev_date, ev_color, ev_label, _ = ev
            row = QHBoxLayout()
            row.setSpacing(6)

            # Color picker button
            color_btn = QPushButton()
            color_btn.setFixedSize(18, 18)
            color_btn.setToolTip(trs("pick_color"))
            color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ev_color};
                    border: 1px solid #888;
                    border-radius: 9px;
                }}
                QPushButton:hover {{
                    border: 2px solid #333;
                }}
            """)
            color_btn.setProperty("event_id", ev_id)
            color_btn.setProperty("label", ev_label)
            color_btn.clicked.connect(self._on_pick_event_color)

            lbl = QLabel(ev_label)
            lbl.setStyleSheet("color: #4a3f35; font-size: 13px;")
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

            del_btn = QPushButton("Del")
            del_btn.setFixedSize(40, 20)
            del_btn.setToolTip(trs("delete_marker"))
            del_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #c0392b;
                    border: 1px solid #c0392b;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 0px 2px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                    color: white;
                }
            """)
            del_btn.setProperty("event_id", ev_id)
            del_btn.clicked.connect(self._on_delete_event_btn)

            row.addWidget(color_btn)
            row.addWidget(lbl, 1)
            row.addWidget(del_btn)
            self.events_list_layout.addLayout(row)

    def _on_add_event(self):
        label = self.event_input.text().strip()
        if not label:
            return
        self.db.add_calendar_event(self.date_str, self._selected_event_color, label)
        self.event_input.clear()
        self._load_events()
        self.events_changed.emit()

    def _on_pick_event_color(self, checked=False):
        """Show a color picker menu for an existing event."""
        btn = self.sender()
        if not btn:
            return
        event_id = btn.property("event_id")
        label = btn.property("label")
        if event_id is None or not label:
            return
        menu = QMenu(self)
        for color, name in EVENT_PRESET_COLORS:
            action = QAction(self)
            action.setIcon(self._make_color_icon(color))
            action.setToolTip(name)
            action.setData((event_id, color, label))
            action.triggered.connect(self._on_color_action_triggered)
            menu.addAction(action)
        menu.exec(self.cursor().pos())

    def _make_color_icon(self, color: str):
        from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon
        from PyQt6.QtCore import Qt
        pixmap = QPixmap(18, 18)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(1, 1, 16, 16)
        painter.end()
        return QIcon(pixmap)

    def _on_color_action_triggered(self, checked=False):
        action = self.sender()
        if action and action.data():
            event_id, color, label = action.data()
            self._set_event_color(event_id, color, label)

    def _on_delete_event_btn(self, checked=False):
        btn = self.sender()
        if btn:
            event_id = btn.property("event_id")
            if event_id is not None:
                self._on_delete_event(event_id)

    def _set_event_color(self, event_id: int, color: str, label: str):
        self.db.update_calendar_event(event_id, color, label)
        self._load_events()
        self.events_changed.emit()

    def _on_delete_event(self, event_id: int):
        self.db.delete_calendar_event(event_id)
        self._load_events()
        self.events_changed.emit()

    def _on_add_quadrant_task(self, qid: int):
        """Add a new blank task row to the UI (not saved until Save is clicked)."""
        self._add_task_row(qid)

    def _save(self):
        # Save quadrant tasks
        for qid, widgets in self.task_widgets.items():
            for cb, le in widgets:
                content = le.text().strip()
                completed = 1 if cb.isChecked() else 0
                task_id = le.property("task_id")
                if content:
                    if task_id:
                        self.db.update_quadrant_task(task_id, content, completed)
                    else:
                        self.db.add_quadrant_task(self.date_str, qid, content)
                elif task_id:
                    self.db.delete_quadrant_task(task_id)
        self.accept()


# ====================================================================
# Calendar Widget
# ====================================================================

class CalendarWidget(QWidget):
    date_selected = pyqtSignal(str)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_year = date.today().year
        self.current_month = date.today().month
        self._build_ui()
        self._render_calendar()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header with month navigation
        header = QHBoxLayout()
        header.setSpacing(12)

        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.setStyleSheet(self._nav_btn_style())
        self.prev_btn.clicked.connect(self._prev_month)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.setStyleSheet(self._nav_btn_style())
        self.next_btn.clicked.connect(self._next_month)

        self.month_label = QLabel()
        self.month_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #4a3f35;")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.today_btn = QPushButton()
        self.today_btn.setStyleSheet("""
            QPushButton {
                background-color: #5B8DB8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a7aa5; }
        """)
        self.today_btn.clicked.connect(self._go_today)

        header.addWidget(self.prev_btn)
        header.addWidget(self.month_label, 1)
        header.addWidget(self.today_btn)
        header.addWidget(self.next_btn)
        layout.addLayout(header)

        # Day names header
        days_grid = QGridLayout()
        days_grid.setSpacing(4)
        day_names = [trs("monday"), trs("tuesday"), trs("wednesday"),
                     trs("thursday"), trs("friday"), trs("saturday"), trs("sunday")]
        for i, name in enumerate(day_names):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-weight: bold; color: #7a6f65; padding: 8px;")
            days_grid.addWidget(lbl, 0, i)
        layout.addLayout(days_grid)

        # Calendar days grid
        self.days_layout = QGridLayout()
        self.days_layout.setSpacing(4)
        layout.addLayout(self.days_layout, 1)

        self._retranslate_ui()

    def _retranslate_ui(self):
        self.today_btn.setText(trs("today_btn"))
        self._update_month_label()

    def _nav_btn_style(self):
        return """
            QPushButton {
                background-color: #E8D5C4;
                color: #5a4f45;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #D4C4B5; }
        """

    def _render_calendar(self):
        # Clear existing widgets
        while self.days_layout.count():
            item = self.days_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._update_month_label()

        weeks = monthcalendar(self.current_year, self.current_month)
        today = date.today()

        # Pre-load all events for this month
        month_events = self.db.get_calendar_events_by_month(self.current_year, self.current_month)
        date_to_events = {}
        for ev in month_events:
            ev_date = ev[1]  # date column
            if ev_date not in date_to_events:
                date_to_events[ev_date] = []
            date_to_events[ev_date].append(ev)

        for week_idx, week in enumerate(weeks):
            for day_idx, day in enumerate(week):
                if day == 0:
                    empty = QLabel()
                    empty.setMinimumSize(80, 80)
                    self.days_layout.addWidget(empty, week_idx, day_idx)
                    continue

                day_date = date(self.current_year, self.current_month, day)
                day_str = day_date.isoformat()

                # Style
                is_today = day_date == today
                is_weekend = day_idx >= 5
                bg_color = "#FFF8F0" if not is_today else "#5B8DB8"
                text_color = "white" if is_today else ("#e74c3c" if is_weekend else "#4a3f35")
                border = "2px solid #5B8DB8" if is_today else "1px solid #E8D5C4"

                events = date_to_events.get(day_str, [])
                task_count = len(self.db.get_all_quadrant_tasks(day_str))

                # Use QPushButton as a container with layout for colored event bars
                cell = QPushButton()
                cell.setMinimumSize(80, 80)
                cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                cell.setFlat(True)
                cell.setCursor(Qt.CursorShape.PointingHandCursor)
                cell.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {bg_color};
                        color: {text_color};
                        border: {border};
                        border-radius: 8px;
                        text-align: top center;
                        padding-top: 6px;
                        font-size: 14px;
                        font-weight: {'bold' if is_today else 'normal'};
                    }}
                    QPushButton:hover {{
                        background-color: {'#4a7aa5' if is_today else '#F0E6D8'};
                    }}
                """)

                cell_layout = QVBoxLayout(cell)
                cell_layout.setContentsMargins(6, 6, 6, 6)
                cell_layout.setSpacing(3)

                # Day number label (transparent for mouse events)
                day_label = QLabel(str(day))
                day_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                day_label.setStyleSheet(f"color: {text_color}; font-size: 14px; font-weight: {'bold' if is_today else 'normal'}; background: transparent;")
                day_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
                cell_layout.addWidget(day_label)

                # Colored event bars
                for ev in events[:3]:
                    bar = QLabel(ev[3])
                    bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    bar.setStyleSheet(f"""
                        QLabel {{
                            background-color: {ev[2]};
                            color: white;
                            border-radius: 4px;
                            padding: 2px 6px;
                            font-size: 10px;
                        }}
                    """)
                    bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell_layout.addWidget(bar)

                if len(events) > 3:
                    more = QLabel(trs("more_events").format(len(events)))
                    more.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    more.setStyleSheet(f"color: {text_color}; font-size: 10px; background: transparent;")
                    more.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell_layout.addWidget(more)

                cell_layout.addStretch()

                # Tooltip with full details
                tooltip_parts = []
                if events:
                    tooltip_parts.append(trs("calendar_markers_tip"))
                    for ev in events:
                        tooltip_parts.append(f"  ● {ev[3]}")

                if tooltip_parts:
                    cell.setToolTip("\n".join(tooltip_parts))

                cell.clicked.connect(lambda checked, d=day_str: self._on_day_clicked(d))
                self.days_layout.addWidget(cell, week_idx, day_idx)

    def _update_month_label(self):
        if current_lang() == 'en':
            month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                           'July', 'August', 'September', 'October', 'November', 'December']
            self.month_label.setText(f"{self.current_year} {month_names[self.current_month]}")
        else:
            self.month_label.setText(f"{self.current_year}年 {self.current_month}月")

    def _on_day_clicked(self, day_str: str):
        dialog = QuadrantPlannerDialog(self.db, day_str, self)
        dialog.events_changed.connect(self._render_calendar)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._render_calendar()

    def _prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self._render_calendar()

    def _next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self._render_calendar()

    def _go_today(self):
        self.current_year = date.today().year
        self.current_month = date.today().month
        self._render_calendar()

    def refresh(self):
        self._render_calendar()
