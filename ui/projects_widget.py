"""
Projects page with rich-text notes organized into collapsible sections.
"""
import random
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTextEdit, QLineEdit, QComboBox,
    QSizePolicy, QApplication, QMessageBox, QToolButton, QMenu,
    QColorDialog, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QEvent, QMimeData
from PyQt6.QtGui import (
    QColor, QFont, QAction, QTextCharFormat, QTextCursor, QKeyEvent,
    QTextListFormat, QTextBlockFormat, QTextFormat, QDrag, QPainter
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
        self.header = QFrame(self)
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

        self.lbl_toggle = QLabel("▾" if not self._collapsed else "▸", self)
        self.lbl_toggle.setStyleSheet("font-size: 12px; color: #37474f;")
        header_layout.addWidget(self.lbl_toggle)

        self.lbl_name = QLabel(self._name, self)
        self.lbl_name.setStyleSheet("font-size: 12px; font-weight: bold; color: #37474f;")
        self.lbl_name.setWordWrap(False)
        self.lbl_name.setCursor(Qt.CursorShape.IBeamCursor)
        self.lbl_name.mousePressEvent = self._on_name_click
        header_layout.addWidget(self.lbl_name)
        header_layout.addStretch()

        self.btn_delete = QToolButton(self)
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

        layout.addWidget(self.header)

        # Toolbar
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(4)
        self.toolbar.setContentsMargins(4, 4, 4, 0)

        self._tool_buttons = [
            self._make_tool_btn(trs("fmt_bold"), self._toggle_bold, "font-weight: bold;"),
            self._make_tool_btn(trs("fmt_italic"), self._toggle_italic, "font-style: italic;"),
            self._make_tool_btn(trs("fmt_color"), self._set_text_color, ""),
            self._make_tool_btn(trs("fmt_highlight"), self._set_highlight_color, ""),
            self._make_tool_btn(trs("fmt_list"), self._toggle_bullet_list, ""),
        ]

        toolbar_widget = QWidget(self)
        toolbar_widget.setLayout(self.toolbar)
        toolbar_widget.setVisible(not self._collapsed)
        self.toolbar_widget = toolbar_widget
        layout.addWidget(toolbar_widget)

        # Editor
        self.editor = NoteEditor(self)
        self.editor.setVisible(not self._collapsed)
        self.editor.content_changed.connect(self._on_content_changed)
        self.editor.focusOutEvent = self._on_editor_focus_out
        layout.addWidget(self.editor)

        # Save timer must exist before any setHtml can fire textChanged
        self._init_save_timer()

        # Collapsed sections should not stretch; expanded sections fill space
        if self._collapsed:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _init_save_timer(self):
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_save)

    def _retranslate_ui(self):
        self.lbl_name.setText(self._name)
        labels = [
            trs("fmt_bold"), trs("fmt_italic"), trs("fmt_color"),
            trs("fmt_highlight"), trs("fmt_list"),
        ]
        for btn, label in zip(self._tool_buttons, labels):
            btn.setText(label)

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
        btn = QPushButton(text, self)
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
        return btn

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

    def _on_name_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_rename()

    def _toggle(self):
        self._flush_save()
        self._collapsed = not self._collapsed
        self.editor.setVisible(not self._collapsed)
        self.toolbar_widget.setVisible(not self._collapsed)
        self.lbl_toggle.setText("▸" if self._collapsed else "▾")
        # Collapsed sections keep header-only height; expanded sections stretch
        if self._collapsed:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.updateGeometry()
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

        self._rename_edit = edit

        def finish():
            # Disconnect to prevent double firing
            try:
                edit.editingFinished.disconnect(finish)
            except Exception:
                pass
            try:
                edit.returnPressed.disconnect(finish)
            except Exception:
                pass
            QApplication.instance().removeEventFilter(click_filter)

            new_name = edit.text().strip()
            if new_name:
                self._name = new_name
                self.lbl_name.setText(new_name)
                self.db.update_project_section(self.section_id, name=new_name)
                self.renamed.emit(self.section_id, new_name)
            edit.deleteLater()
            self._rename_edit = None

        edit.editingFinished.connect(finish)
        edit.returnPressed.connect(finish)

        # Finish editing when clicking outside the rename line edit
        class ClickOutsideFilter(QObject):
            def __init__(self, target, callback):
                super().__init__(target)
                self._target = target
                self._callback = callback

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.MouseButtonPress:
                    if isinstance(obj, QWidget) and obj is not self._target and not self._target.isAncestorOf(obj):
                        self._callback()
                return False

        click_filter = ClickOutsideFilter(edit, finish)
        QApplication.instance().installEventFilter(click_filter)

    def _request_delete(self):
        self._flush_save()
        self.deleted.emit(self.section_id)


