from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from src.config import REQUIRED_COLUMNS, VALID_GRANULARITIES
from src.env_loader import load_env
from src.data_processing import (
    aggregate_granularity,
    map_alias_schema,
    map_tcgcsv_schema,
    prepare_data,
    remove_outliers_iqr,
    validate_columns,
)
from src.forecasting import forecast_all
from src.ranking import top_10_unique_cards

load_env()

st.set_page_config(page_title="Pokemon Card Price Forecast", layout="wide")
st.title("Pokemon Card Market Forecast")
st.caption(
    "Upload CSV data and forecast top 10 unique cards over a 30-day window."
)

with st.sidebar:
    st.header("Configuration")
    granularity = st.selectbox("Granularity", options=sorted(VALID_GRANULARITIES), index=0)
    horizon = st.slider("Forecast horizon", min_value=7, max_value=30, value=30, step=1)
    apply_outlier_filter = st.checkbox("Enable outlier filtering (IQR)", value=True)
    pokemon_only = st.checkbox("Pokemon-only filter", value=True)

    st.markdown("### Expected CSV columns")
    st.code(", ".join(REQUIRED_COLUMNS))
    st.caption("Optional columns: variant, expansion_code")

uploaded_file = st.file_uploader("Upload card price CSV", type=["csv"])

if not uploaded_file:
    st.info("Upload a CSV to begin.")
    st.stop()

raw = pd.read_csv(uploaded_file)
mapped_raw = map_alias_schema(raw)
mapped_raw = map_tcgcsv_schema(mapped_raw)

# For TCGCSV product exports, keep likely physical cards and exclude code card listings.
if "extCardType" in raw.columns:
    non_empty_card_type = raw["extCardType"].astype(str).str.strip().ne("")
    not_code_card = ~mapped_raw["card_name"].astype(str).str.contains("code card", case=False, na=False)
    mapped_raw = mapped_raw[non_empty_card_type & not_code_card].copy()

missing = validate_columns(mapped_raw)
if missing:
    st.error(f"Missing required columns: {missing}")
    st.caption("Detected CSV columns:")
    st.code(", ".join(raw.columns.astype(str).tolist()))
    st.stop()

data = prepare_data(mapped_raw, pokemon_only=pokemon_only)
st.subheader("Data Quality")
col1, col2, col3 = st.columns(3)
col1.metric("Rows loaded", f"{len(raw):,}")
col2.metric("Rows after cleaning", f"{len(data):,}")
col3.metric("Distinct series", f"{data['series_id'].nunique():,}")

distinct_dates = data["date"].nunique()
if distinct_dates < 8:
    st.warning(
        "This file has limited historical dates. Forecast output will be low-confidence "
        "until you upload multiple snapshots over time."
    )

if apply_outlier_filter:
    clean_data = remove_outliers_iqr(data)
else:
    clean_data = data.copy()

st.metric("Rows after outlier step", f"{len(clean_data):,}")

agg = aggregate_granularity(clean_data, granularity=granularity)
pred = forecast_all(agg, horizon=horizon, granularity=granularity)

if pred.empty:
    st.warning("Not enough data to forecast.")
    st.stop()

top10 = top_10_unique_cards(pred)

st.subheader("Top 10 Unique Cards (latest forecast point per card)")
display_cols = [
    "card_name",
    "set_name",
    "card_number",
    "variant",
    "condition",
    "predicted_price",
]
if top10.empty:
    st.warning("No top-10 result available for the selected settings.")
else:
    display_df = top10[display_cols].copy()
    display_df = display_df.rename(columns=lambda c: c.replace("_", " ").title())
    st.dataframe(
        display_df,
        column_config={
            "Predicted Price": st.column_config.NumberColumn(
                "Predicted Price",
                format="%.2f",
            )
        },
        hide_index=True,
        use_container_width=True,
    )

st.subheader("Trend Preview (Top 5 by forecast)")
for _, row in top10.head(5).iterrows():
    sid = row["series_id"]
    hist = agg[agg["series_id"] == sid][["date", "price"]].copy()
    fut = pred[pred["series_id"] == sid][["date", "predicted_price"]].copy()
    fut = fut.rename(columns={"predicted_price": "price"})
    chart_df = pd.concat([hist.assign(kind="history"), fut.assign(kind="forecast")])
    st.markdown(
        f"**{row['card_name']}** ({row['set_name']} #{row['card_number']}, {row['condition']})"
    )
    st.line_chart(chart_df.set_index("date")["price"])

csv_out = top10[display_cols].to_csv(index=False).encode("utf-8")
st.download_button(
    "Download Top 10 Forecast CSV",
    data=csv_out,
    file_name="top10_forecast.csv",
    mime="text/csv",
)

report = io.StringIO()
report.write("Pokemon Card Forecast Report\n")
report.write(f"Granularity: {granularity}\n")
report.write(f"Horizon: {horizon} days\n")
report.write("Forecast date: latest available per card series\n")
report.write(f"Rows used: {len(clean_data)}\n")
report.write("Top 10 unique cards by predicted price:\n")
if top10.empty:
    report.write("No results.\n")
else:
    report.write(top10[display_cols].to_string(index=False))
report_bytes = report.getvalue().encode("utf-8")

st.download_button(
    "Download Text Report",
    data=report_bytes,
    file_name="forecast_report.txt",
    mime="text/plain",
)
