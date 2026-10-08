"""Plenary 8: the customs questions, each one query and one number, on the version-3 tables."""

from __future__ import annotations

import pandas as pd

from .peer import peer_values
from .signals import units_consistent

HOME_USE = ("home_use", "warehouse_out")


def _last12(lines: pd.DataFrame) -> pd.DataFrame:
    return lines[lines["month"] > str(pd.Period(lines["month"].max(), freq="M") - 12)]


def duty_at_stake(lines: pd.DataFrame, tariff: pd.DataFrame, threshold: float = 0.70) -> pd.DataFrame:
    """Valuation leakage: (typical - declared) x weight x duty rate, for home-use lines below `threshold` of peers,
    after the units check (a weight keyed in the wrong unit makes the gap absurd)."""
    home = lines[lines["regime"].isin(HOME_USE)]
    home = home[units_consistent(home, tariff)]
    peers = peer_values(home, home)
    low = home[peers["ratio_to_peers"] < threshold]
    stake = (peers.loc[low.index, "peer_median"] - peers.loc[low.index, "unit_value"]) * low["net_kg"] * low["duty_rate"] / 100
    return low.assign(duty_at_stake=stake.round(0), ratio_to_peers=peers.loc[low.index, "ratio_to_peers"].round(3))


def relief_overuse(lines: pd.DataFrame, licences: pd.DataFrame) -> pd.DataFrame:
    """Relieved value per beneficiary over the last 12 months against its licence limit."""
    exempt = _last12(lines[lines["regime"] == "home_use_exempt"])
    used = exempt.groupby("importer_id")["customs_value_lcu"].sum().rename("relief_value_12m")
    out = licences.merge(used, left_on="importer_id", right_index=True, how="left").fillna({"relief_value_12m": 0})
    out["use_of_limit"] = (out["relief_value_12m"] / out["licence_limit_lcu"]).round(2)
    return out.sort_values("use_of_limit", ascending=False)


def foregone_duty(lines: pd.DataFrame, tariff: pd.DataFrame) -> pd.Series:
    """Duty foregone under each relief scheme (customs value x MFN duty)."""
    exempt = lines[lines["regime"] == "home_use_exempt"]
    mfn = exempt["hs8"].map(tariff.set_index("hs8")["duty_mfn"])
    return exempt.assign(foregone=(exempt["customs_value_lcu"] * mfn / 100).round(0)).groupby("exemption_code")["foregone"].sum().sort_values(ascending=False)


def import_vat_lists(lines: pd.DataFrame, importers: pd.DataFrame, registry: pd.DataFrame, returns: pd.DataFrame, threshold: float = 1_500_000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """List 1: importers above the VAT threshold with no registry match. List 2: import VAT credit claimed on returns minus import VAT paid at the border."""
    home = _last12(lines[lines["regime"].isin(HOME_USE)])
    by = home.groupby("importer_id").agg(import_value_12m=("customs_value_lcu", "sum"), import_vat_paid=("vat_lcu", "sum"))
    by["customs_tin"] = importers.set_index("importer_id")["tin"].reindex(by.index).fillna("")
    reg = registry.set_index("tin")
    by["registered"] = by["customs_tin"].map(lambda x: bool(x) and x in reg.index and bool(reg.at[x, "vat_registered"]))
    list1 = by[(by["import_value_12m"] > threshold) & ~by["registered"]].sort_values("import_value_12m", ascending=False)
    periods = sorted(returns["period"].unique())[-12:]
    credit = returns[(returns["period"].isin(periods)) & (returns["filed"] == 1)].groupby("tin")["import_vat_credit_lcu"].sum()
    by["import_vat_credit"] = by["customs_tin"].map(credit)
    by["credit_minus_paid"] = (by["import_vat_credit"] - by["import_vat_paid"]).round(0)
    by["credit_to_paid"] = (by["import_vat_credit"] / by["import_vat_paid"].replace(0, float("nan"))).round(2)
    list2 = by.dropna(subset=["import_vat_credit"]).sort_values("credit_minus_paid", ascending=False)
    return list1, list2


def non_filers(returns: pd.DataFrame, importers: pd.DataFrame, lines: pd.DataFrame, periods: int = 6) -> pd.DataFrame:
    """Registered importers with unfiled returns in the last `periods`, with their 12-month import value."""
    recent = sorted(returns["period"].unique())[-periods:]
    missing = returns[returns["period"].isin(recent) & (returns["filed"] == 0)].groupby("tin").size().rename("missing_returns")
    value = _last12(lines[lines["regime"].isin(HOME_USE)]).groupby("importer_id")["customs_value_lcu"].sum().rename("import_value_12m")
    out = importers[["importer_id", "tin", "legal_name"]].merge(missing, left_on="tin", right_index=True).merge(value, left_on="importer_id", right_index=True, how="left")
    return out.sort_values("import_value_12m", ascending=False)
