from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .ui_strings import (
    ACTIVATION_ERROR_EMPTY,
    ACTIVATION_LICENSE_LABEL,
    ACTIVATION_SUBTITLE,
    ACTIVATION_SUBTITLE_OPTIONAL,
    ACTIVATION_TITLE,
    ACTIVATION_SUBMIT,
    ACTIVATION_EXIT_APP,
    ACTIVATION_CANCEL,
)


class ActivationDialog(QDialog):
    def __init__(self, parent=None, *, mandatory: bool = True) -> None:
        super().__init__(parent)
        self._mandatory = mandatory
        self.setWindowTitle(ACTIVATION_TITLE)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout()
        sub = ACTIVATION_SUBTITLE if mandatory else ACTIVATION_SUBTITLE_OPTIONAL
        subtitle = QLabel(sub)
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setFormAlignment(Qt.AlignmentFlag.AlignRight)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.license_input = QLineEdit()
        self.license_input.setPlaceholderText("")
        self.license_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(ACTIVATION_LICENSE_LABEL, self.license_input)
        root.addLayout(form)

        actions = QHBoxLayout()
        self.submit_btn = QPushButton(ACTIVATION_SUBMIT)
        self.submit_btn.clicked.connect(self._submit)
        actions.addWidget(self.submit_btn)
        if mandatory:
            exit_btn = QPushButton(ACTIVATION_EXIT_APP)
            exit_btn.clicked.connect(self.reject)
            actions.addWidget(exit_btn)
        else:
            cancel_btn = QPushButton(ACTIVATION_CANCEL)
            cancel_btn.clicked.connect(self.reject)
            actions.addWidget(cancel_btn)
        root.addLayout(actions)
        self.setLayout(root)
        self.license_key = ""

    def _submit(self) -> None:
        key = self.license_input.text().strip()
        if len(key) < 8:
            QMessageBox.warning(self, ACTIVATION_TITLE, ACTIVATION_ERROR_EMPTY)
            return
        self.license_key = key
        self.accept()
