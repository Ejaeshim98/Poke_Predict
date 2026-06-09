from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

from .env_loader import get_env

API_VERSION = "v1.39.0"
API_BASE = "https://api.tcgplayer.com"
POKEMON_CATEGORY_ID = 3
BATCH_SIZE = 100


class TCGplayerClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _credentials(self) -> tuple[str, str]:
        public_key = (
            get_env("TCGPLAYER_PUBLIC_KEY")
            or get_env("TCGPLAYER_CLIENT_ID")
            or get_env("TCGPLAYER_API_KEY")
        )
        private_key = (
            get_env("TCGPLAYER_PRIVATE_KEY")
            or get_env("TCGPLAYER_CLIENT_SECRET")
            or get_env("TCGPLAYER_API_SECRET")
        )
        if not public_key or not private_key:
            raise RuntimeError(
                "TCGplayer credentials incomplete. Add both keys to .env:\n"
                "TCGPLAYER_PUBLIC_KEY=your_public_key\n"
                "TCGPLAYER_PRIVATE_KEY=your_private_key"
            )
        return public_key, private_key

    def get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        public_key, private_key = self._credentials()
        response = requests.post(
            f"{API_BASE}/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": public_key,
                "client_secret": private_key,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + float(payload.get("expires_in", 3600))
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"bearer {self.get_token()}",
        }

    def fetch_product_prices(self, product_ids: list[int]) -> list[dict[str, Any]]:
        if not product_ids:
            return []

        results: list[dict[str, Any]] = []
        for start in range(0, len(product_ids), BATCH_SIZE):
            batch = product_ids[start : start + BATCH_SIZE]
            ids_csv = ",".join(str(pid) for pid in batch)
            url = f"{API_BASE}/{API_VERSION}/pricing/product/{ids_csv}"
            response = requests.get(url, headers=self._headers(), timeout=60)
            response.raise_for_status()
            payload = response.json()
            if payload.get("success"):
                results.extend(payload.get("results", []))
        return results


def has_api_credentials() -> bool:
    try:
        TCGplayerClient()._credentials()
        return True
    except RuntimeError:
        return False


def enrich_catalog_with_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill missing prices using TCGplayer product IDs when available.
    Expands one catalog row into one row per priced condition/subtype.
    """
    if "price" in df.columns and df["price"].notna().any():
        return df

    if "tcgplayer_id" not in df.columns:
        return df

    ids = (
        pd.to_numeric(df["tcgplayer_id"], errors="coerce")
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )
    if not ids:
        return df

    client = TCGplayerClient()
    price_rows = client.fetch_product_prices(ids)
    if not price_rows:
        return df

    price_df = pd.DataFrame(price_rows)
    price_df = price_df.rename(columns={"productId": "tcgplayer_id"})
    price_df["tcgplayer_id"] = price_df["tcgplayer_id"].astype(int)
    price_df["price"] = price_df["marketPrice"]
    price_df["condition"] = price_df["subTypeName"].astype(str).str.strip().str.lower()

    priced = price_df.dropna(subset=["price"]).copy()
    priced = priced[priced["price"] > 0]
    if priced.empty:
        return df

    base_cols = [c for c in df.columns if c not in {"price", "condition"}]
    merged = df[base_cols].merge(
        priced[["tcgplayer_id", "price", "condition"]],
        on="tcgplayer_id",
        how="inner",
    )
    return merged


def fetch_pokemon_prices_snapshot(limit: int = 250) -> pd.DataFrame:
    """
    Pull a Pokemon-only product search snapshot with current market prices.
    """
    client = TCGplayerClient()
    search_url = f"{API_BASE}/{API_VERSION}/catalog/categories/{POKEMON_CATEGORY_ID}/search"
    response = requests.post(
        search_url,
        headers={**client._headers(), "Content-Type": "application/json"},
        json={"limit": limit, "offset": 0, "filters": []},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    product_ids = payload.get("results", [])
    if not product_ids:
        return pd.DataFrame()

    products_url = (
        f"{API_BASE}/{API_VERSION}/catalog/products/"
        f"{','.join(str(pid) for pid in product_ids[:limit])}?getExtendedFields=true"
    )
    products_response = requests.get(products_url, headers=client._headers(), timeout=60)
    products_response.raise_for_status()
    products = products_response.json().get("results", [])

    price_rows = client.fetch_product_prices([int(p["productId"]) for p in products])
    price_map: dict[tuple[int, str], float] = {}
    for row in price_rows:
        market = row.get("marketPrice")
        if market is None or market <= 0:
            continue
        key = (int(row["productId"]), str(row.get("subTypeName", "normal")).strip().lower())
        price_map[key] = float(market)

    rows: list[dict[str, Any]] = []
    today = pd.Timestamp.utcnow().normalize()
    for product in products:
        product_id = int(product["productId"])
        extended = product.get("extendedData") or []
        ext = {item.get("name"): item.get("value") for item in extended if item.get("name")}
        card_number = ext.get("Number") or ext.get("Card Number") or ""
        card_name = product.get("name", "")
        set_name = product.get("group", {}).get("name") if isinstance(product.get("group"), dict) else ""

        for (pid, condition), price in price_map.items():
            if pid != product_id:
                continue
            rows.append(
                {
                    "date": today,
                    "card_name": card_name,
                    "set_name": set_name or "Unknown",
                    "card_number": str(card_number).strip(),
                    "condition": condition,
                    "price": price,
                    "variant": ext.get("Rarity", ""),
                    "expansion_code": "",
                    "tcgplayer_id": product_id,
                }
            )

    return pd.DataFrame(rows)
