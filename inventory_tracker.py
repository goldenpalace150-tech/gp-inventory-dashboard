import streamlit as st
import pandas as pd
from PIL import Image

# Page configuration
st.set_page_config(page_title="Golden Palace Inventory", layout="wide")
st.title("Golden Palace - Daily Inventory Tracker")

# ==========================================
# 1. CONTROLS SECTION (ALWAYS AT THE TOP)
# ==========================================
st.subheader("Control Panel")

# Place uploaders side-by-side
col1, col2 = st.columns(2)

with col1:
    uploaded_stock_report = st.file_uploader("1. Upload Excel Stock Report (.xlsx)", type=["xlsx", "xls"])

with col2:
    uploaded_invoice = st.file_uploader("2. Upload Delivery Note Image", type=["png", "jpg", "jpeg"])

# The master button locked at the top
extract_button = st.button("Extract Data & Update Stock", type="primary", use_container_width=True)

st.divider()

# ==========================================
# 2. DISPLAY & PROCESSING SECTION (BELOW)
# ==========================================

# Button Logic
if extract_button:
    if uploaded_invoice is None or uploaded_stock_report is None:
        st.warning("⚠️ Please upload both the Excel stock report and the Delivery Note image first.")
    else:
        st.info("AI extraction in progress... (Integration Pending)")
        # Structural notice for mapping
        st.write("⚙️ **System Note:** Data aggregation will strictly map extracted quantities via **رمز المادة** (Item Code).")

# Display Image (if uploaded)
if uploaded_invoice is not None:
    st.subheader("Uploaded Delivery Note")
    invoice_img = Image.open(uploaded_invoice)
    st.image(invoice_img, caption="Ready for Extraction", width=600)

# Display Excel Table (if uploaded)
if uploaded_stock_report is not None:
    try:
        st.subheader("Current Stock Overview")
        
        # Read the Excel file, skipping the first row (header=1)
        stock_df = pd.read_excel(uploaded_stock_report, header=1)
        
        # Filter down strictly to the required columns
        stock_df = stock_df[['رمز المادة', 'اسم المادة', 'الكمية']]
        
        # Clean up any trailing empty rows from the bottom of the Excel sheet
        stock_df = stock_df.dropna(subset=['رمز المادة'])

        # Display the cleaned table safely using HTML
        html_table = stock_df.to_html(index=False)
        st.markdown(html_table, unsafe_allow_html=True)
        
    except KeyError:
        st.error("Error: Could not find the exact column names. Please ensure the second row contains 'رمز المادة', 'اسم المادة', and 'الكمية'.")
    except Exception as e:
        st.error(f"Error reading the Excel file: {e}")
elif not extract_button:
    st.info("Please upload your files above to view the data.")
