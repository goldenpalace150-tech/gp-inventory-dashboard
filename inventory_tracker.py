import streamlit as st
import pandas as pd
from PIL import Image
import io
import json
import re
import unicodedata
import base64
import hashlib
import os
import sqlite3
import uuid
import urllib.error
import urllib.request
from datetime import datetime

# ==========================================
# PAGE CONFIGURATION & MOBILE-FRIENDLY RTL STYLING
# ==========================================
st.set_page_config(page_title="متتبع الجرد - القصر الذهبي", layout="wide")


def app_secret(section, key, default=""):
    try:
        return st.secrets.get(section, {}).get(key, default)
    except Exception:
        return default


DATABASE_PATH = str(
    app_secret("inventory", "database_path", "inventory_tracker.db")
).strip()
OPENAI_API_KEY = str(app_secret("openai", "api_key", "")).strip()
OPENAI_VISION_MODEL = str(
    app_secret("openai", "vision_model", "gpt-4.1-mini")
).strip()


def database_connection():
    database_dir = os.path.dirname(os.path.abspath(DATABASE_PATH))
    os.makedirs(database_dir, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with database_connection() as connection:
        connection.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS stock_state (
                item_key TEXT PRIMARY KEY,
                item_code TEXT NOT NULL DEFAULT '',
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                match_key TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS movement_ledger (
                movement_id TEXT PRIMARY KEY,
                operation_id TEXT NOT NULL,
                operation_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                business_date TEXT NOT NULL,
                username TEXT NOT NULL,
                source TEXT NOT NULL,
                movement_type TEXT NOT NULL,
                item_key TEXT NOT NULL,
                item_code TEXT NOT NULL DEFAULT '',
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                quantity_before REAL NOT NULL,
                quantity_after REAL NOT NULL,
                invoice_reference TEXT NOT NULL DEFAULT '',
                without_invoice INTEGER NOT NULL DEFAULT 0,
                delivery_note INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_movement_fingerprint
                ON movement_ledger(operation_fingerprint, item_key, movement_type);
            CREATE TABLE IF NOT EXISTS posted_invoices (
                invoice_reference TEXT PRIMARY KEY,
                image_hash TEXT NOT NULL UNIQUE,
                operation_id TEXT NOT NULL,
                posted_at TEXT NOT NULL,
                username TEXT NOT NULL,
                recognized_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS imported_movement_history (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_code TEXT,
                item_name TEXT,
                movement_date TEXT,
                reference TEXT,
                customer TEXT,
                qty_in REAL,
                qty_out REAL,
                balance REAL,
                username TEXT,
                statement TEXT,
                match_key TEXT
            );
            CREATE TABLE IF NOT EXISTS app_metadata (
                meta_key TEXT PRIMARY KEY,
                meta_value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS daily_closures (
                business_date TEXT PRIMARY KEY,
                closed_at TEXT NOT NULL,
                username TEXT NOT NULL,
                movement_count INTEGER NOT NULL,
                total_in REAL NOT NULL,
                total_out REAL NOT NULL,
                no_invoice_count INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS daily_stock_snapshots (
                business_date TEXT NOT NULL,
                item_key TEXT NOT NULL,
                item_code TEXT NOT NULL DEFAULT '',
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                match_key TEXT NOT NULL,
                PRIMARY KEY (business_date, item_key)
            );
        """)


initialize_database()

st.markdown("""
    <style>
        .stApp {
            direction: rtl;
            text-align: right;
            background: #f4f7fb;
        }
        /* Fix mobile text vertical stacking/wrapping issues */
        h1, h2, h3, h4, p, span, label, div {
            word-break: normal !important;
            overflow-wrap: break-word !important;
            text-align: right;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            flex-wrap: wrap;
            background: white;
            border: 1px solid #dce5f0;
            border-radius: 14px;
            padding: 5px;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: transparent;
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 14px;
            min-height: 44px;
        }
        .stTabs [aria-selected="true"] { background: #eaf1ff !important; color: #1d4ed8 !important; }
        table { width: 100% !important; font-size: 13px !important; }
        .block-container { max-width: 1450px; padding-top: 1.2rem; padding-bottom: 2rem; }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid #dce5f0;
            border-radius: 14px;
            padding: 14px;
            box-shadow: 0 4px 14px rgba(15, 23, 42, .04);
        }
        div[data-testid="stForm"], div[data-testid="stExpander"] {
            background: white;
            border: 1px solid #dce5f0 !important;
            border-radius: 14px !important;
        }
        .gp-hero {
            background: linear-gradient(115deg, #14264a, #245bd8);
            color: white;
            padding: 20px 24px;
            border-radius: 18px;
            margin-bottom: 14px;
            box-shadow: 0 10px 28px rgba(30, 64, 175, .18);
        }
        .gp-hero-title { font-size: 25px; font-weight: 800; }
        .gp-hero-sub { opacity: .82; margin-top: 4px; }
        @media (max-width: 700px) {
            .block-container { padding-left: 10px; padding-right: 10px; }
            .stTabs [data-baseweb="tab"] { padding: 8px 9px; font-size: 12px; }
            .gp-hero { padding: 16px; }
        }
    </style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="gp-hero"><div class="gp-hero-title">القصر الذهبي · إدارة المخزون</div>'
    '<div class="gp-hero-sub">حركة فورية، تدقيق الفواتير، إعادة الطلب وتقارير نهاية اليوم</div></div>',
    unsafe_allow_html=True,
)

# ==========================================
# SESSION STATE INITIALIZATION
# ==========================================
if 'live_stock' not in st.session_state:
    st.session_state['live_stock'] = None
if 'processed_invoices' not in st.session_state:
    st.session_state['processed_invoices'] = {}
if 'invoice_raw_data' not in st.session_state:
    st.session_state['invoice_raw_data'] = {}
if 'file_to_invoice' not in st.session_state:
    st.session_state['file_to_invoice'] = {}
if 'movement_history' not in st.session_state:
    st.session_state['movement_history'] = None
if 'manual_movements' not in st.session_state:
    st.session_state['manual_movements'] = []
if 'manual_movement_flash' not in st.session_state:
    st.session_state['manual_movement_flash'] = None
if 'recognized_invoices' not in st.session_state:
    st.session_state['recognized_invoices'] = {}
if 'manual_operation_nonce' not in st.session_state:
    st.session_state['manual_operation_nonce'] = str(uuid.uuid4())
if 'movement_file_hash' not in st.session_state:
    st.session_state['movement_file_hash'] = None

# Default user database managed by Admin
if 'user_db' not in st.session_state:
    st.session_state['user_db'] = {
        "admin": {"password": "123", "role": "مدير النظام (Admin)"},
        "store": {"password": "123", "role": "أمين مخزن (Storekeeper)"}
    }

if 'logged_in_user' not in st.session_state:
    st.session_state['logged_in_user'] = None

# ==========================================
# 🔐 SIDEBAR: AUTHENTICATION & USER MANAGEMENT
# ==========================================
st.sidebar.header("🔐 نظام تسجيل الدخول والصلاحيات")

if st.session_state['logged_in_user'] is None:
    with st.sidebar.form("login_form"):
        username_input = st.text_input("اسم المستخدم")
        password_input = st.text_input("كلمة المرور", type="password")
        login_btn = st.form_submit_button("تسجيل الدخول", use_container_width=True)
        
        if login_btn:
            if username_input in st.session_state['user_db'] and st.session_state['user_db'][username_input]["password"] == password_input:
                st.session_state['logged_in_user'] = username_input
                st.rerun()
            else:
                st.sidebar.error("اسم المستخدم أو كلمة المرور غير صحيحة.")
else:
    current_user = st.session_state['logged_in_user']
    current_role = st.session_state['user_db'][current_user]["role"]
    
    st.sidebar.success(f"مرحباً: {current_user}")
    st.sidebar.info(f"الصلاحية: {current_role}")
    st.sidebar.success("● الحفظ التلقائي للحركات فعال")
    st.sidebar.caption("يبقى تسجيل الدخول فعالاً حتى تضغط تسجيل الخروج.")
    
    if st.sidebar.button("تسجيل الخروج", use_container_width=True):
        st.session_state['logged_in_user'] = None
        st.rerun()

    if current_role == "مدير النظام (Admin)":
        st.sidebar.divider()
        st.sidebar.subheader("👥 إضافة مستخدم جديد")
        with st.sidebar.form("new_user_form"):
            new_username = st.text_input("اسم المستخدم الجديد")
            new_password = st.text_input("كلمة المرور", type="password")
            new_role = st.selectbox("الصلاحية", ["أمين مخزن (Storekeeper)", "مدير النظام (Admin)"])
            add_user_btn = st.form_submit_button("إضافة المستخدم", use_container_width=True)
            
            if add_user_btn:
                if new_username and new_password:
                    st.session_state['user_db'][new_username] = {"password": new_password, "role": new_role}
                    st.sidebar.success(f"تمت إضافة المستخدم {new_username} بنجاح!")
                else:
                    st.sidebar.warning("يرجى ملء كافة الحقول.")

is_admin = (st.session_state['logged_in_user'] is not None and st.session_state['user_db'][st.session_state['logged_in_user']]["role"] == "مدير النظام (Admin)")

st.divider()

if st.session_state['logged_in_user'] is None:
    st.warning("⚠️ يرجى تسجيل الدخول من القائمة الجانبية لعرض لوحة التحكم.")
    st.stop()

# ==========================================
# REAL INVOICE PHOTO RECOGNITION
# ==========================================
def extract_invoice_data(uploaded_file):
    """Recognize the actual invoice image and return strict structured data."""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "أضف openai.api_key إلى Streamlit Secrets لتفعيل قراءة صور الفواتير."
        )
    image = Image.open(io.BytesIO(uploaded_file.getvalue())).convert("RGB")
    image.thumbnail((2200, 2200))
    optimized = io.BytesIO()
    image.save(optimized, format="JPEG", quality=90, optimize=True)
    image_b64 = base64.b64encode(optimized.getvalue()).decode("ascii")

    invoice_schema = {
        "type": "object",
        "properties": {
            "invoice_number": {"type": "string"},
            "movement_type": {"type": "string", "enum": ["OUT", "IN"]},
            "confidence": {"type": "number"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_code": {"type": "string"},
                        "item_name": {"type": "string"},
                        "quantity": {"type": "number"},
                    },
                    "required": ["item_code", "item_name", "quantity"],
                    "additionalProperties": False,
                },
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "invoice_number", "movement_type", "confidence", "items", "warnings"
        ],
        "additionalProperties": False,
    }
    prompt = (
        "اقرأ صورة فاتورة مخزون عربية أو إنجليزية بدقة. استخرج رقم الفاتورة، "
        "وحدد OUT للمبيعات/الإخراج وIN للمشتريات/المرتجع الداخل، ثم استخرج كل "
        "رمز مادة واسمها والكمية فقط. لا تخمن رمزاً غير ظاهر؛ اتركه فارغاً "
        "وأضف تحذيراً. لا تجمع سطوراً مختلفة ولا تستخدم السعر ككمية."
    )
    payload = {
        "model": OPENAI_VISION_MODEL,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image_b64}",
                    "detail": "high",
                },
            ],
        }],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "inventory_invoice",
                "strict": True,
                "schema": invoice_schema,
            }
        },
        "max_output_tokens": 3000,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"فشل التعرف على الفاتورة (HTTP {error.code}): {detail}")
    except Exception as error:
        raise RuntimeError(f"تعذر الاتصال بخدمة قراءة الفاتورة: {error}")

    output_text = ""
    for output_item in response_data.get("output", []):
        if output_item.get("type") != "message":
            continue
        for content_item in output_item.get("content", []):
            if content_item.get("type") == "output_text":
                output_text += content_item.get("text", "")
    if not output_text:
        raise RuntimeError("لم تُرجع خدمة التعرف بيانات قابلة للقراءة.")
    recognized = json.loads(output_text)
    recognized["image_hash"] = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
    recognized["source_name"] = getattr(uploaded_file, "name", "invoice-photo.jpg")
    return recognized


