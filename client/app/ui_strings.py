TRAY_MENU_USER_GUIDE = "מדריך משתמש"
TRAY_MENU_ACCESSIBILITY_MODE = "מצב נגישות"
TRAY_MENU_EXIT = "יציאה"
APP_TITLE = "Nudge"
TRAY_UNAVAILABLE_MESSAGE = "אזור ההודעות (System Tray) לא זמין. Nudge לא יכול לרוץ בסשן הזה."

ERROR_GENERIC = "שגיאה"
ERROR_INVALID_TEXT = "לא זוהה טקסט תקין"
ERROR_NO_IMAGE = "לא נמצאה תמונה"
ERROR_CANCELLED = "הפעולה בוטלה"

POPUP_IDLE_STATUS = "בחר פעולה"
POPUP_IMAGE_STATUS = "בחר פעולה לתמונה"
POPUP_LOADING_STATUS = "מעבד..."
POPUP_SUCCESS_STATUS = "הועתק"

POPUP_TEXT_HELPER = "בחר פעולה. חלק מהפעולות מעבדות טקסט בענן."
POPUP_IMAGE_HELPER = "חלץ טקסט מהתמונה (OCR בענן)."
POPUP_SUCCESS_HELPER = "התוצאה הועתקה ללוח והחליפה את התוכן הקודם."
POPUP_ACCESSIBILITY_HELPER = "מצב נגישות פעיל: ניתן לנווט עם Tab ולהפעיל עם Enter."
POPUP_CONTEXT_CHANGED_HELPER = "זוהה תוכן חדש. הוא יוצג אוטומטית בסיום הפעולה הנוכחית."

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
