from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

# 1) Auto invoices: keep movement automatic when detected, otherwise allow manual fallback.
app_path=ROOT/'inventory_tracker.py'
app=app_path.read_text(encoding='utf-8')
old='''            if auto_invoice:
                d.text_input(t("Movement type"),value=t(current_kind) if current_kind else t("Not detected"),key="kind_auto_"+suffix,disabled=True)
                kind=current_kind
            else:
                kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)
            if auto_invoice and (not reference.strip() or kind not in ("IN","OUT")):
                st.warning(t("Automatic invoice fields incomplete"))
'''
new='''            movement_fallback=auto_invoice and current_kind not in ("IN","OUT")
            if auto_invoice and not movement_fallback:
                d.text_input(t("Movement type"),value=t(current_kind),key="kind_auto_"+suffix,disabled=True)
                kind=current_kind
            else:
                kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)
                if movement_fallback:st.caption(t("Movement type manual fallback"))
            if auto_invoice and not reference.strip():
                st.warning(t("Automatic invoice number missing"))
'''
if new not in app:
    if old not in app: raise RuntimeError('movement review marker not found')
    app=app.replace(old,new,1)

old='''                    if auto_invoice and not reference.strip():raise AppError("Automatic invoice number required")
                    if auto_invoice and kind not in ("IN","OUT"):raise AppError("Automatic movement type required")
                    updated=dict(payload);updated.update(invoice_number=reference.strip(),movement_type=kind,
'''
new='''                    if auto_invoice and not reference.strip():raise AppError("Automatic invoice number required")
                    if kind not in ("IN","OUT"):raise AppError("Movement type required")
                    updated=dict(payload);updated.update(invoice_number=reference.strip(),movement_type=kind,
'''
if new not in app:
    if old not in app: raise RuntimeError('movement validation marker not found')
    app=app.replace(old,new,1)
app_path.write_text(app,encoding='utf-8')

# 2) Focus Arabic OCR on the actual title/recipient band and add a robust delivery-word fallback.
worker_path=ROOT/'invoice_ocr_worker.py'
worker=worker_path.read_text(encoding='utf-8')
worker=worker.replace('BUILD = "GP-OCR-WAREHOUSE-v16.5"','BUILD = "GP-OCR-WAREHOUSE-v16.6"',1)
old='''def run_header_ocr(array):
    """Read only the document title + recipient/customer strip in Arabic."""
    global _engine
    # Numeric recognition is finished before this call. Release that ONNX session
    # before loading Arabic recognition to stay inside Streamlit Cloud memory.
    _engine = None
    gc.collect()
    height, width = array.shape[:2]
    # The movement title (for example: مذكرة تسليم / إخراج مواد) is printed
    # close to the top of the Golden Palace invoice. Start much earlier than the
    # previous 20% crop while still including the recipient/customer line below.
    left, top = int(width * 0.02), int(height * 0.04)
    right, bottom = int(width * 0.98), int(height * 0.46)
    crop = array[top:bottom, left:right]
    if crop.size == 0:
        return []
    boxes = run_arabic_ocr(crop)
    for box in boxes:
        box["x"] += left
        box["y"] += top
        box["region"] = "header"
    return boxes
'''
new='''def run_header_ocr(array):
    """Read the Golden Palace document title + recipient strip in Arabic.

    A focused crop is more reliable than sending the logo, phone numbers and most
    of the page to the Arabic recognizer. The supplied delivery note prints
    "مذكرة تسليم (إخراج مواد)" in this band.
    """
    global _engine
    _engine = None
    gc.collect()
    height, width = array.shape[:2]
    left, top = int(width * 0.04), int(height * 0.15)
    right, bottom = int(width * 0.96), int(height * 0.42)
    crop = array[top:bottom, left:right]
    if crop.size == 0:
        return []
    boxes = run_arabic_ocr(crop)
    for box in boxes:
        box["x"] += left
        box["y"] += top
        box["region"] = "header"
    return boxes
'''
if new not in worker:
    if old not in worker: raise RuntimeError('header crop marker not found')
    worker=worker.replace(old,new,1)
