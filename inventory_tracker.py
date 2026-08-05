import streamlit as st
import pandas as pd

st.set_page_config(page_title="Golden Palace Inventory", layout="wide")
st.title("Golden Palace - Daily Inventory Tracker")

st.header("Upload Daily Stock Report")

# Create the file uploader widget
uploaded_stock_report = st.file_uploader("Upload your Excel stock report (.xlsx)", type=["xlsx", "xls"])

if uploaded_stock_report is not None:
    try:
        # Read the Excel file
        stock_df = pd.read_excel(uploaded_stock_report)
        st.success("Stock report loaded successfully!")
        
        st.subheader("Current Stock Overview")
        
        # Display interactive table
        st.dataframe(stock_df, use_container_width=True)
        
        # Display the column names to verify mapping
        st.write("**Detected Columns:**", stock_df.columns.tolist())
        
    except Exception as e:
        st.error(f"Error reading the Excel file: {e}")
else:
    st.info("Please upload your daily stock report to begin.")
