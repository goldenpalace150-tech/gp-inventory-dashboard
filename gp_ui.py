"""Arabic labels and scoped styling. No global div/span/flex direction rules."""
from pathlib import Path
import base64
import html

BUILD = "GP-CLOUD-v14"
ROOT = Path(__file__).resolve().parent
AR = {
    "Golden Palace": "\u0627\u0644\u0642\u0635\u0631 \u0627\u0644\u0630\u0647\u0628\u064a",
    "Inventory": "\u0625\u062f\u0627\u0631\u0629 \u0627\u0644\u0645\u062e\u0632\u0648\u0646",
    "Stock": "\u0627\u0644\u0645\u062e\u0632\u0648\u0646",
    "Invoices": "\u0627\u0644\u0641\u0648\u0627\u062a\u064a\u0631",
    "Movements": "\u0627\u0644\u062d\u0631\u0643\u0627\u062a",
    "Analysis": "\u0627\u0644\u062a\u062d\u0644\u064a\u0644",
    "Closing": "\u0625\u0642\u0641\u0627\u0644 \u0627\u0644\u064a\u0648\u0645",
    "Settings": "\u0627\u0644\u0625\u0639\u062f\u0627\u062f\u0627\u062a",
    "Account": "\u0627\u0644\u062d\u0633\u0627\u0628",
    "Sign in": "\u062a\u0633\u062c\u064a\u0644 \u0627\u0644\u062f\u062e\u0648\u0644",
    "Sign out": "\u062e\u0631\u0648\u062c",
    "Username": "\u0627\u0633\u0645 \u0627\u0644\u0645\u0633\u062a\u062e\u062f\u0645",
    "Password": "\u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631",
    "Approval password": "\u0643\u0644\u0645\u0629 \u0645\u0631\u0648\u0631 \u0627\u0644\u0627\u0639\u062a\u0645\u0627\u062f",
    "New password": "\u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631 \u0627\u0644\u062c\u062f\u064a\u062f\u0629",
    "Confirm password": "\u062a\u0623\u0643\u064a\u062f \u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631",
    "Refresh": "\u062a\u062d\u062f\u064a\u062b",
    "Connected": "\u0645\u062a\u0635\u0644",
    "Last save": "\u0622\u062e\u0631 \u062d\u0641\u0638",
    "Saved": "\u062a\u0645 \u0627\u0644\u062d\u0641\u0638",
    "Not saved": "\u0644\u0645 \u064a\u062a\u0645 \u0627\u0644\u062d\u0641\u0638",
    "Cloud storage": "\u0627\u0644\u062d\u0641\u0638 \u0627\u0644\u0633\u062d\u0627\u0628\u064a",
    "admin": "\u0645\u062f\u064a\u0631",
    "store": "\u0623\u0645\u064a\u0646 \u0645\u062e\u0632\u0646",
    "Items": "\u0627\u0644\u0623\u0635\u0646\u0627\u0641",
    "Available": "\u0645\u062a\u0648\u0641\u0631",
    "Today": "\u0627\u0644\u064a\u0648\u0645",
    "Without invoice": "\u0628\u0644\u0627 \u0641\u0627\u062a\u0648\u0631\u0629",
    "Search": "\u0628\u062d\u062b \u0628\u0627\u0644\u0631\u0645\u0632 \u0623\u0648 \u0627\u0644\u0627\u0633\u0645",
    "All": "\u0627\u0644\u0643\u0644",
    "Out of stock": "\u0646\u0627\u0641\u062f",
    "Export": "\u062a\u0635\u062f\u064a\u0631",
    "Prepare export": "\u062a\u062c\u0647\u064a\u0632 \u0627\u0644\u062a\u0635\u062f\u064a\u0631",
    "Download": "\u062a\u0646\u0632\u064a\u0644",
    "Upload stock": "\u0631\u0641\u0639 \u0627\u0644\u062c\u0631\u062f",
    "Upload history": "\u0631\u0641\u0639 \u0627\u0644\u062d\u0631\u0643\u0629",
    "Import": "\u0627\u0639\u062a\u0645\u0627\u062f \u0627\u0644\u0645\u0644\u0641",
    "No stock": "\u0644\u0627 \u064a\u0648\u062c\u062f \u0645\u062e\u0632\u0648\u0646. \u0627\u0631\u0641\u0639 \u0627\u0644\u062c\u0631\u062f \u0645\u0646 \u0627\u0644\u0625\u0639\u062f\u0627\u062f\u0627\u062a.",
    "Invoice image": "\u0635\u0648\u0631\u0629 \u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629",
    "Camera": "\u0627\u0644\u0643\u0627\u0645\u064a\u0631\u0627",
    "Read invoice": "\u0642\u0631\u0627\u0621\u0629 \u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629",
    "Reading": "\u062c\u0627\u0631\u064a \u0627\u0644\u0642\u0631\u0627\u0621\u0629...",
    "Manual invoice": "\u0641\u0627\u062a\u0648\u0631\u0629 \u064a\u062f\u0648\u064a\u0629",
    "Drafts": "\u0627\u0644\u0645\u0633\u0648\u062f\u0627\u062a",
    "Review": "\u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629",
    "Reference": "\u0631\u0642\u0645 \u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629",
    "Movement type": "\u0646\u0648\u0639 \u0627\u0644\u062d\u0631\u0643\u0629",
    "Select": "\u0627\u062e\u062a\u0631",
    "IN": "\u0625\u062f\u062e\u0627\u0644",
    "OUT": "\u0625\u062e\u0631\u0627\u062c",
    "Save draft": "\u062d\u0641\u0638 \u0627\u0644\u0645\u0633\u0648\u062f\u0629",
    "Post invoice": "\u0627\u0639\u062a\u0645\u0627\u062f \u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629",
    "Discard": "\u0627\u0633\u062a\u0628\u0639\u0627\u062f",
    "Confirm review": "\u0631\u0627\u062c\u0639\u062a \u0627\u0644\u0631\u0645\u0648\u0632 \u0648\u0627\u0644\u0643\u0645\u064a\u0627\u062a \u0648\u0646\u0648\u0639 \u0627\u0644\u062d\u0631\u0643\u0629",
    "Draft hint": "\u0627\u0644\u0645\u0633\u0648\u062f\u0629 \u0644\u0627 \u062a\u063a\u064a\u0651\u0631 \u0627\u0644\u0645\u062e\u0632\u0648\u0646. \u0627\u062d\u0641\u0638 \u062a\u0639\u062f\u064a\u0644\u0627\u062a\u0643 \u0642\u0628\u0644 \u0627\u0644\u062e\u0631\u0648\u062c.",
    "OCR hint": "\u0627\u0644\u0642\u0631\u0627\u0621\u0629 \u0644\u0644\u0631\u0645\u0648\u0632 \u0648\u0627\u0644\u0643\u0645\u064a\u0627\u062a. \u0627\u0644\u0623\u0633\u0645\u0627\u0621 \u0645\u0646 \u0627\u0644\u0645\u062e\u0632\u0648\u0646\u060c \u0648\u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629 \u0642\u0628\u0644 \u0627\u0644\u0627\u0639\u062a\u0645\u0627\u062f.",
    "No drafts": "\u0644\u0627 \u062a\u0648\u062c\u062f \u0645\u0633\u0648\u062f\u0627\u062a",
    "New movement": "\u062d\u0631\u0643\u0629 \u062c\u062f\u064a\u062f\u0629",
    "Item": "\u0627\u0644\u0635\u0646\u0641",
    "Quantity": "\u0627\u0644\u0643\u0645\u064a\u0629",
    "Reason": "\u0627\u0644\u0633\u0628\u0628",
    "Reference optional": "\u0627\u0644\u0645\u0631\u062c\u0639 (\u0627\u062e\u062a\u064a\u0627\u0631\u064a)",
    "Delivery confirmed": "\u062a\u0645 \u0627\u0633\u062a\u0644\u0627\u0645 \u0648\u0635\u0644 \u0627\u0644\u062a\u0633\u0644\u064a\u0645",
    "Post movement": "\u0627\u0639\u062a\u0645\u0627\u062f \u0627\u0644\u062d\u0631\u0643\u0629",
    "Movement log": "\u0633\u062c\u0644 \u0627\u0644\u062d\u0631\u0643\u0627\u062a",
    "Date": "\u0627\u0644\u062a\u0627\u0631\u064a\u062e",
    "Empty": "\u0644\u0627 \u062a\u0648\u062c\u062f \u0628\u064a\u0627\u0646\u0627\u062a",
    "Reorder": "\u0625\u0639\u0627\u062f\u0629 \u0627\u0644\u0637\u0644\u0628",
    "Critical": "\u062d\u0631\u062c",
    "Fast": "\u0633\u0631\u064a\u0639\u0629",
    "Clearance": "\u0644\u0644\u062a\u0635\u0631\u064a\u0641",
    "Summary": "\u0645\u0644\u062e\u0635 \u0627\u0644\u064a\u0648\u0645",
    "Close day": "\u0625\u0642\u0641\u0627\u0644 \u0627\u0644\u064a\u0648\u0645",
    "Closed": "\u0645\u0642\u0641\u0644",
    "Open": "\u0645\u0641\u062a\u0648\u062d",
    "Close warning": "\u0628\u0639\u062f \u0627\u0644\u0625\u0642\u0641\u0627\u0644 \u062a\u062a\u0648\u0642\u0641 \u062d\u0631\u0643\u0627\u062a \u0647\u0630\u0627 \u0627\u0644\u064a\u0648\u0645. \u0631\u0627\u062c\u0639 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u0623\u0648\u0644\u0627\u064b.",
    "Confirm closing": "\u0623\u0624\u0643\u062f \u0627\u0646\u062a\u0647\u0627\u0621 \u062d\u0631\u0643\u0627\u062a \u0627\u0644\u064a\u0648\u0645",
    "Import data": "\u0627\u0633\u062a\u064a\u0631\u0627\u062f \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a",
    "Baseline warning": "\u0647\u0630\u0627 \u0627\u0644\u0625\u062c\u0631\u0627\u0621 \u064a\u0633\u062a\u0628\u062f\u0644 \u0627\u0644\u0631\u0635\u064a\u062f \u0627\u0644\u062d\u0627\u0644\u064a. \u064a\u064f\u0633\u0645\u062d \u0628\u0647 \u0642\u0628\u0644 \u0623\u0648\u0644 \u062d\u0631\u0643\u0629 \u0641\u064a \u0627\u0644\u064a\u0648\u0645 \u0641\u0642\u0637.",
    "Confirm baseline": "\u0623\u0624\u0643\u062f \u0627\u0639\u062a\u0645\u0627\u062f \u0631\u0635\u064a\u062f \u0627\u0644\u0628\u062f\u0627\u064a\u0629",
    "History cutoff": "\u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u064a\u063a\u0637\u064a \u0627\u0644\u062d\u0631\u0643\u0627\u062a \u062d\u062a\u0649",
    "Time": "\u0627\u0644\u0648\u0642\u062a",
    "History hint": "\u062d\u062f\u062f \u0648\u0642\u062a \u062a\u063a\u0637\u064a\u0629 \u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0628\u062f\u0642\u0629. \u064a\u0636\u064a\u0641 \u0627\u0644\u062a\u062d\u0644\u064a\u0644 \u062d\u0631\u0643\u0627\u062a \u0627\u0644\u062a\u0637\u0628\u064a\u0642 \u0628\u0639\u062f \u0647\u0630\u0627 \u0627\u0644\u0648\u0642\u062a \u0641\u0642\u0637 \u0644\u0645\u0646\u0639 \u0627\u0644\u062a\u0643\u0631\u0627\u0631. \u0627\u0644\u0627\u0633\u062a\u064a\u0631\u0627\u062f \u0644\u0627 \u064a\u063a\u064a\u0631 \u0627\u0644\u0643\u0645\u064a\u0627\u062a.",
    "Reorder settings": "\u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0637\u0644\u0628",
    "Lead days": "\u0645\u062f\u0629 \u0627\u0644\u062a\u0648\u0631\u064a\u062f",
    "Safety days": "\u0623\u064a\u0627\u0645 \u0627\u0644\u0623\u0645\u0627\u0646",
    "Slow days": "\u062d\u062f \u0627\u0644\u0628\u0637\u0621",
    "Demand days": "\u0641\u062a\u0631\u0629 \u0627\u0644\u0637\u0644\u0628",
    "Review days": "\u062f\u0648\u0631\u0629 \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629",
    "Purchase prefixes": "\u0645\u0631\u0627\u062c\u0639 \u0627\u0644\u0634\u0631\u0627\u0621",
    "Users": "\u0627\u0644\u0645\u0633\u062a\u062e\u062f\u0645\u0648\u0646",
    "New user": "\u0645\u0633\u062a\u062e\u062f\u0645 \u062c\u062f\u064a\u062f",
    "Display name": "\u0627\u0644\u0627\u0633\u0645",
    "Role": "\u0627\u0644\u0635\u0644\u0627\u062d\u064a\u0629",
    "Active": "\u0641\u0639\u0627\u0644",
    "Change password": "\u062a\u063a\u064a\u064a\u0631 \u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631",
    "Save": "\u062d\u0641\u0638",
    "Audit": "\u0633\u062c\u0644 \u0627\u0644\u062a\u062f\u0642\u064a\u0642",
    "Snapshot": "\u0646\u0633\u062e\u0629 \u0643\u0627\u0645\u0644\u0629",
    "Encryption key": "\u0645\u0641\u062a\u0627\u062d \u0627\u0644\u062a\u0634\u0641\u064a\u0631",
    "Cloud hint": "\u062a\u064f\u062d\u0641\u0638 \u0627\u0644\u0639\u0645\u0644\u064a\u0627\u062a \u0627\u0644\u0645\u0639\u062a\u0645\u062f\u0629 \u0641\u064a \u0642\u0627\u0639\u062f\u0629 \u062e\u0627\u0631\u062c \u0627\u0644\u062a\u0637\u0628\u064a\u0642. \u0625\u063a\u0644\u0627\u0642 \u0627\u0644\u0645\u062a\u0635\u0641\u062d \u0644\u0627 \u064a\u062d\u0630\u0641\u0647\u0627.",
    "Past stock unavailable": "\u0644\u0627 \u062a\u0648\u062c\u062f \u0644\u0642\u0637\u0629 \u0645\u062e\u0632\u0648\u0646 \u0645\u0642\u0641\u0644\u0629 \u0644\u0647\u0630\u0627 \u0627\u0644\u064a\u0648\u0645. \u0627\u0644\u0645\u0639\u0631\u0648\u0636 \u0633\u062c\u0644 \u0627\u0644\u062d\u0631\u0643\u0627\u062a \u0641\u0642\u0637.",
    "Login failed or account temporarily locked": "\u062a\u0639\u0630\u0631 \u0627\u0644\u062f\u062e\u0648\u0644. \u0631\u0627\u062c\u0639 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u0623\u0648 \u062d\u0627\u0648\u0644 \u0628\u0639\u062f 15 \u062f\u0642\u064a\u0642\u0629.",
    "Incorrect approval password": "\u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631 \u063a\u064a\u0631 \u0635\u062d\u064a\u062d\u0629",
    "This business day is closed": "\u0647\u0630\u0627 \u0627\u0644\u064a\u0648\u0645 \u0645\u0642\u0641\u0644",
    "Please sign in again": "\u064a\u0631\u062c\u0649 \u062a\u0633\u062c\u064a\u0644 \u0627\u0644\u062f\u062e\u0648\u0644 \u0645\u062c\u062f\u062f\u0627\u064b",
    "Invalid quantity": "\u0627\u0644\u0643\u0645\u064a\u0629 \u063a\u064a\u0631 \u0635\u062d\u064a\u062d\u0629",
    "This invoice or image was already posted": "\u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629 \u0623\u0648 \u0627\u0644\u0635\u0648\u0631\u0629 \u0645\u0639\u062a\u0645\u062f\u0629 \u0633\u0627\u0628\u0642\u0627\u064b",
}


