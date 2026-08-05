import streamlit as st
import pandas as pd
from PIL import Image
import hashlib
import io

# ==========================================
# SESSION STATE (Live Memory)
# ==========================================
# This allows the app to track the stock changes continuously over multiple invoices
if 'live_stock' not in st.session_state:
    st.session_state['live_stock'] = None
if 'processed_invoices' not in st.session_state:
    st.session_state['processed_invoices'] = set()

# ==========================================
# SIMULATED AI EXTRACTION
# ==========================================
def extract_invoice_data(file_name):
    # Generates a stable simulated invoice number (e.g., 6692) based on the image name
    hash_num = str(int(hashlib.md5(file_name.encode()).hexdigest(), 16))[:4]
    invoice_num = f"فاتورة_{hash_num}"
    
    # Matching the 3 exact items from your delivery note
    items = [
        {"رمز المادة": "014019", "الكمية المخصومة": 1.0},
        {"رمز المادة": "0113142", "الكمية المخصومة": 1.0},
        {"رمز المادة": "0124087", "الكمية المخصومة": 1.0}
    ]
    return invoice_num, items

# ==========================================
# HELPER FUNCTION: SEARCH-ONLY TABLE
# ==========================================
def display_searchable_table(df, key_prefix):
    search_query = st.text_input("🔍 بحث (برمز المادة أو اسم المادة):", key=f"search_{key_prefix}")
    
    if search_query:
        # Filter dataframe based on search query in Code or Name
        mask = df['رمز المادة'].astype(str).str.contains(search_query, case=False, na=False) | \
               df['اسم المادة'].astype(str).str.contains(search_query, case=False, na=False)
        display_df = df[mask]
        st.markdown(display_df.to_html(index=False), unsafe_allow_html=True)
    else:
        # Table is completely hidden by default to save page length
        st.info("أدخل مصطلح بحث لعرض المواد (تم إخفاء القائمة الكاملة لتوفير المساحة).")

# ==========================================
# PAGE CONFIGURATION & STYLING
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

st.title("القصر الذهبي - متتبع الجرد اليومي (مباشر)")

# ==========================================
# 1. CONTROLS SECTION
# ==========================================
st.subheader("لوحة التحكم")

col1, col2 = st.columns(2)
with col1:
    uploaded_stock_report = st.file_uploader("1. رفع تقرير المخزون (بداية اليوم)", type=["xlsx", "xls"])
    
    # Initialize the Live Stock if a new file is uploaded
    if uploaded_stock_report is not None and st.session_state['live_stock'] is None:
        try:
            df = pd.read_excel(uploaded_stock_report, header=1)
            df = df[['رمز المادة', 'اسم المادة', 'الكمية']].dropna(subset=['رمز المادة'])
            df['الكمية'] = pd.to_numeric(df['الكمية'], errors='coerce').fillna(0)
            df['رمز المادة'] = df['رمز المادة'].astype(str).str.strip()
            st.session_state['live_stock'] = df
            st.success("✅ تم تحميل المخزون الأساسي وتفعيله كـ (مخزون مباشر).")
        except Exception as e:
            st.error("خطأ في قراءة ملف المخزون.")

with col2:
    # accept_multiple_files enables batch processing of delivery notes
    uploaded_invoices = st.file_uploader("2. رفع صور الفواتير (يمكن تحديد عدة صور)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

# Processing logic for multiple invoices
if uploaded_invoices and st.session_state['live_stock'] is not None:
    
    # Extract metadata for all uploaded invoices
    invoice_data = []
    for f in uploaded_invoices:
        inv_num, items = extract_invoice_data(f.name)
        invoice_data.append((inv_num, f, items))
    
    # Create the action button
    if st.button("خصم الفواتير وتحديث المخزون", type="primary", use_container_width=True):
        new_updates = 0
        with st.spinner("جاري معالجة الفواتير وتحديث المخزون..."):
            for inv_num, f, items in invoice_data:
                # Only process invoices that haven't been processed yet to prevent double-deduction
                if f.name not in st.session_state['processed_invoices']:
                    extracted_df = pd.DataFrame(items)
                    extracted_df['رمز المادة'] = extracted_df['رمز المادة'].astype(str).str.strip()
                    
                    # Merge with Live Stock
                    live_df = st.session_state['live_stock']
                    merged_df = pd.merge(live_df, extracted_df, on='رمز المادة', how='left')
                    merged_df['الكمية المخصومة'] = pd.to_numeric(merged_df['الكمية المخصومة'], errors='coerce').fillna(0)
                    
                    # Deduct
                    merged_df['الكمية'] = merged_df['الكمية'] - merged_df['الكمية المخصومة']
                    
                    # Clean up and update memory
                    merged_df = merged_df.drop(columns=['الكمية المخصومة'])
                    st.session_state['live_stock'] = merged_df
                    st.session_state['processed_invoices'].add(f.name)
                    new_updates += 1
            
            if new_updates > 0:
                st.success(f"✅ تم خصم {new_updates} فاتورة جديدة وتحديث حالة المخزون بنجاح!")
            else:
                st.info("تمت معالجة هذه الفواتير مسبقاً. لم يتم إجراء أي خصم مزدوج.")

    st.divider()

    # ==========================================
    # 2. INVOICE PREVIEWS (TABS / BUTTONS)
    # ==========================================
    st.subheader("معاينة الفواتير")
    st.caption("انقر على رقم الفاتورة أدناه لعرض صورتها.")
    
    # Create interactive tabs (acting as buttons) named dynamically by Invoice Number
    tab_names = [data[0] for data in invoice_data]
    tabs = st.tabs(tab_names)
    
    for tab, data in zip(tabs, invoice_data):
        with tab:
            inv_num, f, items = data
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(Image.open(f), use_column_width=True)
            with col_info:
                if f.name in st.session_state['processed_invoices']:
                    st.success("حالة الفاتورة: تمت المعالجة (مخصومة من المخزون)")
                else:
                    st.warning("حالة الفاتورة: قيد الانتظار (غير مخصومة بعد)")

# ==========================================
# 3. LIVE STOCK & END OF DAY EXPORT
# ==========================================
if st.session_state['live_stock'] is not None:
    st.divider()
    st.subheader("حالة المخزون المباشر (البحث السريع)")
    
    # Display the compact search-only table
    display_searchable_table(st.session_state['live_stock'], "live_stock")
    
    st.divider()
    
    # End of Day Excel Generation
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state['live_stock'].to_excel(writer, index=False, sheet_name='Live_Stock')
    processed_excel = output.getvalue()
    
    st.download_button(
        label="💾 استخراج تقرير الجرد النهائي (نهاية اليوم) - Excel",
        data=processed_excel,
        file_name="GoldenPalace_Final_Stock.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )
