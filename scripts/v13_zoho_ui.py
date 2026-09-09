from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Missing marker: {label}")
    return text.replace(old, new, 1)


# inventory_tracker.py
p = ROOT / "inventory_tracker.py"
text = p.read_text(encoding="utf-8")

insert_after = '''def export_button(name,sheets):
    # Do not keep large XLSX objects in the session across OCR scans.
    if st.button(t("Prepare export"),key="prepare_"+name):
        data=excel_bytes(sheets)
        st.download_button(t("Download"),data,file_name=name+".xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key="download_"+name)


'''

dashboard_func = '''def dashboard_page(store,token,state,stock,daily,actor):
    """Zoho-inspired operational landing page: KPIs, quick actions and recent work."""
    section("Dashboard","Dashboard hint")
    alerts=int(daily["without_invoice"].sum()) if not daily.empty else 0
    available=int((stock[COL_QTY]>0).sum()) if not stock.empty else 0
    out_count=int((stock[COL_QTY]<=0).sum()) if not stock.empty else 0
    st.markdown(kpis_html([
        ("Items",f"{len(stock):,}","Stock"),
        ("Available",f"{available:,}","Items"),
        ("Movements",f"{len(daily):,}","Today"),
        ("Without invoice",f"{alerts:,}","Today"),
    ]),unsafe_allow_html=True)

    st.markdown("### "+t("Quick actions"))
    q1,q2,q3,q4=st.columns(4)
    if q1.button(t("Read invoice"),type="primary",width="stretch",key="dash_invoice"):
        st.session_state["page"]="Invoices"; st.rerun()
    if q2.button(t("New movement"),width="stretch",key="dash_movement"):
        st.session_state["page"]="Movements"; st.rerun()
    if q3.button(t("Stock"),width="stretch",key="dash_stock"):
        st.session_state["page"]="Stock"; st.rerun()
    if q4.button(t("Analysis"),width="stretch",key="dash_analysis"):
        st.session_state["page"]="Analysis"; st.rerun()

    left,right=st.columns([1.15,1])
    with left:
        with st.container(border=True):
            st.markdown("#### "+t("Today's activity"))
            if daily.empty:
                st.info(t("Empty"))
            else:
                cols=[c for c in ["created_at","movement_type","item_code","item_name","quantity","invoice_reference","username"] if c in daily.columns]
                table(daily.tail(10)[cols].iloc[::-1],height=320)
    with right:
        with st.container(border=True):
            st.markdown("#### "+t("Warehouse status"))
            a,b=st.columns(2)
            a.metric(t("Out of stock"),f"{out_count:,}")
            b.metric(t("Available"),f"{available:,}")
            if not stock.empty:
                watch=stock.sort_values(COL_QTY,ascending=True).head(8)
                table(visible_frame(watch),height=245)
            else:
                st.info(t("No stock"))

    with st.container(border=True):
        st.markdown("#### "+t("Recent invoices"))
        posted=store.recent_invoices(token,8)
        if posted:
            frame=pd.DataFrame(posted)
            frame["total_quantity"]=pd.to_numeric(frame["total_quantity"],errors="coerce").fillna(0).map(lambda x:f"{x:.1f}")
            frame["posted_at"]=frame["posted_at"].map(lambda x:aware(x).astimezone(store.tz).strftime("%Y-%m-%d %H:%M"))
            shown=frame[["invoice_reference","customer_name","driver","movement_type","total_quantity","posted_at"]].rename(columns={
                "invoice_reference":t("Invoice number"),"customer_name":t("Customer name"),"driver":t("Driver"),
                "movement_type":t("Movement type"),"total_quantity":t("Total quantity"),"posted_at":t("Date")})
            table(shown,height=270)
        else:
            st.info(t("No posted invoices"))


'''
text = replace_once(text, insert_after, insert_after + dashboard_func, "dashboard insertion")

old_main_header = '''    a,b,c=st.columns([5,1,1])
    stamp=aware(state["updated_at"]).astimezone(store.tz).strftime("%Y-%m-%d %H:%M:%S")
    a.markdown(status_html(actor,stamp),unsafe_allow_html=True)
    if b.button(t("Refresh"),width="stretch",key="global_refresh"):
        get_shell.clear(); get_analysis.clear(); st.rerun()
    with c.popover(t("Account"),width="stretch"):
        st.write(actor["display_name"]+" / "+t(actor["role"]))
        if st.button(t("Sign out"),width="stretch"):
            try:store.logout(token)
            finally:
                st.session_state.clear()
                st.rerun()
    flash=st.session_state.pop("flash",None)
    if flash:st.success(flash)
    nav=["Stock","Invoices","Movements","Analysis","Closing","Settings"]
    with st.container(key="navigation"):
        page=st.segmented_control(t("Inventory"),nav,default="Stock",format_func=t,key="page",label_visibility="collapsed",width="stretch") or "Stock"
    if page not in ("Analysis",):
        alerts=int(daily["without_invoice"].sum()) if not daily.empty else 0
        st.markdown(kpis_html([("Items",f"{len(stock):,}","Stock"),("Available",f"{int((stock[COL_QTY]>0).sum()):,}","Items"),
                               ("Movements",len(daily),"Today"),("Without invoice",alerts,"Today")]),unsafe_allow_html=True)
    try:
        if page=="Stock":stock_page(store,token,state,stock)
        elif page=="Invoices":invoices_page(store,token,state,stock)
        elif page=="Movements":movements_page(store,token,state,stock)
        elif page=="Analysis":analysis_page(store,token,state,stock)
        elif page=="Closing":closing_page(store,token,state,stock,actor)
        elif page=="Settings":settings_page(store,token,state,stock,actor)
'''