def t(value):
    return AR.get(str(value),str(value))


def css():
    return (ROOT/"assets/style.css").read_text()


def brand_html():
    data=base64.b64encode((ROOT/"assets/golden_palace.jpg").read_bytes()).decode()
    return f'''<section class="gp-brand" aria-label="Golden Palace">
        <div class="gp-brand-copy" dir="rtl"><div class="gp-eyebrow">GOLDEN PALACE / INVENTORY</div>
        <h1>{t("Golden Palace")}</h1><p>{t("Inventory")}</p></div>
        <div class="gp-logo"><img src="data:image/jpeg;base64,{data}" alt="Golden Palace"></div>
        </section>'''


def status_html(actor,stamp):
    return f'''<div class="gp-status" dir="rtl"><span class="gp-status-pill"><i></i>{t("Connected")}</span>
    <span><b>{html.escape(actor["display_name"])}</b> / {t(actor["role"])}</span>
    <span class="gp-muted">{t("Last save")} <bdi>{html.escape(str(stamp))}</bdi></span></div>'''


def kpis_html(values):
    return '<div class="gp-kpis" dir="rtl">'+''.join(
        f'<article class="gp-kpi"><span>{html.escape(t(label))}</span><strong dir="ltr">{html.escape(str(value))}</strong><small>{html.escape(t(note))}</small></article>'
        for label,value,note in values)+'</div>'


