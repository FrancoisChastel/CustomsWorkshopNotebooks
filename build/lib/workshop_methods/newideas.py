"""Two new ideas for 1B: groups inside one tariff line (clustering) and a trader against its own past (time series)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from .peer import MAD_TO_SD


def tariff_line_groups(lines: pd.DataFrame, k: int = 2, seed: int = 0) -> pd.DataFrame:
    """k-means on value per kilo and weight per unit (both standardised).

    Returns the group of each line and its distance to the nearest group centre, in typical
    spreads: the line farthest from every group is the one that 'fits neither'.
    """
    if "usd_per_kg" in lines:
        usd_per_kg = lines["usd_per_kg"]
    else:  # local currency per kilo: the grouping is the same, only the axis label changes
        usd_per_kg = lines["customs_value_lcu"] / lines["net_weight_kg"]
    kg_per_unit = lines["kg_per_unit"] if "kg_per_unit" in lines else lines["net_weight_kg"] / lines["quantity"]
    x = np.column_stack([usd_per_kg, kg_per_unit])
    scaled = StandardScaler().fit_transform(x)
    model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(scaled)
    distance = np.min(np.linalg.norm(scaled[:, None, :] - model.cluster_centers_[None, :, :], axis=2), axis=1)
    order = np.argsort(model.cluster_centers_[:, 0])  # group 1 = cheapest
    rename = {old: new + 1 for new, old in enumerate(order)}
    return pd.DataFrame(
        {
            "usd_per_kg": np.round(usd_per_kg, 1),
            "kg_per_unit": np.round(kg_per_unit, 3),
            "group": [rename[g] for g in model.labels_],
            "distance_to_nearest_group": np.round(distance, 3),
        },
        index=lines.index,
    )


def own_band(series: pd.DataFrame, z: float = 2.5, floor_share: float = 0.06, warmup: int = 6) -> pd.DataFrame:
    """The trader's own band, month by month, built only from earlier months.

    Expanding median and MAD of all months so far, shifted by one month so a month never judges
    itself; the spread has a floor (6% of the median) and nothing is flagged before `warmup`
    months of history, so the first months do not alarm.
    """
    frames = []
    for (trader, code), g in series.sort_values("month").groupby(["trader_ref", "ahtn8"]):
        uv = g["uv_lcu_per_kg"].reset_index(drop=True)
        median = uv.expanding().median().shift(1)
        mad = uv.expanding().apply(lambda s: np.median(np.abs(s - np.median(s))), raw=True).shift(1)
        spread = np.maximum(MAD_TO_SD * mad, floor_share * median)
        lower = (median - z * spread).where(np.arange(len(uv)) >= warmup)
        frames.append(pd.DataFrame({
            "trader_ref": trader, "ahtn8": code, "month": g["month"].to_numpy(), "uv_lcu_per_kg": uv.to_numpy(),
            "band_median": median.round(2).to_numpy(), "band_lower": lower.round(2).to_numpy(),
            "below_band": (uv < lower).to_numpy(), "ref_median": g["ref_median"].to_numpy(),
        }))
    if not frames:  # no trader matched the filter: an empty band, not an error
        columns = ["trader_ref", "ahtn8", "month", "uv_lcu_per_kg", "band_median", "band_lower", "below_band", "ref_median"]
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)


def first_flag(band: pd.DataFrame) -> pd.Series:
    """First month each trader falls below its own band (NaN when it never does)."""
    flagged = band[band["below_band"]]
    return flagged.groupby("trader_ref")["month"].min()
