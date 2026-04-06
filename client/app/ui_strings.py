TRAY_MENU_USER_GUIDE = "מדריך משתמש"
TRAY_MENU_DIAGNOSTICS = "אבחון ותמיכה"
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
    if "unauthorized" in lowered and "request" in lowered:
        return "ההתחברות פגה או נדחתה. נסו שוב או החליפו מפתח הפעלה מתפריט המגש."
    if "unauthorized" in lowered or "not authenticated" in lowered or "forbidden" in lowered:
        return "ההתחברות פגה או נדחתה. נסו שוב או החליפו מפתח הפעלה מתפריט המגש."
    if "invalid license" in lowered:
        return "מפתח הפעלה שגוי."
    if "already active on another device" in lowered:
        return "מפתח זה כבר פעיל במחשב אחר. לעזרה צרו קשר עם התמיכה."
    if "customer activation is not available" in lowered:
        return "ההפעלה לא זמינה כרגע. צרו קשר עם התמיכה."
    if "too many activation" in lowered:
        return "ניסיונות הפעלה רבים מדי. נסו שוב בעוד כמה דקות."
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
DIAGNOSTICS_TITLE = "אבחון Nudge"
DIAGNOSTICS_COPY_BUTTON = "העתק דוח"
DIAGNOSTICS_CLOSE_BUTTON = "סגירה"
DIAGNOSTICS_COPIED_MESSAGE = "דוח האבחון הועתק ללוח."
ONBOARDING_TITLE = "השלמת פרטי משתמש"
ONBOARDING_SUBTITLE = "כדי לשפר תמיכה ושירות, נשמח למספר פרטים קצרים."
ONBOARDING_NAME_LABEL = "שם מלא"
ONBOARDING_EMAIL_LABEL = "אימייל"
ONBOARDING_PHONE_LABEL = "טלפון (אופציונלי)"
ONBOARDING_OCCUPATION_LABEL = "תחום עיסוק"
ONBOARDING_SUBMIT = "שמירה והמשך"
ONBOARDING_LATER = "מאוחר יותר"
ONBOARDING_ERROR_REQUIRED = "יש למלא שם, אימייל ותחום עיסוק."
ONBOARDING_ERROR_FAILED = "שמירת הפרטים נכשלה. אפשר לנסות שוב מאוחר יותר."

TRAY_MENU_REACTIVATE = "החלפת מפתח הפעלה…"
TRAY_MENU_PIN_SETUP = "הגדרת סיסמה להפעלה מהירה…"
TRAY_MENU_PIN_CLEAR = "מחיקת סיסמה שמורה מקומית"
TRAY_MENU_POPUP_DURATION = "משך תצוגת חלון"
TRAY_MENU_TRIGGER_MODE = "אופן הפעלה"
TRIGGER_MODE_COPY = "בהעתקה (Ctrl+C / עכבר)"
TRIGGER_MODE_DOUBLE_CTRL = "בקיצור מקלדת (Ctrl כפול)"
TRIGGER_MODE_DOUBLE_CTRL_UNAVAILABLE = "לא ניתן להפעיל Ctrl כפול במערכת זו. עוברים למצב העתקה."
POPUP_DURATION_SHORT = "קצר"
POPUP_DURATION_NORMAL = "רגיל"
POPUP_DURATION_LONG = "ארוך"

ACTIVATION_TITLE = "הפעלת Nudge"
ACTIVATION_SUBTITLE = (
    "הזינו את מפתח ההפעלה שקיבלתם ברכישה. "
    "החיבור לשרת מאובטח, ואין צורך בהגדרות נוספות."
)
ACTIVATION_SUBTITLE_OPTIONAL = (
    "הזינו מפתח הפעלה חדש כדי לחדש את הגישה לשירות. "
    "אפשר לבטל ולהמשיך בלי לשנות."
)
ACTIVATION_LICENSE_LABEL = "מפתח הפעלה"
ACTIVATION_SUBMIT = "הפעלה"
ACTIVATION_EXIT_APP = "יציאה מהתוכנה"
ACTIVATION_CANCEL = "ביטול"
ACTIVATION_ERROR_EMPTY = "מפתח ההפעלה קצר מדי. נא להדביק את המפתח המלא."
ACTIVATION_FAILED_GENERIC = "ההפעלה נכשלה. בדקו את המפתח או את החיבור לאינטרנט."

PIN_UNLOCK_TITLE = "הפעלה בסיסמה"
PIN_UNLOCK_SUBMIT = "המשך"
PIN_PASSWORD_LABEL = "סיסמה"
PIN_SETUP_TITLE = "שמירת מפתח מוגן בסיסמה"
PIN_SETUP_LICENSE_LABEL = "מפתח הפעלה"
PIN_SETUP_CONFIRM_LABEL = "אימות סיסמה"
PIN_SETUP_SUBMIT = "שמירה"
PIN_ERROR_SHORT = "הסיסמה חייבת להכיל לפחות 4 תווים."
PIN_ERROR_MISMATCH = "הסיסמאות אינן תואמות."
PIN_ERROR_WRONG = "סיסמה שגויה או נתונים פגומים."
PIN_OFFER_TITLE = "הפעלה מהירה"
PIN_OFFER_MESSAGE = (
    "לשמור את מפתח ההפעלה מוצפן במחשב זה?\n"
    "כשהתוקף של החיבור יפוג או אחרי אתחול שרת, תוכלו להזין רק סיסמה קצרה במקום המפתח המלא.\n"
    "הסיסמה נשמרת רק במחשב זה ואינה נשלחת לשרת."
)


def cloud_confirm_message(reason_text: str) -> str:
    return (
        "זוהה תוכן רגיש אפשרי.\n"
        f"סיבה: {reason_text}\n\n"
        "המידע יישלח לעיבוד בענן (AI/OCR) לפי הפעולה שבחרת.\n"
        "שימו לב: הזיהוי מבוסס דפוסים ואינו מבטיח זיהוי מלא של מידע רגיש.\n"
        "להמשיך?"
    )
