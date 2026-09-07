import streamlit as st
import pandas as pd
from PIL import Image
import io
import json
import re
import unicodedata
from datetime import datetime

# ==========================================
# PAGE CONFIGURATION & MOBILE-FRIENDLY RTL STYLING
# ==========================================
st.set_page_config(page_title="متتبع الجرد - القصر الذهبي", layout="wide")

st.markdown("""
    <style>
        .stApp {
            direction: rtl;
            text-align: right;
        }
        /* Fix mobile text vertical stacking/wrapping issues */
        h1, h2, h3, h4, p, span, label, div {
            word-break: normal !important;
            overflow-wrap: break-word !important;
            text-align: right;
        }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; flex-wrap: wrap; }
        .stTabs [data-baseweb="tab"] {
            background-color: #f0f2f6;
            border-radius: 4px;
            padding: 8px 16px;
            font-size: 14px;
        }
        table { width: 100% !important; font-size: 13px !important; }
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    </style>
""", unsafe_allow_html=True)

st.title("القصر الذهبي - متتبع الجرد اليومي المباشر")

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
# SIMULATED AI EXTRACTION (Invoice #6692)
# ==========================================
def extract_invoice_data(uploaded_file):
    invoice_num = "فاتورة_6692"
    items = [
        {"رمز المادة": "014019", "اسم المادة": "مطري 2*2.5 مم كندان - Kadaan", "الكمية المخصومة": 1.0},
        {"رمز المادة": "0113142", "اسم المادة": "فيش كبير - شوكو", "الكمية المخصومة": 1.0},
        {"رمز المادة": "0124087", "اسم المادة": "قاطع مزدوج 63 امبير SSC-ONE.DC", "الكمية المخصومة": 1.0}
    ]
    return invoice_num, items


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
            return result.reset_index(drop=True)
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


def build_inventory_analysis(stock_df, movement_df, lead_days, safety_days, slow_days):
    """Calculate demand velocity, ABC movement class, reorder and clearance flags."""
    if movement_df is None or movement_df.empty:
        return pd.DataFrame()
    start_date = movement_df["التاريخ"].min()
    end_date = movement_df["التاريخ"].max()
    period_days = max(1, (end_date.date() - start_date.date()).days + 1)

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

    stock_view = stock_df[["مفتاح المطابقة", "رمز المادة", "اسم المادة", "الكمية"]].copy()
    analysis = stock_view.merge(grouped, on="مفتاح المطابقة", how="left")
    analysis["رمز المادة"] = analysis["رمز المادة"].where(
        analysis["رمز المادة"].astype(str).str.strip().ne(""),
        analysis["رمز الحركة"],
    ).fillna("")
    for column in ("إجمالي الإدخال", "إجمالي الإخراج", "عدد الحركات"):
        analysis[column] = pd.to_numeric(analysis[column], errors="coerce").fillna(0)

    analysis["متوسط الخروج اليومي"] = analysis["إجمالي الإخراج"] / period_days
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
    analysis["حد إعادة الطلب"] = (
        analysis["متوسط الخروج اليومي"] * (lead_days + safety_days)
    ).round().astype(int)
    target_days = lead_days + safety_days + 30
    analysis["كمية الطلب المقترحة"] = (
        analysis["متوسط الخروج اليومي"] * target_days - analysis["الكمية"]
    ).clip(lower=0).round().astype(int)
    analysis["حالة الطلب"] = "لا يحتاج"
    reorder_mask = (
        (analysis["متوسط الخروج اليومي"] > 0)
        & (analysis["الكمية"] <= analysis["حد إعادة الطلب"])
    )
    analysis.loc[reorder_mask, "حالة الطلب"] = "إعادة طلب"

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
    analysis["فترة التحليل"] = f"{period_days} يوم"
    return analysis.sort_values(
        ["حالة الطلب", "إجمالي الإخراج"], ascending=[True, False]
    ).reset_index(drop=True)

