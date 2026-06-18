"""
Projects page with rich-text notes organized into collapsible sections.
"""
import random
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTextEdit, QLineEdit, QComboBox,
    QSizePolicy, QApplication, QMessageBox, QToolButton, QMenu,
    QColorDialog, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QAction, QTextCharFormat, QTextCursor, QKeyEvent,
    QTextListFormat, QTextBlockFormat, QTextFormat
)

from core.database import Database, Project, ProjectSection
from utils.i18n import trs
from utils.logger import get_logger

_log = get_logger("projects")

SECTION_PALETTE = [
    "#E3F2FD", "#F3E5F5", "#E8F5E9", "#FFF3E0",
    "#FFEBEE", "#E0F7FA", "#FBE9E7", "#F1F8E9",
]

PROJECT_PALETTE = [
    "#5B8DB8", "#7E57C2", "#43A047", "#FB8C00",
    "#E53935", "#00897B", "#3949AB", "#D81B60",
]


class NoteEditor(QTextEdit):
    """Rich-text editor with toolbar and tab-to-spaces behavior."""

    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: none;
                padding: 8px;
                font-size: 13px;
                line-height: 1.4;
            }
        """)
        self.textChanged.connect(self.content_changed.emit)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Tab and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.insertPlainText("        ")
            return
        super().keyPressEvent(event)


class SectionWidget(QFrame):
    """Collapsible section containing a colored header and a note editor."""

    renamed = pyqtSignal(int, str)
    deleted = pyqtSignal(int)

    SAVE_DELAY_MS = 2000

    def __init__(self, db: Database, section: ProjectSection, parent=None):
        super().__init__(parent)
        self.db = db
        self.section_id = section.id
        self._collapsed = bool(section.collapsed)
        self._color = section.color or SECTION_PALETTE[0]
        self._name = section.name or trs("new_section")
        self._pending_content: Optional[str] = None
        self._setup_ui()
        self._load_note()

    def _setup_ui(self):
        self.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        # Header
        self.header = QFrame()
        self.header.setFixedHeight(32)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet(f"""
            QFrame {{
                background-color: {self._color};
                border-radius: 6px;
            }}
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 0, 4, 0)
        header_layout.setSpacing(4)

        self.lbl_toggle = QLabel("▾" if not self._collapsed else "▸")
        self.lbl_toggle.setStyleSheet("font-size: 12px; color: #37474f;")
        header_layout.addWidget(self.lbl_toggle)

        self.lbl_name = QLabel(self._name)
        self.lbl_name.setStyleSheet("font-size: 12px; font-weight: bold; color: #37474f;")
        self.lbl_name.setWordWrap(False)
        header_layout.addWidget(self.lbl_name)
        header_layout.addStretch()

        self.btn_delete = QToolButton()
        self.btn_delete.setText("×")
        self.btn_delete.setStyleSheet("""
            QToolButton {
                border: none;
                color: #37474f;
                font-size: 14px;
                font-weight: bold;
            }
            QToolButton:hover { color: #e53935; }
        """)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self._request_delete)
        header_layout.addWidget(self.btn_delete)

        self.header.mousePressEvent = self._on_header_click
        self.header.mouseDoubleClickEvent = self._on_header_double_click

        layout.addWidget(self.header)

        # Toolbar
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(4)
        self.toolbar.setContentsMargins(4, 4, 4, 0)

        self._make_tool_btn(trs("fmt_bold"), self._toggle_bold, "font-weight: bold;")
        self._make_tool_btn(trs("fmt_italic"), self._toggle_italic, "font-style: italic;")
        self._make_tool_btn(trs("fmt_color"), self._set_text_color, "")
        self._make_tool_btn(trs("fmt_highlight"), self._set_highlight_color, "")
        self._make_tool_btn(trs("fmt_list"), self._toggle_bullet_list, "")

        toolbar_widget = QWidget()
        toolbar_widget.setLayout(self.toolbar)
        toolbar_widget.setVisible(not self._collapsed)
        self.toolbar_widget = toolbar_widget
        layout.addWidget(toolbar_widget)

        # Editor
        self.editor = NoteEditor()
        self.editor.setVisible(not self._collapsed)
        self.editor.content_changed.connect(self._on_content_changed)
        self.editor.focusOutEvent = self._on_editor_focus_out
        layout.addWidget(self.editor)

        # Save timer must exist before any setHtml can fire textChanged
        self._init_save_timer()

    def _init_save_timer(self):
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_save)

    def _on_content_changed(self):
        self._pending_content = self.editor.toHtml()
        self._save_timer.stop()
        self._save_timer.start(self.SAVE_DELAY_MS)

    def _on_editor_focus_out(self, event):
        # Save immediately when user leaves the editor
        self._flush_save()
        QTextEdit.focusOutEvent(self.editor, event)

    def _flush_save(self):
        self._save_timer.stop()
        if self._pending_content is not None:
            self.db.update_project_note(self.section_id, self._pending_content)
            self._pending_content = None

    def _save_note(self):
        # Kept for explicit save calls; debounced path uses _on_content_changed
        self.db.update_project_note(self.section_id, self.editor.toHtml())

    def _make_tool_btn(self, text: str, callback, style: str):
        btn = QPushButton(text)
        base_style = """
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                color: #37474f;
                min-width: 36px;
            }
            QPushButton:hover { background-color: #e0e0e0; }
            QPushButton:pressed { background-color: #d0d0d0; }
        """
        btn.setStyleSheet(base_style + style)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(24)
        btn.clicked.connect(callback)
        self.toolbar.addWidget(btn)

    def _is_selection_bold(self) -> bool:
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            fmt = cursor.charFormat()
            return fmt.fontWeight() == QFont.Weight.Bold
        return self.editor.fontWeight() == QFont.Weight.Bold

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(
            QFont.Weight.Normal if self._is_selection_bold() else QFont.Weight.Bold
        )
        self.editor.mergeCurrentCharFormat(fmt)

    def _is_selection_italic(self) -> bool:
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            return cursor.charFormat().fontItalic()
        return self.editor.fontItalic()

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self._is_selection_italic())
        self.editor.mergeCurrentCharFormat(fmt)

    def _set_text_color(self):
        color = QColorDialog.getColor(Qt.GlobalColor.black, self)
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self.editor.mergeCurrentCharFormat(fmt)

    def _set_highlight_color(self):
        color = QColorDialog.getColor(QColor("#FFEB3B"), self)
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self.editor.mergeCurrentCharFormat(fmt)

    def _toggle_bullet_list(self):
        cursor = self.editor.textCursor()
        if cursor.currentList():
            cursor.setBlockFormat(QTextBlockFormat())
        else:
            list_fmt = QTextListFormat()
            list_fmt.setStyle(QTextListFormat.Style.ListDisc)
            cursor.createList(list_fmt)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _load_note(self):
        note = self.db.get_project_note(self.section_id)
        if note and note.content:
            self.editor.setHtml(note.content)

    def _on_header_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle()

    def _on_header_double_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_rename()

    def _toggle(self):
        self._flush_save()
        self._collapsed = not self._collapsed
        self.editor.setVisible(not self._collapsed)
        self.toolbar_widget.setVisible(not self._collapsed)
        self.lbl_toggle.setText("▸" if self._collapsed else "▾")
        self.db.update_project_section(self.section_id, collapsed=int(self._collapsed))

    def _start_rename(self):
        edit = QLineEdit(self._name, self.header)
        edit.setGeometry(self.lbl_name.geometry())
        edit.setStyleSheet("""
            QLineEdit {
                background-color: white;
                border: 1px solid #90caf9;
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 12px;
                font-weight: bold;
                color: #37474f;
            }
        """)
        edit.selectAll()
        edit.show()
        edit.setFocus()

        def finish():
            new_name = edit.text().strip()
            if new_name:
                self._name = new_name
                self.lbl_name.setText(new_name)
                self.db.update_project_section(self.section_id, name=new_name)
                self.renamed.emit(self.section_id, new_name)
            edit.deleteLater()

        edit.editingFinished.connect(finish)
        edit.returnPressed.connect(finish)

    def _request_delete(self):
        self._flush_save()
        self.deleted.emit(self.section_id)


