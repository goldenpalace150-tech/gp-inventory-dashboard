import streamlit as st
import pandas as pd
from PIL import Image

# ==========================================
# SIMULATED AI EXTRACTION (Instant)
# ==========================================
def extract_invoice_data(image):
    # This instantly returns structured data mapped by Item Code.
    # In production, this is where the API call (e.g., Google Gemini) goes.
    return [
        {"رمز المادة": "0104084", "الكمية المخصومة": 14.0},
        {"رمز المادة": "50009", "الكمية المخصومة": 1.0}
    ]

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Golden Palace Inventory", layout="wide")
st.title("Golden Palace - Daily Inventory Tracker")

# ==========================================
# 1. CONTROLS SECTION (ALWAYS AT THE TOP)
# ==========================================
st.subheader("Control Panel")

col1, col2 = st.columns(2)
with col1:
    uploaded_stock_report = st.file_uploader("1. Upload Excel Stock Report (.xlsx)", type=["xlsx", "xls"])
with col2:
    uploaded_invoice = st.file_uploader("2. Upload Delivery Note Image", type=["png", "jpg", "jpeg"])

extract_button = st.button("Extract Data & Update Stock", type="primary", use_container_width=True)

st.divider()

# ==========================================
# 2. DISPLAY & PROCESSING SECTION
# ==========================================

if extract_button:
    if uploaded_invoice is None or uploaded_stock_report is None:
        st.warning("⚠️ Please upload both the Excel stock report and the Delivery Note image first.")
    else:
        with st.spinner("Extracting delivery note and mapping via رمز المادة..."):
            try:
                # 1. Run instant extraction
                extracted_items = extract_invoice_data(uploaded_invoice)
                extracted_df = pd.DataFrame(extracted_items)
                
                # 2. Read and clean the Excel file
                stock_df = pd.read_excel(uploaded_stock_report, header=1)
                stock_df = stock_df[['رمز المادة', 'اسم المادة', 'الكمية']]
                stock_df = stock_df.dropna(subset=['رمز المادة'])
                
                # Rename the original quantity column to represent the "Before" state
                stock_df.rename(columns={'الكمية': 'الكمية السابقة'}, inplace=True)
                
                # Ensure Item Codes are treated as strings for perfect mapping
                stock_df['رمز المادة'] = stock_df['رمز المادة'].astype(str).str.strip()
                extracted_df['رمز المادة'] = extracted_df['رمز المادة'].astype(str).str.strip()
                
                # 3. Merge data strictly using Item Code (رمز المادة)
                updated_df = pd.merge(stock_df, extracted_df, on='رمز المادة', how='left')
                
                # Fill items that were not on the invoice with 0 deduction
                updated_df['الكمية المخصومة'] = updated_df['الكمية المخصومة'].fillna(0)
                
                # 4. Calculate the "After" state
                updated_df['الكمية الجديدة'] = updated_df['الكمية السابقة'] - updated_df['الكمية المخصومة']
                
                # Filter down to only show the items that changed
                changed_items_df = updated_df[updated_df['الكمية المخصومة'] > 0]
                
                # --- UI DISPLAY ---
                st.success("✅ Extraction complete! Stock updated instantly.")
                
                # Show Before and After Comparison
                st.subheader("Invoice Impact (Before & After)")
                st.markdown(changed_items_df.to_html(index=False), unsafe_allow_html=True)
                
                st.divider()
                
                # Show Full Updated Stock
                st.subheader("Full Updated Stock Report")
                st.markdown(updated_df.to_html(index=False), unsafe_allow_html=True)
                
            except KeyError:
                st.error("Error: Could not find the exact column names. Ensure the second row contains 'رمز المادة', 'اسم المادة', and 'الكمية'.")
            except Exception as e:
                st.error(f"An error occurred: {e}")

# If the button hasn't been clicked, but files are uploaded, just show previews
elif uploaded_invoice is not None or uploaded_stock_report is not None:
    col_img, col_data = st.columns(2)
    
    with col_img:
        if uploaded_invoice is not None:
            st.subheader("Invoice Preview")
            st.image(Image.open(uploaded_invoice), use_column_width=True)
            
    with col_data:
        if uploaded_stock_report is not None:
            st.subheader("Current Stock (Unchanged)")
            preview_df = pd.read_excel(uploaded_stock_report, header=1)[['رمز المادة', 'اسم المادة', 'الكمية']].dropna(subset=['رمز المادة'])
            st.markdown(preview_df.to_html(index=False), unsafe_allow_html=True)