def section_html(title,note=""):
    return f'<div class="gp-section" dir="rtl"><h2>{html.escape(t(title))}</h2><p>{html.escape(t(note))}</p></div>'

# ---- v6 bilingual / branded waiting helpers ----
BUILD = "GP-CLOUD-v12"
LANGUAGE = "ar"
AR.update({
    "Language": "اللغة", "Arabic": "العربية", "English": "English",
    "Loading": "جاري التحميل...", "Processing": "جاري التنفيذ...",
    "Reading report": "جاري قراءة التقرير...", "Saving to cloud": "جاري الحفظ السحابي...",
    "Loading data": "جاري تحميل البيانات...", "Preparing analysis": "جاري تجهيز التحليل...",
    "Preparing export": "جاري تجهيز الملف...", "Importing stock": "جاري اعتماد رصيد البداية...",
    "Importing history": "جاري اعتماد حركة المادة...",
    "Use at most four decimal places": "الكمية تحتوي منازل عشرية أكثر من المسموح.",
})


def set_language(value):
    global LANGUAGE
    LANGUAGE = "en" if str(value).lower().startswith("en") else "ar"


def language_dir():
    return "rtl" if LANGUAGE == "ar" else "ltr"


def t(value):
    value = str(value)
    return AR.get(value, value) if LANGUAGE == "ar" else value


