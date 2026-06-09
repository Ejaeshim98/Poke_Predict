from __future__ import annotations

import numpy as np
import pandas as pd
import re

from .config import OPTIONAL_COLUMNS, REQUIRED_COLUMNS


def validate_columns(df: pd.DataFrame, *, require_price: bool = True) -> list[str]:
    required = list(REQUIRED_COLUMNS)
    if not require_price and "price" in required:
        required.remove("price")
    missing = [col for col in required if col not in df.columns]
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


def map_alias_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Best-effort mapping for CSVs that use different column names.
    """
    alias_map = {
        "date": ["date", "datetime", "timestamp", "modifiedOn", "updated_at"],
        "card_name": ["card_name", "name", "product_name", "title", "Name"],
        "set_name": ["set_name", "set", "expansion", "setCode", "group_name", "Expansion"],
        "card_number": ["card_number", "number", "collector_number", "extNumber", "Number"],
        "condition": ["condition", "subTypeName", "card_condition"],
        "price": ["price", "marketPrice", "market_price", "midPrice", "last_sold_price"],
        "variant": ["variant", "extRarity", "rarity", "print_variant", "Rarity"],
        "expansion_code": ["expansion_code", "set_code", "groupId", "Expansion Code"],
        "tcgplayer_id": ["tcgplayer_id", "TCGPlayer ID", "productId", "product_id"],
        "game": ["game", "Game", "category", "tcg"],
    }

    work = df.copy()
    cols_lower = {c.lower(): c for c in work.columns}

    def pick(alias_list: list[str]) -> str | None:
        for a in alias_list:
            if a in work.columns:
                return a
            if a.lower() in cols_lower:
                return cols_lower[a.lower()]
        return None

    for target, aliases in alias_map.items():
        if target in work.columns:
            continue
        source = pick(aliases)
        if source:
            work[target] = work[source]

    # Reasonable default when condition is missing in source data.
    if "condition" not in work.columns:
        work["condition"] = "normal"

    return work


def map_pokemon_catalog_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize catalog-style exports that list cards without prices or dates.
    """
    work = df.copy()
    catalog_markers = {"Name", "Expansion", "Game", "Number", "TCGPlayer ID"}
    is_catalog = bool(catalog_markers.intersection(work.columns)) or (
        {"card_name", "set_name", "tcgplayer_id"}.issubset(work.columns)
        and "price" not in work.columns
    )
    if not is_catalog:
        return work

    if "game" in work.columns:
        work = work[work["game"].astype(str).str.strip().str.lower() == "pokemon"].copy()

    if "variant" in work.columns:
        work = work[work["variant"].astype(str).str.strip().str.lower() != "sealed"].copy()

    if "date" not in work.columns:
        work["date"] = pd.Timestamp.utcnow().normalize()

    if "condition" not in work.columns:
        work["condition"] = "normal"

    return work


def normalize_csv_schema(df: pd.DataFrame) -> pd.DataFrame:
    work = map_alias_schema(df)
    work = map_tcgcsv_schema(work)
    work = map_pokemon_catalog_schema(work)
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


def looks_like_pokemon_card_row(df: pd.DataFrame) -> pd.Series:
    """
    Heuristic for TCGCSV exports: Pokemon cards usually contain Pokemon-specific
    stat fields like HP, stage, and attacks.
    """
    candidate_cols = [
        "extHP",
        "extStage",
        "extAttack1",
        "extAttack2",
        "extWeakness",
        "extResistance",
        "extRetreatCost",
    ]
    present = [c for c in candidate_cols if c in df.columns]
    if not present:
        # If we don't have any Pokemon-specific columns, don't filter.
        return pd.Series([True] * len(df), index=df.index)

    mask = pd.Series(False, index=df.index)
    for c in present:
        col = df[c]
        if col.dtype == object:
            mask = mask | col.astype(str).str.strip().ne("")
        else:
            # Numeric columns: keep non-null values
            mask = mask | col.notna()
    return mask


def prepare_data(df: pd.DataFrame, *, pokemon_only: bool = True) -> pd.DataFrame:
    df = normalize_csv_schema(df)

    if "price" not in df.columns:
        df = df.copy()
        df["price"] = pd.NA

    # Keep only expected columns plus known optional fields.
    keep_cols = [c for c in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if c in df.columns]
    if pokemon_only:
        df = df[looks_like_pokemon_card_row(df)].copy()

    work = df[keep_cols].copy()

    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["price"] = pd.to_numeric(work["price"], errors="coerce")
    work["condition"] = work["condition"].astype(str).str.strip().str.lower()
    work["card_name"] = work["card_name"].astype(str).str.strip()
    work["set_name"] = work["set_name"].astype(str).str.strip()
    work["card_number"] = work["card_number"].astype(str).str.strip()

    work = work.dropna(subset=["date", "price", "card_name", "set_name", "condition"])
    if work.empty:
        return work

    work = work[work["price"] > 0]
    work = work[work["card_number"].apply(has_valid_card_number)]
    work = work[~work["card_name"].str.contains("box", case=False, na=False)]
    if work.empty:
        return work

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
