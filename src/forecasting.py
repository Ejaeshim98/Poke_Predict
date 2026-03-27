from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


def forecast_series(series_df: pd.DataFrame, horizon: int, default_freq: str = "D") -> pd.DataFrame:
    """
    Forecast with trend on log-price and fallback to last value.
    Returns one row per forecast step with predicted_price.
    """
    series_df = series_df.sort_values("date").copy()
    y = series_df["price"].values
    n = len(y)

    if n < 3:
        last = float(y[-1]) if n else np.nan
        preds = [last] * horizon
    else:
        x = np.arange(n).reshape(-1, 1)
        model = LinearRegression()
        model.fit(x, np.log1p(y))
        future_x = np.arange(n, n + horizon).reshape(-1, 1)
        preds = np.expm1(model.predict(future_x))
        preds = np.maximum(preds, 0.01)

    last_date = series_df["date"].max()
    dates = pd.to_datetime(series_df["date"], errors="coerce").dropna().sort_values().drop_duplicates()
    inferred_freq = default_freq
    if len(dates) >= 3:
        maybe_freq = pd.infer_freq(dates)
        if maybe_freq:
            inferred_freq = maybe_freq
    future_dates = pd.date_range(
        start=last_date,
        periods=horizon + 1,
        freq=inferred_freq,
    )[1:]

    out = pd.DataFrame(
        {
            "date": future_dates,
            "predicted_price": preds,
        }
    )
    return out


def forecast_all(agg_df: pd.DataFrame, horizon: int, granularity: str = "daily") -> pd.DataFrame:
    rows = []
    default_freq = "D" if granularity == "daily" else "W-SUN"
    for series_id, g in agg_df.groupby("series_id"):
        if g["price"].notna().sum() < 1:
            continue
        pred = forecast_series(g[["date", "price"]], horizon=horizon, default_freq=default_freq)
        pred["series_id"] = series_id
        rows.append(pred)
    if not rows:
        return pd.DataFrame(columns=["date", "predicted_price", "series_id"])
    return pd.concat(rows, ignore_index=True)
