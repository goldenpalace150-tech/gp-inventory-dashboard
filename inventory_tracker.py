import streamlit as st
import pandas as pd
from PIL import Image

# ==========================================
# SIMULATED AI EXTRACTION (Instant)
# ==========================================
def extract_invoice_data(image):
    # Simulated data extraction mapping directly to Item Code
    return [
        {"رمز المادة": "0104084", "الكمية المخصومة": 14.0},
        {"رمز المادة": "50009", "الكمية المخصومة": 1.0}
    ]

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="متتبع الجرد - القصر الذهبي", layout="wide")

# Force Right-to-Left (RTL) layout for Arabic text support
st.markdown("""
    <style>
        .stApp {
            direction: rtl;
        }
    </style>
""", unsafe_allow_html=True)

st.title("القصر الذهبي - متتبع الجرد اليومي")

# ==========================================
# 1. CONTROLS SECTION
# ==========================================
st.subheader("لوحة التحكم")

col1, col2 = st.columns(2)
with col1:
    uploaded_stock_report = st.file_uploader("1. رفع تقرير المخزون (Excel)", type=["xlsx", "xls"])
with col2:
    uploaded_invoice = st.file_uploader("2. رفع صورة الفاتورة أو وصل التسليم", type=["png", "jpg", "jpeg"])

extract_button = st.button("استخراج البيانات وتحديث المخزون", type="primary", use_container_width=True)

st.divider()

# ==========================================
# 2. DISPLAY & PROCESSING SECTION
# ==========================================

if extract_button:
    if uploaded_invoice is None or uploaded_stock_report is None:
        st.warning("⚠️ يرجى رفع تقرير المخزون وصورة الفاتورة أولاً.")
    else:
        with st.spinner("جاري استخراج بيانات الفاتورة ومطابقتها عبر رمز المادة..."):
            try:
                # 1. Run instant extraction
                extracted_items = extract_invoice_data(uploaded_invoice)
                extracted_df = pd.DataFrame(extracted_items)
                
                # 2. Read and clean the Excel file
                stock_df = pd.read_excel(uploaded_stock_report, header=1)
                stock_df = stock_df[['رمز المادة', 'اسم المادة', 'الكمية']]
                stock_df = stock_df.dropna(subset=['رمز المادة'])
                
                stock_df.rename(columns={'الكمية': 'الكمية السابقة'}, inplace=True)
                
                # CRITICAL FIX: Force the Excel quantities to be treated as numbers, not text
                stock_df['الكمية السابقة'] = pd.to_numeric(stock_df['الكمية السابقة'], errors='coerce').fillna(0)
                
                # Ensure Item Codes are stripped text strings for perfect mapping
                stock_df['رمز المادة'] = stock_df['رمز المادة'].astype(str).str.strip()
                extracted_df['رمز المادة'] = extracted_df['رمز المادة'].astype(str).str.strip()
                
                # 3. Merge data strictly using Item Code (رمز المادة)
                updated_df = pd.merge(stock_df, extracted_df, on='رمز المادة', how='left')
                
                # Fill missing deductions with 0
                updated_df['الكمية المخصومة'] = pd.to_numeric(updated_df['الكمية المخصومة'], errors='coerce').fillna(0)
                
                # 4. Calculate the "After" state
                updated_df['الكمية الجديدة'] = updated_df['الكمية السابقة'] - updated_df['الكمية المخصومة']
                
                changed_items_df = updated_df[updated_df['الكمية المخصومة'] > 0]
                
                # --- UI DISPLAY ---
                st.success("✅ تمت عملية الاستخراج! تم تحديث المخزون بنجاح.")
                
                st.subheader("تأثير الفاتورة (قبل وبعد الخصم)")
                st.markdown(changed_items_df.to_html(index=False), unsafe_allow_html=True)
                
                st.divider()
                
                st.subheader("تقرير المخزون الكامل المحدث")
                st.markdown(updated_df.to_html(index=False), unsafe_allow_html=True)
                
            except KeyError:
                st.error("خطأ: لم يتم العثور على الأعمدة المطلوبة. تأكد من أن الصف الثاني في ملف الإكسيل يحتوي على 'رمز المادة'، 'اسم المادة'، و 'الكمية'.")
            except Exception as e:
                st.error(f"حدث خطأ أثناء المعالجة: {e}")

# If the button hasn't been clicked, but files are uploaded, show previews
elif uploaded_invoice is not None or uploaded_stock_report is not None:
    col_img, col_data = st.columns(2)
    
    with col_img:
        if uploaded_invoice is not None:
            st.subheader("معاينة الفاتورة")
            st.image(Image.open(uploaded_invoice), use_column_width=True)
            
    with col_data:
        if uploaded_stock_report is not None:
            st.subheader("المخزون الحالي (بدون تعديل)")
            preview_df = pd.read_excel(uploaded_stock_report, header=1)[['رمز المادة', 'اسم المادة', 'الكمية']].dropna(subset=['رمز المادة'])
            st.markdown(preview_df.to_html(index=False), unsafe_allow_html=True)
