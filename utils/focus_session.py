"""
Focus Session model
Groups contiguous active segments into focused work blocks.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from core.database import ActivitySegment
from utils.helpers import duration_between, time_to_minutes

# Gap threshold: if gap between segments exceeds this (seconds), start a new session
IDLE_GAP_THRESHOLD_SECONDS = 120  # 2 minutes


@dataclass
class FocusSession:
    """A contiguous block of active work time."""
    start_time: str       # "HH:MM:SS"
    end_time: str         # "HH:MM:SS"
    segments: List[ActivitySegment]

    @property
    def total_seconds(self) -> int:
        """Total duration of this session (sum of segment durations)."""
        return sum(duration_between(s.start_time, s.end_time) for s in self.segments)

    @property
    def task_durations(self) -> Dict[Optional[int], int]:
        """Map task_id -> total seconds within this session."""
        result: Dict[Optional[int], int] = {}
        for seg in self.segments:
            dur = duration_between(seg.start_time, seg.end_time)
            result[seg.task_id] = result.get(seg.task_id, 0) + dur
        return result

    @property
    def task_segment_counts(self) -> Dict[Optional[int], int]:
        """Map task_id -> number of segments within this session."""
        result: Dict[Optional[int], int] = {}
        for seg in self.segments:
            result[seg.task_id] = result.get(seg.task_id, 0) + 1
        return result

    @property
    def dominant_task_id(self) -> Optional[int]:
        """The task with the longest duration in this session."""
        td = self.task_durations
        if not td:
            return None
        return max(td.items(), key=lambda x: x[1])[0]

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def mean_segment_duration(self) -> int:
        """Average duration of each segment in seconds."""
        if not self.segments:
            return 0
        return self.total_seconds // len(self.segments)


def build_focus_sessions(segments: List[ActivitySegment],
                         gap_threshold: int = IDLE_GAP_THRESHOLD_SECONDS) -> List[FocusSession]:
    """Build FocusSession list from raw segments.

    Rules:
      - Skip idle segments
      - Sort by start_time
      - If gap to previous segment > gap_threshold, start new session
      - Otherwise merge into current session
    """
    active = [s for s in segments if not s.is_idle]
    if not active:
        return []

    sorted_segs = sorted(active, key=lambda s: time_to_minutes(s.start_time))
    sessions: List[FocusSession] = []
    current_segs = [sorted_segs[0]]

    for seg in sorted_segs[1:]:
        last = current_segs[-1]
        gap = duration_between(last.end_time, seg.start_time)
        if gap > gap_threshold:
            # Finish current session
            sessions.append(FocusSession(
                start_time=current_segs[0].start_time,
                end_time=current_segs[-1].end_time,
                segments=list(current_segs),
            ))
            current_segs = [seg]
        else:
            current_segs.append(seg)

    # Final session
    sessions.append(FocusSession(
        start_time=current_segs[0].start_time,
        end_time=current_segs[-1].end_time,
        segments=list(current_segs),
    ))

    return sessions
