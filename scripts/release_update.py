from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# -----------------------------
# Invoice-number manual fallback
# -----------------------------
app_path = ROOT / "inventory_tracker.py"
app = app_path.read_text(encoding="utf-8")

old = '''            reference=a.text_input(t("Reference"),value=str(payload.get("invoice_number","")),key="reference_"+suffix,disabled=auto_invoice)
            customer=b.text_input(t("Customer name"),value=str(payload.get("customer_name","")),key="customer_"+suffix,disabled=auto_invoice)
'''
new = '''            detected_reference=str(payload.get("invoice_number","")).strip()
            reference_fallback=auto_invoice and not detected_reference
            reference=a.text_input(t("Reference"),value=detected_reference,key="reference_"+suffix,disabled=auto_invoice and not reference_fallback)
            if reference_fallback:st.caption(t("Invoice number manual fallback"))
            customer=b.text_input(t("Customer name"),value=str(payload.get("customer_name","")),key="customer_"+suffix,disabled=auto_invoice)
'''
if new not in app:
    if old not in app:
        raise RuntimeError("invoice reference field marker not found")
    app = app.replace(old, new, 1)

old = '''            if auto_invoice and not reference.strip():
                st.warning(t("Automatic invoice number missing"))
'''
new = '''            if auto_invoice and reference_fallback:
                st.warning(t("Automatic invoice number missing manual allowed"))
'''
if new not in app:
    if old not in app:
        raise RuntimeError("invoice reference warning marker not found")
    app = app.replace(old, new, 1)

old = '''                    if auto_invoice and not reference.strip():raise AppError("Automatic invoice number required")
                    if kind not in ("IN","OUT"):raise AppError("Movement type required")
'''
new = '''                    if not reference.strip():raise AppError("Invoice number required")
                    if kind not in ("IN","OUT"):raise AppError("Movement type required")
'''
if new not in app:
    if old not in app:
        raise RuntimeError("invoice reference validation marker not found")
    app = app.replace(old, new, 1)

# -----------------------------------
# End-of-day physical stock comparison
# -----------------------------------
old = '''    report=day_report_sheets(day,ledger,day_stock,analysis,closure)
    export_button("GoldenPalace_Day_"+day.isoformat(),report)
    if not closure and actor["role"]=="admin" and day==store.today():
        with st.form("close_day"):
'''
new = '''    report=day_report_sheets(day,ledger,day_stock,analysis,closure)
    export_button("GoldenPalace_Day_"+day.isoformat(),report)

    if not closure and actor["role"]=="admin" and day==store.today():
        st.divider()
        section("End of day stock check","End of day stock check hint")
        counted_file=st.file_uploader(t("Upload closing stock report"),type=["xlsx","xls"],key="closing_stock_report")
        if counted_file:
            try:
                counted=parse_stock_report(counted_file.getvalue())
                expected=stock[[COL_KEY,COL_CODE,COL_NAME,COL_QTY]].copy().rename(columns={COL_QTY:"System quantity"})
                physical=counted[[COL_KEY,COL_CODE,COL_NAME,COL_QTY]].copy().rename(columns={COL_QTY:"Counted quantity"})
                comparison=expected.merge(physical[[COL_KEY,"Counted quantity"]],on=COL_KEY,how="outer")
                comparison[COL_CODE]=comparison[COL_CODE].fillna("")
                comparison[COL_NAME]=comparison[COL_NAME].fillna("")
                comparison["System quantity"]=pd.to_numeric(comparison["System quantity"],errors="coerce").fillna(0.0)
                comparison["Counted quantity"]=pd.to_numeric(comparison["Counted quantity"],errors="coerce").fillna(0.0)
                comparison["Difference"]=comparison["Counted quantity"]-comparison["System quantity"]
                differences=comparison[comparison["Difference"].abs()>0.0001].copy()
                a,b,c=st.columns(3)
                a.metric(t("Compared items"),f"{len(comparison):,}")
                b.metric(t("Matching items"),f"{len(comparison)-len(differences):,}")
                c.metric(t("Different items"),f"{len(differences):,}")
                if differences.empty:
                    st.success(t("Closing stock matches"))
                else:
                    st.warning(t("Closing stock differences found"))
                    shown=differences[[COL_CODE,COL_NAME,"System quantity","Counted quantity","Difference"]].rename(columns={
                        "System quantity":t("System quantity"),"Counted quantity":t("Counted quantity"),"Difference":t("Difference")})
                    table(shown,height=360)
                    export_button("GoldenPalace_Stock_Reconciliation_"+day.isoformat(),{"Comparison":comparison,"Differences":differences})
            except Exception as error:show_error(error)

        with st.form("close_day"):
'''
if new not in app:
    if old not in app:
        raise RuntimeError("closing comparison insertion marker not found")
    app = app.replace(old, new, 1)

