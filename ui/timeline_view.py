"""
Daily Timeline View
A custom-painted widget showing a 24-hour vertical timeline.
Users can drag to create blocks, drag to resize/move, double-click to edit.
Quadrant time-management bands with draggable boundaries and task checklists.
"""

from datetime import date, datetime
from typing import Optional, List, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTextEdit, QPushButton, QDialog, QMessageBox, QMenu,
    QScrollArea, QFrame, QSizePolicy, QTimeEdit, QLineEdit
)
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal, QTime
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QFontMetrics

from core.database import Database, ActivitySegment, Task, Quadrant, QuadrantTask
from utils.helpers import time_to_minutes, minutes_to_time, snap_to_grid, duration_between, get_app_display_name, format_duration_short
from utils.i18n import trs
from utils.focus_session import FocusSession, build_focus_sessions
from ui.focus_session_dialog import FocusSessionDialog


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOUR_HEIGHT = 60          # pixels per hour
RULER_WIDTH = 55          # left ruler width
DAY_MINUTES = 24 * 60     # 1440
BLOCK_MARGIN = 8          # horizontal margin inside ruler area
EDGE_GRAB_SIZE = 6        # pixels for resize grab area
SNAP_GRID = 5             # minutes
MIN_CREATE_DURATION = 5   # minimum minutes to create a block by dragging
COLUMN_HEADER_HEIGHT = 28 # height of column header band
QUADRANT_ALPHA = 100      # background band transparency (0-255)
TASK_ROW_HEIGHT = 18      # height of one task row in quadrant panel
CHECKBOX_SIZE = 12        # drawn checkbox size
# Right-hand columns configuration. Append dicts to add more columns.
COLUMNS = [
    {'key': 'description', 'title': 'notes', 'width': 220},
    {'key': 'quadrant_tasks', 'title': 'quadrant_todo', 'width': 240},
]


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class BlockEditDialog(QDialog):
    def __init__(self, db: Database, segment: Optional[ActivitySegment] = None,
                 default_start: str = "09:00", default_end: str = "09:30",
                 parent=None):
        super().__init__(parent)
        self.db = db
        self.segment = segment
        self.setWindowTitle(trs("edit_time_block") if segment else trs("new_time_block"))
        self.setMinimumWidth(350)
        self._init_ui(default_start, default_end)

    def _init_ui(self, default_start: str, default_end: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Time range
        time_layout = QHBoxLayout()
        self.time_start = QTimeEdit()
        self.time_end = QTimeEdit()
        for te in (self.time_start, self.time_end):
            te.setDisplayFormat("HH:mm")
            te.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
            te.setStyleSheet("""
                QTimeEdit {
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 6px 10px;
                    background: white;
                    font-size: 14px;
                }
                QTimeEdit:focus {
                    border: 1px solid #2196F3;
                }
            """)

        def _to_qtime(t_str: str) -> QTime:
            h, m = int(t_str[:2]), int(t_str[3:5])
            return QTime(h, m)

        self.time_start.setTime(_to_qtime(default_start))
        self.time_end.setTime(_to_qtime(default_end))
        if self.segment:
            self.time_start.setTime(_to_qtime(self.segment.start_time))
            self.time_end.setTime(_to_qtime(self.segment.end_time))

        time_layout.addWidget(QLabel(trs("start")))
        time_layout.addWidget(self.time_start)
        time_layout.addWidget(QLabel(trs("end")))
        time_layout.addWidget(self.time_end)
        layout.addLayout(time_layout)

        # Task
        task_layout = QHBoxLayout()
        self.combo_task = QComboBox()
        self.combo_task.addItem(trs("unclassified_task"), None)
        for t in self.db.get_all_tasks():
            self.combo_task.addItem(t.name, t.id)
        if self.segment and self.segment.task_id:
            idx = self.combo_task.findData(self.segment.task_id)
            if idx >= 0:
                self.combo_task.setCurrentIndex(idx)
        task_layout.addWidget(QLabel("任务:"))
        task_layout.addWidget(self.combo_task, 1)
        layout.addLayout(task_layout)

        # Description (Notes) - multi-line
        self.input_desc = QTextEdit()
        self.input_desc.setPlaceholderText(trs("write_something"))
        self.input_desc.setMinimumHeight(80)
        self.input_desc.setStyleSheet("""
            QTextEdit {
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 8px;
                background: white;
                font-size: 13px;
            }
            QTextEdit:focus {
                border: 1px solid #2196F3;
            }
        """)
        if self.segment:
            self.input_desc.setPlainText(self.segment.description or '')
        layout.addWidget(self.input_desc)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton(trs("save"))
        self.btn_save.setStyleSheet("background-color: #27ae60; color: white; padding: 6px 16px;")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = QPushButton(trs("cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def _on_save(self):
        start = self.time_start.time().toString("HH:mm") + ":00"
        end = self.time_end.time().toString("HH:mm") + ":00"
        if time_to_minutes(end) <= time_to_minutes(start):
            QMessageBox.warning(self, trs("tip"), trs("end_time_must_be_after_start"))
            return
        self.accept()

    def get_data(self):
        return {
            'start_time': self.time_start.time().toString("HH:mm") + ":00",
            'end_time': self.time_end.time().toString("HH:mm") + ":00",
            'task_id': self.combo_task.currentData(),
            'description': self.input_desc.toPlainText().strip(),
        }


class QuickEditDialog(QDialog):
    """Inline dialog for editing segment description (Notes column)."""

    def __init__(self, initial_text: str = '', parent=None):
        super().__init__(parent)
        self.setWindowTitle(trs("edit_notes"))
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self.line = QLineEdit(initial_text)
        self.line.setStyleSheet("""
            QLineEdit {
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #2196F3;
            }
        """)
        self.line.returnPressed.connect(self.accept)
        layout.addWidget(self.line)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_save = QPushButton(trs("save"))
        btn_save.setStyleSheet("background-color: #27ae60; color: white; padding: 6px 16px;")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton(trs("cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.line.setFocus()
        self.line.selectAll()

    def get_text(self) -> str:
        return self.line.text().strip()


class QuickAddDialog(QDialog):
    """Quick-add dialog for quadrant tasks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(trs("add_quadrant_task"))
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self.line = QLineEdit()
        self.line.setPlaceholderText(trs("enter_task_content"))
        self.line.setStyleSheet("""
            QLineEdit {
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #2196F3;
            }
        """)
        self.line.returnPressed.connect(self.accept)
        layout.addWidget(self.line)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_save = QPushButton(trs("add_task_short"))
        btn_save.setStyleSheet("background-color: #27ae60; color: white; padding: 6px 16px;")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton(trs("cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.line.setFocus()

    def get_text(self) -> str:
        return self.line.text().strip()


# ---------------------------------------------------------------------------
# Timeline View Widget
# ---------------------------------------------------------------------------

class TimelineView(QWidget):
    segment_changed = pyqtSignal()

    def __init__(self, db: Database, date_str: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.date_str = date_str or date.today().isoformat()
        self.tasks: dict[int, Task] = {}
        self.segments: List[ActivitySegment] = []
        self.quadrants: List[Quadrant] = []
        self.quadrant_tasks: dict[int, List[QuadrantTask]] = {}

        # Column widths (loaded from settings, mutable)
        self.column_widths: dict[str, int] = self._load_column_widths()

        # Drag / create state
        self._drag_mode: Optional[str] = None
        self._drag_seg: Optional[ActivitySegment] = None
        self._drag_start_y = 0
        self._drag_orig_start_min = 0
        self._drag_orig_end_min = 0

        # Quadrant boundary drag state
        self._drag_quadrant: Optional[Quadrant] = None
        self._drag_boundary_edge: Optional[str] = None
        self._drag_orig_time_min = 0

        # Column resize drag state
        self._drag_col_key: Optional[str] = None
        self._drag_start_x = 0
        self._drag_orig_width = 0

        # Create-preview state (for drag-to-create)
        self._create_preview_seg: Optional[ActivitySegment] = None

        # Selected segment highlight
        self._selected_seg_id: Optional[int] = None

        # Active inline editor for quadrant tasks
        self._active_editor: Optional[QLineEdit] = None

        # Column order (for drag-to-reorder)
        self.column_order: List[str] = self._load_column_order()

        # Right-click box selection state
        self._selection_start_pos: Optional[QPoint] = None
        self._selection_rect: Optional[QRect] = None
        self._selected_seg_ids: set = set()

        # Column reorder drag state
        self._drag_reorder_col_idx: Optional[int] = None
        self._drag_reorder_target_idx: Optional[int] = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(600 + self._column_area_width())
        self.setFixedHeight(COLUMN_HEADER_HEIGHT + DAY_MINUTES * HOUR_HEIGHT // 60 + 20)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._load_data()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self):
        from datetime import datetime, timedelta
        self.tasks = {t.id: t for t in self.db.get_all_tasks()}
        self.segments = self.db.get_segments_by_date(self.date_str)
        self.sessions = build_focus_sessions(self.segments)
        self.quadrants = self.db.get_quadrants()
        self.quadrant_tasks = {}
        self._overnight_yesterday_tasks = {}
        yesterday = (datetime.strptime(self.date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        for q in self.quadrants:
            self.quadrant_tasks[q.id] = self.db.get_quadrant_tasks(self.date_str, q.id)
            if q.start_time > q.end_time:
                self._overnight_yesterday_tasks[q.id] = self.db.get_quadrant_tasks(yesterday, q.id)
        self.update()

    def set_date(self, date_str: str):
        self.date_str = date_str
        self._load_data()

    def refresh(self):
        self._load_data()

    # ------------------------------------------------------------------
    # Coordinate math
    # ------------------------------------------------------------------

    def _content_top(self) -> int:
        return COLUMN_HEADER_HEIGHT + 4

    def _minutes_to_y(self, minutes: int) -> int:
        return self._content_top() + int(minutes * HOUR_HEIGHT / 60)

    def _y_to_minutes(self, y: int) -> int:
        raw = int((y - self._content_top()) * 60 / HOUR_HEIGHT)
        return max(0, min(raw, DAY_MINUTES - 1))

    def _ordered_columns(self) -> List[dict]:
        """Return COLUMNS sorted by self.column_order."""
        key_to_col = {c['key']: c for c in COLUMNS}
        return [key_to_col[k] for k in self.column_order if k in key_to_col]

    def _column_area_width(self) -> int:
        return sum(self.column_widths.get(c['key'], c.get('width', 220)) for c in self._ordered_columns())

    def _col_left(self, col_key: str) -> int:
        """Return the x coordinate of the left edge of a column."""
        col_w = self._column_area_width()
        axis_right = self.width() - col_w
        x_off = axis_right
        for col in self._ordered_columns():
            if col['key'] == col_key:
                return x_off
            x_off += self.column_widths.get(col['key'], col.get('width', 220))
        return x_off

    def _load_column_widths(self) -> dict[str, int]:
        import json
        defaults = {c['key']: c.get('width', 220) for c in COLUMNS}
        saved = self.db.get_setting('column_widths')
        if saved:
            try:
                loaded = json.loads(saved)
                return {**defaults, **loaded}
            except Exception:
                pass
        return defaults

    def _save_column_widths(self):
        import json
        self.db.set_setting('column_widths', json.dumps(self.column_widths))

    def _load_column_order(self) -> List[str]:
        import json
        default = [c['key'] for c in COLUMNS]
        saved = self.db.get_setting('column_order')
        if saved:
            try:
                loaded = json.loads(saved)
                if set(loaded) == set(default):
                    return loaded
            except Exception:
                pass
        return default

    def _save_column_order(self):
        import json
        self.db.set_setting('column_order', json.dumps(self.column_order))

    def _quadrant_y_ranges(self, q: Quadrant) -> List[Tuple[int, int]]:
        """Return list of (y_start, y_end) for drawing this quadrant.
        Handles overnight wrap (e.g. 22:00 -> 01:00)."""
        start_min = time_to_minutes(q.start_time)
        end_min = time_to_minutes(q.end_time)
        if start_min <= end_min:
            return [(self._minutes_to_y(start_min), self._minutes_to_y(end_min))]
        else:
            return [
                (self._minutes_to_y(start_min), self._minutes_to_y(DAY_MINUTES)),
                (self._minutes_to_y(0), self._minutes_to_y(end_min)),
            ]

    def _quadrant_task_ranges(self, q: Quadrant) -> List[Tuple[int, int, str]]:
        """Return (y_start, y_end, date_str) for each quadrant range.
        Overnight quadrants: first range (22:00-24:00) uses self.date_str,
        second range (00:00-07:00) uses yesterday's date."""
        base = self._quadrant_y_ranges(q)
        if len(base) == 1:
            return [(base[0][0], base[0][1], self.date_str)]
        # Overnight
        from datetime import datetime, timedelta
        yesterday = (datetime.strptime(self.date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        return [
            (base[0][0], base[0][1], self.date_str),   # 22:00-24:00 → today
            (base[1][0], base[1][1], yesterday),        # 00:00-07:00 → yesterday
        ]

    def _assign_lanes(self) -> dict[int, int]:
        """Assign each segment to a horizontal lane so overlapping segments don't stack.
        Returns {segment_id: lane_index}.
        """
        if not self.segments:
            return {}
        # Sort by start time
        sorted_segs = sorted(self.segments, key=lambda s: time_to_minutes(s.start_time))
        lanes: list[list[ActivitySegment]] = []
        mapping: dict[int, int] = {}
        for seg in sorted_segs:
            seg_start = time_to_minutes(seg.start_time)
            seg_end = time_to_minutes(seg.end_time)
            placed = False
            for idx, lane in enumerate(lanes):
                last = lane[-1]
                last_end = time_to_minutes(last.end_time)
                if last_end <= seg_start:
                    lane.append(seg)
                    mapping[seg.id] = idx
                    placed = True
                    break
            if not placed:
                lanes.append([seg])
                mapping[seg.id] = len(lanes) - 1
        return mapping

    def _block_rect(self, seg: ActivitySegment, lane_map: dict[int, int] = None) -> QRect:
        start_min = time_to_minutes(seg.start_time)
        end_min = time_to_minutes(seg.end_time)
        y1 = self._minutes_to_y(start_min)
        y2 = self._minutes_to_y(end_min)
        col_w = self._column_area_width()
        axis_right = self.width() - col_w
        axis_width = axis_right - RULER_WIDTH - BLOCK_MARGIN * 2
        lane_idx = 0
        if lane_map is not None:
            lane_idx = lane_map.get(seg.id, 0)
        num_lanes = max(1, max(lane_map.values()) + 1) if lane_map else 1
        lane_width = axis_width // max(1, num_lanes)
        x = RULER_WIDTH + BLOCK_MARGIN + lane_idx * lane_width + 2
        w = max(4, lane_width - 4)
        return QRect(x, y1, w, max(4, y2 - y1))

    def _column_rect(self, seg: ActivitySegment, col_idx: int) -> QRect:
        """Return the rectangle for a given segment's cell in column col_idx."""
        ordered = self._ordered_columns()
        start_min = time_to_minutes(seg.start_time)
        end_min = time_to_minutes(seg.end_time)
        y1 = self._minutes_to_y(start_min)
        y2 = self._minutes_to_y(end_min)
        x_offset = self.width() - self._column_area_width()
        for i in range(col_idx):
            x_offset += self.column_widths.get(ordered[i]['key'], 220)
        return QRect(x_offset, y1, self.column_widths.get(ordered[col_idx]['key'], 220), max(4, y2 - y1))

    def _hit_test_col_border(self, pos: QPoint) -> Optional[Tuple[str, bool]]:
        """Return (col_key, is_left_edge) if near a column border.
        is_left_edge=True means the left edge of the first column (axis_right).
        is_left_edge=False means the right edge of a column."""
        col_w = self._column_area_width()
        axis_right = self.width() - col_w
        x_off = axis_right

        ordered = self._ordered_columns()
        # Left edge of first column
        if ordered:
            first_key = ordered[0]['key']
            if abs(pos.x() - x_off) <= EDGE_GRAB_SIZE:
                return (first_key, True)

        # Right edge of each column
        for col in ordered:
            x_off += self.column_widths.get(col['key'], col.get('width', 220))
            if abs(pos.x() - x_off) <= EDGE_GRAB_SIZE:
                return (col['key'], False)
        return None

    def _hit_test_col_header(self, pos: QPoint) -> Optional[int]:
        """Return column index if pos is inside a column header area."""
        if pos.y() > COLUMN_HEADER_HEIGHT:
            return None
        col_w = self._column_area_width()
        axis_right = self.width() - col_w
        if pos.x() < axis_right:
            return None
        x_off = axis_right
        for idx, col in enumerate(self._ordered_columns()):
            cw = self.column_widths.get(col['key'], col.get('width', 220))
            if x_off <= pos.x() < x_off + cw:
                return idx
            x_off += cw
        return None

    def _hit_test(self, pos: QPoint) -> Tuple[Optional[FocusSession], Optional[str]]:
        """Return (session, edge) where edge is None/'top'/'bottom'."""
        for session in reversed(self.sessions):
            rect = self._session_rect(session)
            if not rect.contains(pos):
                continue
            dy = pos.y() - rect.y()
            h = rect.height()
            if dy < EDGE_GRAB_SIZE:
                return session, 'top'
            if dy > h - EDGE_GRAB_SIZE:
                return session, 'bottom'
            return session, None
        return None, None

    def _hit_test_column(self, pos: QPoint) -> Optional[Tuple[ActivitySegment, int]]:
        """Return (segment, col_idx) if pos is inside a column cell."""
        ordered = self._ordered_columns()
        if not ordered:
            return None
        col_w = self._column_area_width()
        axis_right = self.width() - col_w
        if pos.x() < axis_right:
            return None
        for seg in self.segments:
            for idx, col in enumerate(ordered):
                rect = self._column_rect(seg, idx)
                if rect.contains(pos):
                    return seg, idx
        return None

    def _hit_test_quadrant_boundary(self, pos: QPoint) -> Tuple[Optional[Quadrant], Optional[str]]:
        """Return (quadrant, 'top'|'bottom') if near a draggable quadrant edge.
        For overnight quadrants only the true start (first range top)
        and true end (last range bottom) are draggable."""
        for q in self.quadrants:
            ranges = self._quadrant_y_ranges(q)
            if not ranges:
                continue
            # True start = top of first range
            y_start = ranges[0][0]
            # True end = bottom of last range
            y_end = ranges[-1][1]
            if abs(pos.y() - y_start) <= EDGE_GRAB_SIZE:
                return q, 'top'
            if abs(pos.y() - y_end) <= EDGE_GRAB_SIZE:
                return q, 'bottom'
        return None, None

    def _quadrant_at_pos(self, pos: QPoint) -> Optional[Quadrant]:
        """Return the quadrant whose area contains pos."""
        for q in self.quadrants:
            for y1, y2 in self._quadrant_y_ranges(q):
                if y1 <= pos.y() <= y2:
                    return q
        return None

    def _hit_test_quadrant_task_row(self, pos: QPoint) -> Tuple[Optional[QuadrantTask], bool, Optional[Quadrant], int, str]:
        """Return (task, is_plus, quadrant, row_y, range_date) if pos hits a task row, blank row, or plus button.
        task is None for blank rows; is_plus is True for the '+' button.
        Mirrors the per-range independent logic in _draw_quadrant_tasks_column."""
        qt_left = self._col_left('quadrant_tasks')
        if pos.x() < qt_left + 4 or pos.x() > self.width() - 4:
            return None, False, None, 0, self.date_str

        for q in self.quadrants:
            ranges = self._quadrant_task_ranges(q)
            if not ranges:
                continue

            for y1, y2, range_date in ranges:
                if not (y1 <= pos.y() <= y2):
                    continue

                margin = 6
                if range_date == self.date_str:
                    tasks = self.quadrant_tasks.get(q.id, [])
                else:
                    tasks = self._overnight_yesterday_tasks.get(q.id, [])

                max_rows = (y2 - y1 - margin * 2) // TASK_ROW_HEIGHT
                if max_rows <= 0:
                    continue

                task_y = y1 + margin
                rows_used = 0

                # Existing tasks in this range
                for task in tasks:
                    if rows_used >= max_rows:
                        break
                    if task_y <= pos.y() <= task_y + TASK_ROW_HEIGHT:
                        return task, False, q, task_y, range_date
                    task_y += TASK_ROW_HEIGHT
                    rows_used += 1

                # Plus button (in every range)
                if rows_used < max_rows and task_y + TASK_ROW_HEIGHT <= y2 - margin:
                    if task_y <= pos.y() <= task_y + TASK_ROW_HEIGHT:
                        return None, True, q, task_y, range_date

        return None, False, None, 0, self.date_str

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        top = self._content_top()
        col_w = self._column_area_width()
        axis_right = w - col_w
        lane_map = self._assign_lanes()

        # Background
        painter.fillRect(self.rect(), QColor("#ffffff"))

        # Column header band
        header_bg = QColor("#f5f7fa")
        painter.fillRect(QRect(axis_right, 0, col_w, COLUMN_HEADER_HEIGHT), header_bg)
        painter.setPen(QPen(QColor("#e0e0e0")))
        painter.drawLine(axis_right, COLUMN_HEADER_HEIGHT, w, COLUMN_HEADER_HEIGHT)
        painter.drawLine(axis_right, 0, axis_right, h)

        font_header = QFont("Microsoft YaHei", 9, QFont.Weight.Bold)
        painter.setFont(font_header)
        fm_h = QFontMetrics(font_header)

        # Standard columns
        x_off = axis_right
        ordered = self._ordered_columns()
        for col in ordered:
            col_w = self.column_widths.get(col['key'], 220)
            painter.setPen(QPen(QColor("#555555")))
            tw = fm_h.horizontalAdvance(col['title'])
            col_title = trs(col['title'])
            painter.drawText(x_off + (col_w - tw) // 2,
                             COLUMN_HEADER_HEIGHT - 6,
                             col_title)
            x_off += col_w
            painter.setPen(QPen(QColor("#e0e0e0")))
            painter.drawLine(x_off, 0, x_off, h)

        # Column reorder drag indicator
        if self._drag_mode == 'col_reorder' and self._drag_reorder_col_idx is not None:
            # Highlight the dragged column header
            x_off = axis_right
            for idx, col in enumerate(ordered):
                col_w = self.column_widths.get(col['key'], col.get('width', 220))
                if idx == self._drag_reorder_col_idx:
                    drag_rect = QRect(x_off, 0, col_w, COLUMN_HEADER_HEIGHT)
                    drag_color = QColor("#2196F3")
                    drag_color.setAlpha(60)
                    painter.fillRect(drag_rect, drag_color)
                    painter.setPen(QPen(QColor("#2196F3"), 2))
                    painter.drawRect(drag_rect.adjusted(1, 1, -1, -1))
                # Draw target indicator line
                if self._drag_reorder_target_idx is not None:
                    if idx == self._drag_reorder_target_idx:
                        painter.setPen(QPen(QColor("#2196F3"), 3))
                        painter.drawLine(x_off, 0, x_off, COLUMN_HEADER_HEIGHT)
                        painter.drawLine(x_off + col_w, 0, x_off + col_w, COLUMN_HEADER_HEIGHT)
                x_off += col_w

        # Hour grid lines + ruler text
        pen_light = QPen(QColor("#e8e8e8"))
        pen_light.setWidth(1)
        pen_text = QPen(QColor("#888888"))
        font_small = QFont("Microsoft YaHei", 9)
        painter.setFont(font_small)
        fm = QFontMetrics(font_small)

        for hour in range(25):
            y = top + hour * HOUR_HEIGHT
            if y > h:
                break
            painter.setPen(pen_light)
            painter.drawLine(RULER_WIDTH, y, axis_right, y)
            painter.setPen(pen_text)
            label = f"{hour:02d}:00"
            tw = fm.horizontalAdvance(label)
            painter.drawText(RULER_WIDTH - tw - 6, y + fm.ascent() // 2, label)

        # Quadrant background bands
        self._draw_quadrants(painter)

        # Draw focus sessions as large contiguous blocks
        for session in self.sessions:
            self._draw_session(painter, session)

        # Create-preview block
        if self._create_preview_seg:
            self._draw_block(painter, self._create_preview_seg, is_preview=True, lane_map=lane_map)

        # Column content (segment descriptions)
        ordered = self._ordered_columns()
        if ordered:
            font_col = QFont("Microsoft YaHei", 9)
            painter.setFont(font_col)
            fm_c = QFontMetrics(font_col)
            for seg in self.segments:
                for idx, col in enumerate(ordered):
                    rect = self._column_rect(seg, idx)
                    if rect.height() < 12:
                        continue
                    val = getattr(seg, col['key'], '') or ''
                    elided = fm_c.elidedText(val, Qt.TextElideMode.ElideRight, rect.width() - 8)
                    painter.setPen(QPen(QColor("#444444")))
                    text_y = rect.y() + (rect.height() + fm_c.ascent() - fm_c.descent()) // 2
                    painter.drawText(rect.x() + 4, text_y, elided)

        # Quadrant tasks column (fixed right-hand column)
        self._draw_quadrant_tasks_column(painter)

        # Current time line
        if self.date_str == date.today().isoformat():
            now = datetime.now()
            now_min = now.hour * 60 + now.minute
            y_now = self._minutes_to_y(now_min)
            pen_now = QPen(QColor("#e74c3c"))
            pen_now.setWidth(2)
            painter.setPen(pen_now)
            painter.drawLine(RULER_WIDTH, y_now, w, y_now)

            # Draw current time label on the left side of the ruler
            time_label = now.strftime("%H:%M")
            font_time = QFont("Microsoft YaHei", 9, QFont.Weight.Bold)
            painter.setFont(font_time)
            fm_time = QFontMetrics(font_time)
            tw = fm_time.horizontalAdvance(time_label)
            # Small red dot at the ruler line
            painter.setBrush(QBrush(QColor("#e74c3c")))
            painter.drawEllipse(RULER_WIDTH - 3, y_now - 3, 6, 6)
            # Text left of the ruler
            painter.setPen(QPen(QColor("#e74c3c")))
            painter.drawText(RULER_WIDTH - tw - 8, y_now + fm_time.ascent() // 2 - 2, time_label)

        # Ruler separator
        painter.setPen(QPen(QColor("#cccccc")))
        painter.drawLine(RULER_WIDTH, 0, RULER_WIDTH, h)

        # Selection rectangle
        if self._selection_rect:
            sel_rect = self._selection_rect.normalized()
            sel_color = QColor("#2196F3")
            sel_color.setAlpha(40)
            painter.setBrush(QBrush(sel_color))
            sel_pen = QPen(QColor("#2196F3"))
            sel_pen.setWidth(1)
            sel_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.drawRect(sel_rect.adjusted(0, 0, -1, -1))

        painter.end()

    def _draw_quadrants(self, painter: QPainter):
        w = self.width()
        for q in self.quadrants:
            ranges = self._quadrant_y_ranges(q)
            color = QColor(q.color)
            bg = QColor(color)
            bg.setAlpha(QUADRANT_ALPHA)
            pen_boundary = QPen(QColor("#999999"))
            pen_boundary.setStyle(Qt.PenStyle.DashLine)
            pen_boundary.setWidth(1)

            for i, (y1, y2) in enumerate(ranges):
                if y2 <= y1:
                    continue
                rect = QRect(0, y1, w, y2 - y1)
                painter.fillRect(rect, bg)
                painter.setPen(pen_boundary)
                painter.drawLine(0, y1, w, y1)
                painter.drawLine(0, y2, w, y2)

    def _draw_quadrant_tasks_column(self, painter: QPainter):
        """Draw quadrant tasks in the fixed right-hand column.
        Each range displays its own tasks independently.
        For overnight quadrants, 22:00-24:00 uses today's tasks,
        00:00-07:00 uses yesterday's tasks. All ranges get blank rows and '+'."""
        qt_left = self._col_left('quadrant_tasks')
        qt_w = self.column_widths.get('quadrant_tasks', 240)
        if qt_left < 0 or not self.quadrants:
            return

        sep_pen = QPen(QColor("#e8e8e8"))
        sep_pen.setWidth(1)
        sep_pen.setStyle(Qt.PenStyle.DotLine)
        font_task = QFont("Microsoft YaHei", 9)
        fm_t = QFontMetrics(font_task)
        line_h = TASK_ROW_HEIGHT
        margin = 6
        avail_w = qt_w - margin * 2

        for q in self.quadrants:
            ranges = self._quadrant_task_ranges(q)
            if not ranges:
                continue

            for y1, y2, range_date in ranges:
                if y2 <= y1:
                    continue

                max_rows = (y2 - y1 - margin * 2) // line_h
                if max_rows <= 0:
                    continue

                # Get tasks for this specific range/date
                if range_date == self.date_str:
                    tasks = self.quadrant_tasks.get(q.id, [])
                else:
                    tasks = self._overnight_yesterday_tasks.get(q.id, [])

                # Bottom separator for quadrant area
                painter.setPen(sep_pen)
                painter.drawLine(qt_left + 4, y2, qt_left + qt_w - 4, y2)

                task_y = y1 + margin
                rows_used = 0

                # Existing tasks
                for task in tasks:
                    if rows_used >= max_rows:
                        break
                    self._draw_task_row(painter, task, qt_left + margin, task_y, avail_w, fm_t)
                    task_y += line_h
                    rows_used += 1

                # Plus button (in every range)
                if rows_used < max_rows:
                    plus_x = qt_left + margin + CHECKBOX_SIZE // 2
                    plus_y = task_y + line_h // 2
                    painter.setPen(QPen(QColor("#bbbbbb")))
                    painter.drawEllipse(plus_x - 6, plus_y - 6, 12, 12)
                    painter.setPen(QPen(QColor("#888888")))
                    painter.drawLine(plus_x - 3, plus_y, plus_x + 3, plus_y)
                    painter.drawLine(plus_x, plus_y - 3, plus_x, plus_y + 3)

    def _draw_task_row(self, painter: QPainter, task: QuadrantTask, x: int, y: int, avail_w: int, fm_t: QFontMetrics):
        """Draw a single task row with checkbox and text."""
        line_h = TASK_ROW_HEIGHT
        cb_x = x
        cb_y = y + (line_h - CHECKBOX_SIZE) // 2

        # Checkbox
        painter.setPen(QPen(QColor("#555555")))
        painter.drawRect(cb_x, cb_y, CHECKBOX_SIZE, CHECKBOX_SIZE)
        if task.completed:
            painter.setPen(QPen(QColor("#27ae60"), 2))
            painter.drawLine(cb_x + 2, cb_y + CHECKBOX_SIZE // 2,
                             cb_x + CHECKBOX_SIZE // 2 - 1, cb_y + CHECKBOX_SIZE - 3)
            painter.drawLine(cb_x + CHECKBOX_SIZE // 2 - 1, cb_y + CHECKBOX_SIZE - 3,
                             cb_x + CHECKBOX_SIZE - 2, cb_y + 2)
            painter.setPen(QPen(QColor("#555555")))

        # Text
        text_x = cb_x + CHECKBOX_SIZE + 4
        text_w = avail_w - CHECKBOX_SIZE - 4

        if task.completed:
            font_strike = QFont("Microsoft YaHei", 9)
            font_strike.setStrikeOut(True)
            painter.setFont(font_strike)
        else:
            painter.setFont(QFont("Microsoft YaHei", 9))

        text = fm_t.elidedText(task.content, Qt.TextElideMode.ElideRight, text_w)
        painter.setPen(QPen(QColor("#333333")))
        painter.drawText(text_x, y + fm_t.ascent(), text)

    # ------------------------------------------------------------------
    # Inline editor for quadrant tasks
    # ------------------------------------------------------------------

    def _start_quadrant_task_edit(self, task: Optional[QuadrantTask], quadrant: Quadrant, y_pos: int, date_str: str = None):
        """Embed a QLineEdit at the given y position for inline editing."""
        if self._active_editor:
            self._finish_quadrant_task_editor()

        qt_left = self._col_left('quadrant_tasks')
        qt_w = self.column_widths.get('quadrant_tasks', 240)
        editor = QLineEdit(self)
        editor.setGeometry(qt_left + 20, int(y_pos), qt_w - 28, TASK_ROW_HEIGHT)
        editor.setText(task.content if task else '')
        editor.setStyleSheet("""
            QLineEdit {
                border: 1px solid #2196F3;
                border-radius: 4px;
                padding: 2px 6px;
                background: white;
                font-size: 13px;
            }
        """)
        editor.setPlaceholderText(trs("enter_task"))

        def on_finish():
            text = editor.text().strip()
            if text:
                if task:
                    self.db.update_quadrant_task_content(task.id, text)
                else:
                    self.db.add_quadrant_task(date_str or self.date_str, quadrant.id, text)
            self._active_editor = None
            editor.deleteLater()
            self.refresh()

        editor.editingFinished.connect(on_finish)
        editor.show()
        editor.setFocus()
        self._active_editor = editor

    def _finish_quadrant_task_editor(self):
        """Finish and remove the active inline editor if any."""
        if self._active_editor:
            # Trigger editingFinished which handles save + cleanup
            self._active_editor.clearFocus()
            self._active_editor = None

    def _get_segment_color(self, seg: ActivitySegment) -> QColor:
        if seg.is_idle:
            return QColor("#cccccc")
        elif seg.task_id and seg.task_id in self.tasks:
            return QColor(self.tasks[seg.task_id].color)
        elif seg.source == 'manual':
            return QColor("#3498db")
        else:
            return QColor("#95a5a6")

    def _draw_block_background(self, painter: QPainter, seg: ActivitySegment, lane_map: dict = None):
        """Draw only the background fill for a segment."""
        rect = self._block_rect(seg, lane_map)
        if rect.height() < 2:
            return
        base_color = self._get_segment_color(seg)
        bg = QColor(base_color)
        bg.setAlpha(180)
        painter.fillRect(rect, bg)

    def _draw_block_border_text(self, painter: QPainter, seg: ActivitySegment, lane_map: dict = None):
        """Draw border, selection highlight, and text for a segment."""
        rect = self._block_rect(seg, lane_map)
        if rect.height() < 2:
            return
        base_color = self._get_segment_color(seg)

        # Border
        border = QColor(base_color).darker(120)
        pen = QPen(border)
        pen.setWidth(1)
        if seg.source == 'auto':
            pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawRect(rect)

        # Selection highlight (single or multi-select)
        is_selected = seg.id == self._selected_seg_id or seg.id in self._selected_seg_ids
        if is_selected:
            sel_pen = QPen(QColor("#2196F3"))
            sel_pen.setWidth(2)
            painter.setPen(sel_pen)
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))

        # Text
        painter.setPen(QColor("#2c3e50"))
        font = QFont("Microsoft YaHei", 8)
        painter.setFont(font)
        fm = QFontMetrics(font)

        lines = []
        if seg.app_name and seg.app_name != 'Idle':
            lines.append(get_app_display_name(seg.app_name))
        if seg.task_id and seg.task_id in self.tasks:
            lines.append(self.tasks[seg.task_id].name)
        if seg.is_idle:
            lines.append(f"[{trs('idle')}]")
        time_range = f"{seg.start_time[:5]}–{seg.end_time[:5]}"
        lines.append(time_range)

        y_text = rect.y() + 3
        line_h = fm.height()
        for line in lines:
            if y_text + line_h > rect.y() + rect.height():
                break
            painter.drawText(rect.x() + 4, y_text + fm.ascent(), line)
            y_text += line_h

    def _build_fusion_groups(self) -> List[List[ActivitySegment]]:
        """Group adjacent short segments into fusion groups.
        Criteria: single segment duration <= 5 min and gap to previous <= 1 min."""
        if not self.segments:
            return []
        sorted_segs = sorted(self.segments, key=lambda s: time_to_minutes(s.start_time))
        groups: List[List[ActivitySegment]] = []
        current = [sorted_segs[0]]
        for seg in sorted_segs[1:]:
            last = current[-1]
            last_end = time_to_minutes(last.end_time)
            seg_start = time_to_minutes(seg.start_time)
            seg_dur = time_to_minutes(seg.end_time) - seg_start
            gap = seg_start - last_end
            if gap <= 1 and seg_dur <= 5:
                current.append(seg)
            else:
                if len(current) >= 2:
                    groups.append(current)
                current = [seg]
        if len(current) >= 2:
            groups.append(current)
        return groups

    def _draw_fusion_group(self, painter: QPainter, group: List[ActivitySegment], lane_map: dict = None):
        """Draw a fusion group as one large block with outer border and merged text."""
        first = group[0]
        last = group[-1]
        first_rect = self._block_rect(first, lane_map)
        last_rect = self._block_rect(last, lane_map)
        if first_rect.height() < 2 or last_rect.height() < 2:
            return

        outer = QRect(first_rect.x(), first_rect.y(), first_rect.width(),
                      last_rect.y() + last_rect.height() - first_rect.y())
        base_color = self._get_segment_color(first)
        border = QColor(base_color).darker(120)
        pen = QPen(border)
        pen.setWidth(1)
        if first.source == 'auto':
            pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawRect(outer)

        # Selection highlight (single or multi-select)
        group_selected = any(s.id == self._selected_seg_id or s.id in self._selected_seg_ids for s in group)
        if group_selected:
            sel_pen = QPen(QColor("#2196F3"))
            sel_pen.setWidth(2)
            painter.setPen(sel_pen)
            painter.drawRect(outer.adjusted(-1, -1, 1, 1))

        # Merge text
        seen = set()
        parts = []
        for s in group:
            if s.app_name and s.app_name != 'Idle':
                name = get_app_display_name(s.app_name)
                if name not in seen:
                    seen.add(name)
                    parts.append(name)
            if s.task_id and s.task_id in self.tasks:
                tname = self.tasks[s.task_id].name
                if tname not in seen:
                    seen.add(tname)
                    parts.append(tname)
            if s.description:
                if s.description not in seen:
                    seen.add(s.description)
                    parts.append(s.description)

        merged = " | ".join(parts) if parts else ""
        time_range = f"{first.start_time[:5]}–{last.end_time[:5]}"

        painter.setPen(QColor("#2c3e50"))
        font = QFont("Microsoft YaHei", 8)
        painter.setFont(font)
        fm = QFontMetrics(font)

        lines = []
        if merged:
            elided = fm.elidedText(merged, Qt.TextElideMode.ElideRight, outer.width() - 8)
            lines.append(elided)
        lines.append(time_range)

        y_text = outer.y() + 3
        line_h = fm.height()
        for line in lines:
            if y_text + line_h > outer.y() + outer.height():
                break
            painter.drawText(outer.x() + 4, y_text + fm.ascent(), line)
            y_text += line_h

    def _draw_block(self, painter: QPainter, seg: ActivitySegment, is_preview: bool = False, lane_map: dict = None):
        """Full block draw (background + border + text). Used for preview and standalone blocks."""
        rect = self._block_rect(seg, lane_map)
        if rect.height() < 2:
            return

        base_color = self._get_segment_color(seg)
        bg = QColor(base_color)
        if is_preview:
            bg.setAlpha(100)
        else:
            bg.setAlpha(180)
        painter.fillRect(rect, bg)

        border = QColor(base_color).darker(120)
        pen = QPen(border)
        pen.setWidth(1)
        if is_preview:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(2)
        elif seg.source == 'auto':
            pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawRect(rect)

        if not is_preview and (seg.id == self._selected_seg_id or seg.id in self._selected_seg_ids):
            sel_pen = QPen(QColor("#2196F3"))
            sel_pen.setWidth(2)
            painter.setPen(sel_pen)
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))

        painter.setPen(QColor("#555555") if is_preview else QColor("#2c3e50"))
        font = QFont("Microsoft YaHei", 8)
        painter.setFont(font)
        fm = QFontMetrics(font)

        lines = []
        if seg.app_name and seg.app_name != 'Idle':
            lines.append(get_app_display_name(seg.app_name))
        if seg.task_id and seg.task_id in self.tasks:
            lines.append(self.tasks[seg.task_id].name)
        if seg.is_idle:
            lines.append(f"[{trs('idle')}]")
        time_range = f"{seg.start_time[:5]}–{seg.end_time[:5]}"
        if is_preview:
            time_range += f" ({trs('preview')})"
        lines.append(time_range)

        y_text = rect.y() + 3
        line_h = fm.height()
        for line in lines:
            if y_text + line_h > rect.y() + rect.height():
                break
            painter.drawText(rect.x() + 4, y_text + fm.ascent(), line)
            y_text += line_h

    # ------------------------------------------------------------------
    # Focus session drawing
    # ------------------------------------------------------------------

    def _session_rect(self, session: FocusSession) -> QRect:
        """Return the rectangle for a focus session on the time axis."""
        start_min = time_to_minutes(session.start_time)
        end_min = time_to_minutes(session.end_time)
        y1 = self._minutes_to_y(start_min)
        y2 = self._minutes_to_y(end_min)
        col_w = self._column_area_width()
        axis_right = self.width() - col_w
        x = RULER_WIDTH + BLOCK_MARGIN
        w = max(20, axis_right - x - BLOCK_MARGIN)
        return QRect(x, y1, w, max(4, y2 - y1))

    def _draw_session(self, painter: QPainter, session: FocusSession):
        """Draw a focus session as a single large block."""
        rect = self._session_rect(session)
        if rect.height() < 2:
            return

        # Determine color from dominant task
        task_id = session.dominant_task_id
        if task_id and task_id in self.tasks:
            base_color = QColor(self.tasks[task_id].color)
        else:
            base_color = QColor("#5B8DB8")

        # Background fill
        bg = QColor(base_color)
        bg.setAlpha(180)
        painter.fillRect(rect, bg)

        # Border
        border = QColor(base_color).darker(120)
        pen = QPen(border)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(rect)

        # Selection highlight
        if session is getattr(self, '_selected_session', None):
            sel_pen = QPen(QColor("#2196F3"))
            sel_pen.setWidth(2)
            painter.setPen(sel_pen)
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))

        # Text label (only if block is tall enough)
        if rect.height() >= 18:
            painter.setPen(QColor("#ffffff"))
            font = QFont("Microsoft YaHei", 9, QFont.Weight.Bold)
            painter.setFont(font)
            fm = QFontMetrics(font)

            total_str = format_duration_short(session.total_seconds)
            lines = [total_str]
            if session.segment_count > 1:
                lines.append(f"{session.segment_count} segs")

            y_text = rect.y() + 4
            line_h = fm.height()
            for line in lines:
                if y_text + line_h > rect.y() + rect.height() - 2:
                    break
                tw = fm.horizontalAdvance(line)
                x_center = rect.x() + (rect.width() - tw) // 2
                painter.drawText(x_center, y_text + fm.ascent(), line)
                y_text += line_h

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        pos = event.pos()

        if event.button() == Qt.MouseButton.RightButton:
            self._selection_start_pos = QPoint(pos)
            self._selection_rect = None
            self.update()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # If an inline editor is active, clicking outside finishes it first
        if self._active_editor:
            editor_rect = self._active_editor.geometry()
            if not editor_rect.contains(pos):
                self._finish_quadrant_task_editor()
                return

        # Check quadrant task row click
        task, is_plus, q, row_y, range_date = self._hit_test_quadrant_task_row(pos)
        if task:
            # Toggle completion on checkbox area; edit on text area
            # For simplicity: always toggle on single click
            self.db.toggle_quadrant_task(task.id)
            self.refresh()
            return
        elif is_plus and q:
            new_id = self.db.add_quadrant_task(range_date, q.id, "")
            self.refresh()
            # Find the new task and start editing it
            new_task = None
            task_pool = self.quadrant_tasks.get(q.id, []) if range_date == self.date_str else self._overnight_yesterday_tasks.get(q.id, [])
            for t in task_pool:
                if t.id == new_id:
                    new_task = t
                    break
            self._start_quadrant_task_edit(new_task, q, row_y, range_date)
            return
        elif q and not is_plus:
            # Clicked a blank row -> start inline edit for a new task
            self._start_quadrant_task_edit(None, q, row_y, range_date)
            return

        # Check column header drag (reorder)
        col_header_idx = self._hit_test_col_header(pos)
        if col_header_idx is not None:
            self._drag_mode = 'col_reorder'
            self._drag_reorder_col_idx = col_header_idx
            self._drag_reorder_target_idx = col_header_idx
            self._drag_start_x = pos.x()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            return

        # Check column border drag
        col_border = self._hit_test_col_border(pos)
        if col_border:
            col_key, is_left = col_border
            self._drag_mode = 'col_resize'
            self._drag_col_key = col_key
            self._drag_col_is_left_edge = is_left
            self._drag_start_x = pos.x()
            self._drag_orig_width = self.column_widths.get(col_key, 220)
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return

        # Check quadrant boundary drag
        q, edge = self._hit_test_quadrant_boundary(pos)
        if q and edge:
            self._drag_mode = 'quadrant_boundary'
            self._drag_quadrant = q
            self._drag_boundary_edge = edge
            self._drag_start_y = pos.y()
            self._drag_orig_time_min = time_to_minutes(
                q.start_time if edge == 'top' else q.end_time
            )
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return

        session, block_edge = self._hit_test(pos)
        if session:
            self._selected_session = session
            self._selected_seg_id = None
            self._selected_seg_ids.clear()
            self.update()
        else:
            self._selected_session = None
            self._selected_seg_id = None
            self._selected_seg_ids.clear()
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()

        # Right-click box selection
        if event.buttons() == Qt.MouseButton.RightButton and self._selection_start_pos:
            self._selection_rect = QRect(self._selection_start_pos, pos).normalized()
            self.update()
            return

        if self._drag_mode == 'col_reorder' and self._drag_reorder_col_idx is not None:
            target = self._hit_test_col_header(pos)
            if target is None:
                # Check if pos is in column area but not on a header
                col_w = self._column_area_width()
                axis_right = self.width() - col_w
                if pos.x() >= axis_right and pos.y() <= COLUMN_HEADER_HEIGHT:
                    # Find nearest column by x position
                    x_off = axis_right
                    for idx, col in enumerate(self._ordered_columns()):
                        cw = self.column_widths.get(col['key'], col.get('width', 220))
                        if x_off <= pos.x() < x_off + cw:
                            target = idx
                            break
                        x_off += cw
            if target is not None and target != self._drag_reorder_target_idx:
                self._drag_reorder_target_idx = target
                self.update()
            return

        if self._drag_mode == 'col_resize' and self._drag_col_key:
            delta = pos.x() - self._drag_start_x
            if getattr(self, '_drag_col_is_left_edge', False):
                new_width = self._drag_orig_width - delta
            else:
                new_width = self._drag_orig_width + delta
            new_width = max(80, min(new_width, 600))
            self.column_widths[self._drag_col_key] = new_width
            self.setMinimumWidth(600 + self._column_area_width())
            self.update()
            return

        if self._drag_mode == 'quadrant_boundary' and self._drag_quadrant:
            current_min = snap_to_grid(self._y_to_minutes(pos.y()), SNAP_GRID)
            # Ensure at least 1 minute difference from the opposite boundary
            other_time = time_to_minutes(
                self._drag_quadrant.end_time if self._drag_boundary_edge == 'top'
                else self._drag_quadrant.start_time
            )
            if current_min != other_time:
                if self._drag_boundary_edge == 'top':
                    self._drag_quadrant.start_time = minutes_to_time(current_min) + ":00"
                else:
                    self._drag_quadrant.end_time = minutes_to_time(current_min) + ":00"
            self.update()
            return

        if self._drag_mode == 'create' and self._create_preview_seg:
            start_min = time_to_minutes(self._create_preview_seg.start_time)
            current_min = snap_to_grid(self._y_to_minutes(pos.y()), SNAP_GRID)
            if current_min < start_min:
                self._create_preview_seg.start_time = minutes_to_time(current_min) + ":00"
                self._create_preview_seg.end_time = minutes_to_time(start_min) + ":00"
            else:
                self._create_preview_seg.end_time = minutes_to_time(current_min) + ":00"
            self.update()
            return

        if self._drag_mode and self._drag_seg:
            delta_min = snap_to_grid(
                self._y_to_minutes(pos.y()) - self._y_to_minutes(self._drag_start_y),
                SNAP_GRID
            )
            if self._drag_mode == 'move':
                dur = self._drag_orig_end_min - self._drag_orig_start_min
                new_start = max(0, min(self._drag_orig_start_min + delta_min, DAY_MINUTES - dur - 1))
                new_end = new_start + dur
                self._drag_seg.start_time = minutes_to_time(new_start) + ":00"
                self._drag_seg.end_time = minutes_to_time(new_end) + ":00"
            elif self._drag_mode == 'resize_top':
                new_start = max(0, min(self._drag_orig_start_min + delta_min, self._drag_orig_end_min - 5))
                self._drag_seg.start_time = minutes_to_time(new_start) + ":00"
            elif self._drag_mode == 'resize_bottom':
                new_end = max(self._drag_orig_start_min + 5, min(self._drag_orig_end_min + delta_min, DAY_MINUTES - 1))
                self._drag_seg.end_time = minutes_to_time(new_end) + ":00"
            self.update()
            return

        # Hover cursor
        col_border = self._hit_test_col_border(pos)
        if col_border:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return

        q, edge = self._hit_test_quadrant_boundary(pos)
        if q and edge:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return

        session, block_edge = self._hit_test(pos)
        if session:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return

        # Column area -> default arrow cursor
        col_w = self._column_area_width()
        axis_right = self.width() - col_w
        if pos.x() >= axis_right:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self._selection_start_pos:
                if self._selection_rect and (self._selection_rect.width() > 5 or self._selection_rect.height() > 5):
                    self._perform_box_selection()
                else:
                    # Single right click -> show context menu
                    self._show_context_menu_for_pos(event.pos())
                self._selection_start_pos = None
                self._selection_rect = None
                self.update()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._drag_mode == 'col_resize' and self._drag_col_key:
            self._save_column_widths()
            self._drag_mode = None
            self._drag_col_key = None
            self._drag_col_is_left_edge = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            return

        if self._drag_mode == 'col_reorder' and self._drag_reorder_col_idx is not None:
            target = self._drag_reorder_target_idx
            if target is not None and target != self._drag_reorder_col_idx:
                # Swap columns in column_order
                order = list(self.column_order)
                src = self._drag_reorder_col_idx
                dst = target
                order[src], order[dst] = order[dst], order[src]
                self.column_order = order
                self._save_column_order()
            self._drag_mode = None
            self._drag_reorder_col_idx = None
            self._drag_reorder_target_idx = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            return

        if self._drag_mode == 'quadrant_boundary' and self._drag_quadrant:
            self.db.update_quadrant_times(
                self._drag_quadrant.id,
                self._drag_quadrant.start_time,
                self._drag_quadrant.end_time,
            )
            self._drag_mode = None
            self._drag_quadrant = None
            self._drag_boundary_edge = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            return

        if self._drag_mode == 'create' and self._create_preview_seg:
            # Finalize creation
            seg = self._create_preview_seg
            self._create_preview_seg = None
            start_min = time_to_minutes(seg.start_time)
            end_min = time_to_minutes(seg.end_time)
            duration = end_min - start_min

            if duration >= MIN_CREATE_DURATION:
                # Create in DB then immediately open edit dialog
                new_id = self.db.add_segment(
                    date_str=self.date_str,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                    source='manual',
                    description='',
                )
                self.refresh()
                # Open edit dialog for the newly created block
                new_seg = None
                for s in self.segments:
                    if s.id == new_id:
                        new_seg = s
                        break
                if new_seg:
                    dialog = BlockEditDialog(self.db, segment=new_seg, parent=self)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        data = dialog.get_data()
                        self.db.update_segment_full(
                            new_seg.id,
                            data['start_time'],
                            data['end_time'],
                            data['task_id'],
                            data['description'],
                        )
                        self.refresh()
                        self.segment_changed.emit()
                    else:
                        # User cancelled - delete the newly created segment
                        self.db.delete_segment(new_seg.id)
                        self.refresh()
                else:
                    self.segment_changed.emit()
            else:
                # Too short, discard
                self.update()

        elif self._drag_mode and self._drag_seg:
            # Commit move/resize to DB
            self.db.update_segment_full(
                self._drag_seg.id,
                self._drag_seg.start_time,
                self._drag_seg.end_time,
                self._drag_seg.task_id,
                self._drag_seg.description,
            )
            self.segment_changed.emit()

        self._drag_mode = None
        self._drag_seg = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def mouseDoubleClickEvent(self, event):
        pos = event.pos()

        # Quadrant task double-click -> start inline edit (check BEFORE column cells)
        task, is_plus, q, row_y, range_date = self._hit_test_quadrant_task_row(pos)
        if task:
            self._start_quadrant_task_edit(task, q, row_y, range_date)
            return
        elif is_plus and q:
            # Double-click on '+' button area -> add new task
            new_id = self.db.add_quadrant_task(range_date, q.id, "")
            self.refresh()
            new_task = None
            task_pool = self.quadrant_tasks.get(q.id, []) if range_date == self.date_str else self._overnight_yesterday_tasks.get(q.id, [])
            for t in task_pool:
                if t.id == new_id:
                    new_task = t
                    break
            self._start_quadrant_task_edit(new_task, q, row_y, range_date)
            return
        elif q and not is_plus:
            # Double-click on blank row -> start editing new task
            self._start_quadrant_task_edit(None, q, row_y, range_date)
            return

        session, _ = self._hit_test(pos)
        if session:
            dialog = FocusSessionDialog(session, self.tasks, self)
            dialog.exec()
            return

        # Column double-click -> quick edit description (only for description column)
        col_hit = self._hit_test_column(pos)
        if col_hit:
            seg, col_idx = col_hit
            ordered = self._ordered_columns()
            if col_idx < len(ordered) and ordered[col_idx]['key'] == 'description':
                dialog = QuickEditDialog(seg.description or '', parent=self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    new_desc = dialog.get_text()
                    self.db.update_segment_description(seg.id, new_desc)
                    self.refresh()
                    self.segment_changed.emit()
                return

        # Quadrant double-click -> quick add task
        q = self._quadrant_at_pos(pos)
        if q:
            dialog = QuickAddDialog(parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                content = dialog.get_text()
                if content.strip():
                    self.db.add_quadrant_task(self.date_str, q.id, content.strip())
                    self.refresh()
            return

    def _open_edit_dialog(self, seg: ActivitySegment):
        """Open the edit dialog for a segment and refresh if saved."""
        dialog = BlockEditDialog(self.db, segment=seg, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.db.update_segment_full(
                seg.id,
                data['start_time'],
                data['end_time'],
                data['task_id'],
                data['description'],
            )
            self.refresh()
            self.segment_changed.emit()

    def _show_context_menu_for_pos(self, pos: QPoint):
        """Show context menu for a single right-click at pos."""
        self._show_context_menu(pos)

    def _show_context_menu(self, pos):
        local_pos = self.mapFromGlobal(self.mapToGlobal(pos))

        # Check if on a quadrant task
        task, is_plus, q, row_y, range_date = self._hit_test_quadrant_task_row(local_pos)
        if task:
            menu = QMenu(self)
            delete_action = menu.addAction(trs("delete_task"))
            action = menu.exec(self.mapToGlobal(pos))
            if action == delete_action:
                self.db.delete_quadrant_task(task.id)
                self.refresh()
            return

        session, _ = self._hit_test(local_pos)
        if not session:
            return
        menu = QMenu(self)
        detail_action = menu.addAction(trs("view_details"))
        action = menu.exec(self.mapToGlobal(pos))
        if action == detail_action:
            dialog = FocusSessionDialog(session, self.tasks, self)
            dialog.exec()

    def _seg_full_rect(self, seg: ActivitySegment, lane_map: dict) -> QRect:
        """Return the bounding rect of a segment across the entire widget
        (time-axis + all columns). This ensures box selection works no matter
        which visual area the user drags over."""
        block_rect = self._block_rect(seg, lane_map)
        full = QRect(block_rect)
        for idx, _ in enumerate(self._ordered_columns()):
            col_rect = self._column_rect(seg, idx)
            full = full.united(col_rect)
        return full

    def _perform_box_selection(self):
        """Collect segments intersecting the selection rect and show batch menu.
        Works across both the time-axis area and the column area."""
        if not self._selection_rect:
            return
        # Save rect and clear immediately so the visual rectangle disappears
        # before the modal menu blocks the event loop.
        sel_rect = QRect(self._selection_rect)
        self._selection_rect = None
        self._selection_start_pos = None
        self.update()

        lane_map = self._assign_lanes()
        selected_ids: set[int] = set()

        for seg in self.segments:
            full_rect = self._seg_full_rect(seg, lane_map)
            if sel_rect.intersects(full_rect):
                selected_ids.add(seg.id)

        self._selected_seg_ids = selected_ids
        if selected_ids:
            self._show_batch_menu(list(selected_ids))
        self.update()

    def _show_batch_menu(self, seg_ids: List[int]):
        """Show batch operations menu for selected segments."""
        menu = QMenu(self)
        delete_action = menu.addAction(trs("batch_delete").format(len(seg_ids)))
        action = menu.exec(self.cursor().pos())
        if action == delete_action:
            reply = QMessageBox.question(
                self, trs("confirm"), trs("delete_selected_blocks").format(len(seg_ids)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.db.delete_segments_batch(seg_ids)
                self._selected_seg_ids.clear()
                self._selected_seg_id = None
                self.refresh()
                self.segment_changed.emit()

    # ------------------------------------------------------------------
    # Resize handling
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()
