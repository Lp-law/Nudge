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

from .pin_vault import PIN_MIN_LENGTH
from .ui_strings import (
    PIN_PASSWORD_LABEL,
    PIN_SETUP_CONFIRM_LABEL,
    PIN_SETUP_LICENSE_LABEL,
    PIN_SETUP_SUBMIT,
    PIN_SETUP_TITLE,
    PIN_UNLOCK_SUBMIT,
    PIN_UNLOCK_TITLE,
    PIN_ERROR_MISMATCH,
    PIN_ERROR_SHORT,
)


class PinUnlockDialog(QDialog):
    """Enter PIN to decrypt saved license and re-activate."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.pin = ""
        self.setWindowTitle(PIN_UNLOCK_TITLE)
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout()
        root.addWidget(QLabel(PIN_UNLOCK_TITLE))
        form = QFormLayout()
        form.setFormAlignment(Qt.AlignmentFlag.AlignRight)
        self.pin_edit = QLineEdit()
        self.pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(PIN_PASSWORD_LABEL, self.pin_edit)
        root.addLayout(form)
        row = QHBoxLayout()
        ok = QPushButton(PIN_UNLOCK_SUBMIT)
        ok.clicked.connect(self._submit)
        row.addWidget(ok)
        cancel = QPushButton("ביטול")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        root.addLayout(row)
        self.setLayout(root)

    def _submit(self) -> None:
        p = self.pin_edit.text().strip()
        if len(p) < PIN_MIN_LENGTH:
            QMessageBox.warning(self, PIN_UNLOCK_TITLE, PIN_ERROR_SHORT)
            return
        self.pin = p
        self.accept()


class PinSetupDialog(QDialog):
    """Save license encrypted with PIN (license may be fixed or editable)."""

    def __init__(self, parent=None, *, license_key: str = "", license_editable: bool = True) -> None:
        super().__init__(parent)
        self.saved_license = ""
        self.setWindowTitle(PIN_SETUP_TITLE)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout()
        root.addWidget(QLabel(PIN_SETUP_TITLE))
        form = QFormLayout()
        form.setFormAlignment(Qt.AlignmentFlag.AlignRight)
        self.license_edit = QLineEdit()
        self.license_edit.setText(license_key)
        self.license_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.license_edit.setReadOnly(not license_editable)
        form.addRow(PIN_SETUP_LICENSE_LABEL, self.license_edit)
        self.pin_edit = QLineEdit()
        self.pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(PIN_PASSWORD_LABEL, self.pin_edit)
        self.pin2_edit = QLineEdit()
        self.pin2_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(PIN_SETUP_CONFIRM_LABEL, self.pin2_edit)
        root.addLayout(form)
        row = QHBoxLayout()
        ok = QPushButton(PIN_SETUP_SUBMIT)
        ok.clicked.connect(self._submit)
        row.addWidget(ok)
        cancel = QPushButton("ביטול")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        root.addLayout(row)
        self.setLayout(root)

    def _submit(self) -> None:
        lic = self.license_edit.text().strip()
        if len(lic) < 8:
            QMessageBox.warning(self, PIN_SETUP_TITLE, "מפתח ההפעלה קצר מדי.")
            return
        p1 = self.pin_edit.text().strip()
        p2 = self.pin2_edit.text().strip()
        if len(p1) < PIN_MIN_LENGTH:
            QMessageBox.warning(self, PIN_SETUP_TITLE, PIN_ERROR_SHORT)
            return
        if p1 != p2:
            QMessageBox.warning(self, PIN_SETUP_TITLE, PIN_ERROR_MISMATCH)
            return
        self.saved_license = lic
        self.pin = p1
        self.accept()

