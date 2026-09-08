from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path, old, new, count=1):
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:90]!r}")
    text = text.replace(old, new, count)
    p.write_text(text, encoding="utf-8")


# 1) Excel/import quantities may contain harmless binary-float tails. Normalize only imports.
replace("gp_store.py", "from decimal import Decimal, InvalidOperation", "from decimal import Decimal, InvalidOperation, ROUND_HALF_UP")
replace(
    "gp_store.py",
    '''def decimal_qty(value, *, positive=False) -> Decimal:\n    if isinstance(value, bool) or value is None:\n        raise AppError("Invalid quantity")\n    try:\n        number = Decimal(str(value))\n    except (InvalidOperation, ValueError, TypeError):\n        raise AppError("Invalid quantity") from None\n    if not number.is_finite() or abs(number) > MAX_QTY or (positive and number <= 0):\n        raise AppError("Invalid quantity")\n    if number != number.quantize(Decimal("0.0001")):\n        raise AppError("Use at most four decimal places")\n    return number\n''',
    '''def decimal_qty(value, *, positive=False, normalize=False) -> Decimal:\n    """Validate quantities; imported report values may be normalized to DB precision.\n\n    Excel often exposes values such as 2.9999999999999996 even when the sheet\n    visibly contains 3. Imported stock/history is safely rounded to four places,\n    while manually entered/posting quantities remain strict.\n    """\n    if isinstance(value, bool) or value is None:\n        raise AppError("Invalid quantity")\n    try:\n        number = Decimal(str(value))\n    except (InvalidOperation, ValueError, TypeError):\n        raise AppError("Invalid quantity") from None\n    if not number.is_finite() or abs(number) > MAX_QTY or (positive and number <= 0):\n        raise AppError("Invalid quantity")\n    unit = Decimal("0.0001")\n    rounded = number.quantize(unit, rounding=ROUND_HALF_UP)\n    if normalize:\n        number = rounded\n    elif number != rounded:\n        raise AppError("Use at most four decimal places")\n    return number\n'''
)
replace("gp_store.py", "quantity=decimal_qty(r[COL_QTY]),", "quantity=decimal_qty(r[COL_QTY],normalize=True),")
replace("gp_store.py", "qty_in=decimal_qty(r[COL_IN]),\n                qty_out=decimal_qty(r[COL_OUT]),balance=None if pd.isna(r[COL_BAL]) else decimal_qty(r[COL_BAL]),", "qty_in=decimal_qty(r[COL_IN],normalize=True),\n                qty_out=decimal_qty(r[COL_OUT],normalize=True),balance=None if pd.isna(r[COL_BAL]) else decimal_qty(r[COL_BAL],normalize=True),")

# 2) Bilingual UI primitives + branded waiting overlay. Appended definitions override v5 helpers.
gp_ui = ROOT / "gp_ui.py"
ui_text = gp_ui.read_text(encoding="utf-8")
if "GP-CLOUD-v6" not in ui_text:
    ui_text += r'''

# ---- v6 bilingual / branded waiting helpers ----
BUILD = "GP-CLOUD-v6"
LANGUAGE = "ar"
AR.update({
    "Language": "اللغة", "Arabic": "العربية", "English": "English",
    "Loading": "جاري التحميل...", "Processing": "جاري التنفيذ...",
    "Reading report": "جاري قراءة التقرير...", "Saving to cloud": "جاري الحفظ السحابي...",
    "Loading data": "جاري تحميل البيانات...", "Preparing analysis": "جاري تجهيز التحليل...",
    "Preparing export": "جاري تجهيز الملف...", "Importing stock": "جاري اعتماد رصيد البداية...",
    "Importing history": "جاري اعتماد حركة المادة...",
    "Use at most four decimal places": "الكمية تحتوي منازل عشرية أكثر من المسموح.",
})


def set_language(value):
    global LANGUAGE
    LANGUAGE = "en" if str(value).lower().startswith("en") else "ar"


def language_dir():
    return "rtl" if LANGUAGE == "ar" else "ltr"


def t(value):
    value = str(value)
    return AR.get(value, value) if LANGUAGE == "ar" else value


def language_marker():
    return f'<span class="gp-lang-{LANGUAGE}-marker" hidden></span>'


def _logo_data():
    return base64.b64encode((ROOT/"assets/golden_palace.jpg").read_bytes()).decode()


def _icon_data():
    return base64.b64encode((ROOT/"assets/favicon.png").read_bytes()).decode()


def brand_html():
    data = _logo_data()
    d = language_dir()
    return f'''<section class="gp-brand" aria-label="Golden Palace" dir="{d}">
        <div class="gp-brand-copy"><div class="gp-eyebrow">GOLDEN PALACE / INVENTORY</div>
        <h1>{html.escape(t("Golden Palace"))}</h1><p>{html.escape(t("Inventory"))}</p></div>
        <div class="gp-logo"><img src="data:image/jpeg;base64,{data}" alt="Golden Palace"></div>
        </section>'''


def status_html(actor,stamp):
    d = language_dir()
    return f'''<div class="gp-status" dir="{d}"><span class="gp-status-pill"><i></i>{html.escape(t("Connected"))}</span>
    <span><b>{html.escape(actor["display_name"])}</b> / {html.escape(t(actor["role"]))}</span>
    <span class="gp-muted">{html.escape(t("Last save"))} <bdi>{html.escape(str(stamp))}</bdi></span></div>'''


def kpis_html(values):
    d = language_dir()
    return '<div class="gp-kpis" dir="'+d+'">'+''.join(
        f'<article class="gp-kpi"><span>{html.escape(t(label))}</span><strong dir="ltr">{html.escape(str(value))}</strong><small>{html.escape(t(note))}</small></article>'
        for label,value,note in values)+'</div>'


def section_html(title,note=""):
    d = language_dir()
    return f'<div class="gp-section" dir="{d}"><h2>{html.escape(t(title))}</h2><p>{html.escape(t(note))}</p></div>'


def loading_html(message="Loading"):
    d = language_dir()
    return f'''<div class="gp-loading-backdrop"><div class="gp-loading-card" dir="{d}">
      <img src="data:image/png;base64,{_icon_data()}" alt="Golden Palace">
      <div class="gp-loading-ring"></div><strong>{html.escape(t(message))}</strong>
    </div></div>'''
'''
    gp_ui.write_text(ui_text, encoding="utf-8")

