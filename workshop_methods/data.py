"""Load the workshop tables from a local folder or a URL (the public repo's data/outputs)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pandas as pd

TABLES = [
    "declarations", "traders", "brokers", "exporters", "consignees", "tariff", "reference_prices", "fx_rates", "offices",
    "mirror_trade", "tax_registry", "vat_returns", "warehouse_stock", "transit", "parcels", "licences",
    "land_border_mirror", "regional_unit_values", "sector_regional", "monthly_trader_uv", "accepted_history", "invoice_lines",
]
TEXT_COLUMNS = {"ahtn8", "hs6", "chapter", "trader_id", "tin", "duty_cliff_neighbour", "month", "period", "certificate_ref", "relief_scheme", "exporter_id", "consignee_id"}


def _read(base: str, name: str) -> pd.DataFrame:
    try:
        return pd.read_parquet(f"{base}/{name}.parquet")
    except (ImportError, OSError, ValueError):
        frame = pd.read_csv(f"{base}/{name}.csv", dtype={c: str for c in TEXT_COLUMNS}, keep_default_na=True)
        for col in TEXT_COLUMNS & set(frame.columns):
            frame[col] = frame[col].fillna("")
        return frame


def load_tables(base: str | Path, names: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """All (or some) workshop tables; `base` is a folder or an https URL ending in data/outputs."""
    base = str(base).rstrip("/")
    tables = {name: _read(base, name) for name in (names or TABLES)}
    if "declarations" in tables:
        tables["declarations"]["declaration_date"] = pd.to_datetime(tables["declarations"]["declaration_date"])
    return tables


def load_json(base: str | Path, name: str) -> Any:
    path = f"{str(base).rstrip('/')}/{name}.json"
    if path.startswith("http"):
        with urlopen(path) as response:  # noqa: S310 - the workshop's own public data
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(path).read_text(encoding="utf-8"))
