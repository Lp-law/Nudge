from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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
    ONBOARDING_EMAIL_LABEL,
    ONBOARDING_ERROR_REQUIRED,
    ONBOARDING_LATER,
    ONBOARDING_NAME_LABEL,
    ONBOARDING_OCCUPATION_LABEL,
    ONBOARDING_PHONE_LABEL,
    ONBOARDING_SUBMIT,
    ONBOARDING_SUBTITLE,
    ONBOARDING_TITLE,
)


class OnboardingDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ONBOARDING_TITLE)
        self.setModal(True)
        self.setMinimumWidth(390)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout()
        subtitle = QLabel(ONBOARDING_SUBTITLE)
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setFormAlignment(Qt.AlignmentFlag.AlignRight)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.name_input = QLineEdit()
        self.email_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.occupation_combo = QComboBox()
        self.occupation_combo.setEditable(True)
        self.occupation_combo.addItems(
            [
                "עו\"ד",
                "רואה חשבון",
                "נדל\"ן",
                "שיווק",
                "תוכנה",
                "חינוך",
                "בריאות",
                "סטודנט/ית",
                "אחר",
            ]
        )

        form.addRow(ONBOARDING_NAME_LABEL, self.name_input)
        form.addRow(ONBOARDING_EMAIL_LABEL, self.email_input)
        form.addRow(ONBOARDING_PHONE_LABEL, self.phone_input)
        form.addRow(ONBOARDING_OCCUPATION_LABEL, self.occupation_combo)
        root.addLayout(form)

        actions = QHBoxLayout()
        self.submit_btn = QPushButton(ONBOARDING_SUBMIT)
        self.later_btn = QPushButton(ONBOARDING_LATER)
        self.submit_btn.clicked.connect(self._submit)
        self.later_btn.clicked.connect(self.reject)
        actions.addWidget(self.submit_btn)
        actions.addWidget(self.later_btn)
        root.addLayout(actions)

        self.setLayout(root)
        self.payload: dict[str, str | None] = {}

    def _submit(self) -> None:
        name = " ".join(self.name_input.text().split()).strip()
        email = self.email_input.text().strip()
        phone = self.phone_input.text().strip() or None
        occupation = " ".join(self.occupation_combo.currentText().split()).strip()
        if not (name and email and occupation):
            QMessageBox.warning(self, ONBOARDING_TITLE, ONBOARDING_ERROR_REQUIRED)
            return
        self.payload = {
            "full_name": name,
            "email": email,
            "phone": phone,
            "occupation": occupation,
        }
        self.accept()