new_main_header = '''    a,b,c=st.columns([5,1,1])
    stamp=aware(state["updated_at"]).astimezone(store.tz).strftime("%Y-%m-%d %H:%M:%S")
    a.markdown(status_html(actor,stamp),unsafe_allow_html=True)
    if b.button(t("Refresh"),width="stretch",key="global_refresh"):
        get_shell.clear(); get_analysis.clear(); st.rerun()
    with c.popover(t("Account"),width="stretch"):
        st.write(actor["display_name"]+" / "+t(actor["role"]))
        if st.button(t("Sign out"),width="stretch"):
            try:store.logout(token)
            finally:
                st.session_state.clear()
                st.rerun()
    flash=st.session_state.pop("flash",None)
    if flash:st.success(flash)
    nav=["Dashboard","Stock","Invoices","Movements","Analysis","Closing","Settings"]
    if st.session_state.get("page") not in nav:st.session_state["page"]="Dashboard"
    with st.container(key="navigation"):
        page=st.segmented_control(t("Inventory"),nav,format_func=t,key="page",label_visibility="collapsed",width="stretch") or "Dashboard"
    try:
        if page=="Dashboard":dashboard_page(store,token,state,stock,daily,actor)
        elif page=="Stock":stock_page(store,token,state,stock)
        elif page=="Invoices":invoices_page(store,token,state,stock)
        elif page=="Movements":movements_page(store,token,state,stock)
        elif page=="Analysis":analysis_page(store,token,state,stock)
        elif page=="Closing":closing_page(store,token,state,stock,actor)
        elif page=="Settings":settings_page(store,token,state,stock,actor)
'''
text = replace_once(text, old_main_header, new_main_header, "Zoho navigation")
p.write_text(text, encoding="utf-8")


# gp_ui.py
p = ROOT / "gp_ui.py"
text = p.read_text(encoding="utf-8")
text = text.replace('BUILD = "GP-CLOUD-v12"', 'BUILD = "GP-CLOUD-v13"', 1)
if '"Dashboard": "لوحة التحكم"' not in text:
    text += '''\n\n# ---- v13 Zoho-inspired navigation/dashboard ----\nAR.update({\n    "Dashboard": "لوحة التحكم",\n    "Dashboard hint": "نظرة سريعة على حالة المستودع وحركة اليوم وأهم الإجراءات.",\n    "Quick actions": "إجراءات سريعة",\n    "Today's activity": "حركة اليوم",\n    "Warehouse status": "حالة المستودع",\n    "Recent invoices": "أحدث الفواتير",\n})\n'''
p.write_text(text, encoding="utf-8")


# style.css
p = ROOT / "assets/style.css"
css = p.read_text(encoding="utf-8")
if "v13: Zoho-inspired shell" not in css:
    css += '''\n\n/* v13: Zoho-inspired shell - compact, operational, high contrast. */\n[data-testid="stMainBlockContainer"] { max-width:1540px; padding-top:2rem; }\n.gp-brand { padding:18px 24px; border-radius:14px; box-shadow:0 4px 16px #10203810; }\n.gp-brand .gp-brand-copy h1 { font-size:1.7rem; }\n.gp-logo { flex-basis:240px; padding:9px 12px; }\n.gp-logo img { max-width:240px; }\n.st-key-navigation { background:#fff; padding:.45rem; border:1px solid #dfe5ec; border-radius:10px; box-shadow:none; }\n.st-key-navigation [data-testid="stButtonGroup"] > div { gap:2px; }\n.st-key-navigation button { min-height:42px; border-radius:7px; padding:.45rem .9rem; font-size:.92rem; }\n.gp-kpis { gap:10px; }\n.gp-kpi { border-top:1px solid var(--gp-line); border-inline-start:4px solid var(--gp-blue); border-radius:10px; padding:14px 17px; box-shadow:none; }\n.gp-kpi strong { font-size:1.75rem; }\n[data-testid="stVerticalBlockBorderWrapper"] > div { border-radius:10px !important; box-shadow:none !important; }\n[data-testid="stDataFrame"] { border-radius:8px; }\n.stButton button, .stFormSubmitButton button, .stDownloadButton button { border-radius:7px; }\n[data-testid="stForm"] { border-radius:10px; box-shadow:none; }\n[data-testid="stExpander"] { border-radius:9px; }\n@media(max-width:760px) {\n  .gp-brand { padding:14px 16px; }\n  .gp-brand .gp-brand-copy h1 { font-size:1.45rem; }\n  .st-key-navigation button { padding:.4rem .55rem; font-size:.82rem; }\n}\n'''
p.write_text(css, encoding="utf-8")

print("v13 Zoho-inspired UI applied")
