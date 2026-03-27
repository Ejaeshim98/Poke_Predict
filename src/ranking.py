from __future__ import annotations

import pandas as pd


def split_series_id(series_id: pd.Series) -> pd.DataFrame:
    parts = series_id.str.split("|", expand=True)
    parts.columns = ["card_name", "set_name", "card_number", "variant", "condition"]
    return parts.reset_index(drop=True)


def build_unique_card_id(df: pd.DataFrame) -> pd.Series:
    return (
        df["card_name"]
        + "|"
        + df["set_name"]
        + "|"
        + df["card_number"]
        + "|"
        + df["variant"]
    )


def top_10_unique_cards(pred_df: pd.DataFrame) -> pd.DataFrame:
    # Use the latest forecast point for each series so mixed source timestamps
    # still produce a full ranking.
    day = (
        pred_df.sort_values(["series_id", "date"])
        .groupby("series_id", as_index=False)
        .tail(1)
        .copy()
    )
    day = day[day["predicted_price"].notna()]
    if day.empty:
        return pd.DataFrame(columns=pred_df.columns.tolist())

    meta = split_series_id(day["series_id"])
    day = pd.concat([day.reset_index(drop=True), meta], axis=1)
    day["unique_card_id"] = build_unique_card_id(day)

    # Keep the highest predicted condition per unique card to avoid duplicates.
    day = (
        day.sort_values("predicted_price", ascending=False)
        .groupby("unique_card_id", as_index=False)
        .first()
    )
    day = day.sort_values("predicted_price", ascending=False).head(10)
    return day.reset_index(drop=True)
