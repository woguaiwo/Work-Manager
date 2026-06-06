"""
Focus Session Detail Dialog
Shows task breakdown and stats for a single focus session.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.database import Database, Task
from utils.focus_session import FocusSession
from utils.helpers import format_duration_short
from utils.i18n import trs


def _fmt_dur(seconds: int) -> str:
    """Format seconds with second-level precision."""
    if seconds < 60:
        return f"{seconds}s"
    m = seconds // 60
    s = seconds % 60
    if s == 0:
        return f"{m}m"
    return f"{m}m {s}s"


class FocusSessionDialog(QDialog):
    def __init__(self, session: FocusSession, tasks: dict[int, Task], parent=None):
        super().__init__(parent)
        self.session = session
        self.tasks = tasks
        self.setWindowTitle(trs("focus_session_detail"))
        self.setMinimumWidth(420)
        self.setMaximumWidth(480)
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f7fa;
            }
            QLabel {
                color: #37474f;
            }
            QPushButton {
                background-color: #5B8DB8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a7aa5;
            }
            QFrame {
                background-color: white;
                border-radius: 8px;
            }
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #e8e8e8;
                height: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                border-radius: 4px;
            }
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header: time range + total duration
        header = QFrame()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        header_layout.setSpacing(8)

        time_range = f"{self.session.start_time[:5]} – {self.session.end_time[:5]}"
        lbl_time = QLabel(time_range)
        lbl_time.setStyleSheet("font-size: 20px; font-weight: bold; color: #37474f;")
        lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(lbl_time)

        total_str = format_duration_short(self.session.total_seconds)
        lbl_total = QLabel(total_str)
        lbl_total.setStyleSheet("font-size: 32px; font-weight: bold; color: #5B8DB8;")
        lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(lbl_total)

        layout.addWidget(header)

        # Task breakdown
        task_frame = QFrame()
        task_layout = QVBoxLayout(task_frame)
        task_layout.setContentsMargins(16, 16, 16, 16)
        task_layout.setSpacing(12)

        lbl_breakdown = QLabel(trs("task_breakdown"))
        lbl_breakdown.setStyleSheet("font-size: 14px; font-weight: bold; color: #7a6f65;")
        task_layout.addWidget(lbl_breakdown)

        # Sort tasks by duration descending
        td = self.session.task_durations
        total = self.session.total_seconds
        sorted_tasks = sorted(td.items(), key=lambda x: -x[1])

        seg_counts = self.session.task_segment_counts
        for task_id, dur in sorted_tasks:
            pct = (dur / total * 100) if total > 0 else 0
            task_name = self._task_name(task_id)
            color = self._task_color(task_id)
            count = seg_counts.get(task_id, 1)
            mean_dur = dur // count if count > 0 else 0

            # Row 1: dot + name
            row1 = QHBoxLayout()
            row1.setSpacing(8)

            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 16px;")
            row1.addWidget(dot)

            info = QLabel(task_name)
            info.setStyleSheet("font-size: 13px; color: #37474f;")
            row1.addWidget(info, 1)

            avg_text = _fmt_dur(mean_dur)
            mean_label = QLabel(f"{trs('avg_seg')}: {avg_text}")
            mean_label.setStyleSheet("font-size: 11px; color: #90a4ae;")
            row1.addWidget(mean_label)

            task_layout.addLayout(row1)

            # Row 2: progress bar with total duration inside
            bar = QProgressBar()
            bar.setMaximum(100)
            bar.setValue(int(pct))
            bar.setFormat(f"  {_fmt_dur(dur)}  ")
            bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    border-radius: 4px;
                    background-color: #e8e8e8;
                    height: 20px;
                    text-align: center;
                    color: white;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 4px;
                }}
            """)
            task_layout.addWidget(bar)

        task_layout.addStretch()
        layout.addWidget(task_frame)

        # Stats footer
        stats = QFrame()
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(16, 12, 16, 12)
        stats_layout.setSpacing(20)

        lbl_segments = QLabel(f"{trs('segments')}: {self.session.segment_count}")
        lbl_segments.setStyleSheet("font-size: 13px; color: #78909c;")
        stats_layout.addWidget(lbl_segments)

        mean_str = format_duration_short(self.session.mean_segment_duration)
        lbl_mean = QLabel(f"{trs('mean_segment')}: {mean_str}")
        lbl_mean.setStyleSheet("font-size: 13px; color: #78909c;")
        stats_layout.addWidget(lbl_mean)

        stats_layout.addStretch()
        layout.addWidget(stats)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton(trs("close"))
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _task_name(self, task_id: Optional[int]) -> str:
        if task_id is None:
            return trs("unclassified")
        task = self.tasks.get(task_id)
        return task.name if task else trs("unclassified")

    def _task_color(self, task_id: Optional[int]) -> str:
        if task_id is None:
            return "#9E9E9E"
        task = self.tasks.get(task_id)
        return task.color if task else "#9E9E9E"
