"""
Settings Dialog
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame, QCheckBox
)
from PyQt6.QtCore import Qt

from core.database import Database
from utils.i18n import trs, set_language, current_lang
from utils.autostart import is_autostart_enabled, set_autostart


class SettingsDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(trs("settings"))
        self.setMinimumWidth(360)
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f7fa;
            }
            QLabel {
                font-size: 14px;
                color: #37474f;
            }
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                background: white;
                font-size: 13px;
                min-width: 140px;
            }
            QComboBox:focus {
                border: 1px solid #2196F3;
            }
            QPushButton {
                padding: 8px 20px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Language section
        lang_frame = QFrame()
        lang_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                padding: 8px;
            }
        """)
        lang_layout = QHBoxLayout(lang_frame)
        lang_layout.setContentsMargins(16, 16, 16, 16)

        lang_label = QLabel(trs("language"))
        lang_label.setStyleSheet("font-weight: bold;")

        self.lang_combo = QComboBox()
        self.lang_combo.addItem(trs("chinese"), "zh")
        self.lang_combo.addItem(trs("english"), "en")
        current = current_lang()
        idx = self.lang_combo.findData(current)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)

        lang_layout.addWidget(lang_label)
        lang_layout.addStretch()
        lang_layout.addWidget(self.lang_combo)

        layout.addWidget(lang_frame)

        # Autostart section
        auto_frame = QFrame()
        auto_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                padding: 8px;
            }
        """)
        auto_layout = QVBoxLayout(auto_frame)
        auto_layout.setContentsMargins(16, 16, 16, 16)
        auto_layout.setSpacing(8)

        self.autostart_check = QCheckBox(trs("autostart"))
        self.autostart_check.setChecked(is_autostart_enabled())
        self.autostart_check.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.autostart_check.stateChanged.connect(self._on_autostart_changed)

        auto_desc = QLabel(trs("autostart_desc"))
        auto_desc.setStyleSheet("font-size: 12px; color: #78909c;")

        auto_layout.addWidget(self.autostart_check)
        auto_layout.addWidget(auto_desc)

        layout.addWidget(auto_frame)
        layout.addStretch()

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton(trs("close"))
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #5B8DB8;
                color: white;
            }
            QPushButton:hover {
                background-color: #4a7aa5;
            }
        """)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _on_language_changed(self):
        lang = self.lang_combo.currentData()
        if lang != current_lang():
            set_language(lang)
            self.db.set_setting("language", lang)

    def _on_autostart_changed(self, state):
        enabled = state == Qt.CheckState.Checked.value
        success = set_autostart(enabled)
        if not success:
            # Revert checkbox if operation failed
            self.autostart_check.setChecked(is_autostart_enabled())
