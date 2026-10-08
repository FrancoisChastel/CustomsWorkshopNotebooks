"""Peer groups with a fallback hierarchy: compare each line with the typical value of similar goods.

Plain words: "the typical value per kilo for the same goods from the same origin over the last
12 months; when fewer than 30 lines exist, fall back to a wider group".
Technical: reference class with a minimum cell size and a three-level fallback (DATASET-v3 section 7).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LEVELS: list[tuple[str, ...]] = [("hs8", "origin"), ("hs8",), ("hs6",)]
LEVEL_NAMES = ["same goods code and origin, last 12 months", "same goods code, any origin, last 12 months", "same 6-digit heading, any origin, last 12 months"]
MIN_LINES = 30
MAD_TO_SD = 1.4826


def unit_value(frame: pd.DataFrame) -> pd.Series:
    """Customs value per kilogram, in local currency units."""
    return frame["customs_value_lcu"] / frame["net_kg"].clip(lower=0.001)


def window(lines: pd.DataFrame, months: int = 12, end_month: str | None = None) -> pd.DataFrame:
    end = pd.Period(end_month or lines["month"].max(), freq="M")
    start = str(end - months + 1)
    return lines[(lines["month"] >= start) & (lines["month"] <= str(end))]


def _mad(values: pd.Series) -> float:
    return float(np.median(np.abs(values - np.median(values))))


def level_stats(lines: pd.DataFrame, months: int = 12, end_month: str | None = None) -> list[pd.DataFrame]:
    """Median, spread and count of value per kilo at each level over the window."""
    pool = window(lines, months, end_month).assign(uv=lambda d: unit_value(d))
    out = []
    for keys in LEVELS:
        g = pool.groupby(list(keys))["uv"]
        out.append(pd.DataFrame({"median": g.median(), "mad": g.agg(_mad), "n": g.size()}).reset_index())
    return out


def peer_values(lines: pd.DataFrame, reference: pd.DataFrame, min_lines: int = MIN_LINES, months: int = 12, fixed_level: int | None = None) -> pd.DataFrame:
    """For each line: the peer median, spread and count at the first level with enough lines.

    fixed_level (1-3) forces one level and leaves lines without enough peers empty.
    """
    stats = level_stats(reference, months)
    result = pd.DataFrame(index=lines.index, data={"peer_median": np.nan, "peer_mad": np.nan, "peer_n": 0, "peer_level": 0})
    levels = [fixed_level - 1] if fixed_level else range(len(LEVELS))
    for i in levels:
        keys = list(LEVELS[i])
        merged = lines[keys].merge(stats[i], on=keys, how="left")
        merged.index = lines.index
        ok = (merged["n"] >= min_lines) & (result["peer_level"] == 0)
        result.loc[ok, "peer_median"] = merged.loc[ok, "median"]
        result.loc[ok, "peer_mad"] = merged.loc[ok, "mad"]
        result.loc[ok, "peer_n"] = merged.loc[ok, "n"]
        result.loc[ok, "peer_level"] = i + 1
    uv = unit_value(lines)
    result["unit_value"] = uv
    result["ratio_to_peers"] = uv / result["peer_median"]
    spread = np.maximum(MAD_TO_SD * result["peer_mad"], 0.02 * result["peer_median"])
    result["robust_z"] = (uv - result["peer_median"]) / spread.replace(0, np.nan)
    return result


def levels_for_line(line: pd.Series, reference: pd.DataFrame, min_lines: int = MIN_LINES, months: int = 12) -> pd.DataFrame:
    """The three levels for one line: how many peers each has and which one is used."""
    stats = level_stats(reference, months)
    rows, used = [], None
    for i, keys in enumerate(LEVELS):
        match = stats[i]
        for key in keys:
            match = match[match[key] == line[key]]
        n = int(match["n"].iloc[0]) if len(match) else 0
        median = float(match["median"].iloc[0]) if len(match) else np.nan
        if used is None and n >= min_lines:
            used = i + 1
        rows.append({"level": i + 1, "peer_group": LEVEL_NAMES[i], "lines": n, "typical_value_per_kg": median})
    frame = pd.DataFrame(rows)
    frame["used"] = frame["level"] == used
    return frame
