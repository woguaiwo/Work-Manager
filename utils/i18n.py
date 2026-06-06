"""
Internationalization (i18n) module
Single global translator with language-change signal.
Usage:
    from utils.i18n import tr, set_language, language_changed
    btn.setText(tr("save"))
    language_changed.connect(on_language_changed)
"""

from PyQt6.QtCore import QObject, pyqtSignal


class _I18nManager(QObject):
    language_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._lang = "zh"
        self._translations = {
            "zh": {
                # --- main_window ---
                "app_title": "工作管理系统",
                "timeline": "时间线",
                "dashboard": "仪表盘",
                "weekly_plan": "周计划",
                "calendar": "日历",
                "task_management": "任务管理",
                "settings": "设置",
                "pause_recording": "暂停记录",
                "start_recording": "开始记录",
                "current_app": "当前应用",
                "current_app_detecting": "当前应用: 检测中...",
                "current_app_paused": "当前应用: --\n状态: 已暂停",
                "status_idle": "状态: 空闲 | 已暂停计时",
                "status_active": "状态: 活跃 | 本次会话: {}",
                "status_detecting": "状态: 检测中...",
                "today_active": "今日活跃: {}",
                "day_active": "当日活跃: {}",
                "error": "错误",
                "start_tracking_failed": "启动追踪失败，请查看日志文件。",
                "app_running": "{} - 运行中",
                "app_paused": "{} - 已暂停",
                "show_main_window": "显示主窗口",
                "quit": "退出",
                "tray_minimized_title": "工作记录",
                "tray_minimized_msg": "程序已最小化到系统托盘，后台继续运行",
                "feature_in_development": "功能开发中...",
                "current_time": "当前时间",
                "focus_session_detail": "专注时段详情",
                "task_breakdown": "任务分布",
                "segments": "片段数",
                "mean_segment": "平均片段",
                "avg_seg": "平均段长",
                "view_details": "查看详情",
                "focus_total": "专注总时长",
                "task_time_distribution": "任务时长分布",
                "preview": "预览",
                "delete_task": "删除任务",
                "edit": "编辑",
                "delete": "删除",
                "confirm": "确认",
                "delete_this_block": "删除这个时间段?",
                "batch_delete": "批量删除 ({} 个)",
                "delete_selected_blocks": "删除选中的 {} 个时间段?",
                # --- project_indicator ---
                "select_current_task": "选择当前任务",
                "unclassified": "未分类",
                "paused": "已暂停",
                "idle": "空闲中",
                "open_main_window": "打开主窗口",
                # --- timeline_container ---
                "prev_day": "前一天",
                "today_btn": "今天",
                "next_day": "后一天",
                "date_label": "日期:",
                # --- timeline_view ---
                "notes": "备注",
                "quadrant_todo": "象限待办",
                "edit_time_block": "编辑时间段",
                "new_time_block": "新建时间段",
                "start": "开始:",
                "end": "结束:",
                "task_label": "任务:",
                "unclassified_task": "-- 未分类 --",
                "write_something": "写点什么...",
                "save": "保存",
                "cancel": "取消",
                "tip": "提示",
                "end_time_must_be_after_start": "结束时间必须晚于开始时间",
                "edit_notes": "编辑备注",
                "add_quadrant_task": "添加象限任务",
                "enter_task_content": "输入任务内容...",
                "enter_task": "输入任务...",
                # --- dashboard ---
                "work_stats_dashboard": "工作统计仪表盘",
                "stats_period": "统计周期:",
                "today": "今日",
                "this_week": "本周",
                "this_month": "本月",
                "this_year": "本年",
                "total_active_time": "专注总时长",
                "num_blocks": "专注时段",
                "top_app": "最长应用",
                "app_time_distribution": "应用时长分布",
                "task_time_ratio": "任务时间比重",
                "app_usage_top10": "应用使用时长 (Top 10)",
                "minutes": "分钟",
                "no_data": "暂无数据",
                "date": "日期",
                "hours": "小时",
                "daily_work_time": "每日工作时长",
                "monday": "周一",
                "tuesday": "周二",
                "wednesday": "周三",
                "thursday": "周四",
                "friday": "周五",
                "saturday": "周六",
                "sunday": "周日",
                "weekly_work_time_from": "本周工作时长 ({}起)",
                "month": "月份",
                "monthly_work_time": "每月工作时长",
                "total_minutes": "分钟",
                "task_category": "任务分类",
                "weekly_task_ratio": "本周任务时间比重",
                # --- calendar_widget ---
                "add_task": "+ 添加任务",
                "calendar_markers": "日历标注",
                "enter_marker_placeholder": "输入标注内容，如：考试、出差...",
                "add": "+ 添加",
                "pick_color": "点击选择颜色",
                "delete_marker": "删除此标注",
                "del": "Del",
                "year_month": "{}年 {}月",
                "more_events": "等{}个",
                "quadrant_plan": "象限规划",
                "calendar_markers_tip": "📌 日历标注:",
                # --- task_dialog ---
                "manage_task_categories": "管理你的任务分类",
                "create_task_tags_desc": "为不同的工作内容创建任务标签，方便后续统计和分析时间分配。",
                "enter_new_task_name": "输入新任务名称...",
                "pick_color_short": "选择颜色",
                "add_task_short": "添加",
                "delete_selected": "删除选中",
                "close": "关闭",
                "enter_task_name": "请输入任务名称",
                "unclassified_system_default": "'未分类' 是系统默认任务，不能重复创建",
                "task_exists": "任务 '{}' 已存在",
                "select_task_first": "请先选择一个任务",
                "unclassified_cannot_delete": "默认任务 '未分类' 不能删除",
                "confirm_delete": "确认删除",
                "delete_task_warning": "确定要删除任务 '{}' 吗？\n注意：已分配的时间记录将被重置为'未分类'。",
                # --- helpers app names ---
                "file_explorer": "文件资源管理器",
                "notepad": "记事本",
                "command_prompt": "命令提示符",
                "wechat": "微信",
                "dingtalk": "钉钉",
                "feishu": "飞书",
                "work_manager": "工作管理系统",
                # --- settings dialog ---
                "language": "语言",
                "chinese": "中文",
                "english": "English",
            },
            "en": {
                # --- main_window ---
                "app_title": "Work Manager",
                "timeline": "Timeline",
                "dashboard": "Dashboard",
                "weekly_plan": "Weekly Plan",
                "calendar": "Calendar",
                "task_management": "Task Management",
                "settings": "Settings",
                "pause_recording": "Pause Recording",
                "start_recording": "Start Recording",
                "current_app": "Current App",
                "current_app_detecting": "Current App: Detecting...",
                "current_app_paused": "Current App: --\nStatus: Paused",
                "status_idle": "Status: Idle | Timer Paused",
                "status_active": "Status: Active | Session: {}",
                "status_detecting": "Status: Detecting...",
                "today_active": "Today's Active: {}",
                "day_active": "Day's Active: {}",
                "error": "Error",
                "start_tracking_failed": "Failed to start tracking. Please check the log file.",
                "app_running": "{} - Running",
                "app_paused": "{} - Paused",
                "show_main_window": "Show Main Window",
                "quit": "Quit",
                "tray_minimized_title": "Work Recorder",
                "tray_minimized_msg": "Minimized to system tray. Running in background.",
                "feature_in_development": "Feature in development...",
                "current_time": "Current Time",
                "focus_session_detail": "Focus Session Detail",
                "task_breakdown": "Task Breakdown",
                "segments": "Segments",
                "mean_segment": "Mean Segment",
                "avg_seg": "Avg Seg",
                "view_details": "View Details",
                "focus_total": "Focus Total",
                "task_time_distribution": "Task Time Distribution",
                "preview": "Preview",
                "delete_task": "Delete Task",
                "edit": "Edit",
                "delete": "Delete",
                "confirm": "Confirm",
                "delete_this_block": "Delete this time block?",
                "batch_delete": "Batch Delete ({} blocks)",
                "delete_selected_blocks": "Delete {} selected time blocks?",
                # --- project_indicator ---
                "select_current_task": "Select Current Task",
                "unclassified": "Unclassified",
                "paused": "Paused",
                "idle": "Idle",
                "open_main_window": "Open Main Window",
                # --- timeline_container ---
                "prev_day": "Previous Day",
                "today_btn": "Today",
                "next_day": "Next Day",
                "date_label": "Date:",
                # --- timeline_view ---
                "notes": "Notes",
                "quadrant_todo": "Quadrant Todo",
                "edit_time_block": "Edit Time Block",
                "new_time_block": "New Time Block",
                "start": "Start:",
                "end": "End:",
                "task_label": "Task:",
                "unclassified_task": "-- Unclassified --",
                "write_something": "Write something...",
                "save": "Save",
                "cancel": "Cancel",
                "tip": "Tip",
                "end_time_must_be_after_start": "End time must be after start time",
                "edit_notes": "Edit Notes",
                "add_quadrant_task": "Add Quadrant Task",
                "enter_task_content": "Enter task content...",
                "enter_task": "Enter task...",
                # --- dashboard ---
                "work_stats_dashboard": "Work Statistics Dashboard",
                "stats_period": "Stats Period:",
                "today": "Today",
                "this_week": "This Week",
                "this_month": "This Month",
                "this_year": "This Year",
                "total_active_time": "Focus Total",
                "num_blocks": "Focus Sessions",
                "top_app": "Top App",
                "app_time_distribution": "App Time Distribution",
                "task_time_ratio": "Task Time Ratio",
                "app_usage_top10": "App Usage (Top 10)",
                "minutes": "Minutes",
                "no_data": "No Data",
                "date": "Date",
                "hours": "Hours",
                "daily_work_time": "Daily Work Time",
                "monday": "Mon",
                "tuesday": "Tue",
                "wednesday": "Wed",
                "thursday": "Thu",
                "friday": "Fri",
                "saturday": "Sat",
                "sunday": "Sun",
                "weekly_work_time_from": "Weekly Work Time (from {})",
                "month": "Month",
                "monthly_work_time": "Monthly Work Time",
                "total_minutes": "min",
                "task_category": "Task Category",
                "weekly_task_ratio": "Weekly Task Time Ratio",
                # --- calendar_widget ---
                "add_task": "+ Add Task",
                "calendar_markers": "Calendar Markers",
                "enter_marker_placeholder": "Enter marker, e.g., exam, trip...",
                "add": "+ Add",
                "pick_color": "Click to pick color",
                "delete_marker": "Delete this marker",
                "del": "Del",
                "year_month": "{} {}",
                "more_events": "+{} more",
                "quadrant_plan": "Quadrant Plan",
                "calendar_markers_tip": "📌 Markers:",
                # --- task_dialog ---
                "manage_task_categories": "Manage Task Categories",
                "create_task_tags_desc": "Create task tags for different work contents to track and analyze time allocation.",
                "enter_new_task_name": "Enter new task name...",
                "pick_color_short": "Pick Color",
                "add_task_short": "Add",
                "delete_selected": "Delete Selected",
                "close": "Close",
                "enter_task_name": "Please enter a task name",
                "unclassified_system_default": "'Unclassified' is a system default task and cannot be duplicated",
                "task_exists": "Task '{}' already exists",
                "select_task_first": "Please select a task first",
                "unclassified_cannot_delete": "Default task 'Unclassified' cannot be deleted",
                "confirm_delete": "Confirm Delete",
                "delete_task_warning": "Are you sure you want to delete task '{}'?\nNote: Assigned time records will be reset to 'Unclassified'.",
                # --- helpers app names ---
                "file_explorer": "File Explorer",
                "notepad": "Notepad",
                "command_prompt": "Command Prompt",
                "wechat": "WeChat",
                "dingtalk": "DingTalk",
                "feishu": "Feishu",
                "work_manager": "Work Manager",
                # --- settings dialog ---
                "language": "Language",
                "chinese": "中文",
                "english": "English",
            },
        }

    def set_language(self, lang: str):
        if lang != self._lang and lang in self._translations:
            self._lang = lang
            self.language_changed.emit(lang)

    def tr(self, key: str, *args, **kwargs) -> str:
        text = self._translations.get(self._lang, {}).get(key, key)
        if args or kwargs:
            try:
                return text.format(*args, **kwargs)
            except (KeyError, IndexError):
                pass
        return text

    def current_lang(self) -> str:
        return self._lang


# Global singleton instance
_i18n = _I18nManager()

trs = _i18n.tr  # renamed to avoid conflict with PyQt's tr
set_language = _i18n.set_language
current_lang = _i18n.current_lang
language_changed = _i18n.language_changed


_QUADRANT_NAME_MAP = {
    'zh': {},
    'en': {
        'Q1 上午': 'Q1 Morning',
        'Q2 下午': 'Q2 Afternoon',
        'Q3 晚上': 'Q3 Evening',
        'Q4 深夜': 'Q4 Night',
    }
}


def tr_quadrant_name(name: str) -> str:
    """Translate default quadrant names; leave custom names untouched."""
    return _QUADRANT_NAME_MAP.get(current_lang(), {}).get(name, name)


def tr_list(key: str) -> list:
    """Return a list of translated strings for keys like day_names_0..6."""
    result = []
    i = 0
    while True:
        item_key = f"{key}_{i}"
        text = trs(item_key)
        if text == item_key:
            break
        result.append(text)
        i += 1
    return result
