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
POPUP_IMAGE_STATUS = "מוכן לחילוץ טקסט"
POPUP_LOADING_STATUS = "מעבד..."
POPUP_SUCCESS_STATUS = "הועתק"

POPUP_TEXT_HELPER = "בחר פעולה. חלק מהפעולות מעבדות טקסט בענן."
POPUP_IMAGE_HELPER = "חלץ טקסט מהתמונה בלחיצה אחת (OCR בענן)."
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


def resolve_status_text(message: str) -> str:
    value = (message or "").strip()
    if not value:
        return ERROR_GENERIC
    if value in STATUS_TEXT_BY_ERROR:
        return STATUS_TEXT_BY_ERROR[value]

    lowered = value.lower()
    if "ocr service timed out" in lowered or ("ocr" in lowered and "timed out" in lowered):
        return "חילוץ הטקסט לוקח יותר מהרגיל. נסה שוב."
    if "ocr service is busy" in lowered or ("ocr" in lowered and "busy" in lowered):
        return "שירות חילוץ הטקסט עמוס כרגע."
    if "ocr service is currently unavailable" in lowered or (
        "ocr" in lowered and "unavailable" in lowered
    ):
        return "שירות חילוץ הטקסט לא זמין כרגע."
    if "invalid image payload" in lowered:
        return "התמונה לא תקינה לחילוץ טקסט."
    if "image is too large" in lowered:
        return "התמונה גדולה מדי לחילוץ טקסט."
    if "rate limit exceeded" in lowered:
        return "יותר מדי בקשות ברצף. נסה שוב בעוד רגע."
    if "request body is too large" in lowered:
        return "הבקשה גדולה מדי."
    if "internal server error" in lowered:
        return "שגיאת שרת זמנית."
    return value

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
