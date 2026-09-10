from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Missing update marker: {label}")
    return text.replace(old, new, 1)


def regex_once(text, pattern, replacement, label):
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected one match for {label}, got {count}")
    return updated


# ---------------------------------------------------------------------------
# inventory_tracker.py - persistent Zoho-style left navigation + compact work area
# ---------------------------------------------------------------------------
path = ROOT / "inventory_tracker.py"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    'page_icon=Image.open(ROOT/"assets/favicon.png"),layout="wide",initial_sidebar_state="collapsed")',
    'page_icon=Image.open(ROOT/"assets/favicon.png"),layout="wide",initial_sidebar_state="auto")',
    "responsive sidebar state",
)

# Rebuild invoice intake as a compact two-panel workspace.
old_invoice = '''    with st.container(border=True):
        left,right=st.columns([1.6,1])
        with left:
            uploaded=st.file_uploader(t("Invoice image"),type=["png","jpg","jpeg"],key="invoice_upload")
            if st.checkbox(t("Camera"),key="camera_enabled"):
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
                content=uploaded.getvalue(); image_hash=hashlib.sha256(content).hexdigest()
                draft_id=store.create_draft(token,source_name=uploaded.name,image_hash=image_hash)
                st.session_state["selected_draft_id"]=draft_id
                pending={d["draft_id"]:d for d in store.drafts(token)}
                if draft_id not in pending:
                    st.warning(t("This invoice or image was already posted"))
                elif pending[draft_id]["payload"].get("items"):
                    st.info(t("Saved invoice draft found"))
                else:
                    with branded_wait("Reading"):
                        try:
                            result=extract_invoice_data(uploaded,stock)
                            if result.get("movement_type") not in ("IN","OUT"): result["movement_type"]=""
                            result.setdefault("customer_name",""); result.setdefault("driver","")
                            store.save_draft(token,draft_id,result,pending[draft_id]["version"])
                            success(message="Saved")
                        except Exception as error:
                            if isinstance(error,(RuntimeError,ValueError)):st.error(str(error)[:1000])
                            else:show_error(error)
        with right:
            if uploaded:st.image(uploaded.getvalue(),width="stretch")
            else:st.markdown(section_html("Review","Draft hint"),unsafe_allow_html=True)
'''
new_invoice = '''    with st.container(border=True,key="invoice_workspace"):
        preview,tools=st.columns([1.0,1.25])
        with tools:
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
                content=uploaded.getvalue(); image_hash=hashlib.sha256(content).hexdigest()
                draft_id=store.create_draft(token,source_name=uploaded.name,image_hash=image_hash)
                st.session_state["selected_draft_id"]=draft_id
                pending={d["draft_id"]:d for d in store.drafts(token)}
                if draft_id not in pending:
                    st.warning(t("This invoice or image was already posted"))
                elif pending[draft_id]["payload"].get("items"):
                    st.info(t("Saved invoice draft found"))
                else:
                    with branded_wait("Reading"):
                        try:
                            result=extract_invoice_data(uploaded,stock)
                            if result.get("movement_type") not in ("IN","OUT"): result["movement_type"]=""
                            result.setdefault("customer_name",""); result.setdefault("driver","")
                            store.save_draft(token,draft_id,result,pending[draft_id]["version"])
                            success(message="Saved")
                        except Exception as error:
                            if isinstance(error,(RuntimeError,ValueError)):st.error(str(error)[:1000])
                            else:show_error(error)
        with preview:
            st.markdown("#### "+t("Invoice preview"))
            if uploaded:
                st.image(uploaded.getvalue(),width="stretch")
            else:
                st.markdown('<div class="gp-invoice-empty">'+t("Invoice preview hint")+'</div>',unsafe_allow_html=True)
'''
text = replace_once(text, old_invoice, new_invoice, "two-panel invoice intake")

# Simplify review actions: posting with password is the confirmation; keep duplicate choice
# but remove the repeated explanatory line and redundant review checkbox.
old_review_controls = '''            duplicate_action=st.selectbox(t("Duplicate action"),["ignore","overwrite"],format_func=lambda x:t("Ignore duplicate" if x=="ignore" else "Overwrite if changed"),key="duplicate_"+suffix)
            st.caption(t("Duplicate invoice hint"))
            review_checked=st.checkbox(t("Confirm review"),key="checked_"+suffix)
            password=st.text_input(t("Approval password"),type="password",key="password_invoice_"+suffix)
'''
new_review_controls = '''            duplicate_action=st.selectbox(t("Duplicate action"),["ignore","overwrite"],format_func=lambda x:t("Ignore duplicate" if x=="ignore" else "Overwrite if changed"),key="duplicate_"+suffix,help=t("Duplicate invoice hint"))
            password=st.text_input(t("Approval password"),type="password",key="password_invoice_"+suffix)
'''
text = replace_once(text, old_review_controls, new_review_controls, "compact invoice review controls")
text = text.replace('                        if not review_checked:raise AppError("Confirm review")\n', '', 1)

