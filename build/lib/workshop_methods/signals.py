"""The 1B signals on the version-3 tables: units, price against peers, own history, description against code,
origin, code drift, history, tenure. The precomputed columns of features_lines.csv are these same signals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from .peer import MAD_TO_SD, unit_value

MIN_CONFIDENCE = 0.5
LITRE_KG = 1.0


# --------------------------------------------------------------------------- units

def expected_weight(lines: pd.DataFrame, tariff: pd.DataFrame) -> pd.Series:
    """Weight implied by the declared quantity and unit (the 'five units' check)."""
    t = tariff.set_index("hs8")
    per_unit = lines["hs8"].map(t["kg_per_unit"]).astype(float)
    qty = lines["quantity"].astype(float)
    unit = lines["unit"]
    expected = np.select([unit == "kg", unit == "litres", unit == "pieces", unit == "pairs", unit == "dozens"],
                         [qty, qty * LITRE_KG, qty * per_unit, qty * per_unit, qty * 12 * per_unit], default=np.nan)
    return pd.Series(expected, index=lines.index)


def units_consistent(lines: pd.DataFrame, tariff: pd.DataFrame, tolerance: float = 3.0) -> pd.Series:
    """False when the declared unit is not the code's trade unit or the weight disagrees with the quantity."""
    t = tariff.set_index("hs8")
    same_unit = lines["unit"] == lines["hs8"].map(t["unit"])
    ratio = lines["net_kg"] / expected_weight(lines, tariff)
    agrees = ~((ratio > tolerance) | (ratio < 1 / tolerance)) | ratio.isna()
    return same_unit & agrees


# --------------------------------------------------------------------------- own history

def own_history_z(lines: pd.DataFrame, history: pd.DataFrame, min_lines: int = 5) -> pd.Series:
    """Distance of each line from the same importer's typical value for the same code (robust z)."""
    hist = history.assign(uv=unit_value(history))
    g = hist.groupby(["importer_id", "hs8"])["uv"]
    stats = pd.DataFrame({"own_median": g.median(), "own_mad": g.agg(lambda s: float(np.median(np.abs(s - np.median(s))))), "own_n": g.size()}).reset_index()
    merged = lines[["importer_id", "hs8"]].merge(stats, on=["importer_id", "hs8"], how="left")
    merged.index = lines.index
    spread = np.maximum(MAD_TO_SD * merged["own_mad"], 0.05 * merged["own_median"])
    z = (unit_value(lines) - merged["own_median"]) / spread
    return z.where(merged["own_n"] >= min_lines)


# --------------------------------------------------------------------------- description against code

@dataclass
class DescriptionModel:
    """Reads a goods description and says which code it most resembles (trained on the declared codes)."""

    pipeline: object
    classes: np.ndarray

    @classmethod
    def fit(cls, lines: pd.DataFrame) -> "DescriptionModel":
        text = lines["description"].fillna("").str.lower()
        pipe = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2, sublinear_tf=True), LogisticRegression(max_iter=2000, C=8.0))
        pipe.fit(text, lines["hs8"])
        return cls(pipeline=pipe, classes=pipe.classes_)

    def predict(self, lines: pd.DataFrame, tariff: pd.DataFrame) -> pd.DataFrame:
        proba = self.pipeline.predict_proba(lines["description"].fillna("").str.lower())
        duty = tariff.set_index("hs8")["duty_mfn"].reindex(self.classes).to_numpy()
        declared_duty = lines["hs8"].map(tariff.set_index("hs8")["duty_mfn"]).to_numpy()
        higher = duty[None, :] > declared_duty[:, None]
        best = proba.argmax(axis=1)
        readable = proba.max(axis=1) >= MIN_CONFIDENCE
        return pd.DataFrame({"predicted_code": self.classes[best], "confidence": proba.max(axis=1).round(3), "readable": readable,
                             "agrees": self.classes[best] == lines["hs8"].to_numpy(), "p_higher_duty_code": np.where(readable, (proba * higher).sum(axis=1), 0.0).round(3)}, index=lines.index)


# --------------------------------------------------------------------------- origin

def origin_check(lines: pd.DataFrame, tariff: pd.DataFrame, all_lines: pd.DataFrame | None = None) -> pd.DataFrame:
    """A preference claimed from an origin that does not make the goods; how many importers the seller serves."""
    producers = tariff.set_index("hs8")["origin_producers"].str.split("|")
    makes_it = np.array([o in producers.get(c, []) for c, o in zip(lines["hs8"], lines["origin"])])
    claimed = (lines["preference_claim"] == "FTA").to_numpy()
    reach = (all_lines if all_lines is not None else lines).groupby("exporter_id")["importer_id"].nunique()
    return pd.DataFrame({"origin_makes_goods": makes_it, "preference_claimed": claimed, "doubtful_claim": claimed & ~makes_it,
                         "exporter_importers": lines["exporter_id"].map(reach).fillna(0).astype(int).to_numpy()}, index=lines.index)


