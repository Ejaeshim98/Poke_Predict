from __future__ import annotations

import numpy as np
import pandas as pd
import re

from .config import OPTIONAL_COLUMNS, REQUIRED_COLUMNS


def validate_columns(df: pd.DataFrame) -> list[str]:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    return missing


def map_tcgcsv_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map TCGCSV export columns to the app's canonical schema.
    """
    if "modifiedOn" not in df.columns or "marketPrice" not in df.columns:
        return df

    work = df.copy()
    if "date" not in work.columns:
        work["date"] = work["modifiedOn"]
    if "card_name" not in work.columns:
        work["card_name"] = work.get("name", "")
    if "set_name" not in work.columns:
        # Best-effort set field for single-expansion CSVs.
        work["set_name"] = work.get("groupId", "").astype(str)
    if "card_number" not in work.columns:
        work["card_number"] = work.get("extNumber", "")
    if "condition" not in work.columns:
        work["condition"] = work.get("subTypeName", "normal")
    if "price" not in work.columns:
        work["price"] = work["marketPrice"]
    if "variant" not in work.columns:
        work["variant"] = work.get("extRarity", "")
    if "expansion_code" not in work.columns:
        work["expansion_code"] = work.get("groupId", "")
    return work


def normalize_variant(value: str) -> str:
    if not isinstance(value, str):
        return "unknown"

    v = value.strip().lower()
    if "1st" in v or "first edition" in v or "1st edition" in v:
        return "first_edition"
    if "shadowless" in v:
        return "shadowless"
    if "unlimited" in v:
        return "unlimited"
    if "reverse holo" in v or "reverse" in v:
        return "reverse_holo"
    if "holo" in v:
        return "holo"
    return v.replace(" ", "_")


def infer_variant_from_number(card_number: str) -> str:
    if not isinstance(card_number, str):
        return "unknown"
    n = card_number.strip().upper()
    if n.startswith("TG") or n.startswith("GG"):
        return "trainer_gallery_or_galarian_gallery"
    if "/" in n and n.split("/")[0].isdigit():
        return "standard_numbered"
    if any(ch.isalpha() for ch in n) and any(ch.isdigit() for ch in n):
        return "promo_or_special_numbered"
    return "unknown"


def build_variant_column(df: pd.DataFrame) -> pd.Series:
    if "variant" in df.columns:
        base_variant = df["variant"].apply(normalize_variant)
    else:
        base_variant = pd.Series(["unknown"] * len(df), index=df.index)

    inferred = df["card_number"].astype(str).apply(infer_variant_from_number)
    return np.where(base_variant == "unknown", inferred, base_variant)


def has_valid_card_number(value: str) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip().upper()
    if not v:
        return False
    # Typical Pokemon card number formats:
    # - 166/203
    # - TG23/TG30
    # - GG45/GG70
    # - SVP123
    patterns = [
        r"^\d+[A-Z]?/\d+[A-Z]?$",
        r"^(TG|GG)\d+/(TG|GG)\d+$",
        r"^SVP\d+$",
    ]
    return any(re.match(p, v) for p in patterns)


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    df = map_tcgcsv_schema(df)

    # Keep only expected columns plus known optional fields.
    keep_cols = [c for c in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if c in df.columns]
    work = df[keep_cols].copy()

    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["price"] = pd.to_numeric(work["price"], errors="coerce")
    work["condition"] = work["condition"].astype(str).str.strip().str.lower()
    work["card_name"] = work["card_name"].astype(str).str.strip()
    work["set_name"] = work["set_name"].astype(str).str.strip()
    work["card_number"] = work["card_number"].astype(str).str.strip()

    work = work.dropna(subset=["date", "price", "card_name", "set_name", "condition"])
    work = work[work["price"] > 0]
    work = work[work["card_number"].apply(has_valid_card_number)]
    work = work[~work["card_name"].str.contains("box", case=False, na=False)]

    work["variant"] = build_variant_column(work)

    # Unique market entity key: each card print and condition has a distinct price curve.
    work["series_id"] = (
        work["card_name"]
        + "|"
        + work["set_name"]
        + "|"
        + work["card_number"]
        + "|"
        + work["variant"]
        + "|"
        + work["condition"]
    )

    # Unique card key ignores condition for top-10 uniqueness constraint.
    work["unique_card_id"] = (
        work["card_name"]
        + "|"
        + work["set_name"]
        + "|"
        + work["card_number"]
        + "|"
        + work["variant"]
    )
    return work.sort_values("date")


def remove_outliers_iqr(df: pd.DataFrame) -> pd.DataFrame:
    # Filter outliers within each series so one bad sale does not distort trend.
    def _filter(group: pd.DataFrame) -> pd.DataFrame:
        if len(group) < 6:
            return group
        q1 = group["price"].quantile(0.25)
        q3 = group["price"].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        return group[(group["price"] >= lower) & (group["price"] <= upper)]

    # Keep grouping columns in output so downstream aggregation can group by series_id.
    return df.groupby("series_id", group_keys=False).apply(_filter).reset_index(drop=True)


def aggregate_granularity(df: pd.DataFrame, granularity: str) -> pd.DataFrame:
    if granularity == "daily":
        freq = "D"
    else:
        # Week ending Sunday for easier dashboard interpretation.
        freq = "W-SUN"

    g = (
        df.set_index("date")
        .groupby("series_id")
        .resample(freq)["price"]
        .median()
        .reset_index()
    )
    return g.sort_values(["series_id", "date"])