app_path.write_text(app, encoding="utf-8")

# -----------------------------
# Labels and build
# -----------------------------
ui_path = ROOT / "gp_ui.py"
ui = ui_path.read_text(encoding="utf-8")
if 'BUILD = "GP-CLOUD-v16.7"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.6"' not in ui:
        raise RuntimeError("build marker not found")
    ui = ui.replace('BUILD = "GP-CLOUD-v16.6"', 'BUILD = "GP-CLOUD-v16.7"', 1)

labels = '''\n\n# ---- v16.7 invoice fallback + closing stock reconciliation ----\nAR.update({\n    "Invoice number manual fallback": "تعذر قراءة رقم الفاتورة تلقائياً. أدخل رقم الفاتورة يدوياً.",\n    "Automatic invoice number missing manual allowed": "تعذر قراءة رقم الفاتورة تلقائياً. يمكنك إدخاله يدوياً ثم اعتماد الفاتورة.",\n    "Invoice number required": "أدخل رقم الفاتورة.",\n    "End of day stock check": "مطابقة جرد نهاية اليوم",\n    "End of day stock check hint": "ارفع تقرير جرد المستودع في نهاية اليوم لمقارنة الكميات الفعلية مع رصيد النظام قبل الإقفال.",\n    "Upload closing stock report": "رفع تقرير جرد نهاية اليوم",\n    "Compared items": "الأصناف المقارنة",\n    "Matching items": "الأصناف المطابقة",\n    "Different items": "الأصناف المختلفة",\n    "System quantity": "كمية النظام",\n    "Counted quantity": "الكمية الفعلية",\n    "Difference": "الفرق",\n    "Closing stock matches": "الجرد الفعلي مطابق لرصيد النظام.",\n    "Closing stock differences found": "توجد فروقات بين الجرد الفعلي ورصيد النظام.",\n})\n'''
if '"End of day stock check":' not in ui:
    marker = '\ndef set_language('
    pos = ui.find(marker)
    if pos < 0:
        raise RuntimeError("language marker not found")
    ui = ui[:pos] + labels + ui[pos:]
ui_path.write_text(ui, encoding="utf-8")

# -----------------------------
# Regression checks
# -----------------------------
test_path = ROOT / "tests/test_core_and_ocr.py"
test = test_path.read_text(encoding="utf-8")
extra = '''\n\ndef test_invoice_number_manual_fallback_and_closing_stock_compare_present():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'reference_fallback=auto_invoice and not detected_reference' in source\n    assert 'disabled=auto_invoice and not reference_fallback' in source\n    assert 'Invoice number manual fallback' in source\n    assert 'if not reference.strip():raise AppError("Invoice number required")' in source\n    assert 'Upload closing stock report' in source\n    assert 'comparison["Difference"]=comparison["Counted quantity"]-comparison["System quantity"]' in source\n    assert 'GoldenPalace_Stock_Reconciliation_' in source\n'''
if 'def test_invoice_number_manual_fallback_and_closing_stock_compare_present()' not in test:
    test += extra

test_path.write_text(test, encoding="utf-8")

print("v16.7 invoice fallback and closing stock reconciliation applied")
