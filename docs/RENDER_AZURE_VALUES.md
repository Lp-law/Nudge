# Render: איפה למלא כל ערך (Azure + ידני)

הקובץ `render.yaml` מגדיר את **כל** משתני הסביבה. אי אפשר למלא עבורך מפתחות סודיים מהמחשב הזה — צריך להדביק אותם ב־**Render Dashboard → Environment** (או לסנכרן Blueprint ואז למלא שורות עם `sync: false`).

## Azure OpenAI (חובה לפעולות טקסט)

| משתנה ב-Render | איפה ב-Azure Portal |
|----------------|---------------------|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI → המשאב שלך → **Keys and Endpoint** → Key 1 |
| `AZURE_OPENAI_ENDPOINT` | אותו מסך → **Endpoint** (כתובת `https://....openai.azure.com`) |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI → **Deployments** → שם ה-deployment של המודל (לא שם המודל הגולמי) |
| `AZURE_OPENAI_API_VERSION` | בדרך כלל `2024-02-15-preview` (כבר ב־`render.yaml`) |

## Azure AI Document Intelligence (חובה ל-OCR / חילוץ טקסט מתמונה)

| משתנה ב-Render | איפה ב-Azure Portal |
|----------------|---------------------|
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | Document Intelligence (או Cognitive Services) → **Keys and Endpoint** → Endpoint (`https://....cognitiveservices.azure.com`) |
| `AZURE_DOC_INTELLIGENCE_API_KEY` | אותו מסך → Key 1 או 2 |
| `AZURE_DOC_INTELLIGENCE_API_VERSION` | בדרך כלל `2024-02-29-preview` (ברירת מחדל ב־YAML) |

## אימות Nudge (ברירת מחדל בפריסה: `token`)

| משתנה | הערה |
|--------|------|
| `NUDGE_TOKEN_SIGNING_KEY` | ב־Blueprint: `generateValue: true`. אם השורה ריקה בדשבורד — מחקו והחילו מחדש Blueprint, או הדביקו סוד ארוך ידנית. |
| `NUDGE_AUTH_BOOTSTRAP_KEY` | כנ"ל. |
| `NUDGE_AUTH_MODE` | נשאר `token` לפרודקשן. |
| `NUDGE_CUSTOMER_LICENSE_KEYS` / `NUDGE_TRIAL_LICENSE_KEYS` | מפתחות שאתה מנפיק ללקוחות/בודקים (מופרדים בפסיק). |

## אופציונלי

| משתנה | מתי |
|--------|-----|
| `REDIS_URL` | אם תעביר ל־`RATE_LIMIT_BACKEND=redis` ו־`TOKEN_STATE_BACKEND=redis` |
| `NUDGE_BACKEND_API_KEY` | רק אם `NUDGE_ALLOW_LEGACY_API_KEY=true` (לא מומלץ לפרודקשן) |
| `ADMIN_DASHBOARD_*` | אם מפעילים `ADMIN_DASHBOARD_ENABLED=true` |

## למה בדשבורד רואים רק חמש שורות?

שירות שנוצר **בלי** Blueprint מלא, או Blueprint ישן, לא מקבל אוטומטית את כל הרשימה. **פתרון:** קשר מחדש את הפרויקט ל־`render.yaml` מהריפו, או **הוסף ידנית** כל מפתח מהטבלאות למעלה (שמות בדיוק כמו בעמודה הראשונה).
