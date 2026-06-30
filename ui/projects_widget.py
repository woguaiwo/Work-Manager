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
    QColorDialog, QInputDialog, QWidgetAction
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QEvent, QMimeData, QPoint
from PyQt6.QtGui import (
    QColor, QFont, QAction, QTextCharFormat, QTextCursor, QKeyEvent,
    QTextListFormat, QTextBlockFormat, QTextFormat, QDrag, QPainter,
    QCursor, QMouseEvent
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

DEFAULT_TEXT_COLORS = [
    "#000000", "#E53935", "#43A047", "#1565C0",
    "#FB8C00", "#7E57C2", "#D81B60", "#00897B",
]

DEFAULT_HIGHLIGHT_COLORS = [
    "#FFEB3B", "#A5D6A7", "#90CAF9", "#FFCC80",
    "#EF9A9A", "#CE93D8", "#FFF59D", "#B0BEC5",
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

        # Folding: "> " headers are shown as "▶ " (collapsed) / "▽ " (expanded)
        self._fold_timer = QTimer(self)
        self._fold_timer.setSingleShot(True)
        self._fold_timer.timeout.connect(self._update_folding)
        self.textChanged.connect(self._schedule_fold_update)
        self._updating_folding = False
        self._is_undoing = False
        self.setMouseTracking(True)
        # Sealed fold regions for collapsed headers: header position -> end position (exclusive)
        self._fold_regions: dict[int, int] = {}
        self.document().contentsChange.connect(self._on_contents_change)

    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        if self._updating_folding:
            return
        delta = chars_added - chars_removed
        updated = {}
        for header_pos, end_pos in self._fold_regions.items():
            new_header_pos = header_pos
            new_end_pos = end_pos
            # Edits before a boundary shift the boundary; edits at the boundary
            # itself stay outside the sealed region.
            if position < header_pos:
                new_header_pos += delta
            if position < end_pos:
                new_end_pos += delta
            updated[new_header_pos] = new_end_pos
        self._fold_regions = updated

    def _schedule_fold_update(self):
        if self._updating_folding or self._is_undoing:
            return
        self._fold_timer.stop()
        self._fold_timer.start(400)

    def _set_header_icon(self, block, icon: str):
        """Replace the first two characters of a header line ("> ", "▶ " or "▽ ")
        with `icon + " "`, keeping the rest of the line intact, and make the
        icon bold so it stands out. The whole change is wrapped in a single
        undo command so Ctrl+Z restores the original "> ".
        """
        text = block.text()
        stripped = text.lstrip()
        indent = len(text) - len(stripped)
        cursor = QTextCursor(block)
        cursor.beginEditBlock()
        try:
            cursor.setPosition(block.position() + indent)
            cursor.setPosition(block.position() + indent + 2, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(icon + " ")
            cursor.setPosition(block.position() + indent)
            cursor.setPosition(block.position() + indent + 1, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            cursor.mergeCharFormat(fmt)
        finally:
            cursor.endEditBlock()

    def _update_folding(self, is_undo: bool = False):
        if self._updating_folding:
            return
        doc = self.document()
        if doc is None:
            return

        self._updating_folding = True
        try:
            self._apply_folding(0, -1, False, is_undo)
            self.viewport().update()
            # Force the document to recalculate layout after visibility changes
            doc.markContentsDirty(0, doc.characterCount())
            self.updateGeometry()

            # Remove stale fold regions whose header no longer exists
            stale = []
            for pos in self._fold_regions:
                block = doc.findBlock(pos)
                if block.position() != pos or not block.text().lstrip().startswith(("▶ ", "▽ ")):
                    stale.append(pos)
            for pos in stale:
                del self._fold_regions[pos]
        finally:
            self._updating_folding = False

    def _apply_folding(self, start_idx: int, parent_indent: int, parent_hidden: bool, is_undo: bool) -> int:
        """Recursively apply folding starting at start_idx.

        - parent_indent: indent level of the enclosing header (-1 for the root).
        - parent_hidden: True if an ancestor header is collapsed.
        - Returns the index of the first block that is outside this scope.
        """
        i = start_idx
        while i < self.document().blockCount():
            block = self.document().findBlockByNumber(i)
            text = block.text()
            stripped = text.lstrip()
            indent = len(text) - len(stripped)

            # A non-empty line at or before the parent's indent ends this scope.
            if stripped and indent <= parent_indent:
                return i

            # Auto-convert freshly typed "> " to collapsed icon unless this is an undo.
            if not is_undo and stripped.startswith("> "):
                self._set_header_icon(block, "▶")
                block = self.document().findBlockByNumber(i)
                text = block.text()
                stripped = text.lstrip()
                indent = len(text) - len(stripped)

            if stripped.startswith("▶ ") or stripped.startswith("▽ "):
                collapsed = stripped.startswith("▶ ")
                block.setVisible(not parent_hidden)
                pos = block.position()

                # Compute the current fold boundary based on indentation.
                # Blank lines do not end the region so deeper indented content
                # after a blank line is still folded with its parent header.
                j = i + 1
                while j < self.document().blockCount():
                    child = self.document().findBlockByNumber(j)
                    child_stripped = child.text().lstrip()
                    if child_stripped:
                        child_indent = len(child.text()) - len(child_stripped)
                        if child_indent <= indent:
                            break
                    j += 1

                current_end_pos = (self.document().findBlockByNumber(j).position()
                                   if j < self.document().blockCount()
                                   else self.document().characterCount())

                # Collapsed headers keep a sealed fold region so edits made
                # while collapsed do not get absorbed into the fold.
                # The sealed end must never extend past the current indentation
                # boundary, otherwise text typed after the fold would be hidden.
                if collapsed:
                    end_pos = self._fold_regions.get(pos, current_end_pos)
                    if end_pos <= pos:
                        end_pos = current_end_pos
                    end_pos = min(end_pos, current_end_pos)
                    self._fold_regions[pos] = end_pos
                else:
                    end_pos = current_end_pos
                    self._fold_regions[pos] = end_pos

                if end_pos >= self.document().characterCount():
                    end_idx = self.document().blockCount()
                else:
                    end_block = self.document().findBlock(end_pos)
                    if not end_block.isValid():
                        end_block = self.document().lastBlock()
                    end_idx = end_block.blockNumber()
                # Guard against stale end positions that fall inside the header itself.
                if end_idx <= i:
                    end_pos = current_end_pos
                    end_block = self.document().findBlock(end_pos)
                    end_idx = end_block.blockNumber()
                    self._fold_regions[pos] = end_pos

                for k in range(i + 1, end_idx):
                    child = self.document().findBlockByNumber(k)
                    # Blank lines inside a folded region stay visible so the
                    # user can insert paragraph breaks after a header.
                    if child.text().strip():
                        child.setVisible(not parent_hidden and not collapsed)
                    else:
                        child.setVisible(not parent_hidden)

                # Recursively process nested headers inside this region.
                # Blank lines and same-or-less-indented blocks are skipped so
                # they keep the visible state set above and cannot cause loops.
                k = i + 1
                while k < end_idx:
                    child = self.document().findBlockByNumber(k)
                    child_text = child.text()
                    child_stripped = child_text.lstrip()
                    if not child_stripped:
                        k += 1
                        continue
                    child_indent = len(child_text) - len(child_stripped)
                    if child_indent <= indent:
                        k += 1
                        continue
                    next_k = self._apply_folding(k, indent, parent_hidden or collapsed, is_undo)
                    if next_k <= k:
                        k += 1
                    else:
                        k = next_k

                i = end_idx
            else:
                # Blank lines are always kept visible so they can be used as
                # paragraph breaks inside folded regions.
                if block.text().strip():
                    block.setVisible(not parent_hidden)
                else:
                    block.setVisible(True)
                i += 1

        return self.document().blockCount()

    def _toggle_fold(self, block_pos: int):
        doc = self.document()
        block = doc.findBlock(block_pos)
        text = block.text()
        stripped = text.lstrip()
        if stripped.startswith("▶ "):
            self._set_header_icon(block, "▽")
        elif stripped.startswith("▽ "):
            self._set_header_icon(block, "▶")
        else:
            return
        self._fold_timer.stop()
        self._update_folding()

    def _is_over_fold_icon(self, pos) -> bool:
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        text = block.text()
        stripped = text.lstrip()
        indent = len(text) - len(stripped)
        return (stripped.startswith(("▶ ", "▽ ", "> ")) and
                indent <= cursor.positionInBlock() <= indent + 2)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_over_fold_icon(event.position().toPoint()):
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._is_over_fold_icon(event.position().toPoint()):
            cursor = self.cursorForPosition(event.position().toPoint())
            self._toggle_fold(cursor.block().position())
            return
        super().mousePressEvent(event)

    def undo(self):
        self._fold_timer.stop()
        self._is_undoing = True
        try:
            super().undo()
            self._update_folding(is_undo=True)
        finally:
            self._is_undoing = False

    def redo(self):
        self._fold_timer.stop()
        super().redo()
        self._update_folding()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            is_shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            cursor = self.textCursor()
            if cursor.hasSelection() or is_shift:
                self._indent_selection(not is_shift)
            else:
                self.insertPlainText("    ")
            return
        super().keyPressEvent(event)

    def _indent_selection(self, increase: bool):
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        doc = self.document()
        start_block = doc.findBlock(start)
        end_block = doc.findBlock(end)

        cursor.beginEditBlock()
        try:
            block = start_block
            while block.isValid() and block.blockNumber() <= end_block.blockNumber():
                if increase:
                    indent_cursor = QTextCursor(block)
                    indent_cursor.setPosition(block.position())
                    indent_cursor.insertText("    ")
                else:
                    text = block.text()
                    indent_len = 0
                    for char in text:
                        if char == ' ' and indent_len < 4:
                            indent_len += 1
                        elif char == '\t':
                            indent_len = 4
                            break
                        else:
                            break
                    if indent_len > 0:
                        remove_cursor = QTextCursor(block)
                        remove_cursor.setPosition(block.position())
                        remove_cursor.setPosition(block.position() + indent_len, QTextCursor.MoveMode.KeepAnchor)
                        remove_cursor.removeSelectedText()
                block = block.next()
        finally:
            cursor.endEditBlock()


class SectionWidget(QFrame):
    """Collapsible section containing a colored header and a note editor."""

    renamed = pyqtSignal(int, str)
    deleted = pyqtSignal(int)

    SAVE_DELAY_MS = 2000

    def __init__(self, db: Database, section: ProjectSection, parent=None):
        super().__init__(parent)
        self.db = db
        self.section_id = section.id
        self.project_id = section.project_id
        self._collapsed = bool(section.collapsed)
        self._color = section.color or SECTION_PALETTE[0]
        self._name = section.name or trs("new_section")
        self._pending_content: Optional[str] = None
        self._drag_start_pos = None
        self._drag_local_pos = None
        self._drag_candidate = False
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

        self.header.setMouseTracking(True)
        self.lbl_name.setMouseTracking(True)
        self.header.installEventFilter(self)
        self.lbl_name.installEventFilter(self)

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
        self.editor.setAcceptDrops(False)
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
        self._show_color_menu(is_highlight=False)

    def _set_highlight_color(self):
        self._show_color_menu(is_highlight=True)

    def _show_color_menu(self, is_highlight: bool):
        btn = self.sender()
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: white; border: 1px solid #e0e0e0; border-radius: 6px; padding: 4px; }
        """)

        key = 'recent_highlight_colors' if is_highlight else 'recent_text_colors'
        default_colors = DEFAULT_HIGHLIGHT_COLORS if is_highlight else DEFAULT_TEXT_COLORS
        recent_colors = self.db.get_recent_colors(key)

        def _color_grid(colors):
            widget = QWidget()
            grid = QGridLayout(widget)
            grid.setSpacing(4)
            grid.setContentsMargins(4, 4, 4, 4)
            for i, color in enumerate(colors):
                cb = QPushButton()
                cb.setFixedSize(22, 22)
                cb.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        border: 1px solid #e0e0e0;
                        border-radius: 3px;
                    }}
                    QPushButton:hover {{ border: 1px solid #5B8DB8; }}
                """)
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                cb.clicked.connect(lambda checked, c=color: self._apply_color(c, is_highlight))
                grid.addWidget(cb, i // 4, i % 4)
            return widget

        action = QWidgetAction(menu)
        action.setDefaultWidget(_color_grid(default_colors))
        menu.addAction(action)

        if recent_colors:
            menu.addSeparator()
            action = QWidgetAction(menu)
            action.setDefaultWidget(_color_grid(recent_colors))
            menu.addAction(action)

        menu.addSeparator()
        more_action = QAction(trs("more_colors"), menu)
        more_action.triggered.connect(lambda: self._pick_custom_color(is_highlight))
        menu.addAction(more_action)

        if btn:
            menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))
        else:
            menu.exec(QCursor.pos())

    def _apply_color(self, color_name: str, is_highlight: bool):
        color = QColor(color_name)
        fmt = QTextCharFormat()
        if is_highlight:
            fmt.setBackground(color)
        else:
            fmt.setForeground(color)
        self.editor.mergeCurrentCharFormat(fmt)
        key = 'recent_highlight_colors' if is_highlight else 'recent_text_colors'
        self.db.add_recent_color(key, color_name)

    def _pick_custom_color(self, is_highlight: bool):
        default = QColor("#FFEB3B") if is_highlight else Qt.GlobalColor.black
        color = QColorDialog.getColor(default, self)
        if color.isValid():
            self._apply_color(color.name(), is_highlight)

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

    def eventFilter(self, obj, event):
        if obj in (self.header, self.lbl_name) and event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
        ):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._drag_start_pos = event.globalPosition().toPoint()
                    self._drag_local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
                    self._drag_candidate = True
            elif event.type() == QEvent.Type.MouseMove:
                if self._drag_candidate and self._drag_start_pos is not None:
                    if (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength() > 10:
                        self._drag_candidate = False
                        self._start_drag()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton and self._drag_candidate:
                    self._drag_candidate = False
                    label_pos = self.lbl_name.mapFromGlobal(event.globalPosition().toPoint())
                    if self.lbl_name.rect().contains(label_pos):
                        self._start_rename()
                    else:
                        self._toggle()
            return True
        return super().eventFilter(obj, event)

    def _start_drag(self):
        mime = QMimeData()
        mime.setText(f"{self.section_id}:{self.project_id}")
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
        self.sections_container.setAcceptDrops(True)
        layout.addWidget(self.scroll)

        # Drop indicator for reordering sections inside this project
        self._section_drop_indicator = QFrame(self.sections_container)
        self._section_drop_indicator.setStyleSheet("""
            QFrame { background-color: #212121; border-radius: 1px; }
        """)
        self._section_drop_indicator.hide()

        self.sections_container.setAcceptDrops(True)
        self.sections_container.installEventFilter(self)

    def _retranslate_ui(self):
        self.btn_add_section.setText("+ " + trs("new_section"))
        self.action_rename.setText(trs("rename_project"))
        self.action_color.setText(trs("change_color"))
        self.action_delete.setText(trs("delete_project"))
        for i in range(self.sections_layout.count()):
            widget = self.sections_layout.itemAt(i).widget()
            if isinstance(widget, SectionWidget):
                widget._retranslate_ui()

    def eventFilter(self, obj, event):
        if obj is self.sections_container or self._is_descendant_of_sections_container(obj):
            et = event.type()
            if et == QEvent.Type.DragEnter:
                if event.mimeData().hasText():
                    payload = event.mimeData().text()
                    if ":" in payload:
                        _, project_id = payload.split(":", 1)
                        if int(project_id) == self.project.id:
                            event.acceptProposedAction()
                            return True
            elif et == QEvent.Type.DragMove:
                if event.mimeData().hasText():
                    event.acceptProposedAction()
                    pos = self.sections_container.mapFrom(obj, event.position().toPoint())
                    insert_idx = self._compute_section_insert_index(pos)
                    self._update_section_drop_indicator(insert_idx)
                    return True
            elif et == QEvent.Type.DragLeave:
                self._hide_section_drop_indicator()
                return True
            elif et == QEvent.Type.Drop:
                if not event.mimeData().hasText():
                    return True
                payload = event.mimeData().text()
                if ":" not in payload:
                    return True
                section_id_str, project_id_str = payload.split(":", 1)
                if int(project_id_str) != self.project.id:
                    return True
                pos = self.sections_container.mapFrom(obj, event.position().toPoint())
                self._reorder_section(int(section_id_str), pos)
                self._hide_section_drop_indicator()
                event.acceptProposedAction()
                return True
        return super().eventFilter(obj, event)

    def _is_descendant_of_sections_container(self, widget):
        parent = widget.parent()
        while parent is not None:
            if parent is self.sections_container:
                return True
            parent = parent.parent()
        return False

    def _compute_section_insert_index(self, pos) -> int:
        for i in range(self.sections_layout.count()):
            widget = self.sections_layout.itemAt(i).widget()
            if widget is None:
                continue
            if pos.y() < widget.geometry().center().y():
                return i
        return self.sections_layout.count()

    def _update_section_drop_indicator(self, insert_idx: int):
        width = self.sections_container.width()
        if width <= 0:
            width = self.scroll.viewport().width()
        gap = 3
        thickness = 3
        if insert_idx < self.sections_layout.count():
            widget = self.sections_layout.itemAt(insert_idx).widget()
            if widget is None:
                return
            rect = widget.geometry()
            y = max(0, rect.top() - gap)
            self._section_drop_indicator.setGeometry(0, y, width, thickness)
        else:
            last = self.sections_layout.itemAt(self.sections_layout.count() - 1).widget()
            if last is None:
                return
            rect = last.geometry()
            y = min(self.sections_container.height() - thickness, rect.bottom() + gap)
            self._section_drop_indicator.setGeometry(0, y, width, thickness)
        self._section_drop_indicator.raise_()
        self._section_drop_indicator.show()

    def _hide_section_drop_indicator(self):
        self._section_drop_indicator.hide()

    def _reorder_section(self, source_section_id: int, pos):
        source_idx = -1
        for i in range(self.sections_layout.count()):
            widget = self.sections_layout.itemAt(i).widget()
            if isinstance(widget, SectionWidget) and widget.section_id == source_section_id:
                source_idx = i
                break
        if source_idx == -1:
            return
        target_idx = self._compute_section_insert_index(pos)
        if target_idx > source_idx:
            target_idx -= 1
        if target_idx == source_idx:
            return

        sections = []
        for i in range(self.sections_layout.count()):
            widget = self.sections_layout.itemAt(i).widget()
            if isinstance(widget, SectionWidget):
                sections.append(widget)

        section = sections.pop(source_idx)
        sections.insert(target_idx, section)

        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for s in sections:
            self.sections_layout.addWidget(s)

        for i, s in enumerate(sections):
            self.db.update_project_section(s.section_id, sort_order=i)

    def _load_sections(self, force=False):
        if self._sections_loaded and not force:
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
        # Intercept drag events over the section and its children so that
        # section reordering indicators work even when the cursor is above
        # nested editors or toolbars.
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.installEventFilter(self)

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
        self._load_sections(force=True)

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
        self.columns_layout = QHBoxLayout(self.columns_container)
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
        self._column_containers = []

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
            # Clean up existing column containers and detach project columns
            while self.columns_layout.count():
                item = self.columns_layout.takeAt(0)
                col_widget = item.widget()
                if not isinstance(col_widget, QWidget):
                    continue
                inner = col_widget.layout()
                if inner is not None:
                    while inner.count():
                        inner_item = inner.takeAt(0)
                        if inner_item.widget():
                            inner_item.widget().setParent(None)
                self.columns_layout.removeWidget(col_widget)
                col_widget.deleteLater()

            # Create one vertical column per active view slot
            self._column_containers = []
            column_layouts = []
            for _ in range(self._view_mode):
                container = QWidget(self.columns_container)
                layout = QVBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(12)
                layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                self.columns_layout.addWidget(container, 1)
                self._column_containers.append(container)
                column_layouts.append(layout)

            # Distribute project columns row-major into independent vertical columns
            for idx, column in enumerate(self._columns):
                col = idx % self._view_mode
                column_layouts[col].addWidget(column, alignment=Qt.AlignmentFlag.AlignTop)
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
        if not self._columns or not self._column_containers:
            return
        gap = 6  # place line in the middle of the 12px spacing
        thickness = 3

        if insert_idx < len(self._columns):
            target = self._columns[insert_idx]
            rect = target.geometry()
            col = insert_idx % self._view_mode
            col_container = self._column_containers[col]
            col_rect = col_container.geometry()
            if col == 0:
                # Horizontal line within the target column above the card
                y = max(col_rect.top(), rect.top() - gap)
                self._drop_indicator.setGeometry(col_rect.left(), y, col_rect.width(), thickness)
            else:
                # Vertical line in the gap between column containers
                x = max(0, rect.left() - gap)
                self._drop_indicator.setGeometry(x, rect.top(), thickness, rect.height())
        else:
            last = self._columns[-1]
            rect = last.geometry()
            last_col = (len(self._columns) - 1) % self._view_mode
            col_container = self._column_containers[last_col]
            col_rect = col_container.geometry()
            if last_col == self._view_mode - 1:
                # Horizontal line within the last column below the last card
                y = min(col_rect.bottom() - thickness, rect.bottom() + gap)
                self._drop_indicator.setGeometry(col_rect.left(), y, col_rect.width(), thickness)
            else:
                # Vertical line to the right of the last card when the row is not full
                x = min(self.columns_container.width() - thickness, rect.right() + gap)
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
