from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
app_path=ROOT/'inventory_tracker.py'
app=app_path.read_text(encoding='utf-8')

old='''def imports_panel(store,token,state,stock):
    with st.expander(t("Upload stock"),expanded=stock.empty):
        uploaded=st.file_uploader(t("Upload stock"),type=["xlsx","xls"],key="stock_report")
        if uploaded:
            try:
                raw=uploaded.getvalue()
                with branded_wait("Reading report"):
                    df=parse_stock_report(raw)
                # The warehouse report is now the master source for both item code and item name.
                table(visible_frame(df.head(12)))
                st.caption(f"{len(df):,} "+t("Items"))
                with st.form("stock_import"):
                    st.warning(t("Baseline warning"))
                    confirmed=st.checkbox(t("Confirm baseline"))
                    password=st.text_input(t("Approval password"),type="password",key="password_stock")
                    if st.form_submit_button(t("Import"),type="primary"):
                        if not confirmed:raise AppError("Confirm baseline")
                        with branded_wait("Importing stock"):
                            store.replace_stock(token,password,df,nonce("baseline"),state["revision"],source_name=uploaded.name)
                        success("baseline")
            except Exception as error:show_error(error)
'''
new='''def _stock_reconciliation(expected_stock,counted,day):
    expected=expected_stock[[COL_KEY,COL_CODE,COL_NAME,COL_QTY]].copy().rename(columns={COL_QTY:"System quantity"})
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
    return comparison,differences


def imports_panel(store,token,state,stock):
    with st.expander(t("Upload stock"),expanded=stock.empty):
        uploaded=st.file_uploader(t("Upload stock"),type=["xlsx","xls"],key="stock_report")
        if uploaded:
            try:
                raw=uploaded.getvalue()
                with branded_wait("Reading report"):
                    df=parse_stock_report(raw)
                # The warehouse report is now the master source for both item code and item name.
                table(visible_frame(df.head(12)))
                st.caption(f"{len(df):,} "+t("Items"))
                today_moves=store.ledger(token,store.today())
                if not today_moves.empty:
                    st.warning(t("Stock upload compare mode"))
                    st.caption(t("Stock upload compare mode hint"))
                    if stock.empty:
                        st.error(t("No current stock to compare"))
                    else:
                        _stock_reconciliation(stock,df,store.today())
                        if st.button(t("Open closing stock check"),key="stock_upload_open_closing"):
                            st.session_state["nav_request"]="Closing";st.rerun()
                else:
                    with st.form("stock_import"):
                        st.warning(t("Baseline warning"))
                        confirmed=st.checkbox(t("Confirm baseline"))
                        password=st.text_input(t("Approval password"),type="password",key="password_stock")
                        if st.form_submit_button(t("Import"),type="primary"):
                            if not confirmed:raise AppError("Confirm baseline")
                            with branded_wait("Importing stock"):
                                store.replace_stock(token,password,df,nonce("baseline"),state["revision"],source_name=uploaded.name)
                            success("baseline")
            except Exception as error:show_error(error)
'''
if new not in app:
    if old not in app:raise RuntimeError('imports_panel marker not found')
    app=app.replace(old,new,1)

old='''                counted=parse_stock_report(counted_file.getvalue())
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
'''
new='''                counted=parse_stock_report(counted_file.getvalue())
                _stock_reconciliation(stock,counted,day)
'''
if new not in app:
    if old not in app:raise RuntimeError('closing reconciliation marker not found')
    app=app.replace(old,new,1)
app_path.write_text(app,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.13"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.12"' not in ui:raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.12"','BUILD = "GP-CLOUD-v16.13"',1)
labels='''\n\n# ---- v16.13 stock upload mode after daily movements ----\nAR.update({\n    "Stock upload compare mode": "توجد حركات مسجلة اليوم؛ لن يتم استبدال رصيد المستودع بهذا الملف.",\n    "Stock upload compare mode hint": "سيتم استخدام التقرير للمقارنة فقط مع رصيد النظام الحالي. إذا أردت اعتماد رصيد بداية جديد، يجب رفعه قبل أول حركة في اليوم.",\n    "Open closing stock check": "فتح مطابقة نهاية اليوم",\n    "No current stock to compare": "لا يوجد رصيد حالي للمقارنة. يجب اعتماد رصيد بداية قبل بدء الحركات.",\n    "Set a new baseline before the first movement of the day": "لا يمكن استبدال رصيد البداية بعد تسجيل حركات اليوم. استخدم التقرير للمقارنة فقط أو اعتمد رصيد بداية في يوم جديد قبل أول حركة.",\n})\n'''
if '"Stock upload compare mode":' not in ui:
    marker='\ndef set_language('
    pos=ui.find(marker)
    if pos<0:raise RuntimeError('language marker not found')
    ui=ui[:pos]+labels+ui[pos:]
ui_path.write_text(ui,encoding='utf-8')

test_path=ROOT/'tests/test_core_and_ocr.py'
test=test_path.read_text(encoding='utf-8')
extra='''\n\ndef test_stock_upload_after_daily_movements_switches_to_compare_only():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'today_moves=store.ledger(token,store.today())' in source\n    assert 'if not today_moves.empty:' in source\n    assert 'Stock upload compare mode' in source\n    assert '_stock_reconciliation(stock,df,store.today())' in source\n    store_source=(Path(__file__).resolve().parents[1]/"gp_store.py").read_text()\n    assert 'Set a new baseline before the first movement of the day' in store_source\n\ndef test_closing_and_settings_share_stock_reconciliation_helper():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'def _stock_reconciliation(expected_stock,counted,day):' in source\n    assert '_stock_reconciliation(stock,counted,day)' in source\n'''
if 'def test_stock_upload_after_daily_movements_switches_to_compare_only()' not in test:
    test += extra
test_path.write_text(test,encoding='utf-8')

print('v16.13 stock upload compare-only mode applied')