# 3) Faster shell loads, cached report parsing, live language switch and branded waits.
replace(
    "inventory_tracker.py",
    "from pathlib import Path\nimport gzip",
    "from pathlib import Path\nfrom contextlib import contextmanager\nimport gzip",
)
replace(
    "inventory_tracker.py",
    "from gp_ui import BUILD, ROOT, t, css, brand_html, status_html, kpis_html, section_html",
    "from gp_ui import (BUILD, ROOT, t, css, brand_html, status_html, kpis_html, section_html,\n                   set_language, loading_html, language_marker)",
)
replace(
    "inventory_tracker.py",
    '''st.set_page_config(page_title=t("Golden Palace")+" | "+t("Stock"),\n                   page_icon=Image.open(ROOT/"assets/favicon.png"),layout="wide",initial_sidebar_state="collapsed")\nst.markdown("<style>"+css()+"</style>",unsafe_allow_html=True)\nst.markdown(brand_html(),unsafe_allow_html=True)\nLOG=logging.getLogger("golden_palace")\n''',
    '''st.set_page_config(page_title="Golden Palace | Inventory",\n                   page_icon=Image.open(ROOT/"assets/favicon.png"),layout="wide",initial_sidebar_state="collapsed")\nst.markdown("<style>"+css()+"</style>",unsafe_allow_html=True)\nLOG=logging.getLogger("golden_palace")\n'''
)
replace(
    "inventory_tracker.py",
    '''@st.cache_resource(show_spinner=False)\ndef get_store(settings_json):\n    return Store.from_settings(json.loads(settings_json))\n\n\n@st.cache_data(show_spinner=False,ttl=120,max_entries=2)\ndef get_analysis''',
    '''@st.cache_resource(show_spinner=False)\ndef get_store(settings_json):\n    return Store.from_settings(json.loads(settings_json))\n\n\n@st.cache_data(show_spinner=False,ttl=15,max_entries=24)\ndef get_shell(database_id,token_hash,_store,_token):\n    actor=_store.actor(_token)\n    state=_store.state(_token)\n    stock=_store.stock(_token)\n    daily=_store.ledger(_token,_store.today())\n    return actor,state,stock,daily\n\n\n@st.cache_data(show_spinner=False,max_entries=6)\ndef parse_stock_report(raw):\n    return read_stock_report(raw)\n\n\n@st.cache_data(show_spinner=False,max_entries=6)\ndef parse_history_report(raw):\n    return read_movement_report(raw)\n\n\n@contextmanager\ndef branded_wait(message="Loading"):\n    holder=st.empty()\n    holder.markdown(loading_html(message),unsafe_allow_html=True)\n    try:\n        yield\n    finally:\n        holder.empty()\n\n\n@st.cache_data(show_spinner=False,ttl=120,max_entries=2)\ndef get_analysis'''
)
replace(
    "inventory_tracker.py",
    '''def success(name=None,message="Saved"):\n    if name:st.session_state.pop("operation_"+name,None)\n    st.session_state["flash"]=t(message)\n    st.session_state["wipe_passwords"]=True\n    st.rerun()\n''',
    '''def success(name=None,message="Saved"):\n    if name:st.session_state.pop("operation_"+name,None)\n    get_shell.clear(); get_analysis.clear()\n    st.session_state["flash"]=t(message)\n    st.session_state["wipe_passwords"]=True\n    st.rerun()\n'''
)
replace("inventory_tracker.py", "with st.spinner(t(\"Reading\")):", "with branded_wait(\"Reading\"):")
replace("inventory_tracker.py", "df=read_stock_report(uploaded.getvalue())", "raw=uploaded.getvalue()\n                with branded_wait(\"Reading report\"):\n                    df=parse_stock_report(raw)")
replace("inventory_tracker.py", "raw=uploaded.getvalue();df=read_movement_report(raw)", "raw=uploaded.getvalue()\n                with branded_wait(\"Reading report\"):\n                    df=parse_history_report(raw)")
replace(
    "inventory_tracker.py",
    '''                        store.replace_stock(token,password,df,nonce("baseline"),state["revision"])\n                        success("baseline")''',
    '''                        with branded_wait("Importing stock"):\n                            store.replace_stock(token,password,df,nonce("baseline"),state["revision"])\n                        success("baseline")'''
)
replace(
    "inventory_tracker.py",
    '''                        store.import_history(token,password,df,hashlib.sha256(raw).hexdigest(),as_of,nonce("history"))\n                        success("history")''',
    '''                        with branded_wait("Importing history"):\n                            store.import_history(token,password,df,hashlib.sha256(raw).hexdigest(),as_of,nonce("history"))\n                        success("history")'''
)
replace(
    "inventory_tracker.py",
    '''def main():\n    if st.session_state.pop("wipe_passwords",False):''',
    '''def main():\n    if "ui_language" not in st.session_state:\n        st.session_state["ui_language"]="ar"\n    selected_lang=st.segmented_control("Language / اللغة",["ar","en"],\n        default=st.session_state["ui_language"],format_func=lambda x:"العربية" if x=="ar" else "English",\n        key="language_switch",label_visibility="collapsed") or st.session_state["ui_language"]\n    if selected_lang!=st.session_state["ui_language"]:\n        st.session_state["ui_language"]=selected_lang\n        st.rerun()\n    set_language(st.session_state["ui_language"])\n    st.markdown(language_marker(),unsafe_allow_html=True)\n    st.markdown(brand_html(),unsafe_allow_html=True)\n    if st.session_state.pop("wipe_passwords",False):'''
)
replace(
    "inventory_tracker.py",
    '''    try:\n        actor=store.actor(token)\n        state=store.state(token)\n        stock=store.stock(token)\n        daily=store.ledger(token,store.today())\n    except AppError as error:''',
    '''    try:\n        database_id=str(store.engine.url.render_as_string(hide_password=True))\n        token_hash=hashlib.sha256(token.encode()).hexdigest()[:24]\n        with branded_wait("Loading data"):\n            actor,state,stock,daily=get_shell(database_id,token_hash,store,token)\n    except AppError as error:'''
)
replace("inventory_tracker.py", 'if b.button(t("Refresh"),width="stretch",key="global_refresh"):st.rerun()', 'if b.button(t("Refresh"),width="stretch",key="global_refresh"):\n        get_shell.clear(); get_analysis.clear(); st.rerun()')