# Add sidebar helpers before main.
sidebar_helpers = r'''

def _language_picker(key):
    selected=st.segmented_control("Language / اللغة",["ar","en"],
        default=st.session_state.get("ui_language","ar"),
        format_func=lambda x:"العربية" if x=="ar" else "English",
        key=key,label_visibility="collapsed") or st.session_state.get("ui_language","ar")
    if selected!=st.session_state.get("ui_language","ar"):
        st.session_state["ui_language"]=selected
        st.rerun()


def sidebar_navigation(store,token,actor,stamp):
    nav=["Dashboard","Stock","Invoices","Movements","Analysis","Closing","Settings"]
    desired=st.session_state.get("page","Dashboard")
    if desired not in nav:desired="Dashboard"
    if st.session_state.get("sidebar_nav")!=desired:
        st.session_state["sidebar_nav"]=desired
    icons={"Dashboard":"⌂","Stock":"▦","Invoices":"▤","Movements":"⇄","Analysis":"◫","Closing":"✓","Settings":"⚙"}
    with st.sidebar:
        st.image(ROOT/"assets/golden_palace.jpg",width=220)
        st.markdown('<div class="gp-sidebar-title">'+t("Inventory")+'</div>',unsafe_allow_html=True)
        st.caption(t("Warehouse workspace"))
        page=st.radio(t("Navigation"),nav,key="sidebar_nav",label_visibility="collapsed",
            format_func=lambda value:f"{icons[value]}  {t(value)}")
        if page!=st.session_state.get("page"):
            st.session_state["page"]=page
        st.divider()
        st.markdown(status_html(actor,stamp),unsafe_allow_html=True)
        _language_picker("sidebar_language")
        if st.button(t("Refresh"),width="stretch",key="sidebar_refresh"):
            get_shell.clear();get_analysis.clear();st.rerun()
        if st.button(t("Sign out"),width="stretch",key="sidebar_signout"):
            try:store.logout(token)
            finally:
                st.session_state.clear();st.rerun()
    return page
'''
text = replace_once(text, '\n\ndef main():\n', sidebar_helpers + '\n\ndef main():\n', "sidebar helpers")