def language_marker():
    return f'<span class="gp-lang-{LANGUAGE}-marker" hidden></span>'


def _logo_data():
    return base64.b64encode((ROOT/"assets/golden_palace.jpg").read_bytes()).decode()


def _icon_data():
    return base64.b64encode((ROOT/"assets/favicon.png").read_bytes()).decode()


def brand_html():
    data = _logo_data()
    d = language_dir()
    return f'''<section class="gp-brand" aria-label="Golden Palace" dir="{d}">
        <div class="gp-brand-copy"><div class="gp-eyebrow">GOLDEN PALACE / INVENTORY</div>
        <h1>{html.escape(t("Golden Palace"))}</h1><p>{html.escape(t("Inventory"))}</p></div>
        <div class="gp-logo"><img src="data:image/jpeg;base64,{data}" alt="Golden Palace"></div>
        </section>'''


def status_html(actor,stamp):
    d = language_dir()
    return f'''<div class="gp-status" dir="{d}"><span class="gp-status-pill"><i></i>{html.escape(t("Connected"))}</span>
    <span><b>{html.escape(actor["display_name"])}</b> / {html.escape(t(actor["role"]))}</span>
    <span class="gp-muted">{html.escape(t("Last save"))} <bdi>{html.escape(str(stamp))}</bdi></span></div>'''


