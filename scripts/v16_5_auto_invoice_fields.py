from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

app_path=ROOT/'inventory_tracker.py'
app=app_path.read_text(encoding='utf-8')

old='''        draft=choices[selected];payload=draft["payload"];suffix=selected+"_"+str(draft["version"])
        rows=payload.get("items") or []
'''
new='''        draft=choices[selected];payload=draft["payload"];suffix=selected+"_"+str(draft["version"])
        auto_invoice=bool(draft.get("image_hash"))
        rows=payload.get("items") or []
'''
if new not in app:
    if old not in app: raise RuntimeError('draft mode marker not found')
    app=app.replace(old,new,1)

old='''        with st.form("review_"+suffix):
            a,b,c,d=st.columns([1.15,1.5,1.15,1])
            reference=a.text_input(t("Reference"),value=str(payload.get("invoice_number","")),key="reference_"+suffix)
            customer=b.text_input(t("Customer name"),value=str(payload.get("customer_name","")),key="customer_"+suffix)
            driver=c.text_input(t("Driver"),value=str(payload.get("driver","")),key="driver_"+suffix)
            kinds=["","OUT","IN"]
            current_kind=payload.get("movement_type","") if payload.get("movement_type","") in kinds else ""
            kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)
            st.markdown('<div class="gp-form-gap"></div>',unsafe_allow_html=True)
'''
new='''        with st.form("review_"+suffix):
            a,b,c,d=st.columns([1.15,1.5,1.15,1])
            reference=a.text_input(t("Reference"),value=str(payload.get("invoice_number","")),key="reference_"+suffix,disabled=auto_invoice)
            customer=b.text_input(t("Customer name"),value=str(payload.get("customer_name","")),key="customer_"+suffix,disabled=auto_invoice)
            driver=c.text_input(t("Driver"),value=str(payload.get("driver","")),key="driver_"+suffix)
            kinds=["","OUT","IN"]
            current_kind=payload.get("movement_type","") if payload.get("movement_type","") in kinds else ""
            if auto_invoice:
                d.text_input(t("Movement type"),value=t(current_kind) if current_kind else t("Not detected"),key="kind_auto_"+suffix,disabled=True)
                kind=current_kind
            else:
                kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)
            if auto_invoice and (not reference.strip() or kind not in ("IN","OUT")):
                st.warning(t("Automatic invoice fields incomplete"))
            st.markdown('<div class="gp-form-gap"></div>',unsafe_allow_html=True)
'''
if new not in app:
    if old not in app: raise RuntimeError('review fields marker not found')
    app=app.replace(old,new,1)

old='''            duplicate_action=st.selectbox(t("Duplicate action"),["ignore","overwrite"],format_func=lambda x:t("Ignore duplicate" if x=="ignore" else "Overwrite if changed"),key="duplicate_"+suffix,help=t("Duplicate invoice hint"))
            password=st.text_input(t("Approval password"),type="password",key="password_invoice_"+suffix)
'''
new='''            if auto_invoice:
                st.caption(t("Automatic fields hint"))
            st.caption(t("Automatic duplicate hint"))
            password=st.text_input(t("Approval password"),type="password",key="password_invoice_"+suffix)
'''
if new not in app:
    if old not in app: raise RuntimeError('duplicate selector marker not found')
    app=app.replace(old,new,1)

old='''                    canonical_rows,_=canonicalize_invoice_rows(edited.to_dict("records"),stock,drop_unknown=False)
                    updated=dict(payload);updated.update(invoice_number=reference.strip(),movement_type=kind,
                        customer_name=customer.strip(),driver=driver.strip(),items=clean_json(canonical_rows))
                    if save:
'''
new='''                    canonical_rows,_=canonicalize_invoice_rows(edited.to_dict("records"),stock,drop_unknown=False)
                    if auto_invoice and not reference.strip():raise AppError("Automatic invoice number required")
                    if auto_invoice and kind not in ("IN","OUT"):raise AppError("Automatic movement type required")
                    updated=dict(payload);updated.update(invoice_number=reference.strip(),movement_type=kind,
                        customer_name=customer.strip(),driver=driver.strip(),items=clean_json(canonical_rows))
                    if save:
'''
if new not in app:
    if old not in app: raise RuntimeError('auto validation marker not found')
    app=app.replace(old,new,1)