def normalize_item_name(value):
    """Normalize Ameen item names without changing the displayed Arabic text."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace('"', '').replace("'", "")
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalize_item_code(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def split_movement_item(value):
    """Split codes such as SG05LP3-EU-SM2-اسم المادة safely."""
    text = str(value or "").strip()
    match = re.match(r"^\s*(.*?)\s*-\s*(?=[\u0600-\u06FF])(.+)$", text)
    if match:
        return normalize_item_code(match.group(1)), match.group(2).strip()
    return "", text


@st.cache_data(show_spinner=False)
def read_stock_report(file_bytes):
    """Read both the original 2-column report and older code/name/qty reports."""
    excel = pd.ExcelFile(io.BytesIO(file_bytes))
    for sheet_name in excel.sheet_names:
        for header_row in (0, 1, 2):
            candidate = pd.read_excel(
                io.BytesIO(file_bytes), sheet_name=sheet_name, header=header_row
            )
            columns = {str(column).strip(): column for column in candidate.columns}
            name_col = next(
                (columns[key] for key in columns if "اسم المادة" in key), None
            )
            qty_col = next(
                (columns[key] for key in columns if key == "الكمية"), None
            )
            code_col = next(
                (columns[key] for key in columns if "رمز المادة" in key), None
            )
            if name_col is None or qty_col is None:
                continue
            result = pd.DataFrame({
                "رمز المادة": (
                    candidate[code_col].map(normalize_item_code)
                    if code_col is not None
                    else ""
                ),
                "اسم المادة": candidate[name_col].astype(str).str.strip('"'),
                "الكمية": pd.to_numeric(candidate[qty_col], errors="coerce").fillna(0),
            })
            result = result[
                candidate[name_col].notna()
                & result["اسم المادة"].astype(str).str.strip().ne("")
            ].copy()
            result["مفتاح المطابقة"] = result["اسم المادة"].map(normalize_item_name)
            result = result.reset_index(drop=True)
            base_keys = result.apply(
                lambda row: (
                    f"CODE:{normalize_item_code(row['رمز المادة'])}"
                    if normalize_item_code(row['رمز المادة'])
                    else f"NAME:{row['مفتاح المطابقة']}"
                ),
                axis=1,
            )
            duplicate_number = base_keys.groupby(base_keys).cumcount()
            result["مفتاح المخزون"] = [
                base_key if number == 0 else f"{base_key}#{number + 1}"
                for base_key, number in zip(base_keys, duplicate_number)
            ]
            return result
    raise ValueError("لم يتم العثور على أعمدة اسم المادة والكمية في تقرير الجرد.")


@st.cache_data(show_spinner=False)
def read_movement_report(file_bytes):
    """Read the Ameen item-movement report by its stable column positions."""
    excel = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet_name = next(
        (name for name in excel.sheet_names if "حركة" in str(name)),
        excel.sheet_names[0],
    )
    raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=1)
    if raw.shape[1] < 9:
        raise ValueError("تقرير حركة المادة لا يحتوي على أعمدة الإدخال والإخراج المطلوبة.")
    parsed_items = raw.iloc[:, 0].map(split_movement_item)
    movement = pd.DataFrame({
        "رمز المادة": parsed_items.map(lambda item: item[0]),
        "اسم المادة": parsed_items.map(lambda item: item[1]),
        "التاريخ": pd.to_datetime(raw.iloc[:, 1], errors="coerce"),
        "المرجع": raw.iloc[:, 2].fillna("").astype(str).str.strip(),
        "الزبون": raw.iloc[:, 3].fillna("").astype(str).str.strip(),
        "إدخال": pd.to_numeric(raw.iloc[:, 4], errors="coerce").fillna(0),
        "إخراج": pd.to_numeric(raw.iloc[:, 6], errors="coerce").fillna(0),
        "الرصيد": pd.to_numeric(raw.iloc[:, 8], errors="coerce"),
        "المستخدم": raw.iloc[:, 10].fillna("").astype(str).str.strip()
            if raw.shape[1] > 10 else "",
        "بيان": raw.iloc[:, 13].fillna("").astype(str).str.strip()
            if raw.shape[1] > 13 else "",
    })
    movement = movement[movement["التاريخ"].notna()].copy()
    movement["مفتاح المطابقة"] = movement["اسم المادة"].map(normalize_item_name)
    return movement.reset_index(drop=True)


def enrich_stock_codes(stock_df, movement_df):
    """Fill missing stock codes from exact normalized-name matches."""
    stock = stock_df.copy()
    if movement_df is None or movement_df.empty:
        return stock
    code_map = (
        movement_df[movement_df["رمز المادة"].ne("")]
        .drop_duplicates("مفتاح المطابقة")
        .set_index("مفتاح المطابقة")["رمز المادة"]
    )
    missing_code = stock["رمز المادة"].fillna("").astype(str).str.strip().eq("")
    stock.loc[missing_code, "رمز المادة"] = (
        stock.loc[missing_code, "مفتاح المطابقة"].map(code_map).fillna("")
    )
    return stock


def build_inventory_analysis(
    stock_df,
    movement_df,
    lead_days,
    safety_days,
    slow_days,
    demand_window_days=90,
    review_days=30,
    purchase_prefixes=None,
):
    """Build a purchase-aware reorder plan from demand, stock and supply history."""
    if movement_df is None or movement_df.empty:
        return pd.DataFrame()

    movement_df = movement_df.copy()
    movement_df["التاريخ"] = pd.to_datetime(
        movement_df["التاريخ"], errors="coerce"
    )
    movement_df = movement_df[movement_df["التاريخ"].notna()].copy()
    end_date = movement_df["التاريخ"].max().normalize()
    demand_window_days = max(7, int(demand_window_days))
    review_days = max(1, int(review_days))
    recent_start = end_date - pd.Timedelta(days=demand_window_days - 1)
    prior_end = recent_start - pd.Timedelta(days=1)
    prior_start = prior_end - pd.Timedelta(days=demand_window_days - 1)

    purchase_prefixes = tuple(
        prefix.strip()
        for prefix in (purchase_prefixes or ("إد.م. م. م.",))
        if str(prefix).strip()
    )

    grouped = movement_df.groupby("مفتاح المطابقة", as_index=False).agg(
        **{
            "رمز الحركة": ("رمز المادة", "first"),
            "اسم الحركة": ("اسم المادة", "first"),
            "إجمالي الإدخال": ("إدخال", "sum"),
            "إجمالي الإخراج": ("إخراج", "sum"),
            "عدد الحركات": ("التاريخ", "count"),
            "آخر حركة": ("التاريخ", "max"),
        }
    )
    last_out = (
        movement_df[movement_df["إخراج"] > 0]
        .groupby("مفتاح المطابقة")["التاريخ"]
        .max()
    )
    grouped["آخر إخراج"] = grouped["مفتاح المطابقة"].map(last_out)

    recent_out = (
        movement_df[
            (movement_df["إخراج"] > 0)
            & (movement_df["التاريخ"] >= recent_start)
            & (movement_df["التاريخ"] < end_date + pd.Timedelta(days=1))
        ]
        .groupby("مفتاح المطابقة")["إخراج"]
        .sum()
    )
    prior_out = (
        movement_df[
            (movement_df["إخراج"] > 0)
            & (movement_df["التاريخ"] >= prior_start)
            & (movement_df["التاريخ"] < recent_start)
        ]
        .groupby("مفتاح المطابقة")["إخراج"]
        .sum()
    )
    grouped[f"خروج آخر {demand_window_days} يوم"] = (
        grouped["مفتاح المطابقة"].map(recent_out).fillna(0)
    )
    grouped["خروج الفترة السابقة"] = (
        grouped["مفتاح المطابقة"].map(prior_out).fillna(0)
    )

    reference = movement_df["المرجع"].fillna("").astype(str).str.strip()
    if purchase_prefixes:
        purchase_mask = (
            (movement_df["إدخال"] > 0)
            & reference.str.startswith(purchase_prefixes)
        )
    else:
        purchase_mask = pd.Series(False, index=movement_df.index)
    purchases = movement_df[purchase_mask].copy()
    if not purchases.empty:
        purchases["يوم الشراء"] = purchases["التاريخ"].dt.normalize()
        purchase_daily = (
            purchases.groupby(["مفتاح المطابقة", "يوم الشراء"], as_index=False)["إدخال"]
            .sum()
            .sort_values(["مفتاح المطابقة", "يوم الشراء"])
        )
        purchase_summary_rows = []
        for item_key, item_purchases in purchase_daily.groupby("مفتاح المطابقة"):
            unique_dates = item_purchases["يوم الشراء"].sort_values()
            gaps = unique_dates.diff().dt.days.dropna()
            last_row = item_purchases.iloc[-1]
            purchase_summary_rows.append({
                "مفتاح المطابقة": item_key,
                "آخر شراء/توريد": last_row["يوم الشراء"],
                "كمية آخر شراء/توريد": float(last_row["إدخال"]),
                "عدد مرات الشراء/التوريد": int(len(item_purchases)),
                "متوسط فترة التوريد": (
                    float(gaps.mean()) if not gaps.empty else float("nan")
                ),
            })
        purchase_summary = pd.DataFrame(purchase_summary_rows)
        grouped = grouped.merge(
            purchase_summary, on="مفتاح المطابقة", how="left"
        )
    else:
        grouped["آخر شراء/توريد"] = pd.NaT
        grouped["كمية آخر شراء/توريد"] = 0.0
        grouped["عدد مرات الشراء/التوريد"] = 0
        grouped["متوسط فترة التوريد"] = float("nan")

    stock_view = stock_df[["مفتاح المطابقة", "رمز المادة", "اسم المادة", "الكمية"]].copy()
    analysis = stock_view.merge(grouped, on="مفتاح المطابقة", how="left")
    analysis["رمز المادة"] = analysis["رمز المادة"].where(
        analysis["رمز المادة"].astype(str).str.strip().ne(""),
        analysis["رمز الحركة"],
    ).fillna("")
    numeric_columns = (
        "إجمالي الإدخال", "إجمالي الإخراج", "عدد الحركات",
        f"خروج آخر {demand_window_days} يوم", "خروج الفترة السابقة",
        "كمية آخر شراء/توريد", "عدد مرات الشراء/التوريد",
    )
    for column in numeric_columns:
        analysis[column] = pd.to_numeric(analysis[column], errors="coerce").fillna(0)

    recent_column = f"خروج آخر {demand_window_days} يوم"
    analysis["الخروج اليومي الحديث"] = analysis[recent_column] / demand_window_days
    analysis["متوسط الخروج اليومي"] = analysis["الخروج اليومي الحديث"]
    recent_rate = analysis[recent_column] / demand_window_days
    prior_rate = analysis["خروج الفترة السابقة"] / demand_window_days
    trend_ratio = recent_rate / prior_rate.replace(0, pd.NA)
    analysis["اتجاه الطلب"] = "مستقر"
    analysis.loc[(prior_rate <= 0) & (recent_rate > 0), "اتجاه الطلب"] = "صاعد"
    analysis.loc[trend_ratio >= 1.25, "اتجاه الطلب"] = "صاعد"
    analysis.loc[(trend_ratio <= 0.75) & (recent_rate > 0), "اتجاه الطلب"] = "هابط"
    analysis.loc[recent_rate <= 0, "اتجاه الطلب"] = "بدون طلب حديث"
    demand = analysis["إجمالي الإخراج"].sort_values(ascending=False)
    total_demand = demand.sum()
    if total_demand > 0:
        cumulative_before = demand.cumsum().shift(fill_value=0) / total_demand
        abc = pd.Series("بطيئة", index=demand.index)
        abc.loc[cumulative_before < 0.95] = "متوسطة"
        abc.loc[cumulative_before < 0.80] = "سريعة"
        analysis["سرعة الحركة"] = abc.reindex(analysis.index)
    else:
        analysis["سرعة الحركة"] = "بدون حركة"
    analysis.loc[analysis["إجمالي الإخراج"] <= 0, "سرعة الحركة"] = "بدون حركة"

    analysis["أيام منذ آخر خروج"] = (
        end_date.normalize() - pd.to_datetime(analysis["آخر إخراج"])
    ).dt.days
    analysis["أيام منذ آخر شراء/توريد"] = (
        end_date - pd.to_datetime(analysis["آخر شراء/توريد"])
    ).dt.days
    analysis["تغطية المخزون بالأيام"] = (
        analysis["الكمية"] / recent_rate.replace(0, float("nan"))
    ).clip(lower=0).astype(float).round(1)
    analysis["مخزون الأمان"] = (recent_rate * safety_days).round().astype(int)
    analysis["حد إعادة الطلب"] = (
        recent_rate * lead_days + analysis["مخزون الأمان"]
    ).round().astype(int)
    target_days = lead_days + safety_days + review_days
    analysis["كمية الطلب المقترحة"] = (
        recent_rate * target_days - analysis["الكمية"]
    ).clip(lower=0).round().astype(int)

    cover = analysis["تغطية المخزون بالأيام"]
    has_recent_demand = analysis[recent_column] > 0
    critical = has_recent_demand & (
        (analysis["الكمية"] <= 0) | (cover <= lead_days)
    )
    high = has_recent_demand & ~critical & (
        (analysis["الكمية"] <= analysis["حد إعادة الطلب"])
        | (cover <= lead_days + safety_days)
    )
    watch = has_recent_demand & ~critical & ~high & (
        (analysis["اتجاه الطلب"] == "صاعد")
        & (cover <= target_days)
    )
    analysis["أولوية الطلب"] = "لا يحتاج"
    analysis.loc[watch, "أولوية الطلب"] = "مراقبة"
    analysis.loc[high, "أولوية الطلب"] = "عالية"
    analysis.loc[critical, "أولوية الطلب"] = "حرجة"
    analysis["حالة الطلب"] = "لا يحتاج"
    reorder_mask = critical | high | watch
    analysis.loc[reorder_mask, "حالة الطلب"] = "إعادة طلب"

    def decision_reason(row):
        if row["أولوية الطلب"] == "لا يحتاج":
            if row[recent_column] <= 0:
                return "لا يوجد طلب حديث؛ راجع التصريف بدلاً من الشراء"
            return "الرصيد يغطي مدة التوريد والأمان والمراجعة"
        cover_text = (
            f"تغطية {row['تغطية المخزون بالأيام']:.0f} يوم"
            if pd.notna(row["تغطية المخزون بالأيام"])
            else "لا توجد تغطية"
        )
        purchase_text = (
            f"آخر توريد منذ {int(row['أيام منذ آخر شراء/توريد'])} يوم"
            if pd.notna(row["أيام منذ آخر شراء/توريد"])
            else "لا يوجد شراء/توريد مطابق للمرجع المحدد"
        )
        return f"{cover_text}؛ الطلب {row['اتجاه الطلب']}؛ {purchase_text}"

    analysis["سبب القرار"] = analysis.apply(decision_reason, axis=1)

    clearance_mask = (
        (analysis["الكمية"] > 0)
        & (
            analysis["آخر إخراج"].isna()
            | (analysis["أيام منذ آخر خروج"] >= slow_days)
            | (analysis["سرعة الحركة"] == "بطيئة")
        )
    )
    analysis["اقتراح التصريف"] = ""
    analysis.loc[clearance_mask, "اقتراح التصريف"] = "مرشح للتصريف"
    analysis["فترة التحليل"] = f"آخر {demand_window_days} يوم"
    priority_order = {"حرجة": 0, "عالية": 1, "مراقبة": 2, "لا يحتاج": 3}
    analysis["ترتيب الأولوية"] = analysis["أولوية الطلب"].map(priority_order)
    return analysis.sort_values(
        ["ترتيب الأولوية", "كمية الطلب المقترحة"], ascending=[True, False]
    ).drop(columns=["ترتيب الأولوية"]).reset_index(drop=True)


def stock_item_key(row):
    persisted_key = str(row.get("مفتاح المخزون", "") or "").strip()
    if persisted_key:
        return persisted_key
    code = normalize_item_code(row.get("رمز المادة", ""))
    return f"CODE:{code}" if code else f"NAME:{normalize_item_name(row.get('اسم المادة', ''))}"


def ensure_unique_stock_keys(stock_df):
    if "مفتاح المطابقة" not in stock_df.columns:
        stock_df["مفتاح المطابقة"] = stock_df["اسم المادة"].map(normalize_item_name)
    existing = stock_df.get("مفتاح المخزون")
    if existing is not None and existing.notna().all() and existing.is_unique:
        return stock_df
    base_keys = stock_df.apply(
        lambda row: (
            f"CODE:{normalize_item_code(row.get('رمز المادة', ''))}"
            if normalize_item_code(row.get("رمز المادة", ""))
            else f"NAME:{normalize_item_name(row.get('اسم المادة', ''))}"
        ),
        axis=1,
    )
    duplicate_number = base_keys.groupby(base_keys).cumcount()
    stock_df["مفتاح المخزون"] = [
        base_key if number == 0 else f"{base_key}#{number + 1}"
        for base_key, number in zip(base_keys, duplicate_number)
    ]
    return stock_df


def save_stock_state(stock_df):
    """Persist the complete current stock snapshot atomically."""
    ensure_unique_stock_keys(stock_df)
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for _, row in stock_df.iterrows():
        rows.append((
            stock_item_key(row),
            normalize_item_code(row.get("رمز المادة", "")),
            str(row.get("اسم المادة", "") or ""),
            float(row.get("الكمية", 0) or 0),
            str(row.get("مفتاح المطابقة", "") or normalize_item_name(row.get("اسم المادة", ""))),
            now_text,
        ))
    with database_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM stock_state")
        connection.executemany(
            """INSERT INTO stock_state
               (item_key, item_code, item_name, quantity, match_key, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        connection.execute(
            "INSERT OR REPLACE INTO app_metadata(meta_key, meta_value) VALUES (?, ?)",
            ("stock_saved_at", now_text),
        )


def load_stock_state():
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT item_key, item_code, item_name, quantity, match_key FROM stock_state ORDER BY item_name"
        ).fetchall()
    if not rows:
        return None
    return pd.DataFrame([
        {
            "رمز المادة": row["item_code"],
            "اسم المادة": row["item_name"],
            "الكمية": row["quantity"],
            "مفتاح المطابقة": row["match_key"],
            "مفتاح المخزون": row["item_key"],
        }
        for row in rows
    ])


