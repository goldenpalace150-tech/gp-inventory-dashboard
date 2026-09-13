from pathlib import Path

root=Path(__file__).resolve().parents[1]
app_path=root/'inventory_tracker.py'
app=app_path.read_text()

app=app.replace('capture=st.camera_input(t("Invoice image"),key="camera_capture")','capture=st.camera_input(t("Invoice image"),key="camera_capture",resolution="1080p",width="stretch")')

old='''            reference_fallback=auto_invoice and not detected_reference
            reference=a.text_input(t("Reference"),value=detected_reference,key="reference_"+suffix,disabled=auto_invoice and not reference_fallback)
            if reference_fallback:st.caption(t("Invoice number manual fallback"))
'''
new='''            reference=a.text_input(t("Reference"),value=detected_reference,key="reference_"+suffix)
            if auto_invoice and not detected_reference:st.caption(t("Invoice number manual fallback"))
'''
app=app.replace(old,new)

old='''            movement_fallback=auto_invoice and current_kind not in ("IN","OUT")
            if auto_invoice and not movement_fallback:
                d.text_input(t("Movement type"),value=t(current_kind),key="kind_auto_"+suffix,disabled=True)
                kind=current_kind
            else:
                kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)
                if movement_fallback:st.caption(t("Movement type manual fallback"))
            if auto_invoice and reference_fallback:
                st.warning(t("Automatic invoice number missing manual allowed"))
'''
new='''            kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)
            if auto_invoice and current_kind not in ("IN","OUT"):st.caption(t("Movement type manual fallback"))
'''
app=app.replace(old,new)
app_path.write_text(app)

ui_path=root/'gp_ui.py'
ui=ui_path.read_text().replace('BUILD = "GP-CLOUD-v16.16"','BUILD = "GP-CLOUD-v16.18"')
ui_path.write_text(ui)

# Update old source-shape tests to the new operator contract.
test_path=root/'tests/test_core_and_ocr.py'
t=test_path.read_text()
start=t.index('def test_auto_invoice_allows_manual_movement_only_when_ocr_misses_it():')
end=t.index('def test_invoice_entry_is_only_auto_or_manual():')
replacement='''def test_auto_invoice_fields_are_prefilled_but_correctable():
    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()
    assert 'reference=a.text_input(t("Reference"),value=detected_reference,key="reference_"+suffix)' in source
    assert 'kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind)' in source
    assert 'kind_auto_' not in source
    assert 'if kind not in ("IN","OUT"):raise AppError("Movement type required")' in source
    assert 'duplicate_action=' not in source
    assert 'store.replace_invoice(' in source


'''
t=t[:start]+replacement+t[end:]
start=t.index('def test_invoice_number_manual_fallback_and_closing_stock_compare_present():')
end=t.index('def test_admin_can_create_user_and_duplicate_is_safe_error():')
replacement='''def test_invoice_review_and_closing_stock_compare_present():
    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()
    assert 'reference=a.text_input(t("Reference"),value=detected_reference,key="reference_"+suffix)' in source
    assert 'Invoice number manual fallback' in source
    assert 'if not reference.strip():raise AppError("Invoice number required")' in source
    assert 'Upload closing stock report' in source
    assert 'comparison["Difference"]=comparison["Counted quantity"]-comparison["System quantity"]' in source


def test_mobile_camera_requests_1080p_full_width_and_items_are_editable():
    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()
    assert 'resolution="1080p",width="stretch"' in source
    assert 'st.data_editor(frame,hide_index=True,num_rows="dynamic"' in source
    assert 'disabled=["item_name"]' in source


'''
t=t[:start]+replacement+t[end:]
test_path.write_text(t)
print('v16.18 applied')