# Nudge — אפיון מוצר ומגבלות טכניות

מסמך זה מתאר את יכולות הלקוח והשרת, מגבלות, ופרומפטים ל־AI כפי שממומשים בקוד. ערכים תלויים־סביבה (משתני env) עשויים לסטות מברירות המחדל.

**מקורות עיקריים בקוד:** `client/app/`, `app/schemas/ai.py`, `app/services/prompt_builder.py`, `app/services/openai_service.py`, `app/services/ocr_service.py`, `app/routes/ai.py`, `app/core/config.py`.

---

## 1. ארכיטקטורה

| רכיב | תפקיד |
|------|--------|
| **לקוח (Windows)** | אפליקציית מגש (System Tray), ניטור לוח, חלון צף לפעולות, שליחת בקשות HTTPS לשרת |
| **שרת (FastAPI)** | `/ai/action`, `/ai/ocr`, אימות (JWT / מפתחות), rate limiting, לידים וכו' |
| **טקסט + AI** | Azure OpenAI — Chat Completions (`system` + `user`) |
| **תמונה** | Azure Document Intelligence — `prebuilt-read` (OCR), לא LLM |

**מופע יחיד:** הלקוח משתמש ב־`QLocalServer` — הרצה שנייה יוצאת מיד בלי UI נוסף (`client/app/main.py`).

---

## 2. לקוח — טריגר מהלוח וחלון פעולות

| פרמטר | ברירת מחדל | הערות |
|--------|------------|--------|
| מינימום תווים משמעותיים בטקסט | 8 | `minimum_non_space_chars` — `client/app/settings.py` |
| השהיה לפני טיפול בשינוי לוח | 700 ms | `popup_delay_ms` |
| מניעת טיפול חוזר באותו תוכן | 8000 ms | `duplicate_cooldown_ms` |
| סגירה אוטומטית בזמן “בחירת פעולה” | 10250 ms | `ActionPopup.IDLE_AUTO_HIDE_MS` — `client/app/popup.py` |
| אחרי הצלחה | 675 ms | `SUCCESS_AUTO_HIDE_MS` |
| אחרי שגיאה | 1050 ms | `ERROR_AUTO_HIDE_MS` |

### Timeout לבקשות HTTP (לקוח)

| סוג | משתנה סביבה | ברירת מחדל | טווח מותר |
|-----|-------------|------------|-----------|
| בקשות כלליות (אימות, onboarding, …) | `NUDGE_REQUEST_TIMEOUT_MS` | 30000 ms | 8000–120000 |
| `/ai/action`, `/ai/ocr` | `NUDGE_AI_REQUEST_TIMEOUT_MS` | 120000 ms | 20000–240000 |

### תור ללוח

אם בזמן בקשה פתוחה מגיע טקסט/תמונה חדשים — נשמרים ב־`QueuedClipboardContext` ומוצגים אחרי סיום הפעולה (`client/app/lifecycle_logic.py`, `tray_app.py`).

### stale-response

נעשה שימוש בחתימת תוכן הלוח (SHA1) כדי שלא יועתקה תוצאה אם הלוח השתנה באמצע (`tray_app.py`).

### אימות, טוקנים וסיסמה מקומית (`session_state`, `tray_app`, `pin_vault`)

- **שמירה ב־`QSettings` (מפתח `Nudge` / `NudgeClient`):**
  - `refresh_token` — תמיד אחרי הפעלה/רענון מוצלחים.
  - `access_token` — נשמר גם הוא; בפתיחה נטען רק אם ה־JWT עדיין בתוקף (עם מרווח ביטחון ~60 שניות). כך אפשר לחזור לתוכנה בלי לבצע `/auth/refresh` מיידי כל עוד ה־access לא פג.
