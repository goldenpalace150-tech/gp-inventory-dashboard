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
        
        # BYPASS CRASH: Convert dataframe to a raw HTML string
        # This completely avoids the PyArrow memory crash in GitHub Codespaces
        html_table = stock_df.to_html(index=False)
        st.markdown(html_table, unsafe_allow_html=True)
        
        # Display detected columns
        st.write("**Detected Columns:**")
        st.write(stock_df.columns.tolist())
        
    except Exception as e:
        st.error(f"Error reading the Excel file: {e}")
else:
    st.info("Please upload your daily stock report to begin.")
