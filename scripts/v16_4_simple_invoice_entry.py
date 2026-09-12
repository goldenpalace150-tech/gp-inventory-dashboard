from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
app_path=ROOT/'inventory_tracker.py'
text=app_path.read_text(encoding='utf-8')

old='''        with tools:
            st.markdown("#### "+t("New invoice"))
            uploaded=st.file_uploader(t("Invoice image"),type=["png","jpg","jpeg"],key="invoice_upload")
            camera_enabled=st.toggle(t("Camera"),key="camera_enabled")
            if camera_enabled:
                capture=st.camera_input(t("Invoice image"),key="camera_capture")
                if capture:uploaded=capture
            a,b=st.columns(2)
            read=a.button(t("Read invoice"),type="primary",disabled=not (uploaded and ok and code_master_ready),width="stretch")
            manual=b.button(t("Manual invoice"),width="stretch")
            if not ok:st.info("OCR is unavailable on this host. Manual invoice entry remains available.")
            if not code_master_ready:st.warning(t("Warehouse code master required"))
            if manual:
                st.session_state["selected_draft_id"]=store.create_draft(token,source_name=t("Manual invoice"))
                st.rerun()
            if read:
'''
new='''        with tools:
            st.markdown("#### "+t("New invoice"))
            mode=st.radio(t("Invoice entry"),["AUTO","MANUAL"],horizontal=True,
                format_func=lambda x:t("Automatic" if x=="AUTO" else "Manual"),key="invoice_entry_mode")
            uploaded=None
            if mode=="AUTO":
                uploaded=st.file_uploader(t("Invoice image"),type=["png","jpg","jpeg"],key="invoice_upload")
                camera_enabled=st.toggle(t("Camera"),key="camera_enabled")
                if camera_enabled:
                    capture=st.camera_input(t("Invoice image"),key="camera_capture")
                    if capture:uploaded=capture
                read=st.button(t("Read invoice"),type="primary",disabled=not (uploaded and ok and code_master_ready),width="stretch")
                if not ok:st.info("OCR is unavailable on this host. Manual invoice entry remains available.")
                if not code_master_ready:st.warning(t("Warehouse code master required"))
            else:
                read=False
                if st.button(t("Start manual invoice"),type="primary",width="stretch",key="start_manual_invoice"):
                    st.session_state["selected_draft_id"]=store.create_draft(token,source_name=t("Manual invoice"))
                    st.rerun()
            if read:
'''
if new not in text:
    if old not in text: raise RuntimeError('invoice entry block marker not found')
    text=text.replace(old,new,1)

old='''        if len(choices)>1:
            selected=st.selectbox(t("Unfinished invoices"),list(choices),index=list(choices).index(selected),
                format_func=lambda k: (choices[k]["payload"].get("invoice_number") or choices[k]["source_name"] or k[:8]),
                key="draft_selector")
        st.session_state["selected_draft_id"]=selected
'''
new='''        # Keep the operator flow simple: Auto / Manual are the only entry choices.
        # If multiple unfinished drafts exist from older versions, continue the
        # currently selected one (or newest one) without exposing a technical draft picker.
        st.session_state["selected_draft_id"]=selected
'''
if new not in text:
    if old not in text: raise RuntimeError('draft selector marker not found')
    text=text.replace(old,new,1)
app_path.write_text(text,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.4"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.3"' not in ui: raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.3"','BUILD = "GP-CLOUD-v16.4"',1)
labels='''\n\n# ---- v16.4 simple invoice entry ----\nAR.update({\n    "Invoice entry": "طريقة إدخال الفاتورة",\n    "Automatic": "تلقائي",\n    "Manual": "يدوي",\n    "Start manual invoice": "بدء فاتورة يدوية",\n})\n'''
if '"Invoice entry": "طريقة إدخال الفاتورة"' not in ui:
    marker='\ndef set_language('
    pos=ui.find(marker)
    if pos<0: raise RuntimeError('language marker not found')
    ui=ui[:pos]+labels+ui[pos:]
ui_path.write_text(ui,encoding='utf-8')

# lightweight regression marker
p=ROOT/'tests/test_core_and_ocr.py'
t=p.read_text(encoding='utf-8')
extra='''\n\ndef test_invoice_entry_is_only_auto_or_manual():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'st.radio(t("Invoice entry"),["AUTO","MANUAL"]' in source\n    assert 'key="draft_selector"' not in source\n    assert 't("Start manual invoice")' in source\n'''
if 'def test_invoice_entry_is_only_auto_or_manual()' not in t:
    t += extra
p.write_text(t,encoding='utf-8')
print('v16.4 simple invoice entry applied')
