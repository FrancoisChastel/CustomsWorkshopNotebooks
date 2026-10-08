"""2B: mirror data, the bridge, series shapes, regional unit values, sector map (version-3 fields)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def mirror_ratios(mirror: pd.DataFrame) -> pd.DataFrame:
    """Home imports over partner exports: raw, after the chapter wedge (CIF to FOB), and after timing and hub attribution."""
    partner = mirror["partner_exports_fob_usd"]
    ratio = mirror["home_imports_cif_usd"] / partner
    fob_home = mirror["home_imports_fob_usd"].fillna(mirror["home_imports_cif_usd"] / (1 + mirror["cif_fob_adj"]))
    explained = mirror["home_imports_cif_usd"] + mirror["timing_usd"] + mirror["hub_attributed_usd"]
    return mirror.assign(ratio=ratio.round(3), ratio_fob=(fob_home / partner).round(3), ratio_cif_adj=(ratio / (1 + mirror["cif_fob_adj"])).round(3),
                         ratio_after_known=(explained / (partner * (1 + mirror["cif_fob_adj"]))).round(3))


def bridge(partner_exports: float, recorded: float, cif_fob: float, timing: float = 0.0, hub: float = 0.0) -> dict:
    """Subtract each known explanation in turn; what is left is the residual worth a query."""
    expected = partner_exports * (1 + cif_fob)
    explained = recorded + timing + hub
    residual = expected - explained
    return {"partner_exports": round(partner_exports, 1), "expected_cif": round(expected, 1), "recorded": round(recorded, 1), "timing": round(timing, 1), "hub": round(hub, 1),
            "explained": round(explained, 1), "residual": round(residual, 1), "residual_share": round(residual / expected, 3) if expected else np.nan}


def series_shape(ratios: pd.Series, low: float = 0.80, spike_jump: float = 0.30) -> str:
    """persistent / growing / spike / new / normal, from simple rules on the adjusted ratio by year."""
    r = ratios.replace([np.inf, -np.inf], np.nan)
    if (ratios.index.min() == ratios.index.min()) and (r.isna() | (ratios == 0)).sum() >= 2 and r.dropna().shape[0] >= 2:
        return "new"
    r = r.dropna().to_numpy()
    if len(r) < 3:
        return "too few years"
    if (r < low).all():
        return "persistent"
    if (r[-2:] < low).all() and (r[:-2] >= low).mean() >= 0.5:
        return "growing"
    for i, value in enumerate(r):
        others = np.delete(r, i)
        if value < low and np.median(others) - value >= spike_jump:
            return "spike"
    return "normal"


def classify_series(mirror: pd.DataFrame) -> pd.DataFrame:
    rated = mirror_ratios(mirror)
    rows = []
    for (chapter, partner), g in rated.sort_values("year").groupby(["chapter", "partner"]):
        rows.append({"chapter": chapter, "partner": partner, "shape": series_shape(g.set_index("year")["ratio_after_known"]),
                     "mean_ratio": round(float(g["ratio_after_known"].mean()), 3), "years_reported": int(g["partner_reports"].sum())})
    return pd.DataFrame(rows)


def regional_flags(regional: pd.DataFrame, country: str = "Country A", threshold: float = 0.70, min_coverage: float = 0.70, ruler: str = "exporter_stats") -> pd.DataFrame:
    """Commodities where `country` pays less than `threshold` of the regional median, with the weight check."""
    mine = regional[(regional["importer"] == country) & (regional["ruler"] == ruler)]
    out = mine.groupby("commodity").agg(ratio=("uv_ratio", "mean"), weight_coverage=("reported_weight_share", "min"), years=("year", "nunique")).reset_index()
    out["below_threshold"] = out["ratio"] < threshold
    out["trusted"] = out["weight_coverage"] >= min_coverage
    return out.sort_values("ratio")


def sector_map(sector: pd.DataFrame, year: int, grey: bool = True) -> pd.DataFrame:
    """Chapter x country grid of value-weighted ratios to the regional median for one year (greyed cells blank)."""
    frame = sector[sector["year"] == year]
    if grey:
        frame = frame.assign(uv_ratio_to_region=frame["uv_ratio_to_region"].where(frame["greyed"] == 0))
    return frame.pivot(index="chapter", columns="importer", values="uv_ratio_to_region")