class ProjectColumn(QFrame):
    """Vertical column representing one project."""

    deleted = pyqtSignal(int)
    collapsed_changed = pyqtSignal(int, bool)

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
        self._collapsed: bool = bool(project.collapsed)
        self._sections_loaded: bool = False
        self._drag_start_pos = None
        self._drag_local_pos = None
        self._drag_candidate = False
        self._setup_ui()
        self._load_sections()
        self._update_height()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        self.header = QFrame(self)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.lbl_toggle = QLabel("▸" if self._collapsed else "▾", self)
        self.lbl_toggle.setStyleSheet("font-size: 12px; color: #37474f;")
        header_layout.addWidget(self.lbl_toggle)

        self.color_dot = QLabel(self)
        self.color_dot.setFixedSize(10, 10)
        self.color_dot.setStyleSheet(f"""
            background-color: {self.project.color};
            border-radius: 5px;
        """)
        header_layout.addWidget(self.color_dot)

        self.lbl_name = QLabel(self.project.name, self)
        self.lbl_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #37474f;")
        header_layout.addWidget(self.lbl_name)
        header_layout.addStretch()

        self.btn_add_section = QPushButton("+ " + trs("new_section"), self)
        self.btn_add_section.setStyleSheet("""
            QPushButton {
                background-color: #e3f2fd;
                color: #1565c0;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #bbdefb; }
        """)
        self.btn_add_section.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_section.clicked.connect(self._add_section)
        header_layout.addWidget(self.btn_add_section)

        btn_more = QToolButton(self)
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
        self.action_rename = QAction(trs("rename_project"), self)
        self.action_rename.triggered.connect(self._rename_project)
        menu.addAction(self.action_rename)
        self.action_color = QAction(trs("change_color"), self)
        self.action_color.triggered.connect(self._change_color)
        menu.addAction(self.action_color)
        menu.addSeparator()
        self.action_delete = QAction(trs("delete_project"), self)
        self.action_delete.triggered.connect(self._delete_project)
        menu.addAction(self.action_delete)
        btn_more.setMenu(menu)
        header_layout.addWidget(btn_more)

        self.header.mousePressEvent = self._on_header_mouse_press
        self.header.mouseMoveEvent = self._on_header_mouse_move
        self.header.mouseReleaseEvent = self._on_header_mouse_release
        self.header.mouseDoubleClickEvent = self._on_header_double_click

        layout.addWidget(self.header)

        # Scroll area for sections
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.scroll.setVisible(not self._collapsed)

        self.sections_container = QWidget(self.scroll)
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(6)
        self.sections_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # No stretch: sections expand to fill the project column height

        self.scroll.setWidget(self.sections_container)
        layout.addWidget(self.scroll)

    def _retranslate_ui(self):
        self.btn_add_section.setText("+ " + trs("new_section"))
        self.action_rename.setText(trs("rename_project"))
        self.action_color.setText(trs("change_color"))
        self.action_delete.setText(trs("delete_project"))
        for i in range(self.sections_layout.count()):
            widget = self.sections_layout.itemAt(i).widget()
            if isinstance(widget, SectionWidget):
                widget._retranslate_ui()

    def _load_sections(self):
        if self._sections_loaded:
            return
        self._sections_loaded = True
        # Remove existing section widgets
        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sections = self.db.get_project_sections(self.project.id)
        for section in sections:
            self._insert_section_widget(section)

    def _insert_section_widget(self, section: ProjectSection):
        widget = SectionWidget(self.db, section, parent=self.sections_container)
        widget.renamed.connect(lambda sid, name: None)
        widget.deleted.connect(self._delete_section)
        self.sections_layout.addWidget(widget)

    def _add_section(self):
        if not self._sections_loaded:
            self._load_sections()
        color = random.choice(SECTION_PALETTE)
        section_id = self.db.add_project_section(self.project.id, color=color)
        section = self.db.get_project_sections(self.project.id)[-1]
        self._insert_section_widget(section)

    def _delete_section(self, section_id: int):
        if not self._sections_loaded:
            self._load_sections()
        self.db.delete_project_section(section_id)
        self._load_sections()

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
            self._drag_candidate = True

    def _on_header_mouse_move(self, event):
        if not self._drag_candidate or self._drag_start_pos is None:
            return
        if (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength() > 10:
            self._drag_candidate = False
            self._start_drag()

    def _on_header_mouse_release(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_candidate:
            self._drag_candidate = False
            self._toggle_collapse()

    def _on_header_double_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_rename()

    def _start_drag(self):
        mime = QMimeData()
        mime.setText(str(self.project.id))
        drag = QDrag(self)
        drag.setMimeData(mime)

        pixmap = self.grab()
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(pixmap.rect(), QColor(0, 0, 0, 180))
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(self._drag_local_pos if self._drag_local_pos else pixmap.rect().center())

        drag.exec(Qt.DropAction.MoveAction)

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        if not self._collapsed and not self._sections_loaded:
            self._load_sections()
        self.scroll.setVisible(not self._collapsed)
        self.lbl_toggle.setText("▸" if self._collapsed else "▾")
        self._update_height()
        self.collapsed_changed.emit(self.project.id, self._collapsed)

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
        # Defer loading projects until the page is first shown
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._loaded = True
            self._load_projects()
        else:
            self._restore_scroll_position()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.lbl_title = QLabel(trs("projects"), self)
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #37474f;")
        toolbar.addWidget(self.lbl_title)
        toolbar.addStretch()

        self.btn_add_project = QPushButton("+ " + trs("new_project"), self)
        self.btn_add_project.setStyleSheet("""
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
        self.btn_add_project.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_project.clicked.connect(self._add_project)
        toolbar.addWidget(self.btn_add_project)

        self.cmb_view = QComboBox(self)
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
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.columns_container = QWidget(self.scroll)
        self.columns_layout = QGridLayout(self.columns_container)
        self.columns_layout.setContentsMargins(0, 0, 0, 0)
        self.columns_layout.setSpacing(12)
        self.columns_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(self.columns_container)
        layout.addWidget(self.scroll)

        # Drop indicator line shown during project drag reordering
        self._drop_indicator = QFrame(self.columns_container)
        self._drop_indicator.setStyleSheet("""
            QFrame {
                background-color: #212121;
                border-radius: 1px;
            }
        """)
        self._drop_indicator.hide()

        self.setAcceptDrops(True)
        self._columns = []

        # Scroll position persistence timer (debounced)
        self._scroll_save_timer = QTimer(self)
        self._scroll_save_timer.setSingleShot(True)
        self._scroll_save_timer.timeout.connect(self._save_scroll_position)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        # Restore view mode
        saved_mode = self.db.get_setting('projects_view_mode', '1')
        try:
            self._view_mode = max(1, min(3, int(saved_mode)))
        except ValueError:
            self._view_mode = 1
        self.cmb_view.setCurrentIndex(self._view_mode - 1)

    def _retranslate_ui(self):
        self.lbl_title.setText(trs("projects"))
        self.btn_add_project.setText("+ " + trs("new_project"))
        self.cmb_view.setItemText(0, trs("view_1"))
        self.cmb_view.setItemText(1, trs("view_2"))
        self.cmb_view.setItemText(2, trs("view_3"))
        for column in self._columns:
            column._retranslate_ui()

    def _on_view_changed(self):
        self._view_mode = self.cmb_view.currentData()
        self.db.set_setting('projects_view_mode', str(self._view_mode))
        self._relayout_projects()

    def _on_scroll_changed(self):
        self._scroll_save_timer.stop()
        self._scroll_save_timer.start(200)

    def _save_scroll_position(self):
        self.db.set_setting('projects_scroll_y', str(self.scroll.verticalScrollBar().value()))

    def _restore_scroll_position(self):
        saved_y = self.db.get_setting('projects_scroll_y', '0')
        try:
            y = int(saved_y)
        except ValueError:
            y = 0
        self.scroll.verticalScrollBar().setValue(y)

    def _relayout_projects(self):
        self.setUpdatesEnabled(False)
        try:
            # Detach all project columns from the grid
            for i in range(self.columns_layout.count() - 1, -1, -1):
                item = self.columns_layout.takeAt(i)
                if item.widget():
                    item.widget().setParent(None)

            # Equal width for active columns, no stretch for unused ones
            for c in range(3):
                self.columns_layout.setColumnStretch(c, 1 if c < self._view_mode else 0)

            # Row-major order: left-to-right, then top-to-bottom
            for idx, column in enumerate(self._columns):
                row = idx // self._view_mode
                col = idx % self._view_mode
                self.columns_layout.addWidget(
                    column, row, col, alignment=Qt.AlignmentFlag.AlignTop
                )
        finally:
            self.setUpdatesEnabled(True)
        self._refresh_column_heights()

    def _refresh_column_heights(self):
        height = self.scroll.viewport().height()
        column_height = max(200, height - 24)
        for column in self._columns:
            column.set_expanded_height(column_height)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasText():
            return
        event.acceptProposedAction()
        pos = self.columns_container.mapFrom(self, event.position().toPoint())
        insert_idx = self._compute_insert_index(pos)
        self._update_drop_indicator(insert_idx)

    def dragLeaveEvent(self, event):
        self._hide_drop_indicator()

    def dropEvent(self, event):
        if not event.mimeData().hasText():
            return
        try:
            source_id = int(event.mimeData().text())
        except ValueError:
            return
        pos = self.columns_container.mapFrom(self, event.position().toPoint())
        self._reorder_project(source_id, pos)
        self._hide_drop_indicator()
        event.acceptProposedAction()

    def _compute_insert_index(self, pos) -> int:
        if not self._columns:
            return 0
        for i, col in enumerate(self._columns):
            rect = col.geometry()
            if pos.y() < rect.center().y():
                return i
            if pos.y() <= rect.bottom() and pos.x() < rect.center().x():
                return i
        return len(self._columns)

    def _update_drop_indicator(self, insert_idx: int):
        if not self._columns:
            return
        container_width = self.columns_container.width()
        container_height = self.columns_container.height()
        gap = 6  # place line in the middle of the 12px spacing
        thickness = 3
        if insert_idx < len(self._columns):
            target = self._columns[insert_idx]
            rect = target.geometry()
            col = insert_idx % self._view_mode
            if col == 0:
                # Horizontal line above the first card in a row
                y = max(0, rect.top() - gap)
                self._drop_indicator.setGeometry(0, y, container_width, thickness)
            else:
                # Vertical line to the left of a card in the middle/end of a row
                x = max(0, rect.left() - gap)
                self._drop_indicator.setGeometry(x, rect.top(), thickness, rect.height())
        else:
            last = self._columns[-1]
            rect = last.geometry()
            last_col = (len(self._columns) - 1) % self._view_mode
            if last_col == self._view_mode - 1:
                # Horizontal line below the last card when the row is full
                y = min(container_height - thickness, rect.bottom() + gap)
                self._drop_indicator.setGeometry(0, y, container_width, thickness)
            else:
                # Vertical line to the right of the last card when the row is not full
                x = min(container_width - thickness, rect.right() + gap)
                self._drop_indicator.setGeometry(x, rect.top(), thickness, rect.height())
        self._drop_indicator.raise_()
        self._drop_indicator.show()

    def _hide_drop_indicator(self):
        self._drop_indicator.hide()

    def _reorder_project(self, source_id: int, pos):
        source_idx = next((i for i, c in enumerate(self._columns) if c.project.id == source_id), -1)
        if source_idx == -1:
            return
        target_idx = self._compute_insert_index(pos)
        if target_idx > source_idx:
            target_idx -= 1
        if target_idx == source_idx:
            return

        column = self._columns.pop(source_idx)
        self._columns.insert(target_idx, column)

        for i, col in enumerate(self._columns):
            self.db.update_project(col.project.id, sort_order=i)

        self._relayout_projects()

    def _load_projects(self):
        self.setUpdatesEnabled(False)
        self.columns_container.hide()
        try:
            # Clean up existing project columns
            for column in self._columns:
                column.deleteLater()
            self._columns.clear()

            projects = self.db.get_all_projects()
            for project in projects:
                column = ProjectColumn(self.db, project, parent=self.columns_container)
                column.hide()
                column.deleted.connect(self._on_project_deleted)
                column.collapsed_changed.connect(self._on_project_collapsed)
                self._columns.append(column)

            self._relayout_projects()
            self._refresh_column_heights()
            self._restore_scroll_position()
        finally:
            for column in self._columns:
                column.show()
            self.columns_container.show()
            self.setUpdatesEnabled(True)

    def _add_project_column(self, project: Project):
        column = ProjectColumn(self.db, project, parent=self.columns_container)
        column.deleted.connect(self._on_project_deleted)
        column.collapsed_changed.connect(self._on_project_collapsed)
        self._columns.append(column)
        self._relayout_projects()

    def _on_project_deleted(self, project_id: int):
        self._columns = [c for c in self._columns if c.project.id != project_id]
        self._relayout_projects()

    def _on_project_collapsed(self, project_id: int, collapsed: bool):
        self.db.update_project(project_id, collapsed=int(collapsed))

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
