"""
Dashboard with charts
"""

from datetime import date
from typing import Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QGridLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import matplotlib
matplotlib.use('QtAgg')
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib import cm as mpl_cm
from matplotlib.patches import FancyBboxPatch

from core.database import Database
from utils.i18n import trs
from utils.focus_session import build_focus_sessions

# Modern pie color palette
PIE_COLORS = [
    '#5B8DB8', '#E8927C', '#7EB5A6', '#D4A5A5', '#9B8AA5',
    '#F4C724', '#85C1E9', '#F8C471', '#82E0AA', '#D7BDE2',
    '#BB8FCE', '#F1948A', '#73C6B6', '#F7DC6F', '#AED6F1'
]
from utils.helpers import format_duration_short, get_app_display_name


class ChartCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi, tight_layout=True)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        self.setParent(parent)
        self.setStyleSheet("background-color: white;")


class DashboardWidget(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._refreshing = False
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #37474f;")
        header_layout.addWidget(self.title_label)

        self.period_combo = QComboBox()
        self.period_combo.setFixedWidth(130)
        self.period_combo.setStyleSheet("padding: 6px 10px; font-size: 13px;")
        self.period_combo.currentIndexChanged.connect(self.refresh)
        header_layout.addStretch()
        self.lbl_period = QLabel()
        header_layout.addWidget(self.lbl_period)
        header_layout.addWidget(self.period_combo)
        layout.addLayout(header_layout)

        # Summary cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)

        self.card_total = self._create_card("", "0m", "#3498db")
        self.card_segments = self._create_card("", "0", "#e74c3c")
        self.card_focus = self._create_card("", "-", "#2ecc71")

        cards_layout.addWidget(self.card_total)
        cards_layout.addWidget(self.card_segments)
        cards_layout.addWidget(self.card_focus)
        layout.addLayout(cards_layout)

        # Charts
        charts_layout = QGridLayout()
        charts_layout.setSpacing(15)

        self.chart_bar = ChartCanvas(self, width=6, height=4.5)
        self.chart_pie = ChartCanvas(self, width=6, height=4.5)

        self.bar_frame = self._create_chart_frame("", self.chart_bar)
        self.pie_frame = self._create_chart_frame("", self.chart_pie)

        charts_layout.addWidget(self.bar_frame, 0, 0)
        charts_layout.addWidget(self.pie_frame, 0, 1)
        layout.addLayout(charts_layout)

        self._retranslate_ui()

    def _retranslate_ui(self):
        self.title_label.setText(f"📈 {trs('work_stats_dashboard')}")
        self.lbl_period.setText(trs("stats_period"))
        current_idx = self.period_combo.currentIndex()
        self.period_combo.clear()
        self.period_combo.addItems([
            trs("today"), trs("this_week"), trs("this_month"), trs("this_year")
        ])
        if 0 <= current_idx < self.period_combo.count():
            self.period_combo.setCurrentIndex(current_idx)
        self._update_card_titles()
        self._update_chart_frame_titles()
        self.refresh()

    def _update_card_titles(self):
        self._set_card_title(self.card_total, trs("total_active_time"))
        self._set_card_title(self.card_segments, trs("num_blocks"))
        self._set_card_title(self.card_focus, trs("top_app"))

    def _set_card_title(self, frame: QFrame, title: str):
        lbl = frame.findChild(QLabel, "title")
        if lbl:
            lbl.setText(title)

    def _update_chart_frame_titles(self):
        self._set_chart_title(self.bar_frame, trs("app_time_distribution"))
        self._set_chart_title(self.pie_frame, trs("task_time_ratio"))

    def _set_chart_title(self, frame: QFrame, title: str):
        lbl = frame.findChild(QLabel, "chart_title")
        if lbl:
            lbl.setText(title)

    def _create_card(self, title: str, value: str, color: str) -> QFrame:
        # Outer frame for clean rounded card
        outer = QFrame()
        outer.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: none;
            }
        """)
        outer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer.setMinimumHeight(110)
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Left accent strip
        strip = QFrame()
        strip.setFixedWidth(4)
        strip.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: 2px;
            }}
        """)
        outer_layout.addWidget(strip)

        # Inner content
        frame = QFrame()
        frame.setStyleSheet("background-color: transparent; border: none;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 18, 14)
        layout.setSpacing(6)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("title")
        lbl_title.setStyleSheet("font-size: 12px; color: #90a4ae; font-weight: 500;")
        layout.addWidget(lbl_title)

        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {color};")
        lbl_value.setObjectName("value")
        layout.addWidget(lbl_value)

        outer_layout.addWidget(frame, 1)
        return outer

    def _create_chart_frame(self, title: str, canvas: ChartCanvas) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #f0f0f0;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        lbl = QLabel(title)
        lbl.setObjectName("chart_title")
        lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #37474f;")
        layout.addWidget(lbl)
        layout.addWidget(canvas, 1)

        return frame

    def _update_card(self, frame: QFrame, value: str):
        lbl = frame.findChild(QLabel, "value")
        if lbl:
            lbl.setText(value)

    def refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            period_idx = self.period_combo.currentIndex()
            today = date.today()

            if period_idx == 0:
                self._refresh_daily(today.isoformat())
            elif period_idx == 1:
                self._refresh_weekly(today)
            elif period_idx == 2:
                self._refresh_monthly(today.year, today.month)
            else:
                self._refresh_yearly(today.year)
        finally:
            self._refreshing = False

    def _refresh_daily(self, date_str: str):
        segments = self.db.get_segments_by_date(date_str)
        active_segments = [s for s in segments if not s.is_idle]
        sessions = build_focus_sessions(segments)
        focus_total = self.db.get_daily_focus_total(date_str)
        apps = self.db.get_top_apps_by_date(date_str, limit=10)

        self._update_card(self.card_total, format_duration_short(focus_total))
        self._update_card(self.card_segments, str(len(sessions)))
        focus = get_app_display_name(apps[0][0]) if apps else "-"
        self._update_card(self.card_focus, focus)

        # Bar chart: task time distribution
        ax = self.chart_bar.axes
        ax.clear()
        ax.set_facecolor('white')
        task_dist = self.db.get_task_distribution(date_str=date_str)
        if task_dist:
            names = list(task_dist.keys())
            values = [v / 60 for v in task_dist.values()]
            colors = [PIE_COLORS[i % len(PIE_COLORS)] for i in range(len(names))]
            bars = ax.barh(names[::-1], values[::-1], color=colors[::-1], height=0.6)
            ax.set_xlabel(trs("minutes"), fontsize=11, color='#607d8b')
            ax.set_title(trs("task_time_distribution"), fontsize=14, fontweight='bold', color='#37474f', pad=15)
            # Style spines & grid
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#e0e0e0')
            ax.spines['bottom'].set_color('#e0e0e0')
            ax.xaxis.grid(True, linestyle='--', alpha=0.4)
            ax.set_axisbelow(True)
            # Add value labels on bars
            for bar, val in zip(bars, values[::-1]):
                ax.text(val + max(values)*0.01, bar.get_y() + bar.get_height()/2,
                        f"{val:.0f}", va='center', fontsize=9, color='#607d8b')
        else:
            ax.text(0.5, 0.5, trs("no_data"), ha='center', va='center',
                    fontsize=14, color='#90a4ae', transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
        self.chart_bar.draw()

        # Pie chart: task distribution
        self._draw_task_pie(date_str=date_str)

    def _refresh_monthly(self, year: int, month: int):
        monthly = self.db.get_monthly_summary(year, month)
        segments = self.db.get_segments_by_month(year, month)
        active_seg = [s for s in segments if not s.is_idle]
        total = sum(monthly.values())
        apps: Dict[str, int] = {}
        for s in active_seg:
            if s.app_name:
                apps[s.app_name] = apps.get(s.app_name, 0) + self._seg_duration(s)
        top_app = get_app_display_name(max(apps, key=lambda k: apps[k])) if apps else "-"

        self._update_card(self.card_total, format_duration_short(total))
        self._update_card(self.card_segments, str(len(active_seg)))
        self._update_card(self.card_focus, top_app)

        # Bar chart: daily totals
        ax = self.chart_bar.axes
        ax.clear()
        ax.set_facecolor('white')
        if monthly:
            days = sorted(monthly.keys())
            values = [monthly[d] / 3600 for d in days]
            colors = ['#5B8DB8' if v > 0 else '#ecf0f1' for v in values]
            bars = ax.bar(range(len(days)), values, color=colors, width=0.65, edgecolor='white', linewidth=0.5)
            ax.set_xticks(range(len(days)))
            ax.set_xticklabels([d[-2:] for d in days], fontsize=9)
            ax.set_xlabel(trs("date"), fontsize=11, color='#607d8b')
            ax.set_ylabel(trs("hours"), fontsize=11, color='#607d8b')
            ax.set_title(f"{year}-{month:02d} {trs('daily_work_time')}", fontsize=14, fontweight='bold', color='#37474f', pad=15)
            # Style
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#e0e0e0')
            ax.spines['bottom'].set_color('#e0e0e0')
            ax.yaxis.grid(True, linestyle='--', alpha=0.4)
            ax.set_axisbelow(True)
            # Value labels on top of bars
            for bar, val in zip(bars, values):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width()/2, val + max(values)*0.01,
                            f"{val:.1f}", ha='center', fontsize=8, color='#607d8b')
        else:
            ax.text(0.5, 0.5, trs("no_data"), ha='center', va='center',
                    fontsize=14, color='#90a4ae', transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
        self.chart_bar.draw()

        self._draw_task_pie(year=year, month=month)

    def _refresh_weekly(self, today: date):
        # Calculate Monday of this week
        monday = today - __import__('datetime').timedelta(days=today.weekday())
        weekly = self.db.get_weekly_summary(monday)
        # Query all segments in the week for app aggregation
        dates = [(monday + __import__('datetime').timedelta(days=i)).isoformat() for i in range(7)]
        all_segs = []
        for d in dates:
            all_segs.extend(self.db.get_segments_by_date(d))
        active_seg = [s for s in all_segs if not s.is_idle]
        total = sum(weekly.values())
        apps: Dict[str, int] = {}
        for s in active_seg:
            if s.app_name:
                apps[s.app_name] = apps.get(s.app_name, 0) + self._seg_duration(s)
        top_app = get_app_display_name(max(apps, key=lambda k: apps[k])) if apps else "-"

        self._update_card(self.card_total, format_duration_short(total))
        self._update_card(self.card_segments, str(len(active_seg)))
        self._update_card(self.card_focus, top_app)

        # Bar chart: daily totals for the week
        ax = self.chart_bar.axes
        ax.clear()
        ax.set_facecolor('white')
        if weekly:
            days = [trs("monday"), trs("tuesday"), trs("wednesday"),
                    trs("thursday"), trs("friday"), trs("saturday"), trs("sunday")]
            day_keys = [(monday + __import__('datetime').timedelta(days=i)).isoformat() for i in range(7)]
            values = [weekly.get(d, 0) / 3600 for d in day_keys]
            colors = ['#5B8DB8' if v > 0 else '#ecf0f1' for v in values]
            bars = ax.bar(days, values, color=colors, width=0.6, edgecolor='white', linewidth=0.5)
            ax.set_ylabel(trs("hours"), fontsize=11, color='#607d8b')
            ax.set_title(trs("weekly_work_time_from").format(monday.isoformat()), fontsize=14, fontweight='bold', color='#37474f', pad=15)
            # Style
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#e0e0e0')
            ax.spines['bottom'].set_color('#e0e0e0')
            ax.yaxis.grid(True, linestyle='--', alpha=0.4)
            ax.set_axisbelow(True)
            # Value labels
            for bar, val in zip(bars, values):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width()/2, val + max(values)*0.01,
                            f"{val:.1f}", ha='center', fontsize=9, color='#607d8b')
        else:
            ax.text(0.5, 0.5, trs("no_data"), ha='center', va='center',
                    fontsize=14, color='#90a4ae', transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
        self.chart_bar.draw()

        # Task pie for the week
        self._draw_task_pie(date_str=monday.isoformat())  # fallback: pie for Monday only
        # Better: aggregate task distribution for the whole week
        self._draw_task_pie_for_week(monday)

    def _draw_task_pie_for_week(self, monday: date):
        """Draw task distribution pie chart for the whole week."""
        dates = [(monday + __import__('datetime').timedelta(days=i)).isoformat() for i in range(7)]
        cursor = self.db.conn.cursor()
        placeholders = ','.join('?' * len(dates))
        cursor.execute(f'''
            SELECT t.name,
                   COALESCE(SUM((julianday(s.end_time) - julianday(s.start_time)) * 86400), 0)
            FROM activity_segments s
            LEFT JOIN tasks t ON s.task_id = t.id
            WHERE s.date IN ({placeholders}) AND s.is_idle = 0
            GROUP BY t.name
        ''', tuple(dates))
        dist = {row[0] or trs('unclassified'): int(row[1]) for row in cursor.fetchall()}
        self._draw_donut(dist, trs("weekly_task_ratio"))

    def _refresh_yearly(self, year: int):
        yearly = self.db.get_yearly_summary(year)
        segments = self.db.get_segments_by_year(year)
        active_seg = [s for s in segments if not s.is_idle]
        total = sum(yearly.values())
        apps: Dict[str, int] = {}
        for s in active_seg:
            if s.app_name:
                apps[s.app_name] = apps.get(s.app_name, 0) + self._seg_duration(s)
        top_app = get_app_display_name(max(apps, key=lambda k: apps[k])) if apps else "-"

        self._update_card(self.card_total, format_duration_short(total))
        self._update_card(self.card_segments, str(len(active_seg)))
        self._update_card(self.card_focus, top_app)

        # Bar chart: monthly totals
        ax = self.chart_bar.axes
        ax.clear()
        ax.set_facecolor('white')
        if yearly:
            months = [f"{i:02d}" for i in range(1, 13)]
            values = [yearly.get(m, 0) / 3600 for m in months]
            colors = ['#5B8DB8' if v > 0 else '#ecf0f1' for v in values]
            bars = ax.bar(months, values, color=colors, width=0.6, edgecolor='white', linewidth=0.5)
            ax.set_xlabel(trs("month"), fontsize=11, color='#607d8b')
            ax.set_ylabel(trs("hours"), fontsize=11, color='#607d8b')
            ax.set_title(f"{year} {trs('monthly_work_time')}", fontsize=14, fontweight='bold', color='#37474f', pad=15)
            # Style
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#e0e0e0')
            ax.spines['bottom'].set_color('#e0e0e0')
            ax.yaxis.grid(True, linestyle='--', alpha=0.4)
            ax.set_axisbelow(True)
            # Value labels
            for bar, val in zip(bars, values):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width()/2, val + max(values)*0.01,
                            f"{val:.1f}", ha='center', fontsize=8, color='#607d8b')
        else:
            ax.text(0.5, 0.5, trs("no_data"), ha='center', va='center',
                    fontsize=14, color='#90a4ae', transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
        self.chart_bar.draw()

        self._draw_task_pie(year=year)

    def _draw_task_pie(self, date_str=None, year=None, month=None, center_text=None):
        dist = self.db.get_task_distribution(date_str=date_str, year=year, month=month)
        title = trs("task_time_ratio")
        if year and not month:
            title = f"{year} {trs('task_time_ratio')}"
        elif year and month:
            title = f"{year}-{month:02d} {trs('task_time_ratio')}"
        self._draw_donut(dist, title, center_text)

    def _draw_donut(self, dist: Dict[str, int], title: str, center_text: str = None):
        """Draw a modern donut chart with the given task distribution."""
        ax = self.chart_pie.axes
        ax.clear()
        ax.set_facecolor('white')
        for spine in ax.spines.values():
            spine.set_visible(False)

        if not dist:
            ax.text(0.5, 0.5, trs("no_data"), ha='center', va='center',
                    fontsize=14, color='#90a4ae', transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            self.chart_pie.draw()
            return

        labels = list(dist.keys())
        sizes = [v / 60 for v in dist.values()]  # minutes
        total = sum(sizes)

        colors = [PIE_COLORS[i % len(PIE_COLORS)] for i in range(len(labels))]

        # Threshold for showing labels/percentages on small slices
        LABEL_PCT_THRESHOLD = 5.0

        # Explode the largest slice slightly
        max_idx = sizes.index(max(sizes))
        explode = [0.04 if i == max_idx else 0 for i in range(len(sizes))]

        # Calculate percentages to decide which labels to show
        percentages = [(s / total * 100) if total > 0 else 0 for s in sizes]

        # Only show outer label for slices >= threshold
        outer_labels = [
            f"{l}\n{s:.0f}min" if p >= LABEL_PCT_THRESHOLD else ""
            for l, s, p in zip(labels, sizes, percentages)
        ]

        # Draw donut with internal percentages + external labels
        wedges, texts, autotexts = ax.pie(
            sizes,
            explode=explode,
            labels=outer_labels,
            autopct=lambda pct: f"{pct:.1f}%" if pct >= LABEL_PCT_THRESHOLD else "",
            pctdistance=0.76,
            labeldistance=1.18,
            colors=colors,
            startangle=90,
            shadow=False,
            wedgeprops=dict(width=0.5, edgecolor='white', linewidth=2.5),
            textprops=dict(color='#37474f', fontsize=9),
        )

        # Style internal percentage text: white bold
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(9)
            autotext.set_fontweight('bold')

        # Style external labels
        for text in texts:
            text.set_fontsize(9)
            text.set_color('#37474f')

        # Center text: big total + small subtitle
        if center_text is None:
            center_text = f"{total:.0f}{trs('total_minutes')}"
        ax.text(0, 0.06, center_text, ha='center', va='center',
                fontsize=20, fontweight='bold', color='#37474f')
        ax.text(0, -0.14, trs("focus_total"), ha='center', va='center',
                fontsize=11, color='#90a4ae')

        ax.set_title(title, fontsize=15, fontweight='bold', color='#37474f', pad=18)
        self.chart_pie.draw()

    @staticmethod
    def _seg_duration(seg) -> int:
        """Helper to compute segment duration in seconds."""
        from utils.helpers import duration_between
        return duration_between(seg.start_time, seg.end_time)
