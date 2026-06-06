"""
Task Manager Dialog
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QColorDialog,
    QMessageBox, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.database import Database
from utils.i18n import trs


class TaskManagerDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(trs("task_management"))
        self.setMinimumSize(500, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f7fa;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 1px solid #2196F3;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
            }
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
                padding: 6px;
            }
            QListWidget::item {
                padding: 12px;
                border-bottom: 1px solid #f0f0f0;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1565C0;
            }
        """)
        self._init_ui()
        self._load_tasks()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel(f"📝 {trs('manage_task_categories')}")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(trs("create_task_tags_desc"))
        desc.setStyleSheet("color: #666; margin-bottom: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Add new task
        add_layout = QHBoxLayout()
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText(trs("enter_new_task_name"))
        self.btn_color = QPushButton(f"🎨 {trs('pick_color_short')}")
        self.btn_color.setStyleSheet("background-color: #4CAF50; color: white;")
        self.btn_color.clicked.connect(self._choose_color)
        self.selected_color = "#4CAF50"

        self.btn_add = QPushButton(f"➕ {trs('add_task_short')}")
        self.btn_add.setStyleSheet("background-color: #2196F3; color: white;")
        self.btn_add.clicked.connect(self._add_task)

        add_layout.addWidget(self.input_name, 1)
        add_layout.addWidget(self.btn_color)
        add_layout.addWidget(self.btn_add)
        layout.addLayout(add_layout)

        # Task list
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_delete = QPushButton(f"🗑️ {trs('delete_selected')}")
        self.btn_delete.setStyleSheet("background-color: #f44336; color: white;")
        self.btn_delete.clicked.connect(self._delete_task)

        self.btn_close = QPushButton(trs("close"))
        self.btn_close.setStyleSheet("background-color: #607d8b; color: white;")
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _choose_color(self):
        color = QColorDialog.getColor(QColor(self.selected_color), self, trs("pick_color_short"))
        if color.isValid():
            self.selected_color = color.name()
            self.btn_color.setStyleSheet(f"background-color: {self.selected_color}; color: white;")

    def _add_task(self):
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.warning(self, trs("tip"), trs("enter_task_name"))
            return
        if name == "未分类":
            QMessageBox.warning(self, trs("tip"), trs("unclassified_system_default"))
            return

        task_id = self.db.add_task(name, self.selected_color)
        if task_id == -1:
            QMessageBox.warning(self, trs("tip"), trs("task_exists").format(name))
            return

        self.input_name.clear()
        self._load_tasks()

    def _delete_task(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, trs("tip"), trs("select_task_first"))
            return

        task_id = item.data(Qt.ItemDataRole.UserRole)
        task_name = item.text().split(" ")[0]

        if task_name == "未分类":
            QMessageBox.warning(self, trs("tip"), trs("unclassified_cannot_delete"))
            return

        reply = QMessageBox.question(
            self, trs("confirm_delete"),
            trs("delete_task_warning").format(task_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_task(task_id)
            self._load_tasks()

    def _load_tasks(self):
        self.list_widget.clear()
        tasks = self.db.get_all_tasks()
        for t in tasks:
            item = QListWidgetItem(f"{t.name}  ({t.color})")
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            # Color indicator
            item.setBackground(QColor(t.color).lighter(180))
            self.list_widget.addItem(item)
