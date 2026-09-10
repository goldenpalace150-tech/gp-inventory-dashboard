from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Missing update marker: {label}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# inventory_tracker.py
# - warehouse-report delete button is always enabled for an admin
# - remove OCR warning spam from invoice review; uncertain values stay editable
# ---------------------------------------------------------------------------
path = ROOT / "inventory_tracker.py"
text = path.read_text(encoding="utf-8")

old = '''        with st.form("delete_stock_report_form"):
            st.caption(t("Warehouse report delete hint"))
            confirmed=st.checkbox(t("Confirm delete"),key="delete_stock_report_confirm")
            password=st.text_input(t("Approval password"),type="password",key="password_delete_stock")
            if st.form_submit_button(t("Delete warehouse report"),type="primary",disabled=not confirmed):
                try:store.delete_stock_report(token,password,selected);success(message="Deleted")
                except Exception as error:show_error(error)
'''
new = '''        with st.form("delete_stock_report_form"):
            st.caption(t("Warehouse report delete hint"))
            password=st.text_input(t("Approval password"),type="password",key="password_delete_stock")
            if st.form_submit_button(t("Delete warehouse report"),type="primary"):
                try:store.delete_stock_report(token,password,selected);success(message="Deleted")
                except Exception as error:show_error(error)
'''
text = replace_once(text, old, new, "direct admin warehouse report deletion")

old = '''        draft=choices[selected];payload=draft["payload"];suffix=selected+"_"+str(draft["version"])
        for message in payload.get("warnings",[])[:6]:st.warning(str(message))
        st.caption(t("Draft hint"))
        rows=payload.get("items") or []
'''
new = '''        draft=choices[selected];payload=draft["payload"];suffix=selected+"_"+str(draft["version"])
        # OCR diagnostics remain stored in the draft payload for troubleshooting,
        # but the operator sees the extracted fields directly instead of a stack
        # of technical yellow warnings.
        st.caption(t("Draft hint"))
        rows=payload.get("items") or []
'''
text = replace_once(text, old, new, "hide invoice OCR warning stack")

old = '''        if ignored_saved:st.warning(t("Ignored non-item numbers")+": "+", ".join(ignored_saved[:8]))
        rows=rows or [{"item_code":"","item_name":"","quantity":None}]
'''
new = '''        # Numbers that are not valid warehouse item codes are silently ignored.
        # They remain available in OCR diagnostics, but do not confuse the operator.
        rows=rows or [{"item_code":"","item_name":"","quantity":None}]
'''
text = replace_once(text, old, new, "hide ignored OCR number warning")

path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# invoice_ocr_worker.py
# - scan the actual top title band where Golden Palace prints IN/OUT wording
# - tolerate OCR spacing when matching Arabic title phrases
# ---------------------------------------------------------------------------
path = ROOT / "invoice_ocr_worker.py"
text = path.read_text(encoding="utf-8")
text = text.replace('BUILD = "GP-OCR-WAREHOUSE-v12"', 'BUILD = "GP-OCR-WAREHOUSE-v14"', 1)

old = '''    left, top = int(width * 0.02), int(height * 0.20)
    right, bottom = int(width * 0.98), int(height * 0.45)
'''
new = '''    # The movement title (for example: مذكرة تسليم / إخراج مواد) is printed
    # close to the top of the Golden Palace invoice. Start much earlier than the
    # previous 20% crop while still including the recipient/customer line below.
    left, top = int(width * 0.02), int(height * 0.04)
    right, bottom = int(width * 0.98), int(height * 0.46)
'''
text = replace_once(text, old, new, "top-of-invoice Arabic header crop")

old = '''    normalized = [_arabic_search_text(row.get("text", "")) for row in rows]
    joined = " | ".join(normalized)

    movement = ""
    # Prefer explicit stock terminology. Generic delivery/receipt words are only
    # fallbacks because they can also appear in explanatory sentences.
    if any(token in joined for token in ("اخراج مواد", "اخراج مخازن", "حركة اخراج", "مذكرة تسليم")):
        movement = "OUT"
    elif any(token in joined for token in ("ادخال مواد", "ادخال مخازن", "حركة ادخال", "مذكرة استلام")):
        movement = "IN"
    elif "اخراج" in joined:
        movement = "OUT"
    elif "ادخال" in joined:
        movement = "IN"
'''
new = '''    normalized = [_arabic_search_text(row.get("text", "")) for row in rows]
    joined = " | ".join(normalized)
    compact = re.sub(r"\\s+", "", joined)

    def has_phrase(value):
        value = _arabic_search_text(value)
        return value in joined or re.sub(r"\\s+", "", value) in compact

    movement = ""
    # Read the document title first. The compact comparison also catches OCR that
    # inserts/removes spaces between Arabic words.
    if any(has_phrase(token) for token in ("اخراج مواد", "اخراج مخازن", "حركة اخراج", "مذكرة تسليم")):
        movement = "OUT"
    elif any(has_phrase(token) for token in ("ادخال مواد", "ادخال مخازن", "حركة ادخال", "مذكرة استلام")):
        movement = "IN"
    elif has_phrase("اخراج"):
        movement = "OUT"
    elif has_phrase("ادخال"):
        movement = "IN"
'''
text = replace_once(text, old, new, "robust movement title recognition")
path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# gp_ocr.py - keep build marker aligned with worker
# ---------------------------------------------------------------------------
path = ROOT / "gp_ocr.py"
text = path.read_text(encoding="utf-8")
text = text.replace('OCR_BUILD = "GP-OCR-WAREHOUSE-v12"', 'OCR_BUILD = "GP-OCR-WAREHOUSE-v14"', 1)
path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# gp_ui.py - v14 build + concise operator guidance
# ---------------------------------------------------------------------------
path = ROOT / "gp_ui.py"
text = path.read_text(encoding="utf-8")
text = text.replace('BUILD = "GP-CLOUD-v13"', 'BUILD = "GP-CLOUD-v14"', 1)
if '# ---- v14 operator UX cleanup ----' not in text:
    text += '''\n\n# ---- v14 operator UX cleanup ----\nAR.update({\n    "Warehouse report delete hint": "اختر تقرير المستودع وأدخل كلمة مرور الاعتماد ثم اضغط حذف. الحذف متاح للمدير فقط ولا يغيّر الرصيد الحالي أو الحركات اللاحقة.",\n    "OCR hint": "ارفع الفاتورة؛ يقرأ النظام نوع الحركة من عنوان المستند في الأعلى، ثم رقم الفاتورة والمواد والكميات، ويملأ اسم الزبون إذا ظهر بوضوح. راجع الحقول قبل الاعتماد.",\n})\n'''
path.write_text(text, encoding="utf-8")

print("v14 UX cleanup applied")