def kpis_html(values):
    d = language_dir()
    return '<div class="gp-kpis" dir="'+d+'">'+''.join(
        f'<article class="gp-kpi"><span>{html.escape(t(label))}</span><strong dir="ltr">{html.escape(str(value))}</strong><small>{html.escape(t(note))}</small></article>'
        for label,value,note in values)+'</div>'


def section_html(title,note=""):
    d = language_dir()
    return f'<div class="gp-section" dir="{d}"><h2>{html.escape(t(title))}</h2><p>{html.escape(t(note))}</p></div>'


def loading_html(message="Loading"):
    d = language_dir()
    return f'''<div class="gp-loading-backdrop" role="status" aria-live="polite"><div class="gp-loading-card" dir="{d}">
      <img class="gp-loading-logo" src="data:image/jpeg;base64,{_logo_data()}" alt="Golden Palace">
      <div class="gp-loading-ring"></div><strong>{html.escape(t(message))}</strong>
    </div></div>'''

# ---- v9 warehouse terminology and code-master guidance ----
AR.update({
    "Inventory": "إدارة المستودعات",
    "Stock": "المستودع",
    "store": "أمين مستودع",
    "Upload stock": "رفع جرد المستودع",
    "No stock": "لا توجد بيانات للمستودع. ارفع تقرير جرد المستودع من الإعدادات.",
    "Draft hint": "المسودة لا تغيّر رصيد المستودع. احفظ تعديلاتك قبل الخروج.",
    "OCR hint": "تُقرأ الرموز والكميات فقط، ثم يُربط كل رمز حصراً باسمه من تقرير المستودع قبل الاعتماد.",
    "Warehouse code master required": "ارفع تقرير جرد المستودع الذي يحتوي رمز المادة واسم المادة قبل قراءة الفواتير.",
    "Ignored non-item numbers": "تم تجاهل أرقام ليست رموز مواد في المستودع",
    "Importing stock": "جاري اعتماد رصيد المستودع...",
})