# ==========================================
# HELPER: SEARCHABLE TABLE
# ==========================================
def display_searchable_table(df, key_prefix):
    search_query = st.text_input("🔍 بحث في المخزون (بررمز المادة أو اسم المادة):", key=f"search_{key_prefix}")
    
    if search_query:
        mask = df['رمز المادة'].astype(str).str.contains(search_query, case=False, na=False) | \
               df['اسم المادة'].astype(str).str.contains(search_query, case=False, na=False)
        display_df = df[mask]
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
                st.session_state['manual_movements'] = loaded_state.get(
                    'manual_movements', []
                )
                st.success("✅ تمت استعادة الحالة بنجاح!")
                st.rerun()
            except Exception as e:
                st.error("ملف التخزين غير صالح.")

col1, col2, col3 = st.columns(3)

with col1:
    if is_admin:
        uploaded_stock_report = st.file_uploader("📊 1. رفع تقرير المخزون الأساسي (بداية اليوم)", type=["xlsx", "xls"])
        if uploaded_stock_report is not None and st.session_state['live_stock'] is None:
            try:
                df = read_stock_report(uploaded_stock_report.getvalue())
                if st.session_state['movement_history'] is not None:
                    df = enrich_stock_codes(df, st.session_state['movement_history'])
                st.session_state['live_stock'] = df
                st.success("✅ تم تحميل المخزون الأساسي بنجاح.")
            except Exception as e:
                st.error("خطأ في قراءة ملف المخزون.")
    else:
        st.info("🔒 📊 رفع تقرير المخزون الأساسي مقتصر على مدير النظام (Admin).")

