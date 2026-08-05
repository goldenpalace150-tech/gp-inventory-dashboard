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
        # Read the Excel file, skipping the first row (header=1) to grab the correct column names
        stock_df = pd.read_excel(uploaded_stock_report, header=1)
        
        # Filter down strictly to the required columns
        stock_df = stock_df[['رمز المادة', 'اسم المادة', 'الكمية']]
        
        # Clean up any trailing empty rows from the bottom of the Excel sheet
        stock_df = stock_df.dropna(subset=['رمز المادة'])

        st.success("Stock report loaded and filtered successfully!")
        
        st.subheader("Current Stock Overview")
        
        # Display the cleaned table safely using HTML
        html_table = stock_df.to_html(index=False)
        st.markdown(html_table, unsafe_allow_html=True)
        
    except KeyError:
        st.error("Error: Could not find the exact column names. Please ensure the second row contains 'رمز المادة', 'اسم المادة', and 'الكمية'.")
    except Exception as e:
        st.error(f"Error reading the Excel file: {e}")
else:
    st.info("Please upload your daily stock report to begin.")