- **סיסמה מקומית (PIN):** אופציונלי. מפתח ההפעלה המלא מוצפן במחשב עם **PBKDF2** (SHA256, 390,000 איטרציות) + **Fernet** (`cryptography`). אם רענון ה־refresh נכשל (למשל Redis אופף בשרת) אך הכספת קיימת — מוצג דיאלוג להזנת PIN בלבד, פענוח מקומי, ואז קריאה ל־`/auth/activate` עם המפתח המפוענח.
- אחרי הפעלה מוצלחת (מפתח מלא) מוצע דיאלוג האם לשמור כספת.
- תפריט מגש: **הגדרת סיסמה להפעלה מהירה**, **מחיקת סיסמה שמורה מקומית**.
- **החלפת מפתח הפעלה** (תפריט) מנקה גם טוקנים וגם כספת PIN (כדי שלא יישאר מפתח ישן מוצפן).

**מגבלות:** הסיסמה והמפתח המוצפן שמורים רק במחשב המקומי; איבוד PIN = צריך שוב את מפתח ההפעלה המלא. `NUDGE_BACKEND_ACCESS_TOKEN` ב־env אינו נשמר לדיסק (רק זיכרון).

---

## 3. פרטיות — אישור לפני ענן

- **טקסט ל־AI:** לפני `/ai/action` — `detect_sensitive_text` (`client/app/sensitive_guard.py`): אימייל, טלפון, רצף ספרות ארוך, דפוס כרטיס אשראי, מילות מפתח (password, token, api key, …). אם יש פגיעה — דיאלוג אישור.
- **תמונה ל־OCR:** תמיד נדרש אישור (לא נבדק תוכן התמונה מקומית לפני שליחה).

---

## 4. פעולות טקסט — מפתחות API ותוויות UI

מיפוי כפתור ↔ מפתח (ב־`client/app/action_contract.py`):

| תווית (עברית) | מפתח `action` | נתיב עיבוד |
|----------------|---------------|------------|
| סיכום | `summarize` | שרת + OpenAI |
| שיפור ניסוח | `improve` | שרת + OpenAI |
| הפוך למייל | `make_email` | שרת + OpenAI |
| טיוטת תשובה למייל | `reply_email` | שרת + OpenAI |
| תיקון שפה | `fix_language` | שרת + OpenAI |
| תרגם לעברית | `translate_to_he` | שרת + OpenAI |
| תרגם לאנגלית | `translate_to_en` | שרת + OpenAI |
| אנגלית > עברית | `fix_layout_he` | **מקומי בלבד** — ללא שרת |
| הסבר משמעות | `explain_meaning` | שרת + OpenAI |

---

## 5. מגבלות שרת — `/ai/action`

| מגבלה | ערך | מקור |
|--------|-----|------|
| אורך מחרוזת `text` | עד **30000** תווים | `MAX_TEXT_CHARS` — `app/schemas/ai.py` |
| גוף HTTP מקסימלי | 10 MB | `MAX_REQUEST_BODY_BYTES` — `app/core/config.py` |
| Rate limit (ברירת מחדל) | 30 בקשות ל־IP לכל 60 שניות | `RATE_LIMIT_ACTION_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` |
| פעולות מותרות | `summarize`, `improve`, `make_email`, `reply_email`, `fix_language`, `explain_meaning`, `translate_to_he`, `translate_to_en` | `app/schemas/ai.py` |

הטקסט עובר `strip()` בשרת לפני אימות.

---

## 6. פרומפטים — Azure OpenAI (Chat Completions)

הבנייה ב־`app/services/prompt_builder.py` — **הודעת `system` אחת** (בסיס + משימה) + **`user`** = תוכן הטקסט שהמשתמש העתיק.

### 6.1 חלק בסיס (תמיד, באנגלית)

```
You are Nudge, a silent AI assistant that returns compact, helpful output for micro-actions. Keep responses focused and directly usable.
```

### 6.2 שפה

