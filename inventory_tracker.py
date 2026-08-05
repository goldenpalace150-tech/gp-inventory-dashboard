import streamlit as st
import pandas as pd
from PIL import Image
import io
import json

# ==========================================
# PAGE CONFIGURATION & MOBILE-FRIENDLY RTL STYLING
# ==========================================
st.set_page_config(page_title="متتبع الجرد - القصر الذهبي", layout="wide")

st.markdown("""
    <style>
        .stApp { direction: rtl; }
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

# ==========================================
# HELPER: SEARCHABLE TABLE
# ==========================================
def display_searchable_table(df, key_prefix):
    search_query = st.text_input("🔍 بحث في المخزون (برمز المادة أو اسم المادة):", key=f"search_{key_prefix}")
    
    if search_query:
        mask = df['رمز المادة'].astype(str).str.contains(search_query, case=False, na=False) | \
               df['اسم المادة'].astype(str).str.contains(search_query, case=False, na=False)
        display_df = df[mask]
        st.markdown(display_df.to_html(index=False), unsafe_allow_html=True)
    else:
        st.info("أدخل مصطلح بحث أعلاه لعرض المواد (تم إخفاء القائمة الكاملة لتوفير المساحة وتناسب الشاشات).")

# ==========================================
# 1. CONTROLS SECTION WITH ICONS & OPTIONAL CAMERA
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
                "file_to_invoice": st.session_state['file_to_invoice']
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
                st.success("✅ تمت استعادة الحالة بنجاح!")
                st.rerun()
            except Exception as e:
                st.error("ملف التخزين غير صالح.")

col1, col2 = st.columns(2)

with col1:
    if is_admin:
        uploaded_stock_report = st.file_uploader("📊 1. رفع تقرير المخزون الأساسي (بداية اليوم)", type=["xlsx", "xls"])
        if uploaded_stock_report is not None and st.session_state['live_stock'] is None:
            try:
                df = pd.read_excel(uploaded_stock_report, header=1)
                df = df[['رمز المادة', 'اسم المادة', 'الكمية']].dropna(subset=['رمز المادة'])
                df['الكمية'] = pd.to_numeric(df['الكمية'], errors='coerce').fillna(0)
                df['رمز المادة'] = df['رمز المادة'].astype(str).str.strip()
                st.session_state['live_stock'] = df
                st.success("✅ تم تحميل المخزون الأساسي بنجاح.")
            except Exception as e:
                st.error("خطأ في قراءة ملف المخزون.")
    else:
        st.info("🔒 📊 رفع تقرير المخزون الأساسي مقتصر على مدير النظام (Admin).")

with col2:
    uploaded_invoices = st.file_uploader("🖼️ 2. رفع صور الفواتير (من الألبوم)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

# OPTIONAL CAMERA SECTION (Hidden by default, opens ONLY when clicked)
camera_image = None
with st.expander("📸 التقاط صورة الفاتورة بالكاميرا مباشرة (اختياري)"):
    camera_image = st.camera_input("وجه الكاميرا نحو الفاتورة ثم اضغط التقاط")

# Combine uploaded files and optional camera capture into a unified list
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
if active_invoices_list and st.session_state['live_stock'] is not None:
    if st.button("معالجة الفواتير وتحديث المخزون", type="primary", use_container_width=True):
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
# 3. LIVE STOCK & END OF DAY EXPORT
# ==========================================
if st.session_state['live_stock'] is not None:
    st.divider()
    st.subheader("حالة المخزون المباشر الحالية")
    display_searchable_table(st.session_state['live_stock'], "live_stock")
    
    if is_admin:
        st.divider()
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            st.session_state['live_stock'].to_excel(writer, index=False, sheet_name='Final_Stock')
        processed_excel = output.getvalue()
        
        st.download_button(
            label="💾 استخراج تقرير الجرد النهائي (نهاية اليوم) - Excel",
            data=processed_excel,
            file_name="GoldenPalace_Final_EndOfDay_Stock.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
