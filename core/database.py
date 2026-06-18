"""
Database module for Work Manager
Uses SQLite for local data storage
"""

import sqlite3
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from utils.logger import get_logger

_log = get_logger("database")


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Task:
    id: int
    name: str
    color: str
    created_at: str


@dataclass
class ActivitySegment:
    id: int
    date: str
    start_time: str
    end_time: str
    app_name: Optional[str]
    task_id: Optional[int]
    is_idle: int          # 0 or 1
    source: str           # 'auto' | 'manual'
    description: str
    window_title: str = ''


@dataclass
class Quadrant:
    id: int
    name: str
    start_time: str
    end_time: str
    color: str
    sort_order: int


@dataclass
class QuadrantTask:
    id: int
    date: str
    quadrant_id: int
    content: str
    completed: int
    created_at: str


@dataclass
class Project:
    id: int
    name: str
    color: str
    sort_order: int
    collapsed: int
    created_at: str


@dataclass
class ProjectSection:
    id: int
    project_id: int
    name: str
    color: str
    collapsed: int
    sort_order: int


@dataclass
class ProjectNote:
    id: int
    section_id: int
    content: str
    updated_at: str


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

class Database:
    def __init__(self):
        _log.info("Opening database | path=%s", DB_PATH)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._init_tables()
        self._ensure_default_task()
        self._ensure_default_quadrants()
        self._update_default_quadrant_config()
        self._migrate_legacy_data()
        _log.info("Database initialized successfully")

    # ------------------------------------------------------------------
    # Schema init
    # ------------------------------------------------------------------

    def _init_tables(self):
        cursor = self.conn.cursor()

        # Tasks (kept as-is)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#4CAF50',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # NEW: Activity segments (replaces app_usage + time_slots)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                app_name TEXT,
                task_id INTEGER,
                is_idle INTEGER DEFAULT 0,
                source TEXT DEFAULT 'auto',
                description TEXT DEFAULT '',
                window_title TEXT DEFAULT '',
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        ''')
        # Migrate: add window_title column if table already exists without it
        cursor.execute("PRAGMA table_info(activity_segments)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'window_title' not in columns:
            cursor.execute("ALTER TABLE activity_segments ADD COLUMN window_title TEXT DEFAULT ''")
            _log.info("Migrated activity_segments: added window_title column")

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_seg_date ON activity_segments(date)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_seg_start ON activity_segments(date, start_time)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_seg_task ON activity_segments(task_id)
        ''')

        # Quadrant definitions (time management zones)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quadrants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                color TEXT DEFAULT '#FFEBEE',
                sort_order INTEGER DEFAULT 0
            )
        ''')

        # Tasks planned inside each quadrant
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quadrant_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                quadrant_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_qt_date_qid ON quadrant_tasks(date, quadrant_id)
        ''')

        # Calendar event markers (colored dots/labels on calendar days)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#e74c3c',
                label TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ce_date ON calendar_events(date)
        ''')

        # Projects, sections, and rich-text notes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT 'New Project',
                color TEXT DEFAULT '#5B8DB8',
                sort_order INTEGER DEFAULT 0,
                collapsed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Migration: add collapsed column if table exists without it
        cursor.execute("PRAGMA table_info(projects)")
        project_cols = [col[1] for col in cursor.fetchall()]
        if 'collapsed' not in project_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN collapsed INTEGER DEFAULT 0")
            _log.info("Migrated projects: added collapsed column")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL DEFAULT 'New Section',
                color TEXT DEFAULT '#E3F2FD',
                collapsed INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_project_sections_project
            ON project_sections(project_id)
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section_id INTEGER NOT NULL UNIQUE,
                content TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (section_id) REFERENCES project_sections(id) ON DELETE CASCADE
            )
        ''')

        # Application settings (key-value store)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        self.conn.commit()

    def _ensure_default_task(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE name = '未分类'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO tasks (name, color) VALUES ('未分类', '#9E9E9E')")
            self.conn.commit()

    def _ensure_default_quadrants(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM quadrants")
        if cursor.fetchone()[0] == 0:
            defaults = [
                ('Q1 上午', '07:00', '13:00', '#DBEAFE', 1),
                ('Q2 下午', '13:00', '19:00', '#DCFCE7', 2),
                ('Q3 晚上', '19:00', '22:00', '#FFEDD5', 3),
                ('Q4 深夜', '22:00', '07:00', '#D8B4FE', 4),
            ]
            cursor.executemany(
                "INSERT INTO quadrants (name, start_time, end_time, color, sort_order) VALUES (?, ?, ?, ?, ?)",
                defaults
            )
            self.conn.commit()

    def _update_default_quadrant_config(self):
        """Ensure existing default quadrants use the latest color and time defaults."""
        cursor = self.conn.cursor()
        color_updates = [
            ('Q1 上午', '#DBEAFE'),
            ('Q2 下午', '#DCFCE7'),
            ('Q3 晚上', '#FFEDD5'),
            ('Q4 深夜', '#D8B4FE'),
        ]
        for name, color in color_updates:
            cursor.execute(
                "UPDATE quadrants SET color = ? WHERE name = ?",
                (color, name)
            )
        # Migrate Q4 end time from old default 01:00 to 07:00
        cursor.execute(
            "UPDATE quadrants SET end_time = '07:00' WHERE name = 'Q4 深夜' AND end_time = '01:00'"
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Legacy migration
    # ------------------------------------------------------------------

    def _migrate_legacy_data(self):
        """
        If old tables exist, do a best-effort migration then rename them away.
        """
        cursor = self.conn.cursor()

        # Check for old app_usage table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_usage'")
        if cursor.fetchone():
            # Migrate: create one synthetic segment per old row
            cursor.execute("SELECT date, app_name, duration_seconds, task_id FROM app_usage")
            rows = cursor.fetchall()
            migrated = 0
            for row in rows:
                date_str, app_name, duration_sec, task_id = row
                # Best-effort: place at 09:00, extend by duration
                start = datetime.strptime("09:00:00", "%H:%M:%S")
                end = start + timedelta(seconds=duration_sec)
                start_str = start.strftime("%H:%M:%S")
                end_str = end.strftime("%H:%M:%S")
                # Clamp to same day
                if end.day != start.day:
                    end_str = "23:59:59"
                cursor.execute('''
                    INSERT INTO activity_segments
                    (date, start_time, end_time, app_name, task_id, is_idle, source, description)
                    VALUES (?, ?, ?, ?, ?, 0, 'auto', '从历史数据迁移')
                ''', (date_str, start_str, end_str, app_name, task_id))
                migrated += 1

            # Migrate old time_slots too
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='time_slots'")
            if cursor.fetchone():
                cursor.execute("SELECT date, start_time, end_time, task_id, description FROM time_slots")
                for row in cursor.fetchall():
                    date_str, st, et, task_id, desc = row
                    cursor.execute('''
                        INSERT INTO activity_segments
                        (date, start_time, end_time, app_name, task_id, is_idle, source, description)
                        VALUES (?, ?, ?, NULL, ?, 0, 'manual', ?)
                    ''', (date_str, st, et, task_id, desc or ''))

            self.conn.commit()

            # Rename old tables so we don't migrate again
            cursor.execute("ALTER TABLE app_usage RENAME TO _legacy_app_usage")
            try:
                cursor.execute("ALTER TABLE time_slots RENAME TO _legacy_time_slots")
            except sqlite3.OperationalError:
                pass
            self.conn.commit()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def add_task(self, name: str, color: str = '#4CAF50') -> int:
        cursor = self.conn.cursor()
        try:
            cursor.execute("INSERT INTO tasks (name, color) VALUES (?, ?)", (name, color))
            self.conn.commit()
            _log.info("Task added | id=%s | name=%s", cursor.lastrowid, name)
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            _log.warning("Task already exists | name=%s", name)
            return -1

    def delete_task(self, task_id: int) -> bool:
        cursor = self.conn.cursor()
        # Reset segments referencing this task to uncategorized
        cursor.execute("UPDATE activity_segments SET task_id = NULL WHERE task_id = ?", (task_id,))
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_all_tasks(self) -> List[Task]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, color, created_at FROM tasks ORDER BY id")
        rows = cursor.fetchall()
        return [Task(*r) for r in rows]

    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, color, created_at FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return Task(*row) if row else None

    def get_uncategorized_task_id(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE name = '未分类'")
        row = cursor.fetchone()
        return row[0] if row else 1

    # ------------------------------------------------------------------
    # Activity Segments — CRUD
    # ------------------------------------------------------------------

    def add_segment(self, date_str: str, start_time: str, end_time: str,
                    app_name: Optional[str] = None, is_idle: bool = False,
                    task_id: Optional[int] = None, source: str = 'auto',
                    description: str = '', window_title: str = '') -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO activity_segments
            (date, start_time, end_time, app_name, is_idle, task_id, source, description, window_title)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date_str, start_time, end_time, app_name,
              1 if is_idle else 0, task_id, source, description, window_title))
        self.conn.commit()
        return cursor.lastrowid

    def update_segment_end_time(self, seg_id: int, end_time: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE activity_segments SET end_time = ? WHERE id = ?",
            (end_time, seg_id)
        )
        self.conn.commit()

    def update_segment_task(self, seg_id: int, task_id: Optional[int]):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE activity_segments SET task_id = ? WHERE id = ?",
            (task_id, seg_id)
        )
        self.conn.commit()

    def update_segment_full(self, seg_id: int, start_time: str, end_time: str,
                            task_id: Optional[int], description: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE activity_segments
            SET start_time = ?, end_time = ?, task_id = ?, description = ?
            WHERE id = ?
        ''', (start_time, end_time, task_id, description, seg_id))
        self.conn.commit()

    def delete_segment(self, seg_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM activity_segments WHERE id = ?", (seg_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_segments_batch(self, seg_ids: list[int]) -> int:
        """Delete multiple segments in a single transaction for speed."""
        if not seg_ids:
            return 0
        cursor = self.conn.cursor()
        placeholders = ','.join('?' * len(seg_ids))
        cursor.execute(f"DELETE FROM activity_segments WHERE id IN ({placeholders})", seg_ids)
        self.conn.commit()
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Calendar Events
    # ------------------------------------------------------------------

    def get_calendar_events(self, date_str: str) -> List[tuple]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, color, label, created_at
            FROM calendar_events
            WHERE date = ?
            ORDER BY id
        ''', (date_str,))
        return cursor.fetchall()

    def add_calendar_event(self, date_str: str, color: str, label: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO calendar_events (date, color, label) VALUES (?, ?, ?)",
            (date_str, color, label)
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_calendar_event(self, event_id: int, color: str, label: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE calendar_events SET color = ?, label = ? WHERE id = ?",
            (color, label, event_id)
        )
        self.conn.commit()

    def delete_calendar_event(self, event_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
        self.conn.commit()

    def get_calendar_events_by_month(self, year: int, month: int) -> List[tuple]:
        month_str = f"{year}-{month:02d}"
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, color, label, created_at
            FROM calendar_events
            WHERE date LIKE ?
            ORDER BY date, id
        ''', (f"{month_str}%",))
        return cursor.fetchall()

    # ------------------------------------------------------------------
    # Projects / sections / notes
    # ------------------------------------------------------------------

    def get_all_projects(self) -> List[Project]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, name, color, sort_order, collapsed, created_at
            FROM projects ORDER BY sort_order, id
        ''')
        return [Project(*r) for r in cursor.fetchall()]

    def add_project(self, name: str = 'New Project', color: str = '#5B8DB8',
                    sort_order: int = 0, collapsed: int = 0) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO projects (name, color, sort_order, collapsed) VALUES (?, ?, ?, ?)
        ''', (name, color, sort_order, collapsed))
        self.conn.commit()
        return cursor.lastrowid

    def update_project(self, project_id: int, name: Optional[str] = None,
                       color: Optional[str] = None,
                       sort_order: Optional[int] = None,
                       collapsed: Optional[int] = None):
        cursor = self.conn.cursor()
        fields = []
        values = []
        if name is not None:
            fields.append("name = ?")
            values.append(name)
        if color is not None:
            fields.append("color = ?")
            values.append(color)
        if sort_order is not None:
            fields.append("sort_order = ?")
            values.append(sort_order)
        if collapsed is not None:
            fields.append("collapsed = ?")
            values.append(collapsed)
        if not fields:
            return
        values.append(project_id)
        cursor.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)
        self.conn.commit()

    def delete_project(self, project_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()

    def get_project_sections(self, project_id: int) -> List[ProjectSection]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, project_id, name, color, collapsed, sort_order
            FROM project_sections WHERE project_id = ?
            ORDER BY sort_order, id
        ''', (project_id,))
        return [ProjectSection(*r) for r in cursor.fetchall()]

    def add_project_section(self, project_id: int, name: str = 'New Section',
                            color: str = '#E3F2FD', sort_order: int = 0) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO project_sections (project_id, name, color, sort_order)
            VALUES (?, ?, ?, ?)
        ''', (project_id, name, color, sort_order))
        section_id = cursor.lastrowid
        cursor.execute('''
            INSERT INTO project_notes (section_id, content) VALUES (?, ?)
        ''', (section_id, ''))
        self.conn.commit()
        return section_id

    def update_project_section(self, section_id: int,
                               name: Optional[str] = None,
                               color: Optional[str] = None,
                               collapsed: Optional[int] = None,
                               sort_order: Optional[int] = None):
        cursor = self.conn.cursor()
        fields = []
        values = []
        if name is not None:
            fields.append("name = ?")
            values.append(name)
        if color is not None:
            fields.append("color = ?")
            values.append(color)
        if collapsed is not None:
            fields.append("collapsed = ?")
            values.append(collapsed)
        if sort_order is not None:
            fields.append("sort_order = ?")
            values.append(sort_order)
        if not fields:
            return
        values.append(section_id)
        cursor.execute(f"UPDATE project_sections SET {', '.join(fields)} WHERE id = ?", values)
        self.conn.commit()

    def delete_project_section(self, section_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM project_sections WHERE id = ?", (section_id,))
        self.conn.commit()

    def get_project_note(self, section_id: int) -> Optional[ProjectNote]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, section_id, content, updated_at
            FROM project_notes WHERE section_id = ?
        ''', (section_id,))
        row = cursor.fetchone()
        return ProjectNote(*row) if row else None

    def update_project_note(self, section_id: int, content: str):
        cursor = self.conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO project_notes (section_id, content, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(section_id) DO UPDATE SET content = ?, updated_at = ?
        ''', (section_id, content, now, content, now))
        self.conn.commit()

    def get_segments_by_date(self, date_str: str) -> List[ActivitySegment]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, start_time, end_time, app_name, task_id, is_idle, source, description, window_title
            FROM activity_segments
            WHERE date = ?
            ORDER BY start_time
        ''', (date_str,))
        rows = cursor.fetchall()
        return [ActivitySegment(*r) for r in rows]

    def get_segments_by_month(self, year: int, month: int) -> List[ActivitySegment]:
        month_str = f"{year}-{month:02d}"
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, start_time, end_time, app_name, task_id, is_idle, source, description, window_title
            FROM activity_segments
            WHERE date LIKE ?
            ORDER BY date, start_time
        ''', (f"{month_str}%",))
        rows = cursor.fetchall()
        return [ActivitySegment(*r) for r in rows]

    def get_segments_by_year(self, year: int) -> List[ActivitySegment]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, start_time, end_time, app_name, task_id, is_idle, source, description, window_title
            FROM activity_segments
            WHERE date LIKE ?
            ORDER BY date, start_time
        ''', (f"{year}%",))
        rows = cursor.fetchall()
        return [ActivitySegment(*r) for r in rows]

    # ------------------------------------------------------------------
    # Aggregations for Dashboard
    # ------------------------------------------------------------------

    def _merge_intervals_seconds(self, segments: List[ActivitySegment]) -> int:
        """Merge overlapping time intervals and return total unique active seconds."""
        # Extract (start_min, end_min) from non-idle segments
        intervals = []
        for s in segments:
            if s.is_idle:
                continue
            try:
                sm = int(s.start_time[:2]) * 60 + int(s.start_time[3:5])
                em = int(s.end_time[:2]) * 60 + int(s.end_time[3:5])
                if em > sm:
                    intervals.append((sm, em))
            except (ValueError, IndexError):
                continue
        if not intervals:
            return 0
        # Sort by start time
        intervals.sort(key=lambda x: x[0])
        # Merge overlapping intervals
        merged = [intervals[0]]
        for start, end in intervals[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                # Overlapping or adjacent, extend
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        # Sum durations
        return sum((end - start) * 60 for start, end in merged)

    def get_daily_summary(self, date_str: str) -> int:
        """Total unique active (non-idle) seconds for a day (deduplicated)."""
        segs = self.get_segments_by_date(date_str)
        return self._merge_intervals_seconds(segs)

    def get_daily_focus_total(self, date_str: str) -> int:
        """Sum of all non-idle segment durations (not deduplicated)."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COALESCE(SUM((julianday(end_time) - julianday(start_time)) * 86400), 0)
            FROM activity_segments
            WHERE date = ? AND is_idle = 0
        ''', (date_str,))
        result = cursor.fetchone()
        return int(result[0]) if result else 0

    def get_monthly_summary(self, year: int, month: int) -> Dict[str, int]:
        """Map date -> total unique active seconds (deduplicated per day)."""
        month_str = f"{year}-{month:02d}"
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT date, start_time, end_time, is_idle
            FROM activity_segments
            WHERE date LIKE ?
            ORDER BY date, start_time
        ''', (f"{month_str}%",))
        rows = cursor.fetchall()
        # Group by date
        from collections import defaultdict
        day_segments = defaultdict(list)
        for row in rows:
            day_segments[row[0]].append(ActivitySegment(
                id=0, date=row[0], start_time=row[1], end_time=row[2],
                app_name=None, task_id=None, is_idle=row[3],
                source='auto', description=''
            ))
        return {d: self._merge_intervals_seconds(day_segments[d]) for d in sorted(day_segments.keys())}

    def get_yearly_summary(self, year: int) -> Dict[str, int]:
        """Map month -> total unique active seconds (deduplicated)."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT substr(date, 6, 2) as month, start_time, end_time, is_idle
            FROM activity_segments
            WHERE date LIKE ?
            ORDER BY date, start_time
        ''', (f"{year}%",))
        rows = cursor.fetchall()
        from collections import defaultdict
        month_segments = defaultdict(list)
        for row in rows:
            month_segments[row[0]].append(ActivitySegment(
                id=0, date='', start_time=row[1], end_time=row[2],
                app_name=None, task_id=None, is_idle=row[3],
                source='auto', description=''
            ))
        return {m: self._merge_intervals_seconds(month_segments[m]) for m in sorted(month_segments.keys())}

    def get_weekly_summary(self, monday_date: date) -> Dict[str, int]:
        """Map date -> total unique active seconds for a week starting at monday_date."""
        from collections import defaultdict
        dates = [(monday_date + __import__('datetime').timedelta(days=i)).isoformat() for i in range(7)]
        placeholders = ','.join('?' * len(dates))
        cursor = self.conn.cursor()
        cursor.execute(f'''
            SELECT date, start_time, end_time, is_idle
            FROM activity_segments
            WHERE date IN ({placeholders})
            ORDER BY date, start_time
        ''', tuple(dates))
        rows = cursor.fetchall()
        day_segments = defaultdict(list)
        for row in rows:
            day_segments[row[0]].append(ActivitySegment(
                id=0, date=row[0], start_time=row[1], end_time=row[2],
                app_name=None, task_id=None, is_idle=row[3],
                source='auto', description=''
            ))
        result = {d: self._merge_intervals_seconds(day_segments[d]) for d in dates}
        return result

    def get_task_distribution(self, date_str: Optional[str] = None,
                               year: Optional[int] = None,
                               month: Optional[int] = None) -> Dict[str, int]:
        """Map task_name -> total active seconds."""
        cursor = self.conn.cursor()
        base_sql = '''
            SELECT t.name,
                   COALESCE(SUM((julianday(s.end_time) - julianday(s.start_time)) * 86400), 0)
            FROM activity_segments s
            LEFT JOIN tasks t ON s.task_id = t.id
            WHERE s.is_idle = 0
        '''
        if date_str:
            cursor.execute(base_sql + ' AND s.date = ? GROUP BY t.name', (date_str,))
        elif year and month:
            cursor.execute(base_sql + ' AND s.date LIKE ? GROUP BY t.name',
                           (f"{year}-{month:02d}%",))
        elif year:
            cursor.execute(base_sql + ' AND s.date LIKE ? GROUP BY t.name',
                           (f"{year}%",))
        else:
            cursor.execute(base_sql + ' GROUP BY t.name')
        return {row[0] or '未分类': int(row[1]) for row in cursor.fetchall()}

    def get_top_apps_by_date(self, date_str: str, limit: int = 10) -> List[Tuple[str, int]]:
        """Return [(app_name, total_seconds), ...] for a day."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT app_name,
                   COALESCE(SUM((julianday(end_time) - julianday(start_time)) * 86400), 0) as total_sec
            FROM activity_segments
            WHERE date = ? AND is_idle = 0 AND app_name IS NOT NULL
            GROUP BY app_name
            ORDER BY total_sec DESC
            LIMIT ?
        ''', (date_str, limit))
        return [(row[0], int(row[1])) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Quadrants
    # ------------------------------------------------------------------

    def get_quadrants(self) -> List[Quadrant]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, start_time, end_time, color, sort_order FROM quadrants ORDER BY sort_order")
        rows = cursor.fetchall()
        return [Quadrant(*r) for r in rows]

    def update_quadrant_times(self, qid: int, start_time: str, end_time: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE quadrants SET start_time = ?, end_time = ? WHERE id = ?",
            (start_time, end_time, qid)
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Quadrant Tasks
    # ------------------------------------------------------------------

    def get_quadrant_tasks(self, date_str: str, quadrant_id: int) -> List[QuadrantTask]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, quadrant_id, content, completed, created_at
            FROM quadrant_tasks
            WHERE date = ? AND quadrant_id = ?
            ORDER BY id
        ''', (date_str, quadrant_id))
        rows = cursor.fetchall()
        return [QuadrantTask(*r) for r in rows]

    def get_all_quadrant_tasks(self, date_str: str) -> List[QuadrantTask]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, quadrant_id, content, completed, created_at
            FROM quadrant_tasks
            WHERE date = ?
            ORDER BY quadrant_id, id
        ''', (date_str,))
        rows = cursor.fetchall()
        return [QuadrantTask(*r) for r in rows]

    def add_quadrant_task(self, date_str: str, quadrant_id: int, content: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO quadrant_tasks (date, quadrant_id, content) VALUES (?, ?, ?)",
            (date_str, quadrant_id, content)
        )
        self.conn.commit()
        return cursor.lastrowid

    def toggle_quadrant_task(self, task_id: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE quadrant_tasks SET completed = CASE WHEN completed = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (task_id,)
        )
        self.conn.commit()

    def delete_quadrant_task(self, task_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM quadrant_tasks WHERE id = ?", (task_id,))
        self.conn.commit()

    def update_quadrant_task(self, task_id: int, content: str, completed: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE quadrant_tasks SET content = ?, completed = ? WHERE id = ?",
            (content, completed, task_id)
        )
        self.conn.commit()

    def update_quadrant_task_content(self, task_id: int, content: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE quadrant_tasks SET content = ? WHERE id = ?",
            (content, task_id)
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value)
        )
        self.conn.commit()

    def update_segment_description(self, seg_id: int, description: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE activity_segments SET description = ? WHERE id = ?",
            (description, seg_id)
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Current task / indicator position (stored in settings)
    # ------------------------------------------------------------------

    def get_current_task(self) -> Optional[int]:
        val = self.get_setting('current_task_id')
        return int(val) if val else None

    def set_current_task(self, task_id: Optional[int]):
        if task_id is None:
            self.set_setting('current_task_id', '')
        else:
            self.set_setting('current_task_id', str(task_id))

    def get_indicator_pos(self) -> tuple[int, int]:
        x = self.get_setting('indicator_pos_x', '0')
        y = self.get_setting('indicator_pos_y', '0')
        try:
            return int(x), int(y)
        except ValueError:
            return 0, 0

    def set_indicator_pos(self, x: int, y: int):
        self.set_setting('indicator_pos_x', str(x))
        self.set_setting('indicator_pos_y', str(y))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        self.conn.close()