with col2:
    uploaded_invoices = st.file_uploader("🖼️ 2. رفع صور الفواتير (من الألبوم)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

with col3:
    uploaded_movement_report = st.file_uploader(
        "📈 3. رفع تقرير حركة المادة للتحليل",
        type=["xlsx", "xls"],
        help="يستخدم للتحليل والتصنيف فقط؛ لا تُخصم حركاته القديمة من رصيد الجرد الحالي.",
    )
    if uploaded_movement_report is not None:
        try:
            movement_df = read_movement_report(uploaded_movement_report.getvalue())
            st.session_state['movement_history'] = movement_df
            if st.session_state['live_stock'] is not None:
                st.session_state['live_stock'] = enrich_stock_codes(
                    st.session_state['live_stock'], movement_df
                )
            st.success(f"✅ تم تحميل {len(movement_df):,} حركة مخزون للتحليل.")
        except Exception as movement_error:
            st.error(f"تعذر قراءة تقرير الحركة: {movement_error}")

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
# AUTO-ROLLBACK LOGIC FOR DELETED FILES
# ==========================================
current_file_names = {f.name for f in active_invoices_list} if active_invoices_list else set()
processed_file_names = list(st.session_state['file_to_invoice'].keys())
removed_files = [fname for fname in processed_file_names if fname not in current_file_names]

if removed_files and st.session_state['live_stock'] is not None:
    for fname in removed_files:
        inv_num = st.session_state['file_to_invoice'][fname]
        old_items = st.session_state['invoice_raw_data'].get(inv_num, [])
        
        for old_row in old_items:
            code = old_row['رمز المادة']
            qty_to_restore = old_row['الكمية المخصومة']
            st.session_state['live_stock'].loc[
                st.session_state['live_stock']['رمز المادة'] == code, 'الكمية'
            ] += qty_to_restore
            
        st.session_state['processed_invoices'].pop(inv_num, None)
        st.session_state['invoice_raw_data'].pop(inv_num, None)
        st.session_state['file_to_invoice'].pop(fname, None)
        
    st.success("🔄 تم رصد حذف الفاتورة، وتمت إعادة الكميات إلى المخزون تلقائياً!")
    st.rerun()

# ==========================================
# PROCESSING INVOICES LOGIC
# ==========================================
if active_invoices_list:
    if st.button("معالجة الفواتير وتحديث المخزون", type="primary", use_container_width=True):
        if st.session_state['live_stock'] is None:
            st.error("❌ خطأ: يجب عليك رفع تقرير المخزون الأساسي (Excel) أولاً قبل معالجة أي فواتير!")
        else:
            with st.spinner("جاري معالجة البيانات والتحقق من التكرار أو التعديلات..."):
                for f in active_invoices_list:
                    inv_num, items = extract_invoice_data(f)
                    extracted_df = pd.DataFrame(items)
                    extracted_df['رمز المادة'] = extracted_df['رمز المادة'].astype(str).str.strip()
                    
                    st.session_state['file_to_invoice'][f.name] = inv_num
                    
                    old_items = st.session_state['invoice_raw_data'].get(inv_num, None)
                    
                    if old_items is not None:
                        old_sorted = sorted(old_items, key=lambda x: str(x['رمز المادة']))
                        new_sorted = sorted(items, key=lambda x: str(x['رمز المادة']))
                        
                        is_exact_duplicate = (old_sorted == new_sorted)
                        
                        if is_exact_duplicate:
                            st.error(f"❌ خطأ كبير: هذه الفاتورة ({inv_num}) مطابقة تماماً وتمت معالجتها مسبقاً! تم تجاهل رفعها لتجنب التكرار.")
                            continue 
                        else:
                            st.warning(f"⚠️ تم رصد تعديل على الفاتورة ({inv_num})! يتم عكس محتواها القديم وتحديثها بالبيانات الجديدة.")
                            for old_row in old_items:
                                code = old_row['رمز المادة']
                                qty_to_restore = old_row['الكمية المخصومة']
                                st.session_state['live_stock'].loc[
                                    st.session_state['live_stock']['رمز المادة'] == code, 'الكمية'
                                ] += qty_to_restore

                    live_df = st.session_state['live_stock'].copy()
                    live_df.rename(columns={'الكمية': 'الكمية قبل الفاتورة'}, inplace=True)
                    
                    merged_df = pd.merge(live_df, extracted_df[['رمز المادة', 'الكمية المخصومة']], on='رمز المادة', how='inner')
                    merged_df['الكمية بعد الفاتورة'] = merged_df['الكمية قبل الفاتورة'] - merged_df['الكمية المخصومة']
                    
                    st.session_state['processed_invoices'][inv_num] = merged_df
                    st.session_state['invoice_raw_data'][inv_num] = items
                    
                    for idx, row in extracted_df.iterrows():
                        code = row['رمز المادة']
                        qty_deduct = row['الكمية المخصومة']
                        st.session_state['live_stock'].loc[
                            st.session_state['live_stock']['رمز المادة'] == code, 'الكمية'
                        ] -= qty_deduct
                            
                st.success("✅ تمت معالجة الفواتير بنجاح وتحديث حالة المخزون!")

    st.divider()

    # ==========================================
    # 2. INVOICE PREVIEWS & BEFORE/AFTER IMPACT
    # ==========================================
    if st.session_state['processed_invoices']:
        st.subheader("مراجعة الفواتير والمواد المعدلة (قبل وبعد)")
        st.caption("انقر على تبويب رقم الفاتورة أدناه لعرض المواد المؤثرة بدقة.")
        
        inv_tabs = list(st.session_state['processed_invoices'].keys())
        tabs = st.tabs(inv_tabs)
        
        for tab, inv_num in zip(tabs, inv_tabs):
            with tab:
                impact_df = st.session_state['processed_invoices'][inv_num]
                
                col_info, col_table = st.columns([1, 2])
                with col_info:
                    st.write(f"رقم الفاتورة: {inv_num}")
                    st.success("حالة الفاتورة: معالجة ومخصومة من المخزون")
                
                with col_table:
                    st.write("**المواد المؤثرة في هذه الفاتورة (مقارنة قبل وبعد):**")
                    st.markdown(impact_df[['رمز المادة', 'اسم المادة', 'الكمية قبل الفاتورة', 'الكمية المخصومة', 'الكمية بعد الفاتورة']].to_html(index=False), unsafe_allow_html=True)

# ==========================================
# 3. MOVEMENT ANALYSIS, REORDER & CLEARANCE
# ==========================================
inventory_analysis = pd.DataFrame()
analysis_movement_df = st.session_state['movement_history']

if analysis_movement_df is not None and st.session_state['manual_movements']:
    manual_for_analysis = pd.DataFrame(st.session_state['manual_movements'])
    manual_rows = pd.DataFrame({
        "رمز المادة": manual_for_analysis["رمز المادة"],
        "اسم المادة": manual_for_analysis["اسم المادة"],
        "التاريخ": pd.to_datetime(manual_for_analysis["التاريخ"], errors="coerce"),
        "المرجع": manual_for_analysis["رقم الفاتورة / المرجع"],
        "الزبون": "",
        "إدخال": manual_for_analysis.apply(
            lambda row: row["الكمية"] if row["نوع الحركة"] == "IN" else 0,
            axis=1,
        ),
        "إخراج": manual_for_analysis.apply(
            lambda row: row["الكمية"] if row["نوع الحركة"] == "OUT" else 0,
            axis=1,
        ),
        "الرصيد": manual_for_analysis["الكمية بعد الحركة"],
        "المستخدم": manual_for_analysis["المستخدم"],
        "بيان": manual_for_analysis["السبب"],
        "مفتاح المطابقة": manual_for_analysis["اسم المادة"].map(normalize_item_name),
    })
    analysis_movement_df = pd.concat(
        [analysis_movement_df, manual_rows], ignore_index=True
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
        st.caption(
            "كمية الطلب المقترحة تغطي مدة التوريد + الأمان + 30 يوماً للمراجعة القادمة."
        )

    inventory_analysis = build_inventory_analysis(
        st.session_state['live_stock'],
        analysis_movement_df,
        int(lead_days),
        int(safety_days),
        int(slow_days),
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
                "رمز المادة", "اسم المادة", "الكمية", "إجمالي الإخراج",
                "متوسط الخروج اليومي", "حد إعادة الطلب", "كمية الطلب المقترحة",
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
            elif not str(m_note).strip():
                st.warning("⚠️ يرجى كتابة سبب الحركة اليدوية.")
            elif movement_kind == "OUT" and not delivery_note_received:
                st.error("❌ لا يمكن تنفيذ الإخراج قبل تأكيد استلام وصل التسليم.")
            elif movement_kind == "OUT" and m_qty > before_qty:
                st.error(
                    f"❌ الكمية المطلوبة ({m_qty:g}) أكبر من الرصيد الحالي ({before_qty:g})."
                )
            else:
                delta = float(m_qty) if movement_kind == "IN" else -float(m_qty)
                after_qty = before_qty + delta
                st.session_state['live_stock'].at[m_row_index, 'الكمية'] = after_qty
                movement_record = {
                    "التاريخ": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "المستخدم": current_user,
                    "نوع الحركة": movement_kind,
                    "رمز المادة": str(selected_row.get('رمز المادة', '') or ''),
                    "اسم المادة": str(selected_row.get('اسم المادة', '') or ''),
                    "الكمية": float(m_qty),
                    "الكمية قبل الحركة": before_qty,
                    "الكمية بعد الحركة": after_qty,
                    "رقم الفاتورة / المرجع": str(m_reference).strip(),
                    "بدون فاتورة": "نعم" if without_invoice else "لا",
                    "وصل تسليم": "نعم" if delivery_note_received else "لا",
                    "السبب": str(m_note).strip(),
                }
                st.session_state['manual_movements'].append(movement_record)
                message = (
                    f"🚨 تم تحديث المخزون، لكن الحركة {movement_kind} سُجلت بدون فاتورة / مرجع."
                    if without_invoice
                    else f"✅ تم تنفيذ حركة {movement_kind} وتحديث الرصيد إلى {after_qty:g}."
                )
                st.session_state['manual_movement_flash'] = {
                    "message": message,
                    "without_invoice": without_invoice,
                }
                st.rerun()

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
if st.session_state['live_stock'] is not None:
    st.divider()
    st.subheader("حالة المخزون المباشر الحالية")
    display_searchable_table(st.session_state['live_stock'], "live_stock")
    
    if is_admin:
        st.divider()
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_stock = st.session_state['live_stock'].drop(
                columns=['مفتاح المطابقة'], errors='ignore'
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
