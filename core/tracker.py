"""
Event-driven time-segment tracker
Runs in a background thread, polls every ~2 seconds.
Creates a new database segment whenever:
  - The foreground app changes (while user is active)
  - The user returns from idle to active
  - The day rolls over

Idle periods do NOT create segments — they are represented visually by gaps.
"""

import json
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from core.monitor import get_user_state
from core.database import Database
from utils.logger import get_logger

_log = get_logger("tracker")

# How often we poll the system state (seconds)
POLL_INTERVAL = 2.0

# Default idle threshold: 3 minutes of no keyboard/mouse
DEFAULT_IDLE_THRESHOLD_MS = 180_000


class Segment:
    """In-memory representation of one time segment"""
    def __init__(self, date_str: str, start_time: str, app_name: str,
                 is_idle: bool = False, task_id: Optional[int] = None,
                 source: str = 'auto', description: str = '',
                 window_title: str = ''):
        self.date_str = date_str
        self.start_time = start_time
        self.end_time = start_time          # updated in-place as time passes
        self.app_name = app_name
        self.is_idle = is_idle
        self.task_id = task_id
        self.source = source
        self.description = description
        self.window_title = window_title
        self.db_id: Optional[int] = None    # populated once written to DB


class UsageTracker:
    def __init__(self, poll_interval: float = POLL_INTERVAL,
                 idle_threshold_ms: int = DEFAULT_IDLE_THRESHOLD_MS):
        self.poll_interval = poll_interval
        self.idle_threshold_ms = idle_threshold_ms
        self.db = Database()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable] = []
        self._lock = threading.Lock()

        # Current segment state
        self._current_segment: Optional[Segment] = None
        self._last_state: Optional[dict] = None
        self._last_flush_time: float = 0.0

        # User-overridden current task (manual selection)
        self._manual_task_id: Optional[int] = self.db.get_current_task()

        # Context-aware task memory: maps "app_name::project_id" -> task_id
        # Allows each window/project to remember its own task independently
        self._context_tasks: dict[str, Optional[int]] = self._load_context_tasks()

        # When True, tracker pauses change detection (e.g. user interacting with indicator)
        self._paused = False
        _log.info("UsageTracker initialized | poll=%.1fs | idle_threshold=%d ms | manual_task=%s",
                  poll_interval, idle_threshold_ms, self._manual_task_id)

    def add_callback(self, callback: Callable):
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def set_current_task(self, task_id: Optional[int]):
        """Manually set the current task for the current window context."""
        with self._lock:
            self._manual_task_id = task_id
            self.db.set_current_task(task_id)

            # Store in context memory so this app/project remembers the task
            if self._current_segment:
                key = self._make_context_key(
                    self._current_segment.app_name,
                    self._current_segment.window_title
                )
                self._context_tasks[key] = task_id
                self._save_context_tasks()
                _log.info("Context task saved | key=%s | task_id=%s", key, task_id)

            _log.info("Manual task set | task_id=%s", task_id)
            # If we have an open active segment, update its task in-memory
            if self._current_segment and not self._current_segment.is_idle:
                self._current_segment.task_id = task_id

    def pause_polling(self):
        """Pause change detection while user interacts with UI (e.g. indicator)."""
        self._paused = True
        _log.debug("Tracker polling paused")

    def resume_polling(self):
        """Resume normal change detection."""
        self._paused = False
        _log.debug("Tracker polling resumed")



    def start(self):
        if self._running:
            _log.warning("start() called but tracker already running")
            return

        # FIX: if the DB connection was closed by a previous stop(), reopen it
        try:
            self.db.conn.execute("SELECT 1")
        except Exception:
            _log.warning("DB connection was closed, reopening...")
            try:
                self.db = Database()
            except Exception:
                _log.exception("Failed to reopen database connection")
                raise

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        _log.info("Tracker started | thread=%s", self._thread.name)

    def stop(self):
        _log.info("Tracker stopping...")
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.poll_interval + 2)
            _log.debug("Thread joined | alive=%s", self._thread.is_alive())
            self._thread = None
        # Close the final open segment
        self._close_current_segment()
        self.db.close()
        _log.info("Tracker stopped | DB connection closed")

    # ------------------------------------------------------------------
    # Public read-only accessors (thread-safe via copying)
    # ------------------------------------------------------------------

    def get_current_segment_summary(self) -> dict:
        """Return a snapshot of the current segment for UI display."""
        with self._lock:
            if self._current_segment is None:
                return {'app_name': 'Unknown', 'is_active': False,
                        'session_seconds': 0, 'is_idle': False, 'task_id': None}
            seg = self._current_segment
            now_str = datetime.now().strftime("%H:%M:%S")
            fmt = "%H:%M:%S"
            try:
                start_dt = datetime.strptime(seg.start_time, fmt)
                now_dt = datetime.strptime(now_str, fmt)
                elapsed = int((now_dt - start_dt).total_seconds())
            except ValueError:
                elapsed = 0
            return {
                'app_name': seg.app_name,
                'is_active': not seg.is_idle,
                'session_seconds': elapsed,
                'is_idle': seg.is_idle,
                'task_id': seg.task_id,
                'window_title': seg.window_title,
            }

    # ------------------------------------------------------------------
    # Task inference from window title
    # ------------------------------------------------------------------

    def _infer_task_from_title(self, app_name: str, window_title: str) -> Optional[int]:
        """Try to infer task from window title. Returns task_id or None."""
        if not window_title:
            return None

        # WeChat: never infer, leave as None (unclassified)
        if app_name and 'wechat' in app_name.lower():
            return None

        # VS Code: extract workspace name from title
        if app_name and app_name.lower() == 'code.exe':
            m = re.search(r'\s-\s(.+?)\s-\sVisual Studio Code$', window_title)
            if m:
                workspace_name = m.group(1).strip()
                return self._match_task_name(workspace_name)

        # Edge: keyword matching against task names
        if app_name and 'edge' in app_name.lower():
            return self._match_task_name(window_title)

        # WPS: extract filename from title
        if app_name and app_name.lower() in ('wps.exe', 'et.exe', 'wpp.exe'):
            m = re.search(r'^(.+?)\s-\sWPS', window_title)
            if m:
                filename = m.group(1).strip()
                return self._match_task_name(filename)

        return None

    def _match_task_name(self, text: str) -> Optional[int]:
        """Fuzzy match text against task names in DB."""
        text_norm = text.lower().replace(' ', '').replace('_', '').replace('-', '')
        tasks = self.db.get_all_tasks()
        for task in tasks:
            task_norm = task.name.lower().replace(' ', '').replace('_', '').replace('-', '')
            if task_norm in text_norm or text_norm in task_norm:
                return task.id
        return None

    def _extract_project_id(self, app_name: str, window_title: str) -> str:
        """Extract a stable project identifier from window title for change detection."""
        if not window_title:
            return ""
        if app_name and 'code' in app_name.lower():
            m = re.search(r'\s-\s(.+?)\s-\sVisual Studio Code$', window_title)
            if m:
                return m.group(1).strip()
        if app_name and 'wps' in app_name.lower():
            m = re.search(r'^(.+?)\s-\sWPS', window_title)
            if m:
                return m.group(1).strip()
        # For Edge and others, use the first meaningful part
        parts = window_title.split(' - ')
        if parts:
            return parts[0].strip()
        return window_title.strip()

    def _make_context_key(self, app_name: str, window_title: str) -> str:
        """Create a stable context key for per-window task memory."""
        project_id = self._extract_project_id(app_name, window_title)
        return f"{app_name}::{project_id}"

    def _load_context_tasks(self) -> dict:
        """Load persisted context tasks from DB settings."""
        try:
            raw = self.db.get_setting('context_tasks', '{}')
            data = json.loads(raw)
            return {k: (int(v) if v is not None else None) for k, v in data.items()}
        except Exception as e:
            _log.warning("Failed to load context tasks: %s", e)
            return {}

    def _save_context_tasks(self):
        """Persist context tasks to DB settings."""
        try:
            self.db.set_setting('context_tasks', json.dumps(self._context_tasks))
        except Exception as e:
            _log.warning("Failed to save context tasks: %s", e)

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def _loop(self):
        _log.debug("Tracker loop started")
        while self._running:
            time.sleep(self.poll_interval)
            if not self._running:
                break

            try:
                state = get_user_state(self.idle_threshold_ms)
            except Exception:
                _log.exception("get_user_state() failed")
                continue

            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")

            with self._lock:
                # Paused: just slide end_time, no state detection, no new segments
                if self._paused:
                    if self._current_segment:
                        self._current_segment.end_time = time_str
                    # Do NOT update _last_state here — keep it frozen at pre-pause
                    # so that resume doesn't trigger a false app switch
                    continue

                # 1. Day rollover -> close old, start new
                if self._current_segment and self._current_segment.date_str != date_str:
                    _log.info("Day rollover | %s -> %s", self._current_segment.date_str, date_str)
                    self._close_current_segment()
                    if state['is_active']:
                        self._start_new_segment(state, date_str, time_str)
                        self._notify_state_change(state)
                    self._last_state = state
                    continue

                # 2. First run (or after idle gap)
                if self._current_segment is None:
                    if state['is_active']:
                        self._start_new_segment(state, date_str, time_str)
                        self._notify_state_change(state)
                    self._last_state = state
                    continue

                # 3. Detect state changes
                last = self._last_state
                if last is None:
                    changed = True
                else:
                    app_changed = state['app_name'] != last['app_name']
                    active_changed = state['is_active'] != last['is_active']
                    # Detect window title changes within the same app (e.g. VS Code project switch)
                    project_changed = self._extract_project_id(
                        state['app_name'], state.get('window_title', '')
                    ) != self._extract_project_id(
                        last['app_name'], last.get('window_title', '')
                    )
                    changed = app_changed or active_changed or project_changed

                if changed:
                    # User went idle -> close segment, do NOT create new one
                    if not state['is_active']:
                        _log.debug(
                            "User went idle | app=%s | closing active segment",
                            state['app_name'],
                        )
                        self._current_segment.end_time = time_str
                        self._flush_segment(self._current_segment)
                        self._current_segment = None
                        self._notify_state_change(state)
                    # User returned from idle -> create new segment
                    elif not last['is_active']:
                        _log.debug(
                            "User returned from idle | app=%s | creating new segment",
                            state['app_name'],
                        )
                        self._start_new_segment(state, date_str, time_str)
                        self._notify_state_change(state)
                    # Active app switch -> end old, start new with inference
                    else:
                        _log.debug(
                            "App switch | %s -> %s",
                            last.get('app_name') if last else None,
                            state['app_name'],
                        )
                        self._current_segment.end_time = time_str
                        self._flush_segment(self._current_segment)
                        self._start_new_segment(state, date_str, time_str)
                        self._notify_state_change(state)

                else:
                    # Just bump the end time of the current open segment
                    self._current_segment.end_time = time_str
                    # Periodically flush to avoid losing data on crash
                    now_ts = time.time()
                    if now_ts - self._last_flush_time > 60:
                        self._flush_segment(self._current_segment)
                        self._last_flush_time = now_ts

                self._last_state = state
        _log.debug("Tracker loop exited")

    def _start_new_segment(self, state: dict, date_str: str, time_str: str):
        app = state['app_name']
        window_title = state.get('window_title', '')

        # Priority: context memory > auto inference > None (unclassified)
        # Each app/project remembers its own task independently
        key = self._make_context_key(app, window_title)
        if key in self._context_tasks:
            task_id = self._context_tasks[key]  # may be None = explicitly unclassified
            _log.debug("Context task restored | key=%s | task=%s", key, task_id)
        else:
            task_id = self._infer_task_from_title(app, window_title)

        # Keep manual_task_id in sync for current segment display
        self._manual_task_id = task_id

        seg = Segment(
            date_str=date_str,
            start_time=time_str,
            app_name=app,
            is_idle=False,
            task_id=task_id,
            source='auto',
            window_title=window_title,
        )
        self._current_segment = seg
        _log.debug(
            "New segment | %s %s | app=%s | task=%s | title=%.30s",
            date_str, time_str, app, task_id, window_title,
        )

    def _close_current_segment(self):
        with self._lock:
            if self._current_segment:
                now_str = datetime.now().strftime("%H:%M:%S")
                self._current_segment.end_time = now_str
                _log.debug(
                    "Closing segment | db_id=%s | end=%s",
                    self._current_segment.db_id, now_str,
                )
                self._flush_segment(self._current_segment)
                self._current_segment = None

    def _flush_segment(self, seg: Segment):
        """Write (or update) a segment in the DB."""
        # Ignore ultra-short segments (< 2 seconds) to reduce noise
        duration = self._segment_duration_seconds(seg)
        if duration < 2:
            _log.debug("Ignoring short segment | duration=%d s", duration)
            return

        try:
            if seg.db_id is None:
                seg.db_id = self.db.add_segment(
                    date_str=seg.date_str,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                    app_name=seg.app_name,
                    is_idle=seg.is_idle,
                    task_id=seg.task_id,
                    source=seg.source,
                    description=seg.description,
                    window_title=seg.window_title,
                )
                _log.info(
                    "INSERT segment | id=%s | %s %s-%s | app=%s | task=%s",
                    seg.db_id, seg.date_str, seg.start_time, seg.end_time,
                    seg.app_name, seg.task_id,
                )
            else:
                self.db.update_segment_end_time(seg.db_id, seg.end_time)
                _log.debug(
                    "UPDATE segment | id=%s | end=%s",
                    seg.db_id, seg.end_time,
                )
            self._last_flush_time = time.time()
        except Exception:
            _log.exception(
                "Failed to flush segment | db_id=%s | %s %s-%s | app=%s",
                seg.db_id, seg.date_str, seg.start_time, seg.end_time, seg.app_name,
            )
            raise

    @staticmethod
    def _segment_duration_seconds(seg: Segment) -> int:
        fmt = "%H:%M:%S"
        try:
            start_dt = datetime.strptime(seg.start_time, fmt)
            end_dt = datetime.strptime(seg.end_time, fmt)
            return int((end_dt - start_dt).total_seconds())
        except ValueError:
            return 0

    def _notify_state_change(self, state: dict):
        app = state['app_name'] if state['is_active'] else 'Idle'
        for cb in self._callbacks:
            try:
                cb(app)
            except Exception:
                _log.exception("Callback failed: %s", cb)
