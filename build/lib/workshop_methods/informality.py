"""4B: match customs to tax with and without the identifier, the dial, and the four buckets.

Plain words -> technical: matching records -> record linkage; the dial -> match threshold
(precision/recall); probable match -> probabilistic linkage with blocking.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

LEGAL_SUFFIXES = r"\b(co|company|ltd|limited|llc|inc|plc|pte|sdn|bhd|jsc|pvt|group|holdings|intl|international|enterprises|corp|corporation|sons)\b"
ADDRESS_WORDS = {"road": "rd", "street": "st", "lane": "ln"}


def normalise_name(name: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    text = re.sub(LEGAL_SUFFIXES, " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalise_address(address: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", str(address).lower())
    text = re.sub(r"\bunit \d+\b", " ", text)
    for long, short in ADDRESS_WORDS.items():
        text = re.sub(rf"\b{long}\b", short, text)
    return re.sub(r"\s+", " ", text).strip()


def exact_match(importers: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """Join on the TIN customs holds; give the reason for every miss."""
    tins = set(registry["tin"])

    def one_char_off(tin: str) -> bool:
        return any(len(t) == len(tin) and sum(a != b for a, b in zip(t, tin)) == 1 for t in tins)

    def reason(tin: str) -> str:
        if not tin:
            return "blank TIN"
        if tin in tins:
            return "matched"
        if one_char_off(tin):
            return "TIN one character off"
        return "not in registry"

    return importers.assign(exact_status=importers["tin"].fillna("").map(reason))


def probable_scores(importers: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """Score customs-registry pairs: name similarity plus exact bonuses on address, phone and director, blocked on name start and district."""
    cust = importers.assign(norm=importers["legal_name"].map(normalise_name), trade_norm=importers["trading_name"].fillna("").map(normalise_name),
                            addr=importers["address_line"].fillna("").map(normalise_address))
    reg = registry.rename(columns={"tin": "matched_tin"}).assign(norm=registry["legal_name"].map(normalise_name), addr=registry["address_line"].fillna("").map(normalise_address))
    cust["block"] = cust["norm"].str[:3] + "|" + cust["district"]
    reg["block"] = reg["norm"].str[:3] + "|" + reg["district"]
    pairs = cust.merge(reg, on="block", suffixes=("_c", "_r"))
    name = np.maximum([fuzz.token_set_ratio(a, b) for a, b in zip(pairs["norm_c"], pairs["norm_r"])], [fuzz.token_set_ratio(a, b) for a, b in zip(pairs["trade_norm"], pairs["norm_r"])])
    bonus = ((pairs["addr_c"] == pairs["addr_r"]) & (pairs["addr_c"] != "")).astype(int) * 10 + (pairs["phone_c"] == pairs["phone_r"]).astype(int) * 10 \
        + (pairs["director_name_c"] == pairs["director_name_r"]).astype(int) * 10
    pairs["score"] = np.minimum(100, name * 0.7 + bonus)
    best = pairs.sort_values("score", ascending=False).drop_duplicates("importer_id")
    return best[["importer_id", "matched_tin", "legal_name_c", "legal_name_r", "score"]]


def dial(scores: pd.DataFrame, truth: pd.Series, thresholds: range = range(50, 101)) -> pd.DataFrame:
    """Found / wrong / missed at each threshold against the known true TIN of each importer."""
    rows = []
    has_truth = truth.dropna()
    for t in thresholds:
        accepted = scores[scores["score"] >= t].set_index("importer_id")["matched_tin"]
        right = sum(accepted.get(r) == tin for r, tin in has_truth.items())
        rows.append({"threshold": t, "found": int(right), "wrong": int(len(accepted) - right), "missed": int(len(has_truth) - right)})
    return pd.DataFrame(rows)


def buckets(importers: pd.DataFrame, registry: pd.DataFrame, returns: pd.DataFrame, periods: list[str], markup: float = 1.25, gap_periods: int = 6) -> pd.DataFrame:
    """unregistered / not filing / under-reporting / consistent for matched importers.

    `importers` needs importer_id, matched_tin (blank when no match) and import_value_12m.
    """
    reg = registry.set_index("tin")
    recent, last12 = periods[-gap_periods:], periods[-12:]
    filed = returns[returns["period"].isin(recent) & (returns["filed"] == 1)].groupby("tin").size()
    sales = returns[returns["period"].isin(last12) & (returns["filed"] == 1)].groupby("tin")["sales_lcu"].sum()
    out = []
    for row in importers.itertuples(index=False):
        tin = row.matched_tin
        if not tin or tin not in reg.index or not bool(reg.at[tin, "vat_registered"]):
            bucket, reason = "unregistered", "no registry match or not VAT-registered"
        elif filed.get(tin, 0) < gap_periods - 1:
            bucket, reason = "not filing", f"{gap_periods - int(filed.get(tin, 0))} of the last {gap_periods} returns missing"
        elif sales.get(tin, 0) < row.import_value_12m * markup:
            bucket, reason = "under-reporting", f"sales {sales.get(tin, 0) / max(row.import_value_12m, 1):.2f}x imports (expected at least {markup}x)"
        else:
            bucket, reason = "consistent", "sales consistent with imports"
        out.append({"importer_id": row.importer_id, "bucket": bucket, "reason": reason})
    return pd.DataFrame(out)
