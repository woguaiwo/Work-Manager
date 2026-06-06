"""
Timeline Container Widget
Wraps TimelineView in a scroll area with date navigation.
"""

from datetime import date, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal

from core.database import Database
from ui.timeline_view import TimelineView
from utils.i18n import trs


class TimelineContainer(QWidget):
    date_changed = pyqtSignal(str)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #f5f7fa;
                border-bottom: 1px solid #e8e8e8;
            }
            QPushButton {
                background-color: #5B8DB8;
                color: white;
                border: none;
                padding: 6px 14px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4A7BA8;
            }
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #37474f;
            }
            QDateEdit {
                padding: 4px 8px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(15, 10, 15, 10)

        self.btn_prev = QPushButton()
        self.btn_prev.clicked.connect(self._prev_day)

        self.btn_today = QPushButton()
        self.btn_today.clicked.connect(self._go_today)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.dateChanged.connect(self._on_date_changed)

        self.btn_next = QPushButton()
        self.btn_next.clicked.connect(self._next_day)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("color: #78909c; font-weight: normal;")

        toolbar_layout.addWidget(self.btn_prev)
        toolbar_layout.addWidget(self.btn_today)
        self.lbl_date = QLabel()
        toolbar_layout.addWidget(self.lbl_date)
        toolbar_layout.addWidget(self.date_edit)
        toolbar_layout.addWidget(self.btn_next)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.lbl_summary)

        layout.addWidget(toolbar)

        # Scroll area with TimelineView
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.timeline = TimelineView(self.db, parent=self)
        self.timeline.segment_changed.connect(self._update_summary)
        self.scroll.setWidget(self.timeline)

        layout.addWidget(self.scroll, 1)

        self._retranslate_ui()
        self._update_summary()

    def _retranslate_ui(self):
        self.btn_prev.setText(f"◀ {trs('prev_day')}")
        self.btn_today.setText(trs("today_btn"))
        self.btn_next.setText(f"{trs('next_day')} ▶")
        self.lbl_date.setText(trs("date_label"))

    def _on_date_changed(self, qdate: QDate):
        date_str = qdate.toString("yyyy-MM-dd")
        self.timeline.set_date(date_str)
        self.date_changed.emit(date_str)
        self._update_summary()

    def _prev_day(self):
        d = self.date_edit.date().addDays(-1)
        self.date_edit.setDate(d)

    def _next_day(self):
        d = self.date_edit.date().addDays(1)
        self.date_edit.setDate(d)

    def _go_today(self):
        self.date_edit.setDate(QDate.currentDate())

    def _update_summary(self):
        date_str = self.timeline.date_str
        total = self.db.get_daily_summary(date_str)
        from utils.helpers import format_duration_short
        self.lbl_summary.setText(trs("today_active").format(format_duration_short(total)))

    def set_date(self, date_str: str):
        qdate = QDate.fromString(date_str, "yyyy-MM-dd")
        if qdate.isValid():
            self.date_edit.setDate(qdate)

    def refresh(self):
        self.timeline.refresh()
        self._update_summary()