class ProjectColumn(QFrame):
    """Vertical column representing one project."""

    deleted = pyqtSignal(int)

    def __init__(self, db: Database, project: Project, parent=None):
        super().__init__(parent)
        self.db = db
        self.project = project
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            ProjectColumn {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 10px;
            }
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._desired_height: int = 200
        self._setup_ui()
        self._load_sections()
        self._update_height()

    def _setup_ui(self):
        self._collapsed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        self.header = QFrame()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.lbl_toggle = QLabel("▾")
        self.lbl_toggle.setStyleSheet("font-size: 12px; color: #37474f;")
        header_layout.addWidget(self.lbl_toggle)

        self.color_dot = QLabel()
        self.color_dot.setFixedSize(10, 10)
        self.color_dot.setStyleSheet(f"""
            background-color: {self.project.color};
            border-radius: 5px;
        """)
        header_layout.addWidget(self.color_dot)

        self.lbl_name = QLabel(self.project.name)
        self.lbl_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #37474f;")
        header_layout.addWidget(self.lbl_name)
        header_layout.addStretch()

        btn_add = QPushButton("+ " + trs("new_section"))
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #e3f2fd;
                color: #1565c0;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #bbdefb; }
        """)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._add_section)
        header_layout.addWidget(btn_add)

        btn_more = QToolButton()
        btn_more.setText("⋮")
        btn_more.setStyleSheet("""
            QToolButton {
                border: none;
                color: #78909c;
                font-size: 14px;
            }
            QToolButton:hover { color: #37474f; }
        """)
        btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: white; border: 1px solid #e0e0e0; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #e3f2fd; color: #1565c0; }
        """)
        action_rename = QAction(trs("rename_project"), self)
        action_rename.triggered.connect(self._rename_project)
        menu.addAction(action_rename)
        action_color = QAction(trs("change_color"), self)
        action_color.triggered.connect(self._change_color)
        menu.addAction(action_color)
        menu.addSeparator()
        action_delete = QAction(trs("delete_project"), self)
        action_delete.triggered.connect(self._delete_project)
        menu.addAction(action_delete)
        btn_more.setMenu(menu)
        header_layout.addWidget(btn_more)

        self.header.mousePressEvent = self._on_header_click
        self.header.mouseDoubleClickEvent = self._on_header_double_click

        layout.addWidget(self.header)

        # Scroll area for sections
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.sections_container = QWidget()
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(6)
        self.sections_layout.addStretch()

        self.scroll.setWidget(self.sections_container)
        layout.addWidget(self.scroll)

    def _load_sections(self):
        # Remove existing section widgets except stretch
        while self.sections_layout.count() > 1:
            item = self.sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sections = self.db.get_project_sections(self.project.id)
        for section in sections:
            self._insert_section_widget(section)

    def _insert_section_widget(self, section: ProjectSection):
        widget = SectionWidget(self.db, section)
        widget.renamed.connect(lambda sid, name: None)
        widget.deleted.connect(self._delete_section)
        # Insert before stretch
        self.sections_layout.insertWidget(self.sections_layout.count() - 1, widget)

    def _add_section(self):
        color = random.choice(SECTION_PALETTE)
        section_id = self.db.add_project_section(self.project.id, color=color)
        section = self.db.get_project_sections(self.project.id)[-1]
        self._insert_section_widget(section)

    def _delete_section(self, section_id: int):
        self.db.delete_project_section(section_id)
        self._load_sections()

    def _on_header_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_collapse()

    def _on_header_double_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_rename()

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self.scroll.setVisible(not self._collapsed)
        self.lbl_toggle.setText("▸" if self._collapsed else "▾")
        self._update_height()

    def set_expanded_height(self, height: int):
        self._desired_height = max(120, height)
        self._update_height()

    def _update_height(self):
        if self._collapsed:
            # Collapsed: only show header, keep text at the top of the card
            header_h = self.header.sizeHint().height()
            self.setFixedHeight(header_h + 20)
        else:
            self.setFixedHeight(self._desired_height)

    def _start_rename(self):
        text, ok = QInputDialog.getText(
            self, trs("rename_project"), trs("project_name"), text=self.project.name
        )
        if ok and text.strip():
            self.project.name = text.strip()
            self.lbl_name.setText(self.project.name)
            self.db.update_project(self.project.id, name=self.project.name)

    def _rename_project(self):
        text, ok = QInputDialog.getText(self, trs("rename_project"), trs("project_name"),
                                        text=self.project.name)
        if ok and text.strip():
            self.project.name = text.strip()
            self.lbl_name.setText(self.project.name)
            self.db.update_project(self.project.id, name=self.project.name)

    def _change_color(self):
        color = QColorDialog.getColor(QColor(self.project.color), self)
        if color.isValid():
            self.project.color = color.name()
            self.db.update_project(self.project.id, color=self.project.color)
            self.color_dot.setStyleSheet(
                f"background-color: {self.project.color}; border-radius: 5px;"
            )

    def _delete_project(self):
        reply = QMessageBox.question(
            self, trs("delete_project"),
            trs("confirm_delete_project").format(self.project.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_project(self.project.id)
            self.deleted.emit(self.project.id)


class ProjectsWidget(QWidget):
    """Main projects page."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._view_mode = 1
        self._setup_ui()
        self._load_projects()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.lbl_title = QLabel(trs("projects"))
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #37474f;")
        toolbar.addWidget(self.lbl_title)
        toolbar.addStretch()

        btn_add = QPushButton("+ " + trs("new_project"))
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #5B8DB8;
                color: white;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a7aa5; }
        """)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._add_project)
        toolbar.addWidget(btn_add)

        self.cmb_view = QComboBox()
        self.cmb_view.addItem(trs("view_1"), 1)
        self.cmb_view.addItem(trs("view_2"), 2)
        self.cmb_view.addItem(trs("view_3"), 3)
        self.cmb_view.setCurrentIndex(0)
        self.cmb_view.currentIndexChanged.connect(self._on_view_changed)
        self.cmb_view.setStyleSheet("""
            QComboBox {
                padding: 6px 10px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                background: white;
                min-width: 100px;
            }
        """)
        toolbar.addWidget(self.cmb_view)

        layout.addLayout(toolbar)

        # Vertical scroll area for project columns
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.columns_container = QWidget()
        self.columns_layout = QVBoxLayout(self.columns_container)
        self.columns_layout.setContentsMargins(0, 0, 0, 0)
        self.columns_layout.setSpacing(12)
        self.columns_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.columns_layout.addStretch()

        self.scroll.setWidget(self.columns_container)
        layout.addWidget(self.scroll)

    def _on_view_changed(self):
        self._view_mode = self.cmb_view.currentData()
        self._refresh_column_heights()

    def _refresh_column_heights(self):
        height = self.scroll.viewport().height()
        column_height = max(200, height // self._view_mode - 12)
        for i in range(self.columns_layout.count() - 1):  # skip stretch
            item = self.columns_layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, ProjectColumn):
                widget.set_expanded_height(column_height)

    def _load_projects(self):
        # Remove existing columns except stretch
        while self.columns_layout.count() > 1:
            item = self.columns_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        projects = self.db.get_all_projects()
        for project in projects:
            self._add_project_column(project)
        self._refresh_column_heights()

    def _add_project_column(self, project: Project):
        column = ProjectColumn(self.db, project)
        column.deleted.connect(self._load_projects)
        self.columns_layout.insertWidget(self.columns_layout.count() - 1, column)

    def _add_project(self):
        color = random.choice(PROJECT_PALETTE)
        default_name = trs("new_project")
        name, ok = QInputDialog.getText(
            self, trs("new_project"), trs("project_name"), text=default_name
        )
        if ok and name.strip():
            project_name = name.strip()
        else:
            project_name = default_name
        project_id = self.db.add_project(name=project_name, color=color)
        projects = self.db.get_all_projects()
        project = next((p for p in projects if p.id == project_id), None)
        if project:
            self._add_project_column(project)
            self._refresh_column_heights()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_column_heights()
