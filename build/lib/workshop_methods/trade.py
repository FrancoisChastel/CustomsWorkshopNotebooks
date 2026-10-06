"""2B: mirror data, the bridge, series shapes, regional unit values, sector map."""

from __future__ import annotations

import numpy as np
import pandas as pd


def mirror_ratios(mirror: pd.DataFrame) -> pd.DataFrame:
    """Home imports over partner exports, raw and after shipping-and-insurance (CIF/FOB)."""
    ratio = mirror["home_imports_usd"] / mirror["partner_exports_usd"]
    explained = mirror["home_imports_usd"] + mirror["timing_usd"] + mirror["hub_attributed_usd"]
    return mirror.assign(
        ratio=ratio.round(3),
        ratio_cif_adj=(ratio / (1 + mirror["cif_fob_adj"])).round(3),
        ratio_after_known=(explained / (mirror["partner_exports_usd"] * (1 + mirror["cif_fob_adj"]))).round(3),
    )


def bridge(partner_exports: float, recorded: float, cif_fob: float, timing: float = 0.0, hub: float = 0.0) -> dict:
    """Subtract each known explanation in turn; what is left is the residual worth a query."""
    expected = partner_exports * (1 + cif_fob)
    explained = recorded + timing + hub
    residual = expected - explained
    return {
        "partner_exports": round(partner_exports, 1), "expected_cif": round(expected, 1), "recorded": round(recorded, 1),
        "timing": round(timing, 1), "hub": round(hub, 1), "explained": round(explained, 1),
        "residual": round(residual, 1), "residual_share": round(residual / expected, 3) if expected else np.nan,
    }


def series_shape(ratios: pd.Series, low: float = 0.80, spike_jump: float = 0.30, slope_cut: float = -0.05) -> str:
    """persistent / growing / spike / normal, from simple rules on the adjusted ratio by year.

    persistent: every year below `low`; growing: falls by more than 5 points a year and ends
    below `low`; spike: one year at least `spike_jump` below the median of the others.
    """
    r = ratios.dropna().to_numpy()
    if len(r) < 3:
        return "too few years"
    slope = np.polyfit(np.arange(len(r)), r, 1)[0]
    if (r < low).all():
        return "persistent"
    if slope < slope_cut and r[-1] < low:
        return "growing"
    for i, value in enumerate(r):
        others = np.delete(r, i)
        if value < low and np.median(others) - value >= spike_jump:  # a spike is one low year
            return "spike"
    return "normal"


def classify_series(mirror: pd.DataFrame) -> pd.DataFrame:
    rated = mirror_ratios(mirror)
    rows = []
    for (chapter, partner), g in rated.sort_values("year").groupby(["chapter", "partner"]):
        rows.append({
            "chapter": chapter, "partner": partner, "shape": series_shape(g.set_index("year")["ratio_after_known"]),
            "mean_ratio": round(float(g["ratio_after_known"].mean()), 3), "years_reported": int(g["partner_exports_usd"].notna().sum()),
        })
    return pd.DataFrame(rows)


def regional_flags(regional: pd.DataFrame, country: str = "Country A", threshold: float = 0.70, min_coverage: float = 0.70) -> pd.DataFrame:
    """Commodities where `country` pays less than `threshold` of the regional median, with the weight check."""
    mine = regional[regional["importer"] == country]
    out = mine.groupby("commodity").agg(ratio=("uv_ratio", "mean"), weight_coverage=("weight_coverage", "min"), years=("year", "nunique")).reset_index()
    out["below_threshold"] = out["ratio"] < threshold
    out["trusted"] = out["weight_coverage"] >= min_coverage
    return out.sort_values("ratio")


def sector_map(sector: pd.DataFrame, year: int) -> pd.DataFrame:
    """Chapter x country grid of value-weighted ratios to the regional median for one year."""
    return sector[sector["year"] == year].pivot(index="chapter", columns="importer", values="uv_ratio_to_region")