def save_imported_movement_history(movement_df):
    rows = [(
        str(row.get("رمز المادة", "") or ""),
        str(row.get("اسم المادة", "") or ""),
        pd.Timestamp(row["التاريخ"]).strftime("%Y-%m-%d %H:%M:%S"),
        str(row.get("المرجع", "") or ""),
        str(row.get("الزبون", "") or ""),
        float(row.get("إدخال", 0) or 0),
        float(row.get("إخراج", 0) or 0),
        None if pd.isna(row.get("الرصيد")) else float(row.get("الرصيد")),
        str(row.get("المستخدم", "") or ""),
        str(row.get("بيان", "") or ""),
        str(row.get("مفتاح المطابقة", "") or ""),
    ) for _, row in movement_df.iterrows()]
    with database_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM imported_movement_history")
        connection.executemany(
            """INSERT INTO imported_movement_history
               (item_code, item_name, movement_date, reference, customer,
                qty_in, qty_out, balance, username, statement, match_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )


def load_imported_movement_history():
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM imported_movement_history ORDER BY movement_date"
        ).fetchall()
    if not rows:
        return None
    return pd.DataFrame([{
        "رمز المادة": row["item_code"],
        "اسم المادة": row["item_name"],
        "التاريخ": pd.to_datetime(row["movement_date"]),
        "المرجع": row["reference"],
        "الزبون": row["customer"],
        "إدخال": row["qty_in"],
        "إخراج": row["qty_out"],
        "الرصيد": row["balance"],
        "المستخدم": row["username"],
        "بيان": row["statement"],
        "مفتاح المطابقة": row["match_key"],
    } for row in rows])


def verify_operation_password(password):
    expected = st.session_state['user_db'][current_user]["password"]
    return bool(password) and password == expected


def load_manual_movements():
    with database_connection() as connection:
        rows = connection.execute(
            """SELECT * FROM movement_ledger
               WHERE source = 'MANUAL' ORDER BY created_at DESC"""
        ).fetchall()
    return [{
        "التاريخ": row["created_at"],
        "المستخدم": row["username"],
        "نوع الحركة": row["movement_type"],
        "رمز المادة": row["item_code"],
        "اسم المادة": row["item_name"],
        "الكمية": row["quantity"],
        "الكمية قبل الحركة": row["quantity_before"],
        "الكمية بعد الحركة": row["quantity_after"],
        "رقم الفاتورة / المرجع": row["invoice_reference"],
        "بدون فاتورة": "نعم" if row["without_invoice"] else "لا",
        "وصل تسليم": "نعم" if row["delivery_note"] else "لا",
        "السبب": row["reason"],
    } for row in rows]


def movement_exists(operation_fingerprint):
    with database_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM movement_ledger WHERE operation_fingerprint = ? LIMIT 1",
            (operation_fingerprint,),
        ).fetchone()
    return row is not None


def post_stock_operation(stock_df, changes, operation_meta, invoice_payload=None):
    """Commit ledger rows and stock balances together; duplicate requests are rejected."""
    operation_id = operation_meta.get("operation_id") or str(uuid.uuid4())
    fingerprint = operation_meta["fingerprint"]
    if movement_exists(fingerprint):
        raise ValueError("تم تنفيذ هذه العملية سابقاً؛ تم منع التكرار.")

    working_stock = stock_df.copy()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ledger_rows = []
    for line_number, change in enumerate(changes, start=1):
        row_index = int(change["row_index"])
        movement_type = change["movement_type"]
        quantity = float(change["quantity"])
        before_qty = float(working_stock.at[row_index, "الكمية"])
        after_qty = before_qty + quantity if movement_type == "IN" else before_qty - quantity
        if quantity <= 0:
            raise ValueError("يجب أن تكون جميع الكميات أكبر من صفر.")
        if movement_type == "OUT" and after_qty < 0:
            raise ValueError(
                f"رصيد {working_stock.at[row_index, 'اسم المادة']} غير كافٍ."
            )
        working_stock.at[row_index, "الكمية"] = after_qty
        item_row = working_stock.loc[row_index]
        item_key = stock_item_key(item_row)
        ledger_rows.append((
            str(uuid.uuid4()), operation_id, fingerprint,
            created_at, created_at[:10], operation_meta["username"],
            operation_meta["source"], movement_type, item_key,
            normalize_item_code(item_row.get("رمز المادة", "")),
            str(item_row.get("اسم المادة", "")), quantity,
            before_qty, after_qty,
            str(operation_meta.get("invoice_reference", "") or ""),
            int(bool(operation_meta.get("without_invoice"))),
            int(bool(operation_meta.get("delivery_note"))),
            str(operation_meta.get("reason", "") or ""),
        ))

    with database_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM movement_ledger WHERE operation_fingerprint = ? LIMIT 1",
            (fingerprint,),
        ).fetchone():
            raise ValueError("تم تنفيذ هذه العملية سابقاً؛ تم منع التكرار.")
        connection.executemany(
            """INSERT INTO movement_ledger
               (movement_id, operation_id, operation_fingerprint, created_at,
                business_date, username, source, movement_type, item_key,
                item_code, item_name, quantity, quantity_before, quantity_after,
                invoice_reference, without_invoice, delivery_note, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ledger_rows,
        )
        for change in changes:
            saved_row = working_stock.loc[int(change["row_index"])]
            connection.execute(
                """INSERT INTO stock_state
                   (item_key, item_code, item_name, quantity, match_key, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(item_key) DO UPDATE SET
                     item_code = excluded.item_code,
                     item_name = excluded.item_name,
                     quantity = excluded.quantity,
                     match_key = excluded.match_key,
                     updated_at = excluded.updated_at""",
                (
                    stock_item_key(saved_row),
                    normalize_item_code(saved_row.get("رمز المادة", "")),
                    str(saved_row.get("اسم المادة", "")),
                    float(saved_row.get("الكمية", 0)),
                    str(saved_row.get("مفتاح المطابقة", "")),
                    created_at,
                ),
            )
        if invoice_payload is not None:
            connection.execute(
                """INSERT INTO posted_invoices
                   (invoice_reference, image_hash, operation_id, posted_at,
                    username, recognized_json) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    operation_meta["invoice_reference"],
                    invoice_payload["image_hash"], operation_id, created_at,
                    operation_meta["username"],
                    json.dumps(invoice_payload, ensure_ascii=False),
                ),
            )
    return working_stock, ledger_rows


def invoice_already_posted(invoice_reference, image_hash):
    with database_connection() as connection:
        row = connection.execute(
            """SELECT invoice_reference FROM posted_invoices
               WHERE invoice_reference = ? OR image_hash = ? LIMIT 1""",
            (invoice_reference, image_hash),
        ).fetchone()
    return row["invoice_reference"] if row else None


def ledger_for_date(report_date):
    date_text = report_date.strftime("%Y-%m-%d")
    with database_connection() as connection:
        rows = connection.execute(
            """SELECT * FROM movement_ledger
               WHERE business_date = ? ORDER BY created_at, movement_id""",
            (date_text,),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def ledger_as_movement_history():
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM movement_ledger ORDER BY created_at"
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "رمز المادة": row["item_code"],
        "اسم المادة": row["item_name"],
        "التاريخ": pd.to_datetime(row["created_at"]),
        "المرجع": row["invoice_reference"],
        "الزبون": "",
        "إدخال": row["quantity"] if row["movement_type"] == "IN" else 0,
        "إخراج": row["quantity"] if row["movement_type"] == "OUT" else 0,
        "الرصيد": row["quantity_after"],
        "المستخدم": row["username"],
        "بيان": row["reason"],
        "مفتاح المطابقة": normalize_item_name(row["item_name"]),
    } for row in rows])


def close_business_day(report_date, username, stock_df):
    ledger = ledger_for_date(report_date)
    total_in = float(ledger.loc[ledger["movement_type"] == "IN", "quantity"].sum()) if not ledger.empty else 0
    total_out = float(ledger.loc[ledger["movement_type"] == "OUT", "quantity"].sum()) if not ledger.empty else 0
    no_invoice_count = int(ledger["without_invoice"].sum()) if not ledger.empty else 0
    with database_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT OR REPLACE INTO daily_closures
               (business_date, closed_at, username, movement_count,
                total_in, total_out, no_invoice_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                report_date.strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                username, len(ledger), total_in, total_out, no_invoice_count,
            ),
        )
        date_text = report_date.strftime("%Y-%m-%d")
        connection.execute(
            "DELETE FROM daily_stock_snapshots WHERE business_date = ?",
            (date_text,),
        )
        connection.executemany(
            """INSERT INTO daily_stock_snapshots
               (business_date, item_key, item_code, item_name, quantity, match_key)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(
                date_text,
                stock_item_key(row),
                normalize_item_code(row.get("رمز المادة", "")),
                str(row.get("اسم المادة", "")),
                float(row.get("الكمية", 0)),
                str(row.get("مفتاح المطابقة", "")),
            ) for _, row in stock_df.iterrows()],
        )
    return ledger


