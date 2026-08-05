import streamlit as st
import pandas as pd
from PIL import Image
import io

# ==========================================
# PAGE CONFIGURATION & RTL STYLING
# ==========================================
st.set_page_config(page_title="متتبع الجرد - القصر الذهبي", layout="wide")

st.markdown("""
    <style>
        .stApp { direction: rtl; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] {
            background-color: #f0f2f6;
            border-radius: 4px;
            padding: 10px 20px;
        }
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
    # Login Form
    with st.sidebar.form("login_form"):
        username_input = st.text_input("اسم المستخدم")
        password_input = st.text_input("كلمة المرور", type="password")
        login_btn = st.form_submit_button("تسجيل الدخول")
        
        if login_btn:
            if username_input in st.session_state['user_db'] and st.session_state['user_db'][username_input]["password"] == password_input:
                st.session_state['logged_in_user'] = username_input
                st.rerun()
            else:
                st.sidebar.error("اسم المستخدم أو كلمة المرور غير صحيحة.")
else:
    current_user = st.session_state['logged_in_user']
    current_role = st.session_state['user_db'][current_user]["role"]
    
    st.sidebar.success(مرحباً: {current_user})
    st.sidebar.info(الصلاحية: {current_role})
    
    if st.sidebar.button("تسجيل الخروج"):
        st.session_state['logged_in_user'] = None
        st.rerun()

    # Admin Panel to Add New Users and Passwords
    if current_role == "مدير النظام (Admin)":
        st.sidebar.divider()
        st.sidebar.subheader("👥 إضافة مستخدم جديد")
        with st.sidebar.form("new_user_form"):
            new_username = st.text_input("اسم المستخدم الجديد")
            new_password = st.text_input("كلمة المرور", type="password")
            new_role = st.selectbox("الصلاحية", ["أمين مخزن (Storekeeper)", "مدير النظام (Admin)"])
            add_user_btn = st.form_submit_button("إضافة المستخدم")
            
            if add_user_btn:
                if new_username and new_password:
                    st.session_state['user_db'][new_username] = {"password": new_password, "role": new_role}
                    st.sidebar.success(تمت إضافة المستخدم {new_username} بنجاح!)
                else:
                    st.sidebar.warning("يرجى ملء كافة الحقول.")

is_admin = (st.session_state['logged_in_user'] is not None and st.session_state['user_db'][st.session_state['logged_in_user']]["role"] == "مدير النظام (Admin)")

st.divider()

# Stop execution if user is not logged in
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
        st.info("أدخل مصطلح بحث أعلاه لعرض المواد (تم إخفاء القائمة الكاملة لتوفير المساحة).")

# ==========================================
# 1. CONTROLS SECTION
# ==========================================
st.subheader("لوحة التحكم")

col1, col2 = st.columns(2)

with col1:
    if is_admin:
        uploaded_stock_report = st.file_uploader("1. رفع تقرير المخزون الأساسي (بداية اليوم)", type=["xlsx", "xls"])
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
        st.info("🔒 رفع تقرير المخزون الأساسي مقتصر على مدير النظام (Admin).")

with col2:
    uploaded_invoices = st.file_uploader("2. رفع صور الفواتير / وصلات التسليم", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

# Processing invoices logic
if uploaded_invoices and st.session_state['live_stock'] is not None:
    if st.button("معالجة الفواتير وتحديث المخزون", type="primary", use_container_width=True):
        with st.spinner("جاري استخراج البيانات ومقارنة المخزون..."):
            for f in uploaded_invoices:
                inv_num, items = extract_invoice_data(f)
                
                if inv_num not in st.session_state['processed_invoices']:
                    extracted_df = pd.DataFrame(items)
                    extracted_df['رمز المادة'] = extracted_df['رمز المادة'].astype(str).str.strip()
                    
                    # Capture state BEFORE deduction
                    live_df = st.session_state['live_stock'].copy()
                    live_df.rename(columns={'الكمية': 'الكمية قبل الفاتورة'}, inplace=True)
                    
                    # Merge and compute AFTER state
                    merged_df = pd.merge(live_df, extracted_df[['رمز المادة', 'الكمية المخصومة']], on='رمز المادة', how='inner')
                    merged_df['الكمية بعد الفاتورة'] = merged_df['الكمية قبل الفاتورة'] - merged_df['الكمية المخصومة']
                    
                    # Save impact report for this specific invoice
                    st.session_state['processed_invoices'][inv_num] = merged_df
                    
                    # Update global live stock
                    global_live = st.session_state['live_stock']
                    for idx, row in extracted_df.iterrows():
                        code = row['رمز المادة']
                        qty_deduct = row['الكمية المخصومة']
                        global_live.loc[global_live['رمز المادة'] == code, 'الكمية'] -= qty_deduct
                        
            st.success("✅ تم معالجة الفواتير وتحديث المخزون بنجاح!")

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
                    st.write(رقم الفاتورة: {inv_num})
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