# ---- v10 deletion controls / centered loading popup ----
AR.update({
    "Delete data": "حذف البيانات",
    "Delete invoice": "حذف فاتورة",
    "Delete movement": "حذف حركة",
    "Delete warehouse report": "حذف تقرير المستودع",
    "Warehouse reports": "تقارير المستودع",
    "Warehouse report": "تقرير المستودع",
    "Confirm delete": "أؤكد الحذف",
    "Deleted": "تم الحذف",
    "Delete data warning": "الحذف متاح للمدير فقط ويعكس تأثير العملية على رصيد المستودع مع الاحتفاظ بسجل تدقيق.",
    "Delete reverses warehouse quantity": "سيتم عكس تأثير هذه العملية على رصيد المستودع وإعادة احتساب الحركات اللاحقة.",
    "Warehouse report delete hint": "يمكن حذف أحدث تقرير مستودع فقط، بشرط ألا توجد حركات أو إقفالات لاحقة تعتمد عليه.",
    "Only latest warehouse report can be deleted": "يمكن حذف أحدث تقرير مستودع فقط.",
    "No deletable invoices": "لا توجد فواتير قابلة للحذف اليوم.",
    "No deletable movements": "لا توجد حركات قابلة للحذف اليوم.",
    "No warehouse reports": "لا توجد تقارير مستودع محفوظة.",
    "Record not found": "السجل غير موجود أو تم حذفه مسبقاً.",
    "Only today's invoices and movements can be deleted": "يمكن حذف فواتير وحركات اليوم المفتوح فقط.",
    "Cannot delete because later movements depend on this quantity": "لا يمكن الحذف لأن حركات لاحقة تعتمد على هذه الكمية.",
    "Only the latest warehouse report can be deleted": "يمكن حذف أحدث تقرير مستودع فقط.",
    "Delete later movements before deleting this warehouse report": "احذف الحركات اللاحقة أولاً قبل حذف تقرير المستودع.",
    "A closed day depends on this warehouse report": "لا يمكن حذف التقرير لأن يوماً مقفلاً يعتمد عليه.",
})