# Replace the authenticated shell. Keep login branding in the main canvas, but move
# navigation, account actions, language and status into the persistent sidebar.
main_pattern = r'def main\(\):.*?\n\nif __name__=="__main__":'
main_replacement = r'''def main():
    if "ui_language" not in st.session_state:
        st.session_state["ui_language"]="ar"
    set_language(st.session_state["ui_language"])
    st.markdown(language_marker(),unsafe_allow_html=True)

    if st.session_state.pop("wipe_passwords",False):
        for key in list(st.session_state):
            if key.startswith("password_") or key=="login_password":st.session_state.pop(key,None)

    try:
        config=dict(st.secrets.get("database",{}))
        auth=dict(st.secrets.get("auth",{}))
        app_config=dict(st.secrets.get("app",{}))
        if not config:raise AppError("Complete the database settings in Streamlit Secrets")
        store=get_store(json.dumps(config,sort_keys=True))
        store.initialize(auth.get("bootstrap_username","admin"),auth.get("bootstrap_password",""),app_config.get("timezone","Asia/Damascus"))
    except Exception as error:
        st.markdown(brand_html(),unsafe_allow_html=True)
        if isinstance(error,AppError):st.warning(t(str(error)))
        else:show_error(error)
        st.info("Setup: run sql/setup.sql in Supabase, then copy secrets.example.toml into Streamlit Secrets and fill your own database credentials. No local fallback is enabled.")
        st.code("database.host / database.user / database.password / database.dbname\nauth.bootstrap_username / auth.bootstrap_password",language="text")
        return

    token=st.session_state.get("token")
    if not token:
        with st.sidebar:
            st.markdown("### Language / اللغة")
            _language_picker("login_language")
        st.markdown(brand_html(),unsafe_allow_html=True)
        with st.container(key="login"):
            section("Sign in")
            with st.form("login"):
                username=st.text_input(t("Username"),key="login_username")
                password=st.text_input(t("Password"),type="password",key="login_password")
                if st.form_submit_button(t("Sign in"),type="primary",width="stretch"):
                    try:
                        st.session_state["token"]=store.login(username,password,int(auth.get("session_hours",12)))
                        st.session_state["wipe_passwords"]=True
                        st.rerun()
                    except Exception as error:show_error(error)
            st.caption(t("Cloud hint"))
        return

    try:
        database_id=str(store.engine.url.render_as_string(hide_password=True))
        token_hash=hashlib.sha256(token.encode()).hexdigest()[:24]
        with branded_wait("Loading data"):
            actor,state,stock,daily=get_shell(database_id,token_hash,store,token)
    except AppError as error:
        st.session_state.pop("token",None);st.error(t(str(error)))
        if st.button(t("Sign in")):st.rerun()
        return
    except Exception as error:
        show_error(error)
        if st.button(t("Refresh")):st.rerun()
        return

    stamp=aware(state["updated_at"]).astimezone(store.tz).strftime("%Y-%m-%d %H:%M:%S")
    page=sidebar_navigation(store,token,actor,stamp)

    flash=st.session_state.pop("flash",None)
    if flash:st.success(flash)

    try:
        if page=="Dashboard":dashboard_page(store,token,state,stock,daily,actor)
        elif page=="Stock":stock_page(store,token,state,stock)
        elif page=="Invoices":invoices_page(store,token,state,stock)
        elif page=="Movements":movements_page(store,token,state,stock)
        elif page=="Analysis":analysis_page(store,token,state,stock)
        elif page=="Closing":closing_page(store,token,state,stock,actor)
        elif page=="Settings":settings_page(store,token,state,stock,actor)
    except Exception as error:show_error(error)
    st.markdown('<div class="gp-foot">GOLDEN PALACE / '+BUILD+'</div>',unsafe_allow_html=True)


if __name__=="__main__":'''
text = regex_once(text, main_pattern, main_replacement, "authenticated Zoho shell")
path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# gp_ui.py - v15 build and concise Arabic terminology
# ---------------------------------------------------------------------------
path = ROOT / "gp_ui.py"
ui = path.read_text(encoding="utf-8")
ui = ui.replace('BUILD = "GP-CLOUD-v14"', 'BUILD = "GP-CLOUD-v15"', 1)
if '# ---- v15 Zoho workspace shell ----' not in ui:
    ui += '''\n\n# ---- v15 Zoho workspace shell ----\nAR.update({\n    "Inventory": "إدارة المستودعات",\n    "Stock": "المستودع",\n    "Warehouse workspace": "مساحة عمل المستودع",\n    "Navigation": "التنقل",\n    "New invoice": "فاتورة جديدة",\n    "Invoice preview": "معاينة الفاتورة",\n    "Invoice preview hint": "ارفع صورة الفاتورة أو استخدم الكاميرا. ستظهر المعاينة هنا.",\n})\n'''
path.write_text(ui, encoding="utf-8")