# --------------------------------------------------------------------------- drift toward cheaper codes

def code_drift(lines: pd.DataFrame, tariff: pd.DataFrame, min_lines: int = 3) -> pd.DataFrame:
    """Per importer and broker: among lines of dutiable headings, the share under the heading's cheapest code,
    this quarter against the four quarters before, and the trend in points per quarter."""
    cheapest = tariff.loc[tariff.groupby("hs6")["duty_mfn"].idxmin(), ["hs6", "hs8"]].set_index("hs6")["hs8"]
    spread = tariff.groupby("hs6")["duty_mfn"].agg(lambda s: s.max() > s.min())
    frame = lines[lines["hs6"].isin(spread[spread].index)].assign(
        quarter=lambda f: pd.PeriodIndex(f["month"], freq="M").asfreq("Q").astype(str), cheap=lambda f: f["hs8"] == f["hs6"].map(cheapest))
    quarters = sorted(frame["quarter"].unique())
    if len(quarters) < 5:
        raise ValueError(f"code_drift needs five quarters of lines (this one and the four before); got {len(quarters)}")
    last, previous = quarters[-1], quarters[-5:-1]
    key = ["importer_id", "broker_id"]
    recent = frame[frame["quarter"] == last].groupby(key)["cheap"].agg(["mean", "size"])
    before = frame[frame["quarter"].isin(previous)].groupby(key)["cheap"].agg(["mean", "size"])
    out = pd.DataFrame({"share_this_quarter": recent["mean"], "lines_this_quarter": recent["size"], "share_previous_four": before["mean"], "lines_previous_four": before["size"],
                        "lines": frame.groupby(key).size(), "trend_points": _share_trend(frame, quarters, key)}).dropna()
    out = out[(out["lines_this_quarter"] >= min_lines) & (out["lines_previous_four"] >= 2 * min_lines)]
    out["change_points"] = ((out["share_this_quarter"] - out["share_previous_four"]) * 100).round(1)
    return out.sort_values("trend_points", ascending=False)


def _share_trend(frame: pd.DataFrame, quarters: list[str], key: list[str]) -> pd.Series:
    q = frame.groupby(key + ["quarter"])["cheap"].agg(["mean", "size"]).reset_index()
    x = q["quarter"].map({name: i for i, name in enumerate(quarters)}).astype(float)
    w, y = q["size"].astype(float), q["mean"]
    sums = pd.DataFrame({**{k: q[k] for k in key}, "w": w, "wx": w * x, "wy": w * y, "wxx": w * x * x, "wxy": w * x * y}).groupby(key).sum()
    den = sums["w"] * sums["wxx"] - sums["wx"] ** 2
    slope = (sums["w"] * sums["wxy"] - sums["wx"] * sums["wy"]) / den.where(den > 0)
    return (slope * 100).round(1)


# --------------------------------------------------------------------------- history and tenure

def history(declarations: pd.DataFrame) -> pd.DataFrame:
    """Per importer: share of lines amended or withdrawn on the importer's own initiative (lines amended after a finding left out)."""
    own = declarations[declarations["outcome"].fillna("") != "finding"]
    g = own.groupby("importer_id")["status"]
    out = pd.DataFrame({"lines": g.size(), "amended_share": g.apply(lambda s: (s == "amended").mean()), "withdrawn_share": g.apply(lambda s: (s == "withdrawn").mean())})
    out["changed_share"] = out["amended_share"] + out["withdrawn_share"]
    return out.sort_values("changed_share", ascending=False)


def tenure(lines: pd.DataFrame, importers: pd.DataFrame, as_of: str | None = None) -> pd.DataFrame:
    """Per importer: months since registration, 12-month import value."""
    dates = pd.to_datetime(lines["decl_date"])
    as_of_date = pd.Timestamp(as_of or dates.max())
    reg = pd.to_datetime(importers.set_index("importer_id")["registration_date"])
    last12 = lines[dates > as_of_date - pd.DateOffset(months=12)]
    out = pd.DataFrame({"import_value_12m": last12.groupby("importer_id")["customs_value_lcu"].sum()})
    out["months_registered"] = ((as_of_date - reg.reindex(out.index)).dt.days / 30.4).round(1)
    out["new_importer"] = out["months_registered"] < 12
    return out.sort_values("import_value_12m", ascending=False)
