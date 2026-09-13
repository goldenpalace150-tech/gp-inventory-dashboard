from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
app_path=ROOT/'inventory_tracker.py'
app=app_path.read_text(encoding='utf-8')

old='''            detected_reference=str(payload.get("invoice_number","")).strip()\n            reference_fallback=auto_invoice and not detected_reference\n            reference=a.text_input(t("Reference"),value=detected_reference,key="reference_"+suffix,disabled=auto_invoice and not reference_fallback)\n            if reference_fallback:st.caption(t("Invoice number manual fallback"))\n            customer=b.text_input(t("Customer name"),value=str(payload.get("customer_name","")),key="customer_"+suffix,disabled=auto_invoice)\n            driver=c.text_input(t("Driver"),value=str(payload.get("driver","")),key="driver_"+suffix)\n            kinds=["","OUT","IN"]\n            current_kind=payload.get("movement_type","") if payload.get("movement_type","") in kinds else ""\n            movement_fallback=auto_invoice and current_kind not in ("IN","OUT")\n            if auto_invoice and not movement_fallback:\n                d.text_input(t("Movement type"),value=t(current_kind),key="kind_auto_"+suffix,disabled=True)\n                kind=current_kind\n            else:\n                kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)\n                if movement_fallback:st.caption(t("Movement type manual fallback"))\n            if auto_invoice and reference_fallback:\n                st.warning(t("Automatic invoice number missing manual allowed"))\n'''
new='''            detected_reference=str(payload.get("invoice_number","")).strip()\n            reference=a.text_input(t("Reference"),value=detected_reference,key="reference_"+suffix)\n            if auto_invoice and not detected_reference:st.caption(t("Invoice number manual fallback"))\n            customer=b.text_input(t("Customer name"),value=str(payload.get("customer_name","")),key="customer_"+suffix,disabled=auto_invoice)\n            driver=c.text_input(t("Driver"),value=str(payload.get("driver","")),key="driver_"+suffix)\n            kinds=["","OUT","IN"]\n            current_kind=payload.get("movement_type","") if payload.get("movement_type","") in kinds else ""\n            kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)\n            if auto_invoice and current_kind not in ("IN","OUT"):st.caption(t("Movement type manual fallback"))\n'''
if new not in app:
    if old not in app:raise RuntimeError('invoice review auto-field marker not found')
    app=app.replace(old,new,1)
app_path.write_text(app,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.17"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.16"' not in ui:raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.16"','BUILD = "GP-CLOUD-v16.17"',1)
ui_path.write_text(ui,encoding='utf-8')

test_path=ROOT/'tests/test_core_and_ocr.py'
test=test_path.read_text(encoding='utf-8')
extra='''\n\ndef test_ocr_invoice_number_and_movement_remain_editable():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'reference=a.text_input(t("Reference"),value=detected_reference,key="reference_"+suffix)' in source\n    assert 'disabled=auto_invoice and not reference_fallback' not in source\n    assert 'kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind)' in source\n    assert 'key="kind_auto_"+suffix,disabled=True' not in source\n'''
if 'def test_ocr_invoice_number_and_movement_remain_editable()' not in test:
    test += extra
test_path.write_text(test,encoding='utf-8')

print('v16.17 editable OCR defaults applied')