# 4) CSS additions for bilingual direction + branded modal overlay.
style = ROOT / "assets/style.css"
css = style.read_text(encoding="utf-8")
extra = r'''

/* v6 language switch + branded busy overlay */
.st-key-language_switch { max-width:230px; margin:0 0 .55rem auto; }
.st-key-language_switch [data-testid="stButtonGroup"] > div { gap:4px; }
.st-key-language_switch button { min-height:36px; font-weight:800; }
.stApp:has(.gp-lang-en-marker) [data-testid="stMainBlockContainer"] h1,
.stApp:has(.gp-lang-en-marker) [data-testid="stMainBlockContainer"] h2,
.stApp:has(.gp-lang-en-marker) [data-testid="stMainBlockContainer"] h3,
.stApp:has(.gp-lang-en-marker) [data-testid="stMarkdownContainer"] p,
.stApp:has(.gp-lang-en-marker) [data-testid="stWidgetLabel"] { direction:ltr; text-align:left; }
.stApp:has(.gp-lang-en-marker) [data-testid="stTextInput"] input:not([type="password"]),
.stApp:has(.gp-lang-en-marker) [data-testid="stTextArea"] textarea { direction:ltr; text-align:left; }
.stApp:has(.gp-lang-en-marker) .st-key-navigation [data-testid="stButtonGroup"] > div { direction:ltr; }
.stApp:has(.gp-lang-en-marker) .st-key-language_switch { margin-left:auto; margin-right:0; }
.gp-loading-backdrop { position:fixed; inset:0; z-index:999999; display:flex; align-items:center; justify-content:center; background:rgba(18,38,62,.35); backdrop-filter:blur(3px); }
.gp-loading-card { width:min(360px,82vw); background:#fff; border:1px solid #d8c184; border-radius:22px; padding:25px 28px; box-shadow:0 24px 70px rgba(18,38,62,.26); display:flex; align-items:center; justify-content:center; gap:14px; color:var(--gp-navy); font-weight:850; font-size:1.05rem; }
.gp-loading-card img { width:48px; height:48px; object-fit:contain; }
.gp-loading-ring { width:24px; height:24px; border:3px solid #e7edf3; border-top-color:var(--gp-gold); border-radius:50%; animation:gp-spin .75s linear infinite; }
@keyframes gp-spin { to { transform:rotate(360deg); } }
'''
if "v6 language switch" not in css:
    style.write_text(css + extra, encoding="utf-8")

print("Applied GP-CLOUD-v6 source updates")