# ---- v11 invoice workflow / warehouse update ----
AR.update({
    "Invoice details": "تفاصيل الفاتورة",
    "Invoice number": "رقم الفاتورة",
    "Customer name": "اسم الزبون",
    "Driver": "السائق",
    "Total quantity": "إجمالي الكمية",
    "Duplicate action": "عند تكرار رقم الفاتورة",
    "Ignore duplicate": "تجاهل المكرر",
    "Overwrite if changed": "تحديث إذا تغيرت البنود",
    "Duplicate invoice hint": "إذا كان رقم الفاتورة موجوداً: يتم تجاهله عند التطابق، أو يمكن تحديثه بأمان عند تعديل البنود أو الكميات.",
    "Duplicate ignored": "الفاتورة موجودة مسبقاً ولم يتم إنشاء حركة جديدة.",
    "Invoice updated": "تم تحديث الفاتورة وإعادة احتساب أثرها على المستودع.",
    "Posted invoices": "الفواتير المعتمدة",
    "No posted invoices": "لا توجد فواتير معتمدة.",
    "Saved invoice draft found": "تم العثور على مسودة محفوظة لهذه الصورة. راجعها أدناه.",
    "Customer name is too long": "اسم الزبون طويل جداً.",
    "Driver name is too long": "اسم السائق طويل جداً.",
    "Invoice details are too long": "إحدى بيانات الفاتورة طويلة جداً.",
    "Only today's invoices can be updated": "يمكن تحديث فواتير اليوم المفتوح فقط.",
    "Cannot update because later movements depend on this quantity": "لا يمكن تحديث الفاتورة لأن حركات لاحقة تعتمد على هذه الكمية.",
    "This image was already posted under another invoice number": "تم اعتماد هذه الصورة سابقاً تحت رقم فاتورة آخر.",
})


# ---- v12 OCR + accessibility / force report deletion ----
AR.update({
    "Warehouse report delete hint": "الحذف متاح للمدير دون شروط. يتم حذف سجل تقرير المستودع المحدد فقط، ولا يتم تغيير الرصيد الحالي أو الحركات اللاحقة.",
    "OCR hint": "تُقرأ رموز المواد والكميات ورقم الفاتورة تلقائياً، ويحاول النظام أيضاً تحديد نوع الحركة واسم الزبون من رأس المستند عند ظهورهما بوضوح. تبقى المراجعة قبل الاعتماد إلزامية.",
})


# ---- v13 Zoho-inspired navigation/dashboard ----
AR.update({
    "Dashboard": "لوحة التحكم",
    "Dashboard hint": "نظرة سريعة على حالة المستودع وحركة اليوم وأهم الإجراءات.",
    "Quick actions": "إجراءات سريعة",
    "Today's activity": "حركة اليوم",
    "Warehouse status": "حالة المستودع",
    "Recent invoices": "أحدث الفواتير",
})


# ---- v14 operator UX cleanup ----
AR.update({
    "Warehouse report delete hint": "اختر تقرير المستودع وأدخل كلمة مرور الاعتماد ثم اضغط حذف. الحذف متاح للمدير فقط ولا يغيّر الرصيد الحالي أو الحركات اللاحقة.",
    "OCR hint": "ارفع الفاتورة؛ يقرأ النظام نوع الحركة من عنوان المستند في الأعلى، ثم رقم الفاتورة والمواد والكميات، ويملأ اسم الزبون إذا ظهر بوضوح. راجع الحقول قبل الاعتماد.",
})
