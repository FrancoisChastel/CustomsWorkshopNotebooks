"""The 1B signals: price against peers, units, description against code, origin, drift, history, tenure."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from .peer import MAD_TO_SD, unit_value

PALLET_KG = 500.0
CARTON_KG = 12.0
MIN_CONFIDENCE = 0.5  # below this the description is too vague to read ('parts', 'goods', '-')


# --------------------------------------------------------------------------- units

def expected_weight(lines: pd.DataFrame, tariff: pd.DataFrame) -> pd.Series:
    """Weight implied by the declared quantity and unit (the 'five units' check)."""
    t = tariff.set_index("ahtn8")
    per_unit = lines["ahtn8"].map(t["kg_per_unit"])
    trade_unit = lines["ahtn8"].map(t["unit"])
    # A carton is the trade unit for packed goods; for goods counted in units it holds ten of them.
    carton_kg = np.where(trade_unit == "cartons", per_unit, np.where(trade_unit == "units", per_unit * 10, CARTON_KG))
    carton_kg = np.where(np.isnan(carton_kg), CARTON_KG, carton_kg)
    qty = lines["quantity"].astype(float)
    unit = lines["unit"]
    return pd.Series(
        np.select(
            [unit == "kg", unit == "tonnes", unit == "units", unit == "cartons", unit == "pallets"],
            [qty, qty * 1000, qty * per_unit, qty * carton_kg, qty * PALLET_KG],
            default=np.nan,
        ),
        index=lines.index,
    )


def units_consistent(lines: pd.DataFrame, tariff: pd.DataFrame, tolerance: float = 5.0) -> pd.Series:
    """False when net weight and quantity disagree by more than `tolerance` times."""
    ratio = lines["net_weight_kg"] / expected_weight(lines, tariff)
    return ~((ratio > tolerance) | (ratio < 1 / tolerance)) | ratio.isna()


# --------------------------------------------------------------------------- own history

def own_history_z(lines: pd.DataFrame, history: pd.DataFrame, min_lines: int = 5) -> pd.Series:
    """Distance of each line from the same trader's typical value for the same code (robust z).

    The trader's median and spread come from all its lines in that code; the spread has a floor
    of 5% of the median so a very regular importer does not alarm on small moves.
    """
    hist = history.assign(uv=unit_value(history))
    g = hist.groupby(["trader_ref", "ahtn8"])["uv"]
    stats = pd.DataFrame({
        "own_median": g.median(),
        "own_mad": g.agg(lambda s: float(np.median(np.abs(s - np.median(s))))),
        "own_n": g.size(),
    }).reset_index()
    merged = lines[["trader_ref", "ahtn8"]].merge(stats, on=["trader_ref", "ahtn8"], how="left")
    merged.index = lines.index
    spread = np.maximum(MAD_TO_SD * merged["own_mad"], 0.05 * merged["own_median"])
    z = (unit_value(lines) - merged["own_median"]) / spread
    return z.where(merged["own_n"] >= min_lines)


# --------------------------------------------------------------------------- description against code

@dataclass
class DescriptionModel:
    """Reads a goods description and says which code it most resembles.

    Trained on the declared codes of all lines: the few misdeclared lines are noise the model
    outvotes. Seeded misclassifications move goods to a neighbouring code in the same chapter,
    so the model predicts the 8-digit code, not only the chapter. A near-empty description gives
    no confident reading: it is marked readable=False and scores 0 on p_higher_duty_code rather
    than spreading its probability over every dearer code.
    """

    pipeline: object
    classes: np.ndarray

    @classmethod
    def fit(cls, lines: pd.DataFrame) -> "DescriptionModel":
        text = lines["description"].fillna("").str.lower()
        pipe = make_pipeline(
            TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2, sublinear_tf=True),
            LogisticRegression(max_iter=2000, C=8.0),
        )
        pipe.fit(text, lines["ahtn8"])
        return cls(pipeline=pipe, classes=pipe.classes_)

    def predict(self, lines: pd.DataFrame, tariff: pd.DataFrame) -> pd.DataFrame:
        proba = self.pipeline.predict_proba(lines["description"].fillna("").str.lower())
        duty = tariff.set_index("ahtn8")["duty_mfn"].reindex(self.classes).to_numpy()
        declared_duty = lines["ahtn8"].map(tariff.set_index("ahtn8")["duty_mfn"]).to_numpy()
        higher = duty[None, :] > declared_duty[:, None]
        best = proba.argmax(axis=1)
        readable = proba.max(axis=1) >= MIN_CONFIDENCE
        return pd.DataFrame(
            {
                "predicted_code": self.classes[best],
                "confidence": proba.max(axis=1).round(3),
                "readable": readable,
                "agrees": self.classes[best] == lines["ahtn8"].to_numpy(),
                "p_higher_duty_code": np.where(readable, (proba * higher).sum(axis=1), 0.0).round(3),
            },
            index=lines.index,
        )


# --------------------------------------------------------------------------- origin

def origin_check(lines: pd.DataFrame, tariff: pd.DataFrame, all_lines: pd.DataFrame | None = None) -> pd.DataFrame:
    """A preference claimed from an origin that does not make the goods; how many importers the seller serves."""
    producers = tariff.set_index("ahtn8")["origin_producers"].str.split("|")
    makes_it = [o in producers.get(c, []) for c, o in zip(lines["ahtn8"], lines["origin_country"])]
    claimed = lines["preference_claim"].isin(["ATIGA", "other"]).to_numpy()
    reach = (all_lines if all_lines is not None else lines).groupby("exporter_id")["trader_ref"].nunique()
    return pd.DataFrame(
        {
            "origin_makes_goods": makes_it,
            "preference_claimed": claimed,
            "doubtful_claim": claimed & ~np.array(makes_it),
            "exporter_importers": lines["exporter_id"].map(reach).fillna(0).astype(int).to_numpy(),
        },
        index=lines.index,
    )


# --------------------------------------------------------------------------- drift toward cheaper codes

def code_drift(imports: pd.DataFrame, tariff: pd.DataFrame, min_lines: int = 3) -> pd.DataFrame:
    """Per trader: among lines in a 'dear code / cheaper neighbour' pair, the share under the cheaper
    code, its trend over the quarters and this quarter against the four quarters before.

    Looking only inside the pairs keeps importers who always buy the cheaper goods (a steady
    share) apart from importers who are moving toward the cheaper code (a rising share). The
    trend (points per quarter, each quarter weighted by its lines) uses every quarter, so a
    handful of lines in one quarter cannot top the list on their own.
    """
    pairs = tariff.dropna(subset=["duty_cliff_neighbour"])
    cheaper = set(pairs["duty_cliff_neighbour"])
    in_pair = set(pairs["ahtn8"]) | cheaper
    frame = imports[imports["ahtn8"].isin(in_pair)].assign(
        quarter=lambda f: pd.PeriodIndex(f["month"], freq="M").asfreq("Q").astype(str),
        cheap=lambda f: f["ahtn8"].isin(cheaper),
    )
    quarters = sorted(frame["quarter"].unique())
    if len(quarters) < 5:
        raise ValueError(f"code_drift needs five quarters of lines (this one and the four before); got {len(quarters)}")
    last, previous = quarters[-1], quarters[-5:-1]
    recent = frame[frame["quarter"] == last].groupby("trader_ref")["cheap"].agg(["mean", "size"])
    before = frame[frame["quarter"].isin(previous)].groupby("trader_ref")["cheap"].agg(["mean", "size"])
    out = pd.DataFrame({
        "share_this_quarter": recent["mean"], "lines_this_quarter": recent["size"],
        "share_previous_four": before["mean"], "lines_previous_four": before["size"],
        "lines": frame.groupby("trader_ref").size(), "trend_points": _share_trend(frame, quarters),
    }).dropna()
    out = out[(out["lines_this_quarter"] >= min_lines) & (out["lines_previous_four"] >= 2 * min_lines)]
    out["change_points"] = ((out["share_this_quarter"] - out["share_previous_four"]) * 100).round(1)
    return out.sort_values("trend_points", ascending=False)


def _share_trend(frame: pd.DataFrame, quarters: list[str]) -> pd.Series:
    """Slope of the quarterly cheap-code share, in points per quarter (least squares weighted by lines)."""
    q = frame.groupby(["trader_ref", "quarter"])["cheap"].agg(["mean", "size"]).reset_index()
    x = q["quarter"].map({name: i for i, name in enumerate(quarters)}).astype(float)
    w, y = q["size"].astype(float), q["mean"]
    sums = pd.DataFrame({"trader_ref": q["trader_ref"], "w": w, "wx": w * x, "wy": w * y, "wxx": w * x * x, "wxy": w * x * y}).groupby("trader_ref").sum()
    den = sums["w"] * sums["wxx"] - sums["wx"] ** 2
    slope = (sums["w"] * sums["wxy"] - sums["wx"] * sums["wy"]) / den.where(den > 0)
    return (slope * 100).round(1)


# --------------------------------------------------------------------------- history and tenure

def history(declarations: pd.DataFrame) -> pd.DataFrame:
    """Per trader: share of lines amended or withdrawn on the trader's own initiative.

    Lines amended after an inspection finding are left out: they show what the inspection found,
    not the trader's habit.
    """
    own = declarations[declarations["inspection_outcome"] != "finding"]
    g = own.groupby("trader_ref")["status"]
    out = pd.DataFrame({
        "lines": g.size(),
        "amended_share": g.apply(lambda s: (s == "amended").mean()),
        "withdrawn_share": g.apply(lambda s: (s == "withdrawn").mean()),
    })
    out["changed_share"] = out["amended_share"] + out["withdrawn_share"]
    return out.sort_values("changed_share", ascending=False)


def tenure(imports: pd.DataFrame, traders: pd.DataFrame, as_of: str | None = None) -> pd.DataFrame:
    """Per importer: months since registration, 12-month import value and value against peers."""
    dates = pd.to_datetime(imports["declaration_date"])  # CSV files hold the dates as text
    as_of_date = pd.Timestamp(as_of or dates.max())
    reg = pd.to_datetime(traders.set_index("trader_ref")["registration_date"])
    last12 = imports[dates > as_of_date - pd.DateOffset(months=12)]
    value = last12.groupby("trader_ref")["customs_value_lcu"].sum()
    out = pd.DataFrame({"import_value_12m": value})
    out["months_registered"] = ((as_of_date - reg.reindex(out.index)).dt.days / 30.4).round(1)
    out["new_importer"] = out["months_registered"] < 12
    return out.sort_values("import_value_12m", ascending=False)