old='''                        if duplicate.get("exists"):
                            if duplicate.get("identical") or duplicate_action=="ignore":
                                store.discard_draft(token,selected);success(message="Duplicate ignored")
                            else:
                                store.replace_invoice(token,password,changes,nonce("invoice_update_"+selected),reference=reference,
                                    image_hash=draft["image_hash"],reviewed=updated,draft_id=selected,expected_draft_version=draft["version"],
                                    customer_name=customer,driver=driver)
                                success("invoice_update_"+selected,message="Invoice updated")
'''
new='''                        if duplicate.get("exists"):
                            if duplicate.get("identical"):
                                store.discard_draft(token,selected);success(message="Duplicate ignored")
                            else:
                                store.replace_invoice(token,password,changes,nonce("invoice_update_"+selected),reference=reference,
                                    image_hash=draft["image_hash"],reviewed=updated,draft_id=selected,expected_draft_version=draft["version"],
                                    customer_name=customer,driver=driver)
                                success("invoice_update_"+selected,message="Invoice updated")
'''
if new not in app:
    if old not in app: raise RuntimeError('duplicate behavior marker not found')
    app=app.replace(old,new,1)

app_path.write_text(app,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.5"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.4"' not in ui: raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.4"','BUILD = "GP-CLOUD-v16.5"',1)
labels='''\n\n# ---- v16.5 automatic invoice metadata ----\nAR.update({\n    "Not detected": "غير مكتشف",\n    "Automatic fields hint": "في الوضع التلقائي يقرأ النظام نوع الحركة ورقم الفاتورة واسم الزبون إن وُجد. السائق هو الحقل اليدوي الوحيد من بيانات رأس الفاتورة.",\n    "Automatic duplicate hint": "الفاتورة المكررة تُعالج تلقائياً: إذا كانت مطابقة يتم تجاهلها، وإذا تغيّرت البنود أو الكميات يتم تحديث الفاتورة الموجودة.",\n    "Automatic invoice fields incomplete": "لم تكتمل القراءة التلقائية لرأس الفاتورة. أعد التصوير بصورة أوضح قبل الاعتماد.",\n    "Automatic invoice number required": "تعذر قراءة رقم الفاتورة تلقائياً. أعد التصوير بصورة أوضح.",\n    "Automatic movement type required": "تعذر قراءة نوع الحركة تلقائياً. أعد التصوير بصورة أوضح.",\n})\n'''
if '"Automatic fields hint":' not in ui:
    marker='\ndef set_language('
    pos=ui.find(marker)
    if pos<0: raise RuntimeError('language marker not found')
    ui=ui[:pos]+labels+ui[pos:]
ui_path.write_text(ui,encoding='utf-8')

worker_path=ROOT/'invoice_ocr_worker.py'
worker=worker_path.read_text(encoding='utf-8')
worker=worker.replace('BUILD = "GP-OCR-WAREHOUSE-v16"','BUILD = "GP-OCR-WAREHOUSE-v16.5"',1)
worker=worker.replace('warnings.append("نوع الحركة غير مؤكد؛ اختر إدخال أو إخراج يدوياً.")','warnings.append("نوع الحركة غير مؤكد؛ أعد تصوير الفاتورة بصورة أوضح.")',1)
worker=worker.replace('warnings.append("تعذر قراءة بيانات رأس الفاتورة؛ أدخل نوع الحركة واسم الزبون يدوياً عند الحاجة.")','warnings.append("تعذر قراءة بيانات رأس الفاتورة؛ أعد تصوير الفاتورة بصورة أوضح.")',1)
worker=worker.replace('warnings.append("Reference is uncertain; enter the reference from the document.")','warnings.append("Reference is uncertain; retake a clearer invoice photo.")',1)
worker_path.write_text(worker,encoding='utf-8')

ocr_path=ROOT/'gp_ocr.py'
ocr=ocr_path.read_text(encoding='utf-8')
ocr=ocr.replace('OCR_BUILD = "GP-OCR-WAREHOUSE-v16"','OCR_BUILD = "GP-OCR-WAREHOUSE-v16.5"',1)
ocr_path.write_text(ocr,encoding='utf-8')

test_path=ROOT/'tests/test_core_and_ocr.py'
t=test_path.read_text(encoding='utf-8')
extra='''\n\ndef test_auto_invoice_metadata_is_read_only_and_duplicates_are_automatic():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'auto_invoice=bool(draft.get("image_hash"))' in source\n    assert 'disabled=auto_invoice' in source\n    assert 'kind_auto_' in source and 'disabled=True' in source\n    assert 'duplicate_action=' not in source\n    assert 'if duplicate.get("identical"):' in source\n    assert 'store.replace_invoice(' in source\n    assert 'Automatic invoice number required' in source\n    assert 'Automatic movement type required' in source\n'''
if 'def test_auto_invoice_metadata_is_read_only_and_duplicates_are_automatic()' not in t:
    marker='\ndef test_invoice_entry_is_only_auto_or_manual():'
    pos=t.find(marker)
    if pos<0: raise RuntimeError('invoice test marker not found')
    t=t[:pos]+extra+t[pos:]
test_path.write_text(t,encoding='utf-8')

print('v16.5 automatic invoice metadata and duplicate handling applied')
