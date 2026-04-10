/**
 * Hebrew UI strings -- default language.
 * Matches the desktop client's ui_strings.py and action_contract.py labels.
 */
const he = {
  // General
  appTitle: "Nudge",
  loading: "...טוען",
  error: "שגיאה",
  cancel: "ביטול",
  copy: "העתק",
  copied: "הועתק",
  back: "חזרה",
  settings: "הגדרות",
  about: "אודות",
  logout: "התנתקות",
  logoutConfirm: "להתנתק מ-Nudge?",
  logoutConfirmYes: "התנתקות",

  // Activation
  activationTitle: "הפעלת Nudge",
  activationSubtitle:
    "הזינו את מפתח ההפעלה שקיבלתם ברכישה. החיבור לשרת מאובטח, ואין צורך בהגדרות נוספות.",
  activationLicenseLabel: "מפתח הפעלה",
  activationSubmit: "הפעלה",
  activationErrorEmpty: "מפתח ההפעלה קצר מדי. נא להדביק את המפתח המלא.",
  activationFailedGeneric:
    "ההפעלה נכשלה. בדקו את המפתח או את החיבור לאינטרנט.",

  // Home
  homeTitle: "Nudge",
  homeInputPlaceholder: "הדביקו או הקלידו טקסט כאן...",
  homeSelectAction: "בחר פעולה",

  // Actions (match ACTION_LABELS from action_contract.py)
  action_summarize: "סיכום",
  action_improve: "שיפור ניסוח",
  action_make_email: "הפוך למייל",
  action_reply_email: "טיוטת תשובה למייל",
  action_fix_language: "תיקון שפה",
  action_translate_to_he: "תרגם לעברית",
  action_translate_to_en: "תרגם לאנגלית",
  action_fix_layout_he: "אנגלית > עברית",
  action_explain_meaning: "הסבר משמעות",

  // Result
  resultTitle: "תוצאה",
  resultCopied: "התוצאה הועתקה ללוח.",
  resultEmpty: "תוצאה ריקה",

  // OCR
  ocrTitle: "חילוץ טקסט (OCR)",
  ocrPickCamera: "צלם תמונה",
  ocrPickGallery: "בחר מהגלריה",
  ocrProcessing: "מעבד...",
  ocrNoImage: "לא נבחרה תמונה.",
  ocrExtractButton: "חלץ טקסט",

  // Errors (matching desktop ui_strings.py)
  errorInvalidText: "לא זוהה טקסט תקין",
  errorNoImage: "לא נמצאה תמונה",
  errorCancelled: "הפעולה בוטלה",
  errorTimeout: "תם הזמן",
  errorNetwork: "שגיאת רשת",
  errorRequestFailed: "הבקשה נכשלה",
  errorBadResponse: "תגובה לא תקינה",
  errorEmptyResult: "תוצאה ריקה",
  errorOcrFailed: "חילוץ טקסט נכשל",
  errorRateLimited: "יותר מדי בקשות ברצף. נסה שוב בעוד רגע.",
  errorUnauthorized:
    "ההתחברות פגה או נדחתה. נסו שוב או הפעילו מחדש עם מפתח הפעלה.",
  errorInvalidLicense: "מפתח הפעלה שגוי.",
  errorDeviceMismatch:
    "מפתח זה כבר פעיל במחשב אחר. לעזרה צרו קשר עם התמיכה.",
  errorActivationUnavailable: "ההפעלה לא זמינה כרגע. צרו קשר עם התמיכה.",
  errorTooManyActivations: "ניסיונות הפעלה רבים מדי. נסו שוב בעוד כמה דקות.",
  errorServerError: "שגיאת שרת זמנית.",

  // Settings
  settingsTitle: "הגדרות",
  settingsLanguage: "שפה",
  settingsVersion: "גרסה",
  settingsBuildInfo: "מידע על הבנייה",
} as const;

export type TranslationKeys = keyof typeof he;
export default he;
