"""2B valuation track: what similar goods were accepted at.

Plain words: for an invoice line, find the accepted lines of the same 6-digit heading and origin
whose descriptions are most alike, put every price on one basis (US dollars, FOB), and read the
range: the median and the middle half. The range is a reference for a question, never a value.

Technical: k nearest neighbours by cosine similarity of multilingual sentence embeddings, with a
similarity floor and a time window; robust distance (median, MAD).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

K = 30
FLOOR = 0.85
WINDOW_DAYS = 90
ENOUGH = 25  # neighbours needed before a range can carry a question
# Shipping and insurance as a share of FOB, by chapter (OECD margins; the tariff's cif_fob_wedge; 6% elsewhere).
CIF_FOB = {"03": 0.09, "08": 0.12, "10": 0.22, "17": 0.08, "22": 0.10, "24": 0.04, "27": 0.28, "30": 0.03, "33": 0.05, "39": 0.07, "40": 0.06, "90": 0.03, "52": 0.06,
           "61": 0.05, "64": 0.05, "72": 0.11, "84": 0.04, "85": 0.03, "87": 0.06, "94": 0.08}
DEFAULT_CIF_FOB = 0.06


def incoterm_factor(incoterm: str, chapter: str) -> float:
    """Multiply a price quoted under `incoterm` by this to get the FOB price (freight is 85% of the margin)."""
    margin = CIF_FOB.get(chapter, DEFAULT_CIF_FOB)
    return {"FOB": 1.0, "FCA": 1.0, "EXW": 1.03, "CFR": 1 / (1 + 0.85 * margin), "CIF": 1 / (1 + margin)}[incoterm]


def usd_per_unit(fx: pd.DataFrame, month: str, currency: str) -> float:
    rates = fx[fx["month"] == month].set_index("currency")["lcu_per_unit"]
    if rates.empty:  # a date past the table: the latest month's rates (they are fixed anyway)
        rates = fx[fx["month"] == fx["month"].max()].set_index("currency")["lcu_per_unit"]
    return float(rates[currency] / rates["USD"])


def to_fob_usd(lines: pd.DataFrame, fx: pd.DataFrame, date_column: str) -> pd.Series:
    """Unit price, net of any discount, in US dollars on an FOB basis, at the month's exchange rate."""
    months = pd.to_datetime(lines[date_column]).dt.strftime("%Y-%m")
    discount = lines["discount"] if "discount" in lines else 0.0
    rate = [usd_per_unit(fx, m, c) for m, c in zip(months, lines["currency"])]
    factor = [incoterm_factor(i, h[:2]) for i, h in zip(lines["incoterm"], lines["hs6"].astype(str))]
    return (lines["unit_price"] * (1 - discount) * np.array(rate) * np.array(factor)).round(2)


def neighbours(line: pd.Series, history: pd.DataFrame, similarity: dict[str, float], fx: pd.DataFrame,
               k: int = K, floor: float = FLOOR, window_days: int = WINDOW_DAYS, as_of: str | None = None) -> pd.DataFrame:
    """The accepted lines of the same heading and origin, within the window, at or above the floor, closest first."""
    same = history[(history["hs6"].astype(str) == str(line["hs6"])) & (history["origin"] == line["origin"])].copy()
    accepted = pd.to_datetime(same["accepted_on"])
    end = pd.Timestamp(as_of) if as_of else pd.to_datetime(history["accepted_on"]).max()
    same = same[accepted > end - pd.Timedelta(days=window_days)]
    same["similarity"] = same["line_id"].map(similarity)
    kept = same[same["similarity"] >= floor].sort_values(["similarity", "accepted_on"], ascending=[False, False]).head(k)
    kept = kept.assign(fob_usd=to_fob_usd(kept, fx, "accepted_on"))
    return kept[["line_id", "accepted_on", "description", "origin", "currency", "incoterm", "unit_price", "fob_usd", "similarity"]]


def price_range(kept: pd.DataFrame) -> dict[str, float]:
    prices = kept["fob_usd"]
    if prices.empty:
        return {"count": 0, "median": np.nan, "p25": np.nan, "p75": np.nan, "mad": np.nan}
    median = float(prices.median())
    return {"count": int(len(prices)), "median": median, "p25": float(prices.quantile(0.25)), "p75": float(prices.quantile(0.75)),
            "mad": float((prices - median).abs().median())}


def assess(declared_fob_usd: float, rng: dict[str, float], enough: int = ENOUGH) -> dict[str, object]:
    """Where the declared price sits in the range, and what an officer could do with it."""
    if rng["count"] == 0:
        return {"share_of_median": np.nan, "distance": np.nan, "below_p25": False, "decision": "nothing",
                "reason": "no accepted line of the same goods and origin passes the floor"}
    share = declared_fob_usd / rng["median"]
    distance = (declared_fob_usd - rng["median"]) / rng["mad"] if rng["mad"] else np.nan
    below = declared_fob_usd < rng["p25"]
    if rng["count"] < enough:
        decision, reason = "nothing", f"only {rng['count']} neighbours: too thin a range to carry a question"
    elif below and distance <= -1.5:
        decision, reason = "question", (f"{share:.0%} of the median, {distance:.1f} spreads below, under the middle half: "
                                        "ask the importer through the valuation procedure")
    elif below:
        decision, reason = "indicator", f"{share:.0%} of the median, under the middle half: an indicator for the risk profile"
    else:
        decision, reason = "nothing", f"{share:.0%} of the median, inside the middle half"
    return {"share_of_median": round(share, 3), "distance": round(distance, 2) if distance == distance else np.nan,
            "below_p25": bool(below), "decision": decision, "reason": reason}