# ---------------------------------------------------------------------------
# assets/style.css - persistent left shell, denser cards/forms, mobile drawer
# ---------------------------------------------------------------------------
path = ROOT / "assets/style.css"
css = path.read_text(encoding="utf-8")
if 'v15: persistent Zoho-style workspace shell' not in css:
    css += r'''

/* v15: persistent Zoho-style workspace shell */
[data-testid="stAppViewContainer"] { background:#f6f8fb; }
[data-testid="stMainBlockContainer"] { max-width:none; padding:1.25rem 1.6rem 2rem; }
[data-testid="stSidebar"] { background:#10263f; border-inline-end:1px solid #25415d; }
[data-testid="stSidebar"] > div:first-child { padding-top:1rem; }
[data-testid="stSidebar"] [data-testid="stImage"] { background:#fff; border:1px solid #d9c58e; border-radius:10px; padding:7px; margin-bottom:.25rem; }
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] { color:#dbe6f0 !important; }
[data-testid="stSidebar"] hr { border-color:#35506b; margin:.75rem 0; }
.gp-sidebar-title { direction:rtl; text-align:right; color:#fff; font-size:1.2rem; font-weight:850; margin:.15rem 0 0; }
[data-testid="stSidebar"] [data-testid="stRadio"] > div { gap:.25rem; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { width:100%; padding:.55rem .65rem; border-radius:8px; border:1px solid transparent; transition:background .12s ease,border-color .12s ease; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background:#183956; border-color:#31516f; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:#fff; border-color:#fff; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p { color:#10263f !important; font-weight:850; }
[data-testid="stSidebar"] [data-testid="stRadio"] label p { font-size:.95rem; font-weight:720; }
[data-testid="stSidebar"] .gp-status { display:grid; gap:4px; color:#dbe6f0; font-size:.78rem; }
[data-testid="stSidebar"] .gp-status-pill { color:#9fe0c5; }
[data-testid="stSidebar"] .gp-muted { color:#9fb1c3; }
[data-testid="stSidebar"] .stButton button { min-height:39px; border-radius:7px; }

/* Main workspace is dense and operational instead of card-heavy. */
.gp-section { margin:2px 0 8px; }
.gp-section h2 { font-size:1.45rem; line-height:1.45; }
.gp-section p { margin:1px 0 8px; }
.gp-kpis { gap:9px; margin:3px 0 10px; }
.gp-kpi { padding:12px 15px; border-radius:8px; }
.gp-kpi strong { font-size:1.6rem; }
[data-testid="stVerticalBlockBorderWrapper"] > div { border-radius:8px !important; }
[data-testid="stForm"] { padding:.9rem 1rem; border-radius:8px; }
[data-testid="stForm"] [data-testid="stHorizontalBlock"] { gap:8px !important; }
[data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { border:1px solid #dbe3eb; border-radius:8px; padding:8px 10px 6px; background:#fff; }
[data-testid="stFileUploaderDropzone"] { min-height:92px; border-radius:8px; background:#f9fbfd; }
[data-testid="stAlert"] { border-radius:8px; padding:.6rem .75rem; }
[data-testid="stDataFrame"] { border-radius:6px; }
.stButton button, .stFormSubmitButton button, .stDownloadButton button { min-height:40px; border-radius:6px; }
.gp-form-gap { height:8px; }

/* Invoice workspace */
.st-key-invoice_workspace { background:#fff; }
.gp-invoice-empty { min-height:230px; border:1.5px dashed #c7d2de; border-radius:8px; background:#f8fafc; display:flex; align-items:center; justify-content:center; padding:24px; text-align:center; color:#718195; direction:rtl; }

/* English restores LTR inside the sidebar; Arabic stays RTL. */
[data-testid="stAppViewContainer"]:has(.gp-lang-en-marker) [data-testid="stSidebar"] p,
[data-testid="stAppViewContainer"]:has(.gp-lang-en-marker) .gp-sidebar-title { direction:ltr; text-align:left; }

@media(max-width:760px) {
  [data-testid="stMainBlockContainer"] { padding:1rem .65rem 1.6rem; }
  .gp-section h2 { font-size:1.3rem; }
  .gp-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); }
  [data-testid="stForm"] { padding:.75rem; }
  [data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { padding:7px 8px 5px; }
  .gp-invoice-empty { min-height:150px; }
}
'''
path.write_text(css, encoding="utf-8")


# ---------------------------------------------------------------------------
# tests - sidebar is now intentional; retain guard against unsafe global RTL CSS.
# ---------------------------------------------------------------------------
path = ROOT / "tests/test_core_and_ocr.py"
tests = path.read_text(encoding="utf-8")
old_test = '''def test_ui_has_no_sidebar_or_global_rtl_rule():
    root=Path(__file__).resolve().parents[1]
    source=(root/"inventory_tracker.py").read_text()
    assert "st.sidebar" not in source and "use_container_width" not in source
    stylesheet=(root/"assets/style.css").read_text()
    assert "h1, h2, h3, h4, p, span, label, div" not in stylesheet
    for f in root.glob("*.py"):ast.parse(f.read_text())
'''
new_test = '''def test_ui_uses_sidebar_without_global_rtl_rule():
    root=Path(__file__).resolve().parents[1]
    source=(root/"inventory_tracker.py").read_text()
    assert "with st.sidebar:" in source and "sidebar_navigation" in source
    assert "use_container_width" not in source
    stylesheet=(root/"assets/style.css").read_text()
    assert "h1, h2, h3, h4, p, span, label, div" not in stylesheet
    assert '[data-testid="stSidebar"]' in stylesheet
    for f in root.glob("*.py"):ast.parse(f.read_text())
'''
tests = replace_once(tests, old_test, new_test, "sidebar regression test")
path.write_text(tests, encoding="utf-8")

print("v15 Zoho shell applied")
