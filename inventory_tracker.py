import streamlit as st
import pandas as pd
from PIL import Image

# ==========================================
# SIMULATED AI EXTRACTION (Matching your WhatsApp Image)
# ==========================================
def extract_invoice_data(image):
    # This now perfectly matches the 3 items in your uploaded delivery note
    return [
        {"رمز المادة": "014019", "الكمية المخصومة": 1.0},
        {"رمز المادة": "0113142", "الكمية المخصومة": 1.0},
        {"رمز المادة": "0124087", "الكمية المخصومة": 1.0}
    ]

# ==========================================
# HELPER FUNCTION: SEARCHABLE COMPACT TABLE
# ==========================================
def display_searchable_table(df, key_prefix):
    search_query = st.text_input("🔍 بحث (برمز المادة أو اسم المادة):", key=f"search_{key_prefix}")
    
    if search_query:
        # Filter dataframe based on search query in Code or Name
        mask = df['رمز المادة'].astype(str).str.contains(search_query, case=False, na=False) | \
               df['اسم المادة'].astype(str).str.contains(search_query, case=False, na=False)
        display_df = df[mask]
    else:
        # Hide the massive table, just show the top 3 rows as a preview
        display_df = df.head(3)
        st.caption("يتم عرض أول 3 مواد فقط لتوفير المساحة. استخدم شريط البحث أعلاه للعثور على مواد محددة في المخزون.")
        
    st.markdown(display_df.to_html(index=False), unsafe_allow_html=True)

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="متتبع الجرد - القصر الذهبي", layout="wide")

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
                # 1. Run extraction (matching your image)
                extracted_items = extract_invoice_data(uploaded_invoice)
                extracted_df = pd.DataFrame(extracted_items)
                
                # 2. Read and clean the Excel file
                stock_df = pd.read_excel(uploaded_stock_report, header=1)
                stock_df = stock_df[['رمز المادة', 'اسم المادة', 'الكمية']]
                stock_df = stock_df.dropna(subset=['رمز المادة'])
                
                stock_df.rename(columns={'الكمية': 'الكمية السابقة'}, inplace=True)
                stock_df['الكمية السابقة'] = pd.to_numeric(stock_df['الكمية السابقة'], errors='coerce').fillna(0)
                
                # Ensure Item Codes are stripped text strings for perfect mapping
                stock_df['رمز المادة'] = stock_df['رمز المادة'].astype(str).str.strip()
                extracted_df['رمز المادة'] = extracted_df['رمز المادة'].astype(str).str.strip()
                
                # 3. Merge data strictly using Item Code (رمز المادة)
                updated_df = pd.merge(stock_df, extracted_df, on='رمز المادة', how='left')
                updated_df['الكمية المخصومة'] = pd.to_numeric(updated_df['الكمية المخصومة'], errors='coerce').fillna(0)
                
                # 4. Calculate the "After" state
                updated_df['الكمية الجديدة'] = updated_df['الكمية السابقة'] - updated_df['الكمية المخصومة']
                
                # Filter down to only show the items that changed
                changed_items_df = updated_df[updated_df['الكمية المخصومة'] > 0]
                
                # --- UI DISPLAY ---
                st.success("✅ تمت عملية الاستخراج! تم تحديث المخزون بنجاح.")
                
                # 1st Table: Just the items that were deducted (Always shown fully)
                st.subheader("تأثير الفاتورة (المواد التي تم خصمها فقط)")
                st.markdown(changed_items_df.to_html(index=False), unsafe_allow_html=True)
                
                st.divider()
                
                # 2nd Table: The compact, searchable full stock
                st.subheader("البحث في تقرير المخزون الكامل المحدث")
                display_searchable_table(updated_df, "updated_stock")
                
            except KeyError:
                st.error("خطأ: لم يتم العثور على الأعمدة المطلوبة. تأكد من أن الصف الثاني في ملف الإكسيل يحتوي على 'رمز المادة'، 'اسم المادة'، و 'الكمية'.")
            except Exception as e:
                st.error(f"حدث خطأ أثناء المعالجة: {e}")

# If the button hasn't been clicked, but files are uploaded, show previews with search
elif uploaded_invoice is not None or uploaded_stock_report is not None:
    col_img, col_data = st.columns(2)
    
    with col_img:
        if uploaded_invoice is not None:
            st.subheader("معاينة الفاتورة")
            st.image(Image.open(uploaded_invoice), use_column_width=True)
            
    with col_data:
        if uploaded_stock_report is not None:
            try:
                stock_df = pd.read_excel(uploaded_stock_report, header=1)[['رمز المادة', 'اسم المادة', 'الكمية']].dropna(subset=['رمز المادة'])
                st.subheader("البحث في المخزون الحالي (قبل الخصم)")
                display_searchable_table(stock_df, "preview_stock")
            except Exception as e:
                st.error("خطأ في قراءة ملف المخزون.")