def load_daily_stock_snapshot(report_date):
    with database_connection() as connection:
        rows = connection.execute(
            """SELECT * FROM daily_stock_snapshots
               WHERE business_date = ? ORDER BY item_name""",
            (report_date.strftime("%Y-%m-%d"),),
        ).fetchall()
    if not rows:
        return None
    return pd.DataFrame([{
        "رمز المادة": row["item_code"],
        "اسم المادة": row["item_name"],
        "الكمية": row["quantity"],
        "مفتاح المطابقة": row["match_key"],
        "مفتاح المخزون": row["item_key"],
    } for row in rows])


def daily_closure_for_date(report_date):
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM daily_closures WHERE business_date = ?",
            (report_date.strftime("%Y-%m-%d"),),
        ).fetchone()
    return dict(row) if row else None


def build_end_of_day_report(report_date, stock_df, analysis_df):
    ledger = ledger_for_date(report_date)
    total_in = float(ledger.loc[ledger["movement_type"] == "IN", "quantity"].sum()) if not ledger.empty else 0
    total_out = float(ledger.loc[ledger["movement_type"] == "OUT", "quantity"].sum()) if not ledger.empty else 0
    no_invoice_count = int(ledger["without_invoice"].sum()) if not ledger.empty else 0
    affected = pd.DataFrame()
    if not ledger.empty:
        affected = ledger.groupby(
            ["item_key", "item_code", "item_name"], as_index=False
        ).agg(
            **{
                "الرصيد الافتتاحي": ("quantity_before", "first"),
                "إجمالي الإدخال": (
                    "quantity",
                    lambda values: float(values[ledger.loc[values.index, "movement_type"] == "IN"].sum()),
                ),
                "إجمالي الإخراج": (
                    "quantity",
                    lambda values: float(values[ledger.loc[values.index, "movement_type"] == "OUT"].sum()),
                ),
                "الرصيد الختامي": ("quantity_after", "last"),
            }
        ).rename(columns={
            "item_code": "رمز المادة",
            "item_name": "اسم المادة",
        })

    summary = pd.DataFrame([
        {"البيان": "تاريخ التقرير", "القيمة": report_date.strftime("%Y-%m-%d")},
        {"البيان": "عدد الحركات", "القيمة": len(ledger)},
        {"البيان": "إجمالي الإدخال", "القيمة": total_in},
        {"البيان": "إجمالي الإخراج", "القيمة": total_out},
        {"البيان": "حركات بدون فاتورة", "القيمة": no_invoice_count},
        {"البيان": "وقت إنشاء التقرير", "القيمة": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, index=False, sheet_name="Daily_Summary")
        ledger.to_excel(writer, index=False, sheet_name="Daily_Movements")
        affected.drop(columns=["item_key"], errors="ignore").to_excel(
            writer, index=False, sheet_name="Affected_Items"
        )
        stock_df.drop(
            columns=["مفتاح المطابقة", "مفتاح المخزون"], errors="ignore"
        ).to_excel(
            writer, index=False, sheet_name="Closing_Stock"
        )
        if not ledger.empty:
            ledger[ledger["without_invoice"] == 1].to_excel(
                writer, index=False, sheet_name="No_Invoice_Alerts"
            )
        if analysis_df is not None and not analysis_df.empty:
            clean_analysis = analysis_df.drop(
                columns=["مفتاح المطابقة", "رمز الحركة", "اسم الحركة"],
                errors="ignore",
            )
            clean_analysis[clean_analysis["حالة الطلب"] == "إعادة طلب"].to_excel(
                writer, index=False, sheet_name="Reorder_List"
            )
            clean_analysis[
                clean_analysis["اقتراح التصريف"] == "مرشح للتصريف"
            ].to_excel(writer, index=False, sheet_name="Slow_Clearance")
    return output.getvalue(), ledger, affected


# Restore the last committed state automatically after app/server reruns.
if st.session_state['live_stock'] is None:
    st.session_state['live_stock'] = load_stock_state()
if st.session_state['movement_history'] is None:
    st.session_state['movement_history'] = load_imported_movement_history()
st.session_state['manual_movements'] = load_manual_movements()

if st.session_state['live_stock'] is not None:
    today_ledger = ledger_for_date(datetime.now().date())
    total_items = len(st.session_state['live_stock'])
    positive_items = int((st.session_state['live_stock']['الكمية'] > 0).sum())
    today_operations = len(today_ledger)
    today_no_invoice = int(today_ledger['without_invoice'].sum()) if not today_ledger.empty else 0
    dash1, dash2, dash3, dash4 = st.columns(4)
    dash1.metric("إجمالي المواد", f"{total_items:,}")
    dash2.metric("مواد برصيد موجب", f"{positive_items:,}")
    dash3.metric("حركات اليوم", f"{today_operations:,}")
    dash4.metric("تنبيهات بلا فاتورة", f"{today_no_invoice:,}")

setup_tab, invoice_tab, manual_tab, analysis_tab, reports_tab = st.tabs([
    "⚙️ الإعداد والبيانات",
    "🧾 قراءة الفواتير",
    "↔️ حركة يدوية",
    "📊 التحليل والطلب",
    "🌙 تقارير نهاية اليوم",
])
setup_tab.__enter__()

# ==========================================
# HELPER: SEARCHABLE TABLE
# ==========================================
def display_searchable_table(df, key_prefix):
    search_query = st.text_input("🔍 بحث في المخزون (بررمز المادة أو اسم المادة):", key=f"search_{key_prefix}")
    
    if search_query:
        mask = df['رمز المادة'].astype(str).str.contains(search_query, case=False, na=False) | \
               df['اسم المادة'].astype(str).str.contains(search_query, case=False, na=False)
        display_df = df[mask].drop(
            columns=['مفتاح المطابقة', 'مفتاح المخزون'], errors='ignore'
        )
        st.markdown(display_df.to_html(index=False), unsafe_allow_html=True)
    else:
        st.info("أدخل مصطلح بحث أعلاه لعرض المواد (تم إخفاء القائمة الكاملة لتوفير المساحة وتناسب الشاشات).")

# ==========================================
# 1. CONTROLS SECTION
# ==========================================
st.subheader("لوحة التحكم")

# Session State Backup & Restore
with st.expander("💾 حفظ أو استعادة حالة العمل (لتجنب فقدان البيانات عند الخروج)"):
    col_save, col_load = st.columns(2)
    with col_save:
        if st.session_state['live_stock'] is not None:
            state_data = {
                "live_stock": st.session_state['live_stock'].to_json(orient='split'),
                "processed_invoices": {k: v.to_json(orient='split') for k, v in st.session_state['processed_invoices'].items()},
                "invoice_raw_data": st.session_state['invoice_raw_data'],
                "file_to_invoice": st.session_state['file_to_invoice'],
                "movement_history": (
                    st.session_state['movement_history'].to_json(
                        orient='split', date_format='iso'
                    ) if st.session_state['movement_history'] is not None else None
                ),
                "manual_movements": st.session_state['manual_movements']
            }
            json_bytes = json.dumps(state_data, ensure_ascii=False).encode('utf-8')
            st.download_button(
                label="📥 تنزيل ملف حفظ الحالة الحالية",
                data=json_bytes,
                file_name="golden_palace_session_backup.json",
                mime="application/json",
                use_container_width=True
            )
        else:
            st.info("لا يوجد مخزون مفعل لحفظه حالياً.")
            
    with col_load:
        uploaded_backup = st.file_uploader("📤 استعادة ملف حفظ سابق (.json)", type=["json"])
        if uploaded_backup is not None:
            try:
                loaded_state = json.load(uploaded_backup)
                st.session_state['live_stock'] = pd.read_json(loaded_state['live_stock'], orient='split')
                st.session_state['processed_invoices'] = {k: pd.read_json(v, orient='split') for k, v in loaded_state['processed_invoices'].items()}
                st.session_state['invoice_raw_data'] = loaded_state['invoice_raw_data']
                st.session_state['file_to_invoice'] = loaded_state['file_to_invoice']
                movement_json = loaded_state.get('movement_history')
                st.session_state['movement_history'] = (
                    pd.read_json(io.StringIO(movement_json), orient='split')
                    if movement_json else None
                )
                if st.session_state['movement_history'] is not None:
                    st.session_state['movement_history']['التاريخ'] = pd.to_datetime(
                        st.session_state['movement_history']['التاريخ'], errors='coerce'
                    )
                save_stock_state(st.session_state['live_stock'])
                if st.session_state['movement_history'] is not None:
                    save_imported_movement_history(
                        st.session_state['movement_history']
                    )
                st.session_state['manual_movements'] = load_manual_movements()
                st.success("✅ تمت استعادة الحالة وحفظها تلقائياً!")
                st.rerun()
            except Exception as e:
                st.error("ملف التخزين غير صالح.")

col1, col3 = st.columns(2)

with col1:
    if is_admin:
        uploaded_stock_report = st.file_uploader("📊 1. رفع تقرير المخزون الأساسي (بداية اليوم)", type=["xlsx", "xls"])
        if uploaded_stock_report is not None:
            try:
                df = read_stock_report(uploaded_stock_report.getvalue())
                if st.session_state['movement_history'] is not None:
                    df = enrich_stock_codes(df, st.session_state['movement_history'])
                if st.session_state['live_stock'] is None:
                    st.session_state['live_stock'] = df
                    save_stock_state(df)
                    st.success("✅ تم تحميل المخزون الأساسي وحفظه تلقائياً.")
                    st.rerun()
                else:
                    st.warning(
                        "يوجد رصيد محفوظ. اعتماد الملف سيستبدل الرصيد الحالي كنقطة بداية جديدة."
                    )
                    replace_stock_password = st.text_input(
                        "كلمة المرور لاعتماد رصيد بداية جديد",
                        type="password",
                        key="replace_stock_password",
                    )
                    if st.button(
                        "اعتماد ملف الجرد كبداية جديدة",
                        use_container_width=True,
                        key="replace_stock_button",
                    ):
                        if not verify_operation_password(replace_stock_password):
                            st.error("كلمة المرور غير صحيحة؛ لم يتم استبدال الرصيد.")
                        else:
                            st.session_state['live_stock'] = df
                            save_stock_state(df)
                            st.success("تم حفظ رصيد البداية الجديد.")
                            st.rerun()
            except Exception as e:
                st.error(f"خطأ في قراءة ملف المخزون: {e}")
    else:
        st.info("🔒 📊 رفع تقرير المخزون الأساسي مقتصر على مدير النظام (Admin).")

with col3:
    uploaded_movement_report = st.file_uploader(
        "📈 2. رفع تقرير حركة المادة للتحليل",
        type=["xlsx", "xls"],
        help="يستخدم للتحليل والتصنيف فقط؛ لا تُخصم حركاته القديمة من رصيد الجرد الحالي.",
    )
    if uploaded_movement_report is not None:
        try:
            movement_bytes = uploaded_movement_report.getvalue()
            movement_hash = hashlib.sha256(movement_bytes).hexdigest()
            if st.session_state['movement_file_hash'] != movement_hash:
                movement_df = read_movement_report(movement_bytes)
                st.session_state['movement_history'] = movement_df
                if st.session_state['live_stock'] is not None:
                    st.session_state['live_stock'] = enrich_stock_codes(
                        st.session_state['live_stock'], movement_df
                    )
                    save_stock_state(st.session_state['live_stock'])
                save_imported_movement_history(movement_df)
                st.session_state['movement_file_hash'] = movement_hash
                st.success(
                    f"✅ تم تحميل وحفظ {len(movement_df):,} حركة مخزون للتحليل."
                )
            else:
                st.caption("تقرير الحركة محفوظ ومحدّث.")
        except Exception as movement_error:
            st.error(f"تعذر قراءة تقرير الحركة: {movement_error}")

setup_tab.__exit__(None, None, None)
invoice_tab.__enter__()
st.subheader("🧾 قراءة الفاتورة ومراجعتها")
st.caption("ارفع الصورة، راجع النتيجة، ثم أدخل كلمة المرور لاعتماد الحركة.")
uploaded_invoices = st.file_uploader(
    "رفع صور الفواتير",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

# STRICT OPTIONAL CAMERA: Fully off until checked
camera_image = None
enable_camera = st.checkbox("📸 تفعيل الكاميرا لالتقاط صورة الفاتورة مباشرة")
if enable_camera:
    camera_image = st.camera_input("وجه الكاميرا نحو الفاتورة ثم اضغط التقاط")

# Combine uploaded files and optional camera capture
active_invoices_list = []
if uploaded_invoices:
    active_invoices_list.extend(uploaded_invoices)
if camera_image:
    active_invoices_list.append(camera_image)

# ==========================================
# REAL INVOICE REVIEW & PASSWORD-AUTHORIZED POSTING
# ==========================================
invoice_flash = st.session_state.pop("invoice_flash", None)
if invoice_flash:
    st.success(invoice_flash)

if active_invoices_list:
    if not OPENAI_API_KEY:
        st.error(
            "قراءة الفاتورة الحقيقية غير مفعلة. أضف مفتاح OpenAI في Secrets؛ "
            "لن يغيّر التطبيق المخزون اعتماداً على بيانات تجريبية."
        )
    if st.button(
        "🔎 قراءة صور الفواتير",
        type="primary",
        use_container_width=True,
        disabled=not OPENAI_API_KEY,
    ):
        for invoice_file in active_invoices_list:
            image_hash = hashlib.sha256(invoice_file.getvalue()).hexdigest()
            if image_hash in st.session_state['recognized_invoices']:
                continue
            with st.spinner(f"جاري قراءة {invoice_file.name}..."):
                try:
                    st.session_state['recognized_invoices'][image_hash] = (
                        extract_invoice_data(invoice_file)
                    )
                except Exception as recognition_error:
                    st.error(f"{invoice_file.name}: {recognition_error}")

for image_hash, recognized in list(st.session_state['recognized_invoices'].items()):
    invoice_label = recognized.get("invoice_number") or "فاتورة بلا رقم"
    with st.expander(f"🧾 مراجعة {invoice_label}", expanded=True):
        confidence = float(recognized.get("confidence", 0) or 0)
        if confidence < 0.85:
            st.warning(
                f"دقة القراءة المعلنة {confidence:.0%}. راجع كل سطر قبل الاعتماد."
            )
        for warning in recognized.get("warnings", []):
            st.warning(str(warning))

        raw_items = pd.DataFrame(recognized.get("items", []))
        if raw_items.empty:
            st.error("لم يتم التعرف على أي مادة في هذه الصورة.")
            continue
        review_items = raw_items.rename(columns={
            "item_code": "رمز المادة",
            "item_name": "اسم المادة",
            "quantity": "الكمية",
        })[["رمز المادة", "اسم المادة", "الكمية"]]

        with st.form(f"invoice_review_{image_hash}"):
            review_col1, review_col2 = st.columns([1.25, 0.75])
            with review_col1:
                invoice_reference = st.text_input(
                    "رقم الفاتورة",
                    value=str(recognized.get("invoice_number", "")),
                    key=f"invoice_number_{image_hash}",
                )
            with review_col2:
                movement_type = st.selectbox(
                    "تأثير الفاتورة",
                    options=["OUT", "IN"],
                    index=0 if recognized.get("movement_type") == "OUT" else 1,
                    format_func=lambda value: "إخراج / بيع" if value == "OUT" else "إدخال / شراء أو مرتجع",
                    key=f"invoice_type_{image_hash}",
                )
            edited_items = st.data_editor(
                review_items,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key=f"invoice_items_{image_hash}",
            )
            invoice_password = st.text_input(
                "كلمة مرور المستخدم لاعتماد هذه العملية",
                type="password",
                key=f"invoice_password_{image_hash}",
            )
            post_invoice = st.form_submit_button(
                "اعتماد الفاتورة وتحديث المخزون",
                type="primary",
                use_container_width=True,
            )

            if post_invoice:
                try:
                    if st.session_state['live_stock'] is None:
                        raise ValueError("حمّل تقرير المخزون قبل اعتماد الفاتورة.")
                    if not verify_operation_password(invoice_password):
                        raise ValueError("كلمة المرور غير صحيحة؛ لم تُنفذ العملية.")
                    invoice_reference = str(invoice_reference).strip()
                    if not invoice_reference:
                        raise ValueError("رقم الفاتورة مطلوب.")
                    previous_invoice = invoice_already_posted(invoice_reference, image_hash)
                    if previous_invoice:
                        raise ValueError(
                            f"الفاتورة/الصورة منفذة سابقاً تحت المرجع {previous_invoice}."
                        )

                    stock_df = st.session_state['live_stock']
                    changes = []
                    unmatched = []
                    for _, item in edited_items.iterrows():
                        code = normalize_item_code(item.get("رمز المادة", ""))
                        name_key = normalize_item_name(item.get("اسم المادة", ""))
                        quantity = pd.to_numeric(item.get("الكمية"), errors="coerce")
                        code_match = stock_df[
                            stock_df["رمز المادة"].map(normalize_item_code) == code
                        ] if code else pd.DataFrame()
                        name_match = stock_df[
                            stock_df["مفتاح المطابقة"] == name_key
                        ] if name_key else pd.DataFrame()
                        match = code_match if not code_match.empty else name_match
                        if match.empty or len(match) > 1 or pd.isna(quantity):
                            unmatched.append(f"{code} {item.get('اسم المادة', '')}".strip())
                            continue
                        changes.append({
                            "row_index": int(match.index[0]),
                            "movement_type": movement_type,
                            "quantity": float(quantity),
                        })
                    if unmatched:
                        raise ValueError(
                            "مواد غير مطابقة بشكل آمن: " + "، ".join(unmatched[:8])
                        )
                    if not changes:
                        raise ValueError("لا توجد مواد صالحة للاعتماد.")

                    grouped_changes = {}
                    for change in changes:
                        group_key = (change["row_index"], change["movement_type"])
                        grouped_changes[group_key] = (
                            grouped_changes.get(group_key, 0) + change["quantity"]
                        )
                    changes = [
                        {
                            "row_index": row_index,
                            "movement_type": line_type,
                            "quantity": quantity,
                        }
                        for (row_index, line_type), quantity in grouped_changes.items()
                    ]

                    normalized_lines = sorted(
                        (change["row_index"], change["movement_type"], change["quantity"])
                        for change in changes
                    )
                    fingerprint = hashlib.sha256(
                        json.dumps(
                            [image_hash, invoice_reference, normalized_lines],
                            ensure_ascii=False,
                        ).encode("utf-8")
                    ).hexdigest()
                    approved_payload = dict(recognized)
                    approved_payload["reviewed_items"] = edited_items.to_dict("records")
                    updated_stock, _ = post_stock_operation(
                        stock_df,
                        changes,
                        {
                            "fingerprint": fingerprint,
                            "username": current_user,
                            "source": "INVOICE",
                            "invoice_reference": invoice_reference,
                            "without_invoice": False,
                            "delivery_note": True,
                            "reason": "فاتورة معترف عليها من الصورة ومراجعة من المستخدم",
                        },
                        invoice_payload=approved_payload,
                    )
                    st.session_state['live_stock'] = updated_stock
                    del st.session_state['recognized_invoices'][image_hash]
                    st.session_state["invoice_flash"] = (
                        f"تم حفظ الفاتورة {invoice_reference} وتحديث {len(changes)} مادة."
                    )
                    st.rerun()
                except Exception as posting_error:
                    st.error(str(posting_error))

# ==========================================
# 3. MOVEMENT ANALYSIS, REORDER & CLEARANCE
# ==========================================
invoice_tab.__exit__(None, None, None)
analysis_tab.__enter__()
inventory_analysis = pd.DataFrame()
analysis_movement_df = st.session_state['movement_history']
ledger_history = ledger_as_movement_history()
if not ledger_history.empty:
    analysis_movement_df = (
        pd.concat([analysis_movement_df, ledger_history], ignore_index=True)
        if analysis_movement_df is not None
        else ledger_history
    )

if st.session_state['live_stock'] is not None and analysis_movement_df is not None:
    st.divider()
    st.subheader("📊 تحليل حركة المخزون وإعادة الطلب")
    with st.expander("⚙️ إعدادات قرار إعادة الطلب والتصريف", expanded=False):
        setting_col1, setting_col2, setting_col3 = st.columns(3)
        with setting_col1:
            lead_days = st.number_input(
                "مدة التوريد بالأيام", min_value=1, value=30, step=1
            )
        with setting_col2:
            safety_days = st.number_input(
                "مخزون الأمان بالأيام", min_value=0, value=15, step=1
            )
        with setting_col3:
            slow_days = st.number_input(
                "يُعد بطيئاً بعد عدم خروج لمدة", min_value=30, value=90, step=15
            )
        setting_col4, setting_col5 = st.columns(2)
        with setting_col4:
            demand_window_days = st.number_input(
                "فترة قياس الطلب الحديث (يوم)",
                min_value=30,
                value=90,
                step=30,
            )
        with setting_col5:
            review_days = st.number_input(
                "الفترة حتى مراجعة الطلب القادمة (يوم)",
                min_value=7,
                value=30,
                step=7,
            )
        purchase_prefix_text = st.text_input(
            "مراجع حركات الشراء/التوريد",
            value="إد.م. م. م.",
            help=(
                "افصل أكثر من بداية مرجع بفاصلة. لا تُحسب أرصدة البداية أو "
                "تسويات الجرد أو المرتجعات كشراء إلا إذا أضفت مرجعها هنا."
            ),
        )
        purchase_prefixes = [
            part.strip()
            for part in purchase_prefix_text.replace("،", ",").split(",")
            if part.strip()
        ]
        st.caption(
            "القرار يجمع الرصيد الحالي، الطلب الحديث، تغطية المخزون، اتجاه الطلب، "
            "وموعد آخر شراء/توريد مطابق للمراجع أعلاه."
        )

    inventory_analysis = build_inventory_analysis(
        st.session_state['live_stock'],
        analysis_movement_df,
        int(lead_days),
        int(safety_days),
        int(slow_days),
        int(demand_window_days),
        int(review_days),
        purchase_prefixes,
    )
    reorder_df = inventory_analysis[
        inventory_analysis["حالة الطلب"] == "إعادة طلب"
    ].copy()
    fast_df = inventory_analysis[
        inventory_analysis["سرعة الحركة"] == "سريعة"
    ].copy()
    slow_df = inventory_analysis[
        inventory_analysis["اقتراح التصريف"] == "مرشح للتصريف"
    ].copy()
    no_invoice_df = pd.DataFrame([
        row for row in st.session_state['manual_movements']
        if row.get("بدون فاتورة") == "نعم"
    ])

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("مواد تحتاج إعادة طلب", f"{len(reorder_df):,}")
    kpi2.metric("مواد سريعة الحركة", f"{len(fast_df):,}")
    kpi3.metric("مواد مرشحة للتصريف", f"{len(slow_df):,}")
    kpi4.metric("حركات يدوية بدون فاتورة", f"{len(no_invoice_df):,}")

    reorder_tab, fast_tab, slow_tab, control_tab = st.tabs([
        "🛒 إعادة الطلب",
        "⚡ سريعة الحركة",
        "🐢 بطيئة / للتصريف",
        "🚨 رقابة الحركات اليدوية",
    ])
    with reorder_tab:
        st.dataframe(
            reorder_df[[
                "أولوية الطلب", "رمز المادة", "اسم المادة", "الكمية",
                f"خروج آخر {int(demand_window_days)} يوم",
                "الخروج اليومي الحديث", "تغطية المخزون بالأيام", "اتجاه الطلب",
                "آخر شراء/توريد", "كمية آخر شراء/توريد",
                "أيام منذ آخر شراء/توريد", "متوسط فترة التوريد",
                "حد إعادة الطلب", "كمية الطلب المقترحة", "سبب القرار",
            ]],
            use_container_width=True,
            hide_index=True,
        )
    with fast_tab:
        st.dataframe(
            fast_df[[
                "رمز المادة", "اسم المادة", "الكمية", "إجمالي الإخراج",
                "عدد الحركات", "آخر إخراج", "حالة الطلب",
            ]],
            use_container_width=True,
            hide_index=True,
        )
    with slow_tab:
        st.warning("هذه القائمة للمراجعة التجارية قبل الخصم أو التصفية، وليست أمراً آلياً.")
        st.dataframe(
            slow_df[[
                "رمز المادة", "اسم المادة", "الكمية", "إجمالي الإخراج",
                "أيام منذ آخر خروج", "سرعة الحركة", "اقتراح التصريف",
            ]],
            use_container_width=True,
            hide_index=True,
        )
    with control_tab:
        if no_invoice_df.empty:
            st.success("لا توجد حركات يدوية مسجلة بدون فاتورة / مرجع.")
        else:
            st.error(
                f"تنبيه رقابي: توجد {len(no_invoice_df)} حركة يدوية بدون فاتورة / مرجع."
            )
            st.dataframe(no_invoice_df, use_container_width=True, hide_index=True)

# ==========================================
# 4. MANUAL IN / OUT STOCK MOVEMENTS
# ==========================================
analysis_tab.__exit__(None, None, None)
manual_tab.__enter__()
st.divider()
st.subheader("📝 حركة المخزون اليدوية (إدخال / إخراج)")
flash = st.session_state.pop('manual_movement_flash', None)
if flash:
    if flash.get("without_invoice"):
        st.warning(flash["message"])
    else:
        st.success(flash["message"])

if st.session_state['live_stock'] is None:
    st.info("حمّل تقرير المخزون أولاً لتسجيل حركة يدوية.")
else:
    live_stock_for_form = st.session_state['live_stock']

    def manual_item_label(row_index):
        row = live_stock_for_form.loc[row_index]
        code = str(row.get('رمز المادة', '') or '').strip()
        name = str(row.get('اسم المادة', '') or '').strip()
        return f"{code} — {name}" if code else name

    with st.form("manual_movement_form"):
        m_col1, m_col2, m_col3 = st.columns([1.8, 1, 0.8])
        with m_col1:
            m_row_index = st.selectbox(
                "المادة",
                options=live_stock_for_form.index.tolist(),
                format_func=manual_item_label,
            )
        with m_col2:
            m_type = st.selectbox(
                "نوع الحركة",
                ["إدخال (IN - زيادة المخزون)", "إخراج (OUT - خصم من المخزون)"],
            )
        with m_col3:
            m_qty = st.number_input("الكمية", min_value=0.0, step=1.0)

        reference_col, reason_col = st.columns(2)
        with reference_col:
            m_reference = st.text_input(
                "رقم الفاتورة / المرجع (اختياري)",
                help="إذا تُرك فارغاً ستُنفذ الحركة مع تسجيل تنبيه رقابي واضح.",
            )
        with reason_col:
            m_note = st.text_input("ملاحظات / سبب الحركة")

        operation_password = st.text_input(
            "كلمة مرور المستخدم لتنفيذ هذه الحركة",
            type="password",
            help="تُطلب كلمة المرور في كل عملية إدخال أو إخراج ولا يتم حفظها في السجل.",
        )

        delivery_note_received = True
        if "إخراج" in m_type:
            st.warning(
                "⚠️ وصل التسليم مطلوب لحركة الإخراج اليدوي، حتى عند عدم وجود فاتورة."
            )
            delivery_note_received = st.checkbox(
                "✅ أؤكد استلام وصل التسليم الخاص بهذه الحركة"
            )

        m_submit = st.form_submit_button(
            "تنفيذ الحركة اليدوية وتحديث المخزون", use_container_width=True
        )

        if m_submit:
            selected_row = st.session_state['live_stock'].loc[m_row_index]
            before_qty = float(selected_row['الكمية'])
            movement_kind = "IN" if "إدخال" in m_type else "OUT"
            without_invoice = not str(m_reference).strip()

            if m_qty <= 0:
                st.warning("⚠️ يرجى إدخال كمية صحيحة أكبر من صفر.")
            elif not verify_operation_password(operation_password):
                st.error("❌ كلمة المرور غير صحيحة؛ لم تُنفذ العملية.")
            elif not str(m_note).strip():
                st.warning("⚠️ يرجى كتابة سبب الحركة اليدوية.")
            elif movement_kind == "OUT" and not delivery_note_received:
                st.error("❌ لا يمكن تنفيذ الإخراج قبل تأكيد استلام وصل التسليم.")
            elif movement_kind == "OUT" and m_qty > before_qty:
                st.error(
                    f"❌ الكمية المطلوبة ({m_qty:g}) أكبر من الرصيد الحالي ({before_qty:g})."
                )
            else:
                try:
                    fingerprint = hashlib.sha256(
                        st.session_state['manual_operation_nonce'].encode("utf-8")
                    ).hexdigest()
                    updated_stock, ledger_rows = post_stock_operation(
                        st.session_state['live_stock'],
                        [{
                            "row_index": int(m_row_index),
                            "movement_type": movement_kind,
                            "quantity": float(m_qty),
                        }],
                        {
                            "fingerprint": fingerprint,
                            "username": current_user,
                            "source": "MANUAL",
                            "invoice_reference": str(m_reference).strip(),
                            "without_invoice": without_invoice,
                            "delivery_note": delivery_note_received,
                            "reason": str(m_note).strip(),
                        },
                    )
                    st.session_state['live_stock'] = updated_stock
                    st.session_state['manual_movements'] = load_manual_movements()
                    after_qty = float(ledger_rows[0][13])
                    message = (
                        f"🚨 تم الحفظ تلقائياً، لكن الحركة {movement_kind} بلا فاتورة / مرجع."
                        if without_invoice
                        else f"✅ تم حفظ حركة {movement_kind} تلقائياً. الرصيد الجديد {after_qty:g}."
                    )
                    st.session_state['manual_movement_flash'] = {
                        "message": message,
                        "without_invoice": without_invoice,
                    }
                    st.session_state['manual_operation_nonce'] = str(uuid.uuid4())
                    st.rerun()
                except Exception as movement_error:
                    st.error(str(movement_error))

    if st.session_state['manual_movements']:
        with st.expander(
            f"📋 سجل الحركات اليدوية ({len(st.session_state['manual_movements'])})",
            expanded=False,
        ):
            manual_log_df = pd.DataFrame(st.session_state['manual_movements'])
            st.dataframe(manual_log_df, use_container_width=True, hide_index=True)
            without_invoice_count = int(
                (manual_log_df["بدون فاتورة"] == "نعم").sum()
            )
            if without_invoice_count:
                st.error(
                    f"🚨 {without_invoice_count} حركة يدوية تحتاج مراجعة لأنها بلا فاتورة / مرجع."
                )

# ==========================================
# 5. LIVE STOCK & END OF DAY EXPORT
# ==========================================
manual_tab.__exit__(None, None, None)
reports_tab.__enter__()
if st.session_state['live_stock'] is not None:
    st.divider()
    st.subheader("🌙 تقرير وإقفال نهاية اليوم")
    report_date_col, report_status_col = st.columns([0.45, 1.55])
    with report_date_col:
        end_of_day_date = st.date_input(
            "تاريخ التقرير", value=datetime.now().date(), key="end_of_day_date"
        )
    closure = daily_closure_for_date(end_of_day_date)
    with report_status_col:
        if closure:
            st.success(
                f"اليوم مقفل بواسطة {closure['username']} بتاريخ {closure['closed_at']}"
            )
        else:
            st.info("التقرير مباشر. الإقفال يثبت ملخص اليوم في سجل التدقيق.")

    report_stock = load_daily_stock_snapshot(end_of_day_date)
    if report_stock is None:
        report_stock = st.session_state['live_stock']
    end_report_bytes, end_ledger, affected_items = build_end_of_day_report(
        end_of_day_date,
        report_stock,
        inventory_analysis,
    )
    day_in = float(
        end_ledger.loc[end_ledger["movement_type"] == "IN", "quantity"].sum()
    ) if not end_ledger.empty else 0
    day_out = float(
        end_ledger.loc[end_ledger["movement_type"] == "OUT", "quantity"].sum()
    ) if not end_ledger.empty else 0
    day_alerts = int(end_ledger["without_invoice"].sum()) if not end_ledger.empty else 0
    eod1, eod2, eod3, eod4 = st.columns(4)
    eod1.metric("حركات اليوم", len(end_ledger))
    eod2.metric("إجمالي الإدخال", f"{day_in:g}")
    eod3.metric("إجمالي الإخراج", f"{day_out:g}")
    eod4.metric("بدون فاتورة", day_alerts)

    if not end_ledger.empty:
        with st.expander("عرض حركات اليوم والمواد المتأثرة", expanded=False):
            st.dataframe(end_ledger, use_container_width=True, hide_index=True)
            if not affected_items.empty:
                st.dataframe(
                    affected_items.drop(columns=["item_key"], errors="ignore"),
                    use_container_width=True,
                    hide_index=True,
                )

    eod_download_col, eod_close_col = st.columns(2)
    with eod_download_col:
        st.download_button(
            "📥 تنزيل تقرير نهاية اليوم الكامل",
            data=end_report_bytes,
            file_name=f"GoldenPalace_EndOfDay_{end_of_day_date:%Y-%m-%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with eod_close_col:
        with st.form("close_business_day_form"):
            close_password = st.text_input(
                "كلمة المرور لإقفال اليوم", type="password"
            )
            close_clicked = st.form_submit_button(
                "🔒 إقفال وتثبيت ملخص اليوم",
                use_container_width=True,
                disabled=closure is not None,
            )
            if close_clicked:
                if not verify_operation_password(close_password):
                    st.error("كلمة المرور غير صحيحة؛ لم يتم إقفال اليوم.")
                else:
                    close_business_day(
                        end_of_day_date,
                        current_user,
                        st.session_state['live_stock'],
                    )
                    st.success("تم إقفال اليوم وتثبيت ملخصه في سجل التدقيق.")
                    st.rerun()

    st.divider()
    st.subheader("حالة المخزون المباشر الحالية")
    display_searchable_table(st.session_state['live_stock'], "live_stock")
    
    if is_admin:
        st.divider()
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_stock = st.session_state['live_stock'].drop(
                columns=['مفتاح المطابقة', 'مفتاح المخزون'], errors='ignore'
            )
            export_stock.to_excel(writer, index=False, sheet_name='Final_Stock')
            if not inventory_analysis.empty:
                export_analysis = inventory_analysis.drop(
                    columns=['مفتاح المطابقة', 'رمز الحركة', 'اسم الحركة'],
                    errors='ignore',
                )
                export_analysis.to_excel(
                    writer, index=False, sheet_name='Movement_Analysis'
                )
                export_analysis[
                    export_analysis['حالة الطلب'] == 'إعادة طلب'
                ].to_excel(writer, index=False, sheet_name='Reorder_List')
                export_analysis[
                    export_analysis['اقتراح التصريف'] == 'مرشح للتصريف'
                ].to_excel(writer, index=False, sheet_name='Slow_Clearance')
            if st.session_state['movement_history'] is not None:
                st.session_state['movement_history'].drop(
                    columns=['مفتاح المطابقة'], errors='ignore'
                ).to_excel(writer, index=False, sheet_name='Movement_History')
            if st.session_state['manual_movements']:
                manual_export = pd.DataFrame(st.session_state['manual_movements'])
                manual_export.to_excel(
                    writer, index=False, sheet_name='Manual_Movements'
                )
                manual_export[
                    manual_export['بدون فاتورة'] == 'نعم'
                ].to_excel(writer, index=False, sheet_name='No_Invoice_Alerts')
        processed_excel = output.getvalue()
        
        st.download_button(
            label="💾 استخراج تقرير الجرد والتحليل المحدّث - Excel",
            data=processed_excel,
            file_name="GoldenPalace_Inventory_Movement_Analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )

reports_tab.__exit__(None, None, None)
