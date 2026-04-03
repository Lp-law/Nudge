from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


GUIDES: dict[str, dict[str, str]] = {
    "he": {
        "label": "עברית",
        "title": "מדריך משתמש - Nudge",
        "layout": "rtl",
        "full": """מה זה Nudge
Nudge הוא עוזר קטן ל-Windows שעוזר לשפר טקסט במהירות בזמן העבודה.
אחרי שמעתיקים טקסט, מופיע חלון קטן עם פעולות חכמות. בוחרים פעולה, והתוצאה מועתקת ללוח.

דרישות בסיסיות
- Windows 10 ומעלה
- אינטרנט פעיל
- הפעלה ברקע (System Tray)

התקנה
1) הורידו מהאתר הרשמי של Nudge.
2) פתחו את הקובץ ואשרו הרשאות Windows.
3) אם מופיע SmartScreen: More info -> Run anyway (רק מהמקור הרשמי).
4) בסיום ההתקנה Nudge יפעל ברקע.

הפעלה ראשונה
- האייקון מופיע ליד השעון.
- אין חלון ראשי גדול.
- להפעיל: סמנו טקסט ולחצו Ctrl+C.

שימוש בטקסט
1) סמנו טקסט.
2) Ctrl+C.
3) המתינו לחלון הפעולות.
4) בחרו פעולה.
5) התוצאה מועתקת ללוח.
6) Ctrl+V להדבקה.

שימוש בתמונה (OCR)
1) העתיקו/צלמו תמונה עם טקסט.
2) המתינו לחלון.
3) לחצו "חלץ טקסט".
4) הדביקו את התוצאה.

הסבר פעולות
- סיכום: תקציר קצר וברור.
- שיפור ניסוח: ניסוח ברור יותר עם אותה משמעות.
- הפוך למייל: ניסוח בסגנון מייל מקצועי.
- תיקון שפה: תיקון כתיב, דקדוק ופיסוק.
- אנגלית > עברית: תיקון טקסט שהוקלד בפריסת מקלדת שגויה.
- הסבר משמעות: הסבר פשוט למילה/ביטוי/משפט.
- חלץ טקסט: OCR מתמונה שהועתקה.

פתרון תקלות
- לא מופיע חלון: ודאו שהאייקון ב-Tray, העתיקו טקסט משמעותי, המתינו רגע.
- אין תוצאה: בדקו אינטרנט ונסו שוב.
- OCR לא עובד: ודאו שהועתקה תמונה ברורה.
- הסבר משמעות: זו פרשנות, לא תרגום מילולי.

פרטיות
Nudge מעבד תוכן מועתק כדי לספק פעולות AI/OCR בענן.
כאשר מזוהה מידע רגיש אפשרי, תופיע בקשת אישור לפני שליחה.
השתמשו בזהירות עם מידע רגיש.

תמיכה
support@nudge.example
https://www.nudge.example/help

נגישות (לעיוורים ולמשתמשי קורא מסך)
- Nudge ניתן להפעלה מלאה עם מקלדת.
- להורדה והתקנה נגישה: פתחו את אתר Nudge בדפדפן עם קורא מסך, עברו לכותרת "Download", לחצו Enter על קישור ההורדה ופעלו לפי הוראות ההתקנה הקוליות של Windows.
- אם מופיע SmartScreen, נווטו עם Tab ל-"More info", לחצו Enter, ואז Tab ל-"Run anyway" ולחצו Enter.
- שימוש יומי נגיש:
  1) סמנו טקסט והעתיקו עם Ctrl+C.
  2) המתינו לחלון Nudge.
  3) עברו בין פעולות עם Tab/Shift+Tab.
  4) אשרו פעולה עם Enter.
  5) הדביקו תוצאה עם Ctrl+V.
- ל-OCR: העתיקו תמונה עם טקסט, בחרו "חלץ טקסט" עם Tab + Enter, והדביקו.
- אם חלון הפעולות לא מופיע, בדקו ש-Nudge פעיל באזור השעון.
- למשתמשים עם קורא מסך מומלץ לעבוד עם NVDA או JAWS ב-Windows.""",
        "short_install": """התקנה מהירה:
1) הורידו מהאתר הרשמי.
2) פתחו את הקובץ ואשרו הרשאות.
3) אם יש SmartScreen: More info -> Run anyway.
4) בסיום, Nudge יופיע ב-System Tray.""",
        "short_use": """שימוש מהיר:
1) Ctrl+C על טקסט.
2) בחרו פעולה בחלון Nudge.
3) Ctrl+V להדבקה.
לתמונה: העתיקו תמונה -> "חלץ טקסט" -> הדבקה.""",
    },
    "en": {
        "label": "English",
        "title": "Nudge User Guide",
        "layout": "ltr",
        "full": """What is Nudge
Nudge is a lightweight Windows assistant for fast text improvements.
After you copy text, a small popup appears with smart actions. Choose one action and the result is copied to your clipboard.

Basic requirements
- Windows 10 or newer
- Active internet connection
- Background tray app allowed

Installation
1) Download Nudge from the official website.
2) Open the downloaded file and allow Windows prompts.
3) If SmartScreen appears: More info -> Run anyway (official source only).
4) Finish setup. Nudge starts in the background.

First run
- Nudge icon appears in the system tray.
- No large main window opens.
- Trigger it by selecting text and pressing Ctrl+C.

Using text actions
1) Select text.
2) Press Ctrl+C.
3) Wait for the popup.
4) Choose an action.
5) Result is copied to clipboard.
6) Paste with Ctrl+V.

Using image OCR
1) Copy or snip an image with text.
2) Wait for popup.
3) Click "Extract Text".
4) Paste the extracted text.

Action guide
- Summarize: short clear summary.
- Improve Wording: cleaner wording, same meaning.
- Make Email: polished email style.
- Fix Language: grammar/spelling/punctuation fixes.
- English > Hebrew Layout: fix wrong keyboard layout text.
- Explain Meaning: simple meaning explanation.
- Extract Text: OCR from copied image.

Troubleshooting
- No popup: confirm tray icon, copy meaningful text, wait 1-2 seconds.
- No result: check internet and retry.
- OCR issue: make sure copied content is a clear image.
- Explain Meaning: interpretation, not literal translation.

Privacy
Nudge processes copied content for cloud AI/OCR actions.
When possible sensitive content is detected, Nudge asks for confirmation before sending.
Use care with sensitive information.

Support
support@nudge.example
https://www.nudge.example/help

Accessibility (for blind users and screen readers)
- Nudge can be used with keyboard-only navigation.
- Accessible download/install:
  open the official website with your screen reader, jump to the Download heading, press Enter on the download link, and follow Windows spoken prompts.
- If SmartScreen appears:
  Tab to "More info", press Enter, Tab to "Run anyway", press Enter.
- Accessible daily use:
  1) Select text and press Ctrl+C.
  2) Wait for the Nudge popup.
  3) Move between actions with Tab / Shift+Tab.
  4) Press Enter to run the selected action.
  5) Paste with Ctrl+V.
- For OCR:
  copy an image with text, select "Extract Text" with Tab + Enter, then paste.
- If popup does not appear, confirm Nudge is running in the system tray.
- NVDA or JAWS are recommended on Windows.""",
        "short_install": """Quick install:
1) Download from official website.
2) Run the file and allow prompts.
3) If SmartScreen appears: More info -> Run anyway.
4) Nudge appears in your system tray.""",
        "short_use": """Quick use:
1) Copy text with Ctrl+C.
2) Choose an action in Nudge popup.
3) Paste result with Ctrl+V.
For OCR: copy image -> Extract Text -> paste.""",
    },
    "ar": {
        "label": "العربية",
        "title": "دليل Nudge",
        "layout": "rtl",
        "full": """ما هو Nudge
Nudge مساعد خفيف على Windows لتحسين النص بسرعة.
بعد نسخ النص تظهر نافذة صغيرة بإجراءات ذكية. اختر إجراءً واحدًا وسيتم نسخ النتيجة إلى الحافظة.

المتطلبات
- Windows 10 أو أحدث
- اتصال إنترنت فعال
- السماح للتطبيق بالعمل في الخلفية

التثبيت
1) نزّل Nudge من الموقع الرسمي.
2) افتح الملف ووافق على رسائل Windows.
3) إذا ظهر SmartScreen: More info ثم Run anyway (من المصدر الرسمي فقط).
4) أكمل التثبيت وسيعمل Nudge في الخلفية.

أول تشغيل
- تظهر أيقونة Nudge قرب الساعة.
- لا توجد نافذة رئيسية كبيرة.
- للتشغيل: حدّد نصًا واضغط Ctrl+C.

استخدام إجراءات النص
1) حدّد النص.
2) اضغط Ctrl+C.
3) انتظر النافذة.
4) اختر الإجراء.
5) تُنسخ النتيجة إلى الحافظة.
6) الصق بـ Ctrl+V.

استخدام OCR للصور
1) انسخ صورة تحتوي نصًا.
2) انتظر النافذة.
3) اختر "استخراج النص".
4) الصق النتيجة.

شرح الإجراءات
- تلخيص
- تحسين الصياغة
- تحويل إلى بريد
- تصحيح اللغة
- إنجليزي > عبري (تصحيح تخطيط لوحة المفاتيح)
- شرح المعنى
- استخراج النص من الصورة

حل المشكلات
- لا تظهر النافذة: تأكد من الأيقونة في الشريط وانسخ نصًا واضحًا.
- لا توجد نتيجة: تحقق من الإنترنت.
- OCR لا يعمل: استخدم صورة أوضح.

الخصوصية
يقوم Nudge بمعالجة المحتوى المنسوخ لإجراءات AI/OCR السحابية.
عند اكتشاف محتوى حساس محتمل، يطلب Nudge تأكيدًا قبل الإرسال.
استخدمه بحذر مع البيانات الحساسة.

الدعم
support@nudge.example
https://www.nudge.example/help

إمكانية الوصول (للمكفوفين ولمستخدمي قارئ الشاشة)
- يمكن استخدام Nudge بالكامل عبر لوحة المفاتيح.
- تنزيل وتثبيت بشكل قابل للوصول:
  افتح الموقع الرسمي باستخدام قارئ الشاشة، انتقل إلى عنوان Download، واضغط Enter على رابط التنزيل، ثم اتبع تعليمات Windows الصوتية.
- عند ظهور SmartScreen:
  استخدم Tab للوصول إلى More info ثم Enter، وبعدها Tab إلى Run anyway ثم Enter.
- الاستخدام اليومي القابل للوصول:
  1) حدّد النص واضغط Ctrl+C.
  2) انتظر نافذة Nudge.
  3) تنقّل بين الأزرار بـ Tab و Shift+Tab.
  4) نفّذ الإجراء بـ Enter.
  5) الصق النتيجة بـ Ctrl+V.
- للـ OCR:
  انسخ صورة تحتوي نصًا، اختر "استخراج النص" باستخدام Tab + Enter ثم الصق.
- إذا لم تظهر النافذة، تأكد أن Nudge يعمل في شريط النظام.
- يُنصح باستخدام NVDA أو JAWS على Windows.""",
        "short_install": """تثبيت سريع:
1) تنزيل من الموقع الرسمي.
2) تشغيل الملف والموافقة على الرسائل.
3) إذا ظهر SmartScreen: More info ثم Run anyway.
4) ستظهر أيقونة Nudge في شريط النظام.""",
        "short_use": """استخدام سريع:
1) انسخ نصًا بـ Ctrl+C.
2) اختر إجراءً من نافذة Nudge.
3) الصق بـ Ctrl+V.
للصور: انسخ صورة -> استخراج النص -> لصق.""",
    },
    "ru": {
        "label": "Русский",
        "title": "Руководство Nudge",
        "layout": "ltr",
        "full": """Что такое Nudge
Nudge - легкий помощник для Windows для быстрого улучшения текста.
После копирования текста появляется небольшое окно с действиями. Выберите действие, и результат скопируется в буфер обмена.

Требования
- Windows 10 и новее
- Интернет
- Разрешение на работу в фоне (tray)

Установка
1) Скачайте Nudge с официального сайта.
2) Откройте файл и подтвердите запросы Windows.
3) Если SmartScreen: More info -> Run anyway (только официальный файл).
4) Завершите установку, Nudge запустится в фоне.

Первый запуск
- Иконка Nudge видна рядом с часами.
- Большое главное окно не открывается.
- Запуск по Ctrl+C на выделенном тексте.

Использование текста
1) Выделите текст.
2) Нажмите Ctrl+C.
3) Дождитесь окна.
4) Выберите действие.
5) Результат скопируется в буфер.
6) Вставьте через Ctrl+V.

OCR для изображений
1) Скопируйте изображение с текстом.
2) Дождитесь окна.
3) Нажмите "Извлечь текст".
4) Вставьте результат.

Действия
- Суммаризация
- Улучшить формулировку
- Сделать письмо
- Исправить язык
- Английская > Иврит раскладка
- Объяснить смысл
- Извлечь текст (OCR)

Проблемы
- Нет окна: проверьте иконку в трее и скопируйте осмысленный текст.
- Нет результата: проверьте интернет.
- OCR: используйте более четкое изображение.

Конфиденциальность
Nudge обрабатывает скопированный контент для облачных AI/OCR-действий.
При обнаружении потенциально чувствительных данных Nudge запрашивает подтверждение перед отправкой.
Будьте осторожны с чувствительными данными.

Поддержка
support@nudge.example
https://www.nudge.example/help

Доступность (для незрячих и пользователей экранного доступа)
- Nudge можно использовать только с клавиатуры.
- Доступная загрузка и установка:
  откройте официальный сайт со скринридером, перейдите к заголовку Download, нажмите Enter на ссылке загрузки и следуйте голосовым подсказкам Windows.
- Если появляется SmartScreen:
  Tab до "More info" -> Enter, затем Tab до "Run anyway" -> Enter.
- Ежедневное использование:
  1) Выделите текст и нажмите Ctrl+C.
  2) Дождитесь окна Nudge.
  3) Переключайтесь между действиями Tab / Shift+Tab.
  4) Подтвердите выбор клавишей Enter.
  5) Вставьте результат через Ctrl+V.
- Для OCR:
  скопируйте изображение с текстом, выберите "Извлечь текст" через Tab + Enter, затем вставьте.
- Если окно не появляется, проверьте, что Nudge запущен в системном трее.
- На Windows рекомендуется NVDA или JAWS.""",
        "short_install": """Быстрая установка:
1) Скачайте с официального сайта.
2) Запустите файл и подтвердите запросы.
3) Если SmartScreen: More info -> Run anyway.
4) Иконка Nudge появится в трее.""",
        "short_use": """Быстрое использование:
1) Ctrl+C по тексту.
2) Выберите действие в окне Nudge.
3) Вставьте результат через Ctrl+V.
Для OCR: скопируйте изображение -> Извлечь текст -> вставить.""",
    },
}


class UserGuideDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nudge - מדריך משתמש")
        self.setMinimumSize(700, 620)

        root = QVBoxLayout()
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(QLabel("Language / שפה"))

        self.language_combo = QComboBox()
        self.language_combo.addItem("עברית", "he")
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("العربية", "ar")
        self.language_combo.addItem("Русский", "ru")
        self.language_combo.currentIndexChanged.connect(self._render_selected_language)
        top_row.addWidget(self.language_combo, 1)
        root.addLayout(top_row)

        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        root.addWidget(self.content, 1)

        close_btn = QPushButton("סגירה / Close")
        close_btn.clicked.connect(self.close)
        root.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self.setLayout(root)
        self._render_selected_language()

    def _render_selected_language(self) -> None:
        language_key = self.language_combo.currentData()
        data = GUIDES.get(language_key or "he", GUIDES["he"])
        is_rtl = data.get("layout") == "rtl"
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if is_rtl else Qt.LayoutDirection.LeftToRight
        )
        self.content.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if is_rtl else Qt.LayoutDirection.LeftToRight
        )
        self.setWindowTitle(data["title"])
        self.content.setPlainText(
            f"{data['full']}\n\n"
            "----------------------------------------\n"
            "SHORT WEBSITE VERSION - INSTALL\n\n"
            f"{data['short_install']}\n\n"
            "SHORT WEBSITE VERSION - USE\n\n"
            f"{data['short_use']}"
        )
