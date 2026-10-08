"""Load the workshop tables from a local folder or a URL (the participant files of DATASET-v3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pandas as pd

TABLES = [
    "declarations_h1", "declarations_h2", "features_lines", "trader_features", "importers", "brokers", "exporters", "consignees", "tariff", "offices", "fx_rates",
    "reference_prices", "accepted_history", "invoice_lines", "valuation_neighbours", "mirror_trade", "regional_unit_values", "sector_regional", "monthly_importer_uv",
    "tax_registry", "vat_returns", "importers_4b", "match_example_600", "licences", "warehouse_stock", "transit", "parcels", "land_border_mirror",
]
TEXT_COLUMNS = {"hs8", "hs6", "chapter", "tin", "tin_customs", "duty_cliff_neighbour", "month", "period", "certificate_ref", "exemption_code", "exporter_id", "consignee_id",
                "lane", "control_type", "outcome", "finding_type", "officer_id", "override_reason", "text_predicted_hs8", "query_id", "line_id"}
DATE_COLUMNS = {"declarations_h1": ["decl_date"], "declarations_h2": ["decl_date"], "accepted_history": ["accepted_on"], "invoice_lines": ["invoice_date"]}


def _read(base: str, name: str) -> pd.DataFrame:
    try:
        return pd.read_parquet(f"{base}/{name}.parquet")
    except (ImportError, OSError, ValueError):
        frame = pd.read_csv(f"{base}/{name}.csv", dtype={c: str for c in TEXT_COLUMNS}, keep_default_na=True)
        for col in TEXT_COLUMNS & set(frame.columns):
            if col not in ("lane", "control_type", "outcome", "finding_type", "officer_id", "override_reason"):
                frame[col] = frame[col].fillna("")
        return frame


def load_tables(base: str | Path, names: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """All (or some) participant tables; `base` is a folder or an https URL ending in data/participant."""
    base = str(base).rstrip("/")
    tables = {name: _read(base, name) for name in (names or TABLES)}
    for name, cols in DATE_COLUMNS.items():
        if name in tables:
            for col in cols:
                tables[name][col] = pd.to_datetime(tables[name][col])
    return tables


def load_declarations(base: str | Path) -> pd.DataFrame:
    """Both halves in one frame (lane and outcomes null where none exist)."""
    tables = load_tables(base, ["declarations_h1", "declarations_h2"])
    return pd.concat([tables["declarations_h1"], tables["declarations_h2"]], ignore_index=True)


def load_json(base: str | Path, name: str) -> Any:
    path = f"{str(base).rstrip('/')}/{name}.json"
    if path.startswith("http"):
        with urlopen(path) as response:  # noqa: S310 - the workshop's own public data
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(path).read_text(encoding="utf-8"))