- זיהוי קל (`detect_primary_output_language`): השוואת ספירת אותיות עבריות (Unicode) מול לטיניות בטקסט המשתמש.
- ל־`summarize`, `improve`, `make_email`, `reply_email`, `fix_language`: נוספת הנחיה להחזיר פלט באותה שפת עיקר של הקלט (עברית↔עברית, אנגלית↔אנגלית).
- ל־`explain_meaning`: **תמיד** הסבר בעברית, גם כשהקלט באנגלית.
- ל־`make_email`: תבנית מייל ושורת נושא (`נושא:` או `Subject:`) לפי השפה שזוהתה.
- ל־`reply_email`: טיוטת תגובה מקצועית לאימייל קיים, בשפת הקלט.
- ל־`translate_to_he`/`translate_to_en`: החזרה של תרגום בלבד (ללא הסברים/מטא), עם כלל זיהוי מקור דטרמיניסטי לפי ספירת אותיות.

### 6.3 משימות ליבה (בקוד; בתוספת בלוק שפה למעט `explain_meaning`)

הטקסטים המדויקים ב־`app/services/prompt_builder.py` — כולל `_OUTPUT_LANG_RULE` ו־`_make_email_instruction`.

### 6.4 פרמטרי קריאה ל־API (לפי פעולה)

| פרמטר | ערך |
|--------|-----|
| `temperature` | 0.2 |
| `max_tokens` / `max_completion_tokens` | לפי טבלה ב־`openai_service.MAX_OUTPUT_TOKENS_BY_ACTION` (אם המודל דוחה `max_tokens`, מעבר אוטומטי ל־`max_completion_tokens`) |
| `model` | `AZURE_OPENAI_DEPLOYMENT`; ל־`summarize` בלבד אופציונלי: `AZURE_OPENAI_DEPLOYMENT_SUMMARIZE` |
| timeout לניסיון | לפי `_REQUEST_TIMEOUT_SECONDS_BY_ACTION` (סיכום ארוך יותר; פעולות קומפקטיות קצרות יותר) |
| לולאת ניסיונות | עד **3** איטרציות; backoff 0.5 שניות (מוכפל) |

**תקרות פלט (ברירת מחדל בקוד):** `summarize` 800 · `improve`/`make_email` 512 · `fix_language` 280 · `explain_meaning` 320.

---

## 7. פעולה מקומית — `fix_layout_he`

- קובץ: `client/app/layout_converter.py`
- מיפוי תווים מפריסת מקלדת אנגלית לעברית (`EN_TO_HE_MAP`; לאותיות משתמשים ב־`lower()` לפני המיפוי).
- **אין** קריאת רשת ו**אין** AI.

---

## 8. OCR — `/ai/ocr`

| מגבלה | ערך |
|--------|-----|
| גודל תמונה | עד **5 MB** (בתים) — `MAX_OCR_IMAGE_BYTES` |
| Rate limit (ברירת מחדל) | 10 בקשות ל־IP לכל 60 שניות |
| שירות | Azure Document Intelligence — `prebuilt-read` |
| **פרומפט LLM** | אין — זה OCR |

פרטי פולינג, retries ו־timeouts: `app/services/ocr_service.py`; timeout פולינג ניתן להגדרה ב־`OCR_POLL_TIMEOUT_SECONDS` (מוגבל בין 8 ל־90 שניות).

---

## 9. נקודות לשיפור מוצר (ייעוץ / roadmap)

1. **אין זרימה “תמונה → סיכום” בלחיצה אחת** — רק חילוץ טקסט; סיכום דורש העתקה ופעולה נפרדת.
2. **לקוח:** טריגר חלון לטקסט קצר — ראה `should_open_popup_for_text` / `client/app/utils.py`; משך תצוגה — תפריט מגש «משך תצוגת חלון» (נשמר ב־`QSettings`).

---

## 10. שינוי מסמך זה

לאחר שינוי קוד (מגבלות, פרומפטים, timeouts), יש לעדכן את המסמך או להפנות לקבצי המקור הרלוונטיים.
