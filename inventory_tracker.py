import streamlit as st
import pandas as pd

# Page configuration
st.set_page_config(page_title="Golden Palace Inventory", layout="wide")
st.title("Golden Palace - Daily Inventory Tracker")

st.header("Upload Daily Stock Report")

# Create the file uploader widget
uploaded_stock_report = st.file_uploader("Upload your Excel stock report (.xlsx)", type=["xlsx", "xls"])

if uploaded_stock_report is not None:
    try:
        # Read the uploaded Excel file
        stock_df = pd.read_excel(uploaded_stock_report)
        st.success("Stock report loaded successfully!")
        
        st.subheader("Current Stock Overview")
        
        # BYPASS THE CRASH: Convert the dataframe to a raw HTML table
        # This avoids PyArrow memory constraints in the cloud container completely
        html_table = stock_df.to_html(index=False)
        st.markdown(html_table, unsafe_allow_html=True)
        
        st.divider()
        st.subheader("System Verification")
        
        # Verify the columns for the upcoming invoice scanner integration
        columns = stock_df.columns.tolist()
        st.write("**Detected Columns:**", columns)
        
        # Prepare for data aggregation mapped via item code
        if "رمز المادة" in columns:
            st.info("✅ 'رمز المادة' (Item Code) detected. The upcoming invoice scanner will strictly map quantities using this code.")
        else:
            st.warning("⚠️ 'رمز المادة' not found in the uploaded file. Please ensure your Excel sheet contains this exact column header.")
        
    except Exception as e:
        st.error(f"Error reading the Excel file: {e}")
else:
    st.info("Please upload your daily stock report to begin.")
