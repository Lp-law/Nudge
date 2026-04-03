TRAY_MENU_USER_GUIDE = "מדריך משתמש"
TRAY_MENU_ACCESSIBILITY_MODE = "מצב נגישות"
TRAY_MENU_EXIT = "יציאה"

ERROR_GENERIC = "שגיאה"
ERROR_INVALID_TEXT = "לא זוהה טקסט תקין"
ERROR_NO_IMAGE = "לא נמצאה תמונה"
ERROR_CANCELLED = "הפעולה בוטלה"

STATUS_TEXT_BY_ERROR: dict[str, str] = {
    "Timeout": "תם הזמן",
    "Network error": "שגיאת רשת",
    "Request failed": "הבקשה נכשלה",
    "Bad response": "תגובה לא תקינה",
    "Empty result": "תוצאה ריקה",
    "OCR failed": "חילוץ טקסט נכשל",
}

CLOUD_CONFIRM_TITLE = "אישור שליחה לענן"
CLOUD_CONFIRM_CONTINUE = "המשך"
CLOUD_CONFIRM_CANCEL = "ביטול"


def cloud_confirm_message(reason_text: str) -> str:
    return (
        "זוהה תוכן רגיש אפשרי.\n"
        f"סיבה: {reason_text}\n\n"
        "המידע יישלח לעיבוד בענן (AI/OCR) לפי הפעולה שבחרת.\n"
        "שימו לב: הזיהוי מבוסס דפוסים ואינו מבטיח זיהוי מלא של מידע רגיש.\n"
        "להמשיך?"
    )