old='''    elif has_phrase("اخراج"):
        movement = "OUT"
    elif has_phrase("ادخال"):
        movement = "IN"
'''
new='''    elif has_phrase("اخراج"):
        movement = "OUT"
    elif has_phrase("ادخال"):
        movement = "IN"
    elif has_phrase("تسليم"):
        movement = "OUT"
    elif has_phrase("استلام"):
        movement = "IN"
'''
if new not in worker:
    if old not in worker: raise RuntimeError('movement parser marker not found')
    worker=worker.replace(old,new,1)
worker=worker.replace('warnings.append("نوع الحركة غير مؤكد؛ أعد تصوير الفاتورة بصورة أوضح.")','warnings.append("نوع الحركة غير مؤكد؛ اختر نوع الحركة يدوياً في المراجعة.")',1)
worker=worker.replace('warnings.append("تعذر قراءة بيانات رأس الفاتورة؛ أعد تصوير الفاتورة بصورة أوضح.")','warnings.append("تعذر قراءة بيانات رأس الفاتورة؛ يمكن اختيار نوع الحركة يدوياً في المراجعة.")',1)
worker_path.write_text(worker,encoding='utf-8')

ocr_path=ROOT/'gp_ocr.py'
ocr=ocr_path.read_text(encoding='utf-8')
ocr=ocr.replace('OCR_BUILD = "GP-OCR-WAREHOUSE-v16.5"','OCR_BUILD = "GP-OCR-WAREHOUSE-v16.6"',1)
ocr_path.write_text(ocr,encoding='utf-8')

# 3) Version and Arabic wording.
ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.6"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.5"' not in ui: raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.5"','BUILD = "GP-CLOUD-v16.6"',1)
labels='''\n\n# ---- v16.6 movement OCR/manual fallback ----\nAR.update({\n    "Movement type manual fallback": "تعذر تحديد نوع الحركة تلقائياً. اختر إدخال أو إخراج يدوياً.",\n    "Automatic invoice number missing": "تعذر قراءة رقم الفاتورة تلقائياً. أعد التصوير بصورة أوضح.",\n    "Movement type required": "اختر نوع الحركة: إدخال أو إخراج.",\n})\n'''
if '"Movement type manual fallback":' not in ui:
    marker='\ndef set_language('
    pos=ui.find(marker)
    if pos<0: raise RuntimeError('language marker not found')
    ui=ui[:pos]+labels+ui[pos:]
ui_path.write_text(ui,encoding='utf-8')

# 4) Regression tests.
test_path=ROOT/'tests/test_core_and_ocr.py'
t=test_path.read_text(encoding='utf-8')
t=t.replace('from invoice_ocr_worker import parse_codes,parse_quantity,parse_summary','from invoice_ocr_worker import parse_codes,parse_quantity,parse_summary,parse_header_metadata',1)
t=t.replace("    assert 'Automatic movement type required' in source\n","    assert 'movement_fallback=auto_invoice and current_kind not in (\"IN\",\"OUT\")' in source\n    assert 'Movement type required' in source\n",1)
extra='''\n\ndef test_delivery_word_fallback_detects_out_movement():\n    boxes=[{\"text\":\"يرجى تسليم المواد المذكورة أدناه\",\"score\":.90,\"x\":500,\"y\":300,\"region\":\"header\"}]\n    movement,customer=parse_header_metadata(boxes,1000,1200)\n    assert movement==\"OUT\"\n\n\ndef test_auto_invoice_allows_manual_movement_only_when_ocr_misses_it():\n    source=(Path(__file__).resolve().parents[1]/\"inventory_tracker.py\").read_text()\n    assert 'movement_fallback=auto_invoice and current_kind not in (\"IN\",\"OUT\")' in source\n    assert 'if movement_fallback:st.caption(t(\"Movement type manual fallback\"))' in source\n    assert 'if kind not in (\"IN\",\"OUT\"):raise AppError(\"Movement type required\")' in source\n    assert 'Automatic movement type required' not in source\n'''
if 'def test_delivery_word_fallback_detects_out_movement()' not in t:
    marker='\ndef test_auto_invoice_metadata_is_read_only_and_duplicates_are_automatic():'
    pos=t.find(marker)
    if pos<0: raise RuntimeError('test insertion marker not found')
    t=t[:pos]+extra+t[pos:]
test_path.write_text(t,encoding='utf-8')

print('v16.6 movement detection and manual fallback applied')
