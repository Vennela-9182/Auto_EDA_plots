import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import os
import tempfile

def shorten_labels(series, max_len=15):
    return pd.Series(series).apply(lambda x: str(x) if len(str(x)) <= max_len else str(x)[:max_len] + "...")

def save_plot_as_image(fig):
    return fig.to_image(format="png")

def store_in_database(plot_bytes, plot_name):
    conn = sqlite3.connect("plots.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS plots (name TEXT, image BLOB)''')
    c.execute("INSERT INTO plots (name, image) VALUES (?, ?)", (plot_name, plot_bytes))
    conn.commit()
    conn.close()

def load_data(file):
    ext = os.path.splitext(file.name)[1]

    if ext == ".csv":
        return pd.read_csv(file)
    elif ext in [".xlsx", ".xls"]:
        return pd.read_excel(file)
    elif ext in [".db", ".sqlite"]:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(file.read())
            tmp_file_path = tmp_file.name
        conn = sqlite3.connect(tmp_file_path)
        tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)
        if tables.empty:
            st.error("No tables found in the database.")
            return None
        table_name = st.selectbox("Select a table to load:", tables['name'].tolist())
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        conn.close()
        return df
    else:
        st.error("Unsupported file format")
        return None

# 🛠️ Added Data Cleaning Step
def clean_data(df):
    df_cleaned = df.copy()
    total_rows = len(df_cleaned)

    for col in df_cleaned.columns:
        missing_count = df_cleaned[col].isnull().sum()
        missing_percent = (missing_count / total_rows) * 100

        if missing_percent < 5:
            if df_cleaned[col].dtype in ['int64', 'float64']:
                df_cleaned[col] = df_cleaned[col].fillna(0)
            else:
                df_cleaned[col] = df_cleaned[col].fillna("None")

        elif missing_percent < 40:
            if df_cleaned[col].dtype in ['int64', 'float64']:
                mean_value = df_cleaned[col].mean()
                df_cleaned[col] = df_cleaned[col].fillna(mean_value)
            # if categorical with missing <40%, do nothing

        else:
            df_cleaned = df_cleaned.drop(columns=[col])

    return df_cleaned

def visualize_column_pair(df):
    cols = st.multiselect("Select 1 or 2 columns for visualization", df.columns.tolist())

    if len(cols) == 1:
        col = cols[0]
        dtype = df[col].dtype

        if dtype in ['int64', 'float64']:
            series = df[col]
            if len(series) > 1000:
                series = series.sample(1000).sort_index()
            if len(series) > 100:
                series = series.rolling(window=5).mean()
            fig1 = px.line(x=series.index, y=series, title=f"Line Plot: {col}")
            st.plotly_chart(fig1)
            store_in_database(save_plot_as_image(fig1), f"Line Plot: {col}")

            fig2 = px.histogram(df, x=col, nbins=50, title=f"Histogram: {col}")
            st.plotly_chart(fig2)
            store_in_database(save_plot_as_image(fig2), f"Histogram: {col}")

        elif dtype in ['object', 'category']:
            counts = df[col].value_counts().head(10)
            counts.index = shorten_labels(counts.index)
            fig = px.bar(x=counts.index, y=counts.values, title=f"Bar Chart: {col}")
            st.plotly_chart(fig)
            store_in_database(save_plot_as_image(fig), f"Bar Chart: {col}")

            pie_fig = px.pie(names=counts.index, values=counts.values, title=f"Pie Chart: {col}")
            st.plotly_chart(pie_fig)
            store_in_database(save_plot_as_image(pie_fig), f"Pie Chart: {col}")

    elif len(cols) == 2:
        col1, col2 = cols
        dtype1, dtype2 = df[col1].dtype, df[col2].dtype

        if dtype1 in ['int64', 'float64'] and dtype2 in ['int64', 'float64']:
            fig = px.scatter(df, x=col1, y=col2, title=f"Scatter Plot: {col1} vs {col2}")
            st.plotly_chart(fig)
            store_in_database(save_plot_as_image(fig), f"Scatter Plot: {col1} vs {col2}")

        elif (dtype1 in ['object', 'category'] and dtype2 in ['int64', 'float64']) or \
             (dtype2 in ['object', 'category'] and dtype1 in ['int64', 'float64']):
            if dtype1 in ['object', 'category']:
                cat_col, num_col = col1, col2
            else:
                cat_col, num_col = col2, col1

            counts = df[cat_col].value_counts().head(10).index
            filtered_df = df[df[cat_col].isin(counts)]
            short_labels = shorten_labels(filtered_df[cat_col])
            filtered_df[cat_col + "_short"] = short_labels

            fig = px.box(filtered_df, x=cat_col + "_short", y=num_col, title=f"Box Plot: {num_col} by {cat_col}")
            st.plotly_chart(fig)
            store_in_database(save_plot_as_image(fig), f"Box Plot: {num_col} by {cat_col}")

        elif dtype1 in ['object', 'category'] and dtype2 in ['object', 'category']:
            top_cat1 = df[col1].value_counts().head(10).index
            top_cat2 = df[col2].value_counts().head(10).index
            filtered_df = df[df[col1].isin(top_cat1) & df[col2].isin(top_cat2)]

            short_labels1 = shorten_labels(filtered_df[col1])
            short_labels2 = shorten_labels(filtered_df[col2])
            filtered_df[col1 + "_short"] = short_labels1
            filtered_df[col2 + "_short"] = short_labels2

            cross_tab = filtered_df.groupby([col1 + "_short", col2 + "_short"]).size().reset_index(name='Count')
            fig = px.bar(cross_tab, x=col1 + "_short", y='Count', color=col2 + "_short",
                         title=f"Grouped Bar Chart: {col1} vs {col2}")
            st.plotly_chart(fig)
            store_in_database(save_plot_as_image(fig), f"Grouped Bar Chart: {col1} vs {col2}")

# Streamlit App
st.set_page_config(layout="wide")
st.title("📊 Automated EDA + Plot Storage + Cleaning")

uploaded_file = st.file_uploader("Upload your dataset", type=["csv", "xlsx", "xls", "db", "sqlite"])

if uploaded_file:
    df = load_data(uploaded_file)
    if df is not None:
        st.success("✅ Data loaded successfully!")

        # 🧹 Clean the data after loading
        df = clean_data(df)

        st.subheader("🔍 Preview of Cleaned Data")
        st.dataframe(df.head())

        visualize_column_pair(df)
                # ⬇️ Add this code after all visualizations are done
        if os.path.exists("plots.db"):
            with open("plots.db", "rb") as f:
                st.download_button(
                    label="📥 Download Plots Database",
                    data=f,
                    file_name="plots.db",
                    mime="application/octet-stream"
        )
