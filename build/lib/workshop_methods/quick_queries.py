"""Plenary 8: three customs questions, each one query and one number."""

from __future__ import annotations

import pandas as pd

from .peer import peer_values
from .signals import units_consistent


def duty_at_stake(declarations: pd.DataFrame, tariff: pd.DataFrame, threshold: float = 0.70) -> pd.DataFrame:
    """Valuation leakage: (typical - declared) x weight x duty rate, for lines below `threshold` of peers.

    Lines whose weight disagrees with their quantity are dropped first: a weight keyed in the
    wrong unit makes the value per kilo, and so the gap, absurd.
    """
    imp = declarations[(declarations["flow"] == "import") & (declarations["procedure"] == "IM4")]
    imp = imp[units_consistent(imp, tariff)]
    peers = peer_values(imp, imp)
    low = imp[peers["ratio_to_peers"] < threshold]
    stake = (peers.loc[low.index, "peer_median"] - peers.loc[low.index, "unit_value"]) * low["net_weight_kg"] * low["duty_rate"] / 100
    return low.assign(duty_at_stake=stake.round(0), ratio_to_peers=peers.loc[low.index, "ratio_to_peers"].round(3))


def relief_overuse(declarations: pd.DataFrame, licences: pd.DataFrame) -> pd.DataFrame:
    """Duty foregone under each relief scheme, and beneficiaries above their licence limit (last 12 months)."""
    imp = declarations[(declarations["relief_scheme"] != "") & (declarations["flow"] == "import")]
    last12 = imp[imp["month"] > str(pd.Period(declarations["month"].max(), freq="M") - 12)]
    used = last12.groupby("trader_ref")["customs_value_lcu"].sum().rename("relief_value_12m")
    out = licences.merge(used, left_on="beneficiary_ref", right_index=True, how="left").fillna({"relief_value_12m": 0})
    out["use_of_limit"] = (out["relief_value_12m"] / out["licence_limit_lcu"]).round(2)
    return out.sort_values("use_of_limit", ascending=False)


def relief_excess_duty(declarations: pd.DataFrame, tariff: pd.DataFrame, licences: pd.DataFrame) -> float:
    """Duty foregone, over the last 12 months, on the part of each beneficiary's relief beyond its licence limit."""
    use = relief_overuse(declarations, licences).set_index("beneficiary_ref")
    over = use[use["use_of_limit"] > 1]
    imp = declarations[(declarations["relief_scheme"] != "") & (declarations["flow"] == "import")]
    last12 = imp[imp["month"] > str(pd.Period(declarations["month"].max(), freq="M") - 12)]
    foregone = (last12["customs_value_lcu"] * last12["ahtn8"].map(tariff.set_index("ahtn8")["duty_mfn"]) / 100).groupby(last12["trader_ref"]).sum()
    return float(sum(foregone.get(b, 0.0) * (1 - 1 / row["use_of_limit"]) for b, row in over.iterrows()))


def foregone_duty(declarations: pd.DataFrame, tariff: pd.DataFrame) -> pd.DataFrame:
    imp = declarations[(declarations["relief_scheme"] != "") & (declarations["flow"] == "import")]
    mfn = imp["ahtn8"].map(tariff.set_index("ahtn8")["duty_mfn"])
    return imp.assign(foregone=(imp["customs_value_lcu"] * mfn / 100).round(0)).groupby("relief_scheme")["foregone"].sum().sort_values(ascending=False)


def import_vat_lists(declarations: pd.DataFrame, traders: pd.DataFrame, registry: pd.DataFrame, returns: pd.DataFrame, threshold: float = 1_500_000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """List 1: importers above the VAT threshold not registered (or not matched).
    List 2: import VAT credit claimed on returns minus import VAT paid at the border."""
    imp = declarations[(declarations["flow"] == "import") & (declarations["procedure"] == "IM4")]
    last12 = imp[imp["month"] > str(pd.Period(imp["month"].max(), freq="M") - 12)]
    by = last12.groupby("trader_ref").agg(import_value_12m=("customs_value_lcu", "sum"), import_vat_paid=("import_vat_lcu", "sum"))
    t = traders.set_index("trader_ref")
    by["customs_tin"] = t["trader_id"].reindex(by.index)
    reg = registry.set_index("tin")
    by["registered"] = by["customs_tin"].map(lambda x: bool(x) and x in reg.index and bool(reg.at[x, "vat_registered"]))
    list1 = by[(by["import_value_12m"] > threshold) & ~by["registered"]].sort_values("import_value_12m", ascending=False)
    months = sorted(returns["period"].unique())[-12:]
    credit = returns[returns["period"].isin(months)].groupby("tin")["import_vat_credit"].sum()
    by["import_vat_credit"] = by["customs_tin"].map(credit)
    by["credit_minus_paid"] = (by["import_vat_credit"] - by["import_vat_paid"]).round(0)
    by["credit_to_paid"] = (by["import_vat_credit"] / by["import_vat_paid"].replace(0, float("nan"))).round(2)
    list2 = by.dropna(subset=["import_vat_credit"]).sort_values("credit_minus_paid", ascending=False)
    return list1, list2
