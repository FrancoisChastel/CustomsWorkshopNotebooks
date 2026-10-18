"""ADD-J: the one implementation of every per-case computation behind the ten sprints.

The sprint pages (through the hub's compute worker), the coach's ladder checks, the data pipeline
(the derived participant files) and the session workbooks all call these functions, so the
number a participant computes by hand, the number the page shows and the number the coach
checks against are the same number. Every function reads participant files only; nothing here
touches a truth column.

Plain words -> technical: the bridge -> mirror-trade reconciliation; fingerprints -> importer-level
risk indicators; the range -> robust price interval (median, middle half, MAD); the dial -> match
threshold; the four counts -> degree counts on the declarant graph.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from . import four_lists, valuation
from .four_lists import list_case, lists_key, lists_table, match_classes, number_table, sector_usual_table  # noqa: F401 - the 4B v2 lists, re-exported (ADD-J section 11)
from .informality import normalise_address, normalise_name
from .trade import bridge, classify_series

H1 = 18
MONTHS = 36
QUARTER = 3
BUDGET_SHARE = 0.05
HOME_USE = ("home_use", "home_use_exempt")
CORRIDOR = ("CHN", "39")        # the plastics corridor of the deck's bridge
CHAIN_CORRIDOR = ("IND", "52")  # the cotton-fabric chain of 2B (ADD-J-2b-cotton-chain J.2): gate 1's answer, sprint 2's importer table
BELOW = 0.85                    # a corridor year "below 0.85": what we recorded, timing and hub included, under 85% of the partner's FOB
SHARED_ADDRESS_MIN = 3          # the customs-declared address shared by 3+ importers (J.3)
LOW_PRICE = 0.75                # a line "under 0.75 of peers" (J.2, J.3)
DIAL = {"link": 0.90, "review": 0.70}
WEIGHTS = {"name": 0.4, "address": 0.3, "director": 0.3}
GAP_PERIODS = 6
HUB_RULE = {"consignees": 8, "addresses": 1, "turnover": 0.20}   # the deck's "11 consignees": the parties clearing under one tax ID
BUNCHING_BAND = (0.62, 0.70)    # prices parked just under R2's 70% threshold
WEIGHT_RATIO_TOLERANCE = 0.20   # our kilos over the partner's kilos: beyond 1 +/- 0.2 the weights are a data question first
ALTERNATING_SHARE, ALTERNATING_MONTHS = 0.7, 6
NEW_MONTHS = 12
FINGERPRINTS = ["new", "broker", "bunching", "alternating", "office", "price"]
CHAPTER_LABELS = {"17": "Sugar and confectionery", "33": "Cosmetics and perfumery", "39": "Plastics", "52": "Cotton", "61": "Apparel, knitted",
                  "72": "Iron and steel", "85": "Electrical machinery", "87": "Vehicles and parts"}
Z_BANDS = ((-2.0, "normal"), (-3.0, "worth a look"), (-math.inf, "a query"))
SENSITIVE_OFFICES = ("AIR2", "LAND1")
PREFERENTIAL_ORIGINS = ("MYS", "IDN")
R2_THRESHOLD = 0.70
LCU_PER_USD = 25.0

LEGACY_LABELS = {"R1": "New importer (first line less than 12 months old)", "R2": "Price below 70% of the 2022 static reference",
                 "R3": "Sensitive chapters at two offices", "R4": "Preference claimed from two origins", "R5": "The random draw"}

# The S2 menu: 24 starting points on allow-listed fields, in plain words and as the evaluator's WHERE.
MENU: list[dict[str, Any]] = [
    {"id": "m01", "label": "Price more than three spreads below today's peers", "sql_where": "robust_z < -3", "robust_z_threshold": -3},
    {"id": "m02", "label": "Price more than two and a half spreads below today's peers", "sql_where": "robust_z < -2.5", "robust_z_threshold": -2.5},
    {"id": "m03", "label": "Price more than two spreads below today's peers", "sql_where": "robust_z < -2", "robust_z_threshold": -2},
    {"id": "m04", "label": "Three spreads below peers on dutiable goods (10% or more)", "sql_where": "robust_z < -3 AND duty_rate >= 10", "robust_z_threshold": -3},
    {"id": "m05", "label": "Price below 70% of today's typical value", "sql_where": "share_of_median < 0.70", "robust_z_threshold": None},
    {"id": "m06", "label": "Price below 60% of today's typical value", "sql_where": "share_of_median < 0.60", "robust_z_threshold": None},
    {"id": "m07", "label": "New importer with a price two spreads below peers", "sql_where": "new_importer = 1 AND robust_z < -2", "robust_z_threshold": -2},
    {"id": "m08", "label": "New importer (the old R1)", "sql_where": "new_importer = 1", "robust_z_threshold": None},
    {"id": "m09", "label": "Less than six months old and below 80% of the typical value", "sql_where": "importer_tenure_months < 6 AND share_of_median < 0.8", "robust_z_threshold": None},
    {"id": "m10", "label": "Description fits a dearer code much better than the declared one", "sql_where": "text_code_disagreement > 0.5", "robust_z_threshold": None},
    {"id": "m11", "label": "Description fits a dearer code, on goods at 15% duty or more", "sql_where": "text_code_disagreement > 0.4 AND duty_rate >= 15", "robust_z_threshold": None},
    {"id": "m12", "label": "Importer-broker pair drifting to the heading's cheapest code", "sql_where": "code_drift_score > 0.3", "robust_z_threshold": None},
    {"id": "m13", "label": "A seller behind eight or more importers", "sql_where": "exporter_importers_12m >= 8", "robust_z_threshold": None},
    {"id": "m14", "label": "A seller behind five or more importers, price two spreads below", "sql_where": "exporter_importers_12m >= 5 AND robust_z < -2", "robust_z_threshold": -2},
    {"id": "m15", "label": "Weight per unit far from the usual for the code", "sql_where": "weight_per_unit_dev < -0.5 OR weight_per_unit_dev > 0.5", "robust_z_threshold": None},
    {"id": "m16", "label": "A broker whose clients were often found (over 30%)", "sql_where": "broker_flagged_share_h1 > 0.3", "robust_z_threshold": None},
    {"id": "m17", "label": "A broker often found, and a price two spreads below", "sql_where": "broker_flagged_share_h1 > 0.25 AND robust_z < -2", "robust_z_threshold": -2},
    {"id": "m18", "label": "Shipped from a hub, price a spread and a half below", "sql_where": "consignment_country IN ('SGP', 'ARE', 'HKG') AND robust_z < -1.5", "robust_z_threshold": -1.5},
    {"id": "m19", "label": "Goods from the two preferential origins, below 80% of the typical value", "sql_where": "origin IN ('MYS', 'IDN') AND share_of_median < 0.8", "robust_z_threshold": None},
    {"id": "m20", "label": "Sensitive chapters, price two spreads below", "sql_where": "chapter IN ('22', '24', '85', '87') AND robust_z < -2", "robust_z_threshold": -2},
    {"id": "m21", "label": "High duty (20% or more) and a price below 75% of the typical value", "sql_where": "duty_rate >= 20 AND share_of_median < 0.75", "robust_z_threshold": None},
    {"id": "m22", "label": "Odd on every signal at once (oddness score in the top 3%)", "sql_where": "oddness_score > 0.556", "robust_z_threshold": None},
    {"id": "m23", "label": "The learned score's top band (top 3%)", "sql_where": "learned_score > 0.193", "robust_z_threshold": None},
    {"id": "m24", "label": "Riskiest importer segment with a price two spreads below", "sql_where": "importer_cluster = 4 AND robust_z < -2", "robust_z_threshold": -2},
]


# --------------------------------------------------------------------------- small helpers

def _num(value: Any, digits: int | None = None) -> float | int | None:
    """A JSON-safe number: None for NaN/inf (and a missing integer), plain Python types otherwise."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, digits) if digits is not None else v
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: _num(v) for k, v in row.items()} for row in frame.to_dict("records")]


def _rate(found: pd.Series) -> float:
    return float((found == "finding").mean()) if len(found) else float("nan")


def sql_to_query(sql: str) -> str:
    """The evaluator's WHERE as a pandas query (the small grammar both sides accept)."""
    text = re.sub(r"\bAND\b", "and", sql)
    text = re.sub(r"\bOR\b", "or", text)
    text = re.sub(r"\bNOT\b", "not", text)
    text = re.sub(r"\bIN\b", "in", text)
    text = re.sub(r"(?<![<>!=])=(?!=)", "==", text)
    return text.replace("<>", "!=")


# --------------------------------------------------------------------------- 1B · the z of a line

def z_log(value: float, median: float, spread: float) -> float:
    """The deck's zscore recipe: ln(value / typical) divided by the spread as a share of the typical value."""
    if not (value > 0 and median > 0 and spread > 0):
        return float("nan")
    return math.log(value / median) / (spread / median)


def z_band(z: float) -> str:
    if z != z:
        return "no peers"
    for cut, label in Z_BANDS:
        if z >= cut:
            return label
    return "a query"


def zscore_row(features: pd.DataFrame, line_id: str) -> dict[str, Any]:
    rows = features[features["line_id"] == line_id]
    if rows.empty:
        raise KeyError(f"no line {line_id}")
    r = rows.iloc[0]
    value, median, spread = float(r["value_per_kg"]), float(r["peer_median_used"]), float(r["peer_spread_used"])
    z = z_log(value, median, spread)
    return {"line_id": line_id, "hs8": str(r["hs8"]), "origin": str(r["origin"]), "value_per_kg": _num(value, 2), "peer_median": _num(median, 2),
            "peer_spread": _num(spread, 2), "peer_level": int(r["peer_level_used"]), "log_ratio": _num(math.log(value / median) if value > 0 and median > 0 else float("nan"), 3),
            "relative_spread": _num(spread / median if median else float("nan"), 3), "z_log": _num(z, 2), "robust_z": _num(float(r["robust_z"]), 2),
            "band": z_band(z)}


# --------------------------------------------------------------------------- 1B · the rule book and the menu

def legacy_masks(features: pd.DataFrame, tariff: pd.DataFrame) -> dict[str, np.ndarray]:
    """R1-R5 as boolean masks over features_lines (the same definitions as legacy_rules.md and the evaluator)."""
    reference = tariff.set_index("hs8")["static_reference_2022"]
    uv_usd = features["value_per_kg"].to_numpy(dtype=float) / LCU_PER_USD
    r2 = uv_usd < R2_THRESHOLD * features["hs8"].astype(str).map(reference).to_numpy(dtype=float)
    chapter, hs6 = features["chapter"].astype(str), features["hs6"].astype(str)
    return {"R1": (features["new_importer"] == 1).to_numpy(),
            "R2": r2,
            "R3": ((chapter.isin(["22", "24", "85", "87"]) | (hs6 == "170199")) & features["office"].isin(SENSITIVE_OFFICES)).to_numpy(),
            "R4": ((features["preference_claim"] == "FTA") & features["origin"].isin(PREFERENTIAL_ORIGINS)).to_numpy(),
            "R5": (features["random_draw"] == 1).to_numpy()}


def period_mask(features: pd.DataFrame, period: str) -> np.ndarray:
    months = features["period_month"].to_numpy()
    return months <= H1 if period == "h1" else months > H1


def rule_numbers(features: pd.DataFrame, mask: np.ndarray, period: str, others: np.ndarray | None = None, budget: float = BUDGET_SHARE) -> dict[str, Any]:
    """The five numbers of a rule on one half, the two extra tiles and the quarterly series (ADD-J contract section 2).

    On months 19-36 the hit rate is read on the random-draw lines the rule flags (the honest basis); on
    months 1-18 on every controlled line it flags. `others` is the union of the other legacy rules:
    'new to the book' is the share of the rule's flags none of them raises.
    """
    half = period_mask(features, period)
    rd = (features["random_draw"] == 1).to_numpy()
    controlled = features["control_type"].notna().to_numpy()
    outcome = features["outcome"]
    basis = (half & rd) if period == "h2" else (half & controlled)
    flagged = half & mask
    draw_rate = _rate(outcome[half & rd])
    hit_rate = _rate(outcome[basis & mask])
    lift = hit_rate / draw_rate if draw_rate else float("nan")
    hits = basis & mask & (outcome == "finding").to_numpy()
    duty = float(features.loc[hits, "duty_recovered_lcu"].sum()) / max(1, int((basis & mask).sum()))
    new_to_book = float((~others[flagged]).mean()) if others is not None and flagged.any() else float("nan")
    compliant = (features["importer_controlled_h1"].to_numpy() > 0) & (features["importer_hit_rate_h1"].to_numpy() == 0)
    burden = float(compliant[flagged].mean()) if flagged.any() else float("nan")
    months = features["period_month"].to_numpy()
    first = 1 if period == "h1" else H1 + 1
    per_month_lines = half.sum() / H1
    flagged_per_month = flagged.sum() / H1
    queue = max(0.0, flagged_per_month - budget * per_month_lines) if flagged.sum() / max(1, half.sum()) > budget else 0.0
    quarterly = []
    for q in range(H1 // QUARTER):
        lo, hi = first + q * QUARTER, first + (q + 1) * QUARTER - 1
        in_q = (months >= lo) & (months <= hi)
        quarterly.append({"quarter": q + 1, "first_month": int(lo), "lines": int(in_q.sum()), "flagged": int((in_q & mask).sum()),
                          "controlled": int((in_q & basis & mask).sum()), "hits": int((in_q & hits).sum()), "hit_rate": _num(_rate(outcome[in_q & basis & mask]), 4)})
    return {"flagged": int(flagged.sum()), "share_of_traffic": _num(flagged.sum() / max(1, half.sum()), 4), "controlled": int((basis & mask).sum()),
            "hits": int(hits.sum()), "hit_rate": _num(hit_rate, 4), "random_hit_rate": _num(draw_rate, 4), "lift": _num(lift, 2), "duty_per_inspection": _num(duty, 0),
            "new_to_book": _num(new_to_book, 3), "burden_on_compliant": _num(burden, 3), "queue_beyond_budget": _num(queue, 0), "quarterly": quarterly}


def lift_range(hits: int, lines: int, draw_rate: float) -> tuple[float | None, float | None]:
    """The 95% range of a lift: the Wilson interval of the rule's hit rate over its lines, divided by the random draw's own hit rate
    (as recipes_1b.py and the deck read it). On months 1-18 the lines are the controlled lines the rule flags."""
    if not lines or not draw_rate or draw_rate != draw_rate:
        return None, None
    lo, hi = four_lists.wilson(int(hits), int(lines))
    return _num(lo / draw_rate, 2), _num(hi / draw_rate, 2)


# 1B sprint 1 (ADD-K K.8): how the deck reads an old rule, in this order. Over the budget (a queue beyond 5% of traffic) or a hit rate that falls
# (the last three quarters below the first three): revise. A rule that selects on a place rather than a risk: retire it as a risk rule. A lift
# whose 95% range spans 1: the draw cannot tell, so retire or keep. Otherwise the committee's rule: keep at lift 2 or more with half or more of
# the flags new to the book, retire under 1.5 or under a fifth new, revise the rest.
SELECTS_ON = {"R1": "the importer's age", "R2": "a price against a 2022 list", "R3": "an office (a place)", "R4": "an origin claim", "R5": "chance"}
PLACE_RULES = ("R3",)


def rule_verdict(rule: str, numbers: dict[str, Any]) -> tuple[str, str]:
    """(verdict, the condition that gave it) for one rule's months 19-36 numbers (a rulebook_numbers row)."""
    quarters = [numbers.get(f"q{q}_hit_rate") for q in range(1, 7)]
    known = [q for q in quarters if q is not None and q == q]
    falls = len(known) == 6 and float(np.mean(quarters[3:])) < float(np.mean(quarters[:3]))
    if (numbers.get("queue_beyond_budget") or 0) > 0 or falls:
        return "revise", "over the budget" if (numbers.get("queue_beyond_budget") or 0) > 0 else "its hit rate falls quarter after quarter"
    if rule in PLACE_RULES:
        return "retire", "it names a place, not a risk"
    lo, hi, lift, new = numbers.get("lift_lo"), numbers.get("lift_hi"), numbers.get("lift"), numbers.get("new_to_book")
    if lo is not None and hi is not None and lo < 1 < hi:
        return "retire or keep", "the draw cannot tell: the lift's 95% range spans 1"
    if lift is not None and new is not None and lift >= 2 and new >= 0.5:
        return "keep", "lift 2 or more, half or more of its flags new to the book"
    if lift is not None and (lift < 1.5 or (new is not None and new < 0.2)):
        return "retire", "lift under 1.5, or under a fifth of its flags new to the book"
    return "revise", "between keep and retire"


def rulebook_numbers(features: pd.DataFrame, tariff: pd.DataFrame, period: str) -> pd.DataFrame:
    """R1-R5 on one half: one row per rule with the five numbers, the lift's 95% range (lift_lo, lift_hi: the reading of a rule that
    rests on few random-draw lines, ADD-K K.8), the tiles and the six quarterly hit rates."""
    masks = legacy_masks(features, tariff)
    half = period_mask(features, period)
    draw_rate = _rate(features["outcome"][half & (features["random_draw"] == 1).to_numpy()])
    rows = []
    for rule in ("R1", "R2", "R3", "R4", "R5"):
        others = np.zeros(len(features), dtype=bool)
        for other in ("R1", "R2", "R3", "R4"):
            if other != rule:
                others |= masks[other]
        numbers = rule_numbers(features, masks[rule], period, None if rule == "R5" else others)
        quarters = {f"q{q['quarter']}_hit_rate": q["hit_rate"] for q in numbers.pop("quarterly")}
        lo, hi = lift_range(numbers["hits"], numbers["controlled"], draw_rate)
        ordered = {k: v for key, value in numbers.items() for k, v in ([(key, value), ("lift_lo", lo), ("lift_hi", hi)] if key == "lift" else [(key, value)])}
        rows.append({"rule": rule, "label": LEGACY_LABELS[rule], "period": period, **ordered, **quarters})
    return pd.DataFrame(rows)


def menu_mask(features: pd.DataFrame, sql_where: str) -> np.ndarray:
    return features.eval(sql_to_query(sql_where)).to_numpy(dtype=bool)


def menu_numbers(features: pd.DataFrame, tariff: pd.DataFrame, period: str = "h1") -> pd.DataFrame:
    """The 24 menu rules scored on one half (months 1-18 for the card-writing sprint)."""
    masks = legacy_masks(features, tariff)
    book = masks["R1"] | masks["R2"] | masks["R3"] | masks["R4"]
    rows = []
    for item in MENU:
        numbers = rule_numbers(features, menu_mask(features, item["sql_where"]), period, book)
        numbers.pop("quarterly")
        rows.append({"id": item["id"], "label": item["label"], "sql_where": item["sql_where"], "robust_z_threshold": item["robust_z_threshold"], "period": period, **numbers})
    return pd.DataFrame(rows)


def rule_quarterly_split(numbers: dict[str, Any], month: int = 30) -> dict[str, Any]:
    """The hit rate before and after a month, from a rule's quarterly series (the expiry question of sprint 3)."""
    before = [q for q in numbers["quarterly"] if q["first_month"] + QUARTER - 1 <= month]
    after = [q for q in numbers["quarterly"] if q["first_month"] > month]

    def pooled(quarters: list[dict[str, Any]]) -> float | None:
        controlled = sum(q["controlled"] for q in quarters)
        return _num(sum(q["hits"] for q in quarters) / controlled, 4) if controlled else None

    return {"month": month, "before": pooled(before), "after": pooled(after)}


# --------------------------------------------------------------------------- 2B · macro: the corridors

def corridor_id(partner: str, chapter: str) -> str:
    return f"{partner}-{chapter}"


def mirror_ratio(mirror: pd.DataFrame) -> pd.Series:
    """What we account for over what the partner shipped, both FOB: (home FOB, or home CIF / (1 + the chapter wedge) when the FOB
    field is empty, + timing + hub) / partner FOB. NaN when the partner does not report."""
    home = mirror["home_imports_fob_usd"].fillna(mirror["home_imports_cif_usd"] / (1 + mirror["cif_fob_adj"]))
    return (home + mirror["timing_usd"].fillna(0) + mirror["hub_attributed_usd"].fillna(0)) / mirror["partner_exports_fob_usd"]


def years_below(mirror: pd.DataFrame, threshold: float = BELOW) -> pd.Series:
    """Per (partner, chapter): how many years the ratio sits under `threshold` (a year without a ratio does not count)."""
    return mirror.assign(below=mirror_ratio(mirror) < threshold).groupby(["partner", "chapter"])["below"].sum().astype(int)


def corridor_table(mirror: pd.DataFrame) -> pd.DataFrame:
    """The 24 corridors in their latest year: the FOB-to-FOB ratio and what it leaves unexplained (residual_share = 1 - ratio,
    as chain_2b.json), the years below 0.85, the bridge in USD million (bridge_residual_share = residual / expected CIF, the
    waterfall's own share), the weight ratio, the series shape and the flags; the largest residual share first."""
    shapes = classify_series(mirror).set_index(["chapter", "partner"])["shape"]
    latest = mirror["year"].max()
    ratios = mirror_ratio(mirror)
    below = years_below(mirror)
    rows = []
    for (partner, chapter), group in mirror.groupby(["partner", "chapter"]):
        r = group[group["year"] == latest].iloc[0]
        reports = int(r["partner_reports"]) == 1 and r["partner_exports_fob_usd"] == r["partner_exports_fob_usd"]
        wedge = float(r["cif_fob_adj"])
        b = bridge(float(r["partner_exports_fob_usd"]) / 1e6, float(r["home_imports_cif_usd"]) / 1e6, wedge, float(r["timing_usd"]) / 1e6, float(r["hub_attributed_usd"]) / 1e6) if reports else None
        note = r["note"] if isinstance(r["note"], str) else ""
        # The three pre-checks are flags; everything else the partner side says is a note (the ladder reads an empty `flags` as "clean").
        flags = []
        if not reports:
            flags.append("the partner does not report this chapter")
        ratio = float(r["weight_ratio"]) if r["weight_ratio"] == r["weight_ratio"] else float("nan")
        if int(r["reported_weight_flag"]) == 0 or ratio != ratio or abs(ratio - 1) > WEIGHT_RATIO_TOLERANCE:
            flags.append("the weights are missing or the weight ratio is far from 1")
        notes_all = " ".join(n for n in group["note"] if isinstance(n, str))  # a recode is written on the year it happened, not on the latest row
        if any(word in notes_all for word in ("another chapter", "HS revision", "recode")):
            flags.append("the series is broken by a recode")
        if r["attribution"] == "origin" and "hub" not in note:
            note = (note + "; " if note else "") + "the partner records exports to the hub, home records origin"
        ratio = _num(ratios[r.name], 4) if reports else None
        rows.append({"id": corridor_id(partner, chapter), "partner": partner, "chapter": str(chapter), "label": CHAPTER_LABELS.get(str(chapter), f"chapter {chapter}"),
                     "year": int(latest), "ratio": ratio, "residual_share": None if ratio is None else round(1 - ratio, 4), "years_below_085": int(below.get((partner, chapter), 0)),
                     "fob_partner": _num(b["partner_exports"] if b else None, 1), "cif_home": _num(float(r["home_imports_cif_usd"]) / 1e6, 1), "wedge": wedge,
                     "expected": _num(b["expected_cif"] if b else None, 1), "recorded": _num(b["recorded"] if b else None, 1), "timing": _num(b["timing"] if b else None, 1),
                     "hub": _num(b["hub"] if b else None, 1), "explained": _num(b["explained"] if b else None, 1), "residual": _num(b["residual"] if b else None, 1),
                     "bridge_residual_share": _num(b["residual_share"] if b else None, 3), "weight_ratio": _num(r["weight_ratio"], 3), "partner_reports": int(reports),
                     "attribution": str(r["attribution"]), "trade_system": str(r["trade_system"]), "series_shape": str(shapes.get((chapter, partner), "normal")), "flags": flags, "note": note})
    return pd.DataFrame(rows).sort_values("residual_share", ascending=False, na_position="last").reset_index(drop=True)


def bridge_row(mirror: pd.DataFrame, id_: str) -> dict[str, Any]:
    """One corridor's bridge as the five steps of the waterfall (USD million)."""
    table = corridor_table(mirror)
    rows = table[table["id"] == id_]
    if rows.empty:
        raise KeyError(f"no corridor {id_}")
    r = {k: v if isinstance(v, list) else _num(v) for k, v in rows.iloc[0].to_dict().items()}
    r["corridor_residual_share"] = r["residual_share"]  # 1 - the FOB-to-FOB ratio, as in the corridor table
    r["residual_share"] = r["bridge_residual_share"]     # the waterfall's own share: residual / expected CIF, the hand calculation
    r["flags"] = list(r["flags"])
    r["note"] = str(r.get("note") or "")
    if r["fob_partner"] is None:
        r["steps"] = []
        return r
    r["steps"] = [{"label": "Partner exports, FOB", "value": r["fob_partner"]},
                  {"label": f"Shipping and insurance (x {1 + r['wedge']:.2f})", "value": _num(r["expected"] - r["fob_partner"], 1)},
                  {"label": "Expected at home, CIF", "value": r["expected"]},
                  {"label": "Recorded at home", "value": r["recorded"]},
                  {"label": "Timing (in transit at the year end)", "value": r["timing"]},
                  {"label": "Recorded under the hub", "value": r["hub"]},
                  {"label": "Accounted for", "value": r["explained"]},
                  {"label": "Residual", "value": r["residual"]},
                  {"label": "Residual as a share of expected", "value": r["residual_share"]}]
    return r


# --------------------------------------------------------------------------- 2B · micro: the corridor's importers

def corridor_lines(features: pd.DataFrame, partner: str = CORRIDOR[0], chapter: str = CORRIDOR[1]) -> pd.DataFrame:
    return features[(features["origin"] == partner) & (features["chapter"].astype(str) == str(chapter)) & features["regime"].isin(HOME_USE)].copy()


def chain_lines(features: pd.DataFrame, partner: str = CHAIN_CORRIDOR[0], chapter: str = CHAIN_CORRIDOR[1]) -> pd.DataFrame:
    """A corridor as the cotton chain reads it (J.2): declared origin and chapter, every regime (the lines chain_2b.json counts)."""
    return features[(features["origin"] == partner) & (features["chapter"].astype(str) == str(chapter))].copy()


def _main(series: pd.Series) -> str:
    """The most frequent value; a tie goes to the first in sort order."""
    counts = series.dropna().astype(str).value_counts()
    return str(min(counts.index[counts == counts.max()])) if len(counts) else ""


def chain_importers(features: pd.DataFrame, importers: pd.DataFrame | None = None, traders: pd.DataFrame | None = None,
                    partner: str = CHAIN_CORRIDOR[0], chapter: str = CHAIN_CORRIDOR[1]) -> pd.DataFrame:
    """Sprint 2's importer table (J.2): one row per importer of the corridor on months 1-18, from participant data only, no outcome.

    lines_h1, value_h1 and value_share_h1 (of the corridor's months 1-18 value); med_ratio_h1 (median share of peers' median) and
    low_share_h1 (share of lines under 0.75 of peers; a line without peers counts as not under); seller, broker and office (the
    most frequent); seller_importers (corridor importers behind that seller); new (a line less than 12 months after registration);
    shared_address (the customs-declared address shared by 3+ importers, from trader_features.csv; without that column, the
    registry address shared with another importer of the corridor). The largest value first.
    """
    lines = chain_lines(features, partner, chapter)
    h1 = lines[lines["period_month"] <= H1]
    if h1.empty:
        return pd.DataFrame(columns=CHAIN_IMPORTER_COLUMNS)
    g = h1.groupby("importer_id")
    out = pd.DataFrame({"lines_h1": g.size(), "value_h1": g["customs_value_lcu"].sum().round(2), "med_ratio_h1": g["share_of_median"].median().round(4),
                        "low_share_h1": g["share_of_median"].apply(lambda s: float((s < LOW_PRICE).mean())).round(4),
                        "seller": g["exporter_id"].agg(_main), "broker": g["broker_id"].agg(_main), "office": g["office"].agg(_main),
                        "new": g["importer_tenure_months"].min().lt(NEW_MONTHS).astype(int)})
    out["value_share_h1"] = (out["value_h1"] / out["value_h1"].sum()).round(4)
    behind = h1.groupby("exporter_id")["importer_id"].nunique()
    out["seller_importers"] = out["seller"].map(behind).fillna(0).astype(int)
    if traders is not None and "address_shared_n" in traders.columns:
        shared = pd.to_numeric(traders.set_index("importer_id")["address_shared_n"], errors="coerce").reindex(out.index)
        out["shared_address"] = (shared >= SHARED_ADDRESS_MIN).astype(int)
    elif importers is not None and "address_line" in importers.columns:
        address = importers.set_index("importer_id")["address_line"].reindex(out.index).fillna("").astype(str)
        counts = address[address != ""].value_counts()
        out["shared_address"] = address.map(lambda a: int(bool(a) and counts.get(a, 0) > 1))
    else:
        out["shared_address"] = 0
    out = out.rename_axis("importer_id").reset_index().sort_values(["value_h1", "importer_id"], ascending=[False, True]).reset_index(drop=True)
    return out[CHAIN_IMPORTER_COLUMNS]


CHAIN_IMPORTER_COLUMNS = ["importer_id", "lines_h1", "value_h1", "value_share_h1", "med_ratio_h1", "low_share_h1", "seller", "seller_importers", "broker", "office", "new", "shared_address"]


def alternating_test(series: pd.Series) -> dict[str, Any]:
    """Does the importer's monthly value per kilo swing above and below its own median month after month?"""
    s = series.dropna()
    if len(s) < 2:
        return {"months": int(len(s)), "ups": 0, "downs": 0, "alternations": 0, "share": None, "verdict": False}
    dev = np.sign(s.to_numpy(dtype=float) - float(s.median()))
    dev = dev[dev != 0]
    changes = int((dev[1:] != dev[:-1]).sum()) if len(dev) > 1 else 0
    share = changes / (len(dev) - 1) if len(dev) > 1 else 0.0
    return {"months": int(len(s)), "ups": int((dev > 0).sum()), "downs": int((dev < 0).sum()), "alternations": changes, "share": _num(share, 3),
            "verdict": bool(len(s) >= ALTERNATING_MONTHS and share >= ALTERNATING_SHARE)}


def importer_months(lines: pd.DataFrame, importer_id: str) -> pd.DataFrame:
    """The importer's monthly series in the corridor: declared value, lines and median value per kilo."""
    mine = lines[lines["importer_id"] == importer_id]
    g = mine.groupby("period_month")
    out = pd.DataFrame({"value_lcu": g["customs_value_lcu"].sum().round(0), "lines": g.size(), "value_per_kg": g["value_per_kg"].median().round(2)})
    return out.reindex(range(1, MONTHS + 1)).rename_axis("month").reset_index()


def fingerprints(features: pd.DataFrame, importers: pd.DataFrame, partner: str = CORRIDOR[0], chapter: str = CORRIDOR[1]) -> pd.DataFrame:
    """One row per importer of the corridor: the six fingerprints, the residual contribution and twelve monthly values."""
    lines = corridor_lines(features, partner, chapter)
    if lines.empty:
        return pd.DataFrame()
    reg = importers.set_index("importer_id")
    h1 = lines["period_month"] <= H1
    office_control = lines[h1].groupby("office")["control_type"].apply(lambda s: s.notna().mean())
    average_control = float(lines.loc[h1, "control_type"].notna().mean())
    silent_offices = set(office_control[office_control < average_control / 2].index)
    contribution = (np.maximum(0.0, lines["peer_median_used"] - lines["value_per_kg"]) * lines["net_kg"]).rename("contribution")
    lines = lines.assign(contribution=contribution, bunch=lines["share_of_median"].between(BUNCHING_BAND[0], BUNCHING_BAND[1], inclusive="left"))
    total_value, total_contribution = float(lines["customs_value_lcu"].sum()), float(lines["contribution"].sum())
    main_broker = lines.groupby("importer_id")["broker_id"].agg(lambda s: s.value_counts().index[0])
    broker_counts = main_broker.value_counts()
    addresses = reg["address_line"].reindex(main_broker.index).fillna("")
    address_counts = addresses[addresses != ""].value_counts()
    last12 = list(range(MONTHS - 11, MONTHS + 1))
    rows = []
    for importer_id, mine in lines.groupby("importer_id"):
        value = float(mine["customs_value_lcu"].sum())
        monthly = mine.groupby("period_month")["value_per_kg"].median()
        alt = alternating_test(monthly)
        main_office = mine["office"].value_counts()
        office_share = float(main_office.iloc[0] / len(mine))
        flags = {"new": bool(mine["importer_tenure_months"].min() < NEW_MONTHS),
                 "broker": bool(broker_counts.get(main_broker[importer_id], 0) > 1),
                 "bunching": bool(mine["bunch"].mean() >= 0.5),
                 "alternating": bool(alt["verdict"]),
                 "office": bool(main_office.index[0] in silent_offices and office_share >= 0.5),
                 "price": bool((mine["share_of_median"] * mine["customs_value_lcu"]).sum() / value - 1 < -0.15)}
        shared_address = bool(address_counts.get(addresses[importer_id], 0) > 1)
        months = mine.groupby("period_month")["customs_value_lcu"].sum()
        rows.append({"importer_id": importer_id, "name": str(reg["legal_name"].get(importer_id, "")), "lines": int(len(mine)), "value_lcu": round(value, 0),
                     "share_of_corridor": _num(value / total_value, 4), "price_distance": _num((mine["share_of_median"] * mine["customs_value_lcu"]).sum() / value - 1, 3),
                     "residual_contribution": round(float(mine["contribution"].sum()), 0), "residual_share": _num(float(mine["contribution"].sum()) / total_contribution if total_contribution else 0.0, 4),
                     "new": int(flags["new"]), "shared_broker": int(flags["broker"]), "shared_address": int(shared_address), "bunching": int(flags["bunching"]),
                     "alternating": int(flags["alternating"]), "silent_office": int(flags["office"]), "main_broker": str(main_broker[importer_id]), "main_office": str(main_office.index[0]),
                     "tenure_months": _num(float(mine["importer_tenure_months"].min()), 1), "alternating_share": alt["share"],
                     "codes": " ".join(code for code, on in flags.items() if on),
                     **{f"m{i + 1}": round(float(months.get(m, 0.0)), 0) for i, m in enumerate(last12)}})
    out = pd.DataFrame(rows).sort_values(["residual_contribution", "importer_id"], ascending=[False, True]).reset_index(drop=True)
    out.insert(2, "rank", range(1, len(out) + 1))
    return out


def fingerprint_detail(table: pd.DataFrame, lines: pd.DataFrame, importer_id: str) -> dict[str, Any]:
    rows = table[table["importer_id"] == importer_id]
    if rows.empty:
        raise KeyError(f"no importer {importer_id} in the corridor")
    row = {k: _num(v) for k, v in rows.iloc[0].to_dict().items()}
    if "codes" in row:  # the fingerprint table; sprint 2's chain table (J.2) has no codes column
        row["codes"] = str(row["codes"]).split()
    monthly = importer_months(lines, importer_id)
    row["monthly"] = _records(monthly)
    row["alternating_test"] = alternating_test(monthly.set_index("month")["value_per_kg"])
    return row


# --------------------------------------------------------------------------- 2B · document: the invoice line

def neighbour_table(neighbours: pd.DataFrame, history: pd.DataFrame, invoice: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    """The 30 nearest accepted lines of each invoice line, with the price on one basis and the floor flag."""
    mine = neighbours[neighbours["query_id"].isin(invoice["ref"])]
    hist = history.set_index("line_id")
    joined = mine.join(hist, on="line_id", how="left")
    joined = joined.assign(fob_usd=valuation.to_fob_usd(joined.assign(hs6=joined["hs6"].astype(str)), fx, "accepted_on"))
    end = pd.to_datetime(invoice["invoice_date"]).max()
    joined["days_before"] = (end - pd.to_datetime(joined["accepted_on"])).dt.days
    joined["above_floor"] = (joined["similarity"] >= valuation.FLOOR).astype(int)
    cols = ["query_id", "rank", "line_id", "similarity", "above_floor", "fob_usd", "unit_price", "currency", "incoterm", "quantity", "unit", "accepted_on", "hs8", "origin", "description", "days_before"]
    out = joined[cols].rename(columns={"fob_usd": "unit_price_usd_fob"})
    out["accepted_on"] = pd.to_datetime(out["accepted_on"]).dt.strftime("%Y-%m-%d")
    return out.sort_values(["query_id", "rank"]).reset_index(drop=True)


def invoice_range(table: pd.DataFrame, history: pd.DataFrame, invoice: pd.DataFrame, fx: pd.DataFrame, ref: str) -> dict[str, Any]:
    """The range of one invoice line from its precomputed neighbours, with the method's verdict."""
    line = invoice[invoice["ref"] == ref]
    if line.empty:
        raise KeyError(f"no invoice line {ref}")
    mine = table[table["query_id"] == ref]
    # The range reads the line's precomputed neighbours above the floor: the same heading and origin within the window for
    # V1-V5 (what valuation.neighbours keeps), the 30 most similar by description, any origin, for the cotton line C1 (J.2).
    kept = mine[mine["similarity"] >= valuation.FLOOR].sort_values(["similarity", "accepted_on"], ascending=[False, False]).head(valuation.K)
    kept = kept.rename(columns={"unit_price_usd_fob": "fob_usd"}).dropna(subset=["fob_usd"])
    rng = valuation.price_range(kept)
    declared = float(valuation.to_fob_usd(line, fx, "invoice_date").iloc[0])
    verdict = valuation.assess(declared, rng)
    return {"ref": ref, "description": str(line["description"].iloc[0]), "declared": _num(declared, 2), "neighbours": int(len(mine)), "above_floor": int(rng["count"]),
            "median": _num(rng["median"], 2), "p25": _num(rng["p25"], 2), "p75": _num(rng["p75"], 2), "mad": _num(rng["mad"], 2),
            "share_of_median": _num(verdict["share_of_median"], 3), "distance_spreads": _num(verdict["distance"], 2), "below_p25": bool(verdict["below_p25"]),
            "verdict": str(verdict["decision"]), "reason": str(verdict["reason"]), "rows": _records(mine)}


# --------------------------------------------------------------------------- 4B · match

def _ratio(a: str, b: str) -> float | None:
    if not a or not b:
        return None
    return round(fuzz.token_set_ratio(a, b) / 100, 3)


def pair_similarities(importer: pd.Series, registry_row: pd.Series) -> dict[str, Any]:
    """The deck's recipe on one pair: three similarities, the weights, the combined confidence and the band."""
    legal, trading = normalise_name(importer.get("importer_name", "") or ""), normalise_name(importer.get("trading_name", "") or "")
    reg_name = normalise_name(registry_row.get("legal_name", "") or "")
    name = max(v for v in (_ratio(legal, reg_name), _ratio(trading, reg_name)) if v is not None) if (legal or trading) and reg_name else None
    address = _ratio(normalise_address(importer.get("address_line", "") or ""), normalise_address(registry_row.get("address_line", "") or ""))
    director = _ratio(normalise_name(importer.get("director_name", "") or ""), normalise_name(registry_row.get("director_name", "") or ""))
    phone_a, phone_b = str(importer.get("phone", "") or ""), str(registry_row.get("phone", "") or "")
    phone = int(bool(phone_a and phone_b and phone_a == phone_b))
    sims = {"name": name, "address": address, "director": director}
    present = {k: v for k, v in sims.items() if v is not None}
    confidence = round(sum(WEIGHTS[k] * v for k, v in present.items()) / sum(WEIGHTS[k] for k in present), 3) if present else 0.0
    band = "link" if confidence >= DIAL["link"] else "review" if confidence >= DIAL["review"] else "no link"
    return {"name_sim": name, "address_sim": address, "director_sim": director, "phone_match": phone, "missing": [k for k, v in sims.items() if v is None],
            "confidence": confidence, "band": band}


def _exact_status(tin: str, tins: set[str]) -> str:
    if not tin:
        return "blank TIN"
    if tin in tins:
        return "matched"
    if any(len(t) == len(tin) and sum(a != b for a, b in zip(t, tin)) == 1 for t in tins):
        return "TIN one character off"
    return "not in registry"


def score_pairs(importers_4b: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """The 25 importers against the registry: the best candidate of each with its similarities and confidence."""
    reg = registry.fillna("").astype(str)
    reg = reg.assign(_norm=reg["legal_name"].map(normalise_name))
    reg["_prefix"] = reg["_norm"].str[:3]
    tins = set(reg["tin"])
    rows = []
    for imp in importers_4b.fillna("").astype(str).itertuples(index=False):
        imp_row = imp._asdict()
        prefix = normalise_name(imp_row["importer_name"])[:3]
        block = reg[(reg["_prefix"] == prefix) | (reg["district"] == imp_row["district"]) | ((reg["phone"] == imp_row["phone"]) & (imp_row["phone"] != ""))]
        if block.empty:
            block = reg
        best, best_row = None, None
        for cand in block.itertuples(index=False):
            cand_row = cand._asdict()
            sims = pair_similarities(pd.Series(imp_row), pd.Series(cand_row))
            key = (sims["confidence"], sims["phone_match"], cand_row["tin"] == imp_row["tin_customs"], -int(cand_row["tin"][1:]) if cand_row["tin"][1:].isdigit() else 0)
            if best is None or key > best:
                best, best_row = key, (cand_row, sims)
        cand_row, sims = best_row
        rows.append({"ref": imp_row["ref"], "importer_id": imp_row["importer_id"], "importer_name": imp_row["importer_name"], "tin_customs": imp_row["tin_customs"],
                     "exact_status": _exact_status(imp_row["tin_customs"], tins), "best_tin": cand_row["tin"], "registry_name": cand_row["legal_name"],
                     "name_sim": sims["name_sim"], "address_sim": sims["address_sim"], "director_sim": sims["director_sim"], "phone_match": sims["phone_match"],
                     "missing": " ".join(sims["missing"]), "confidence": sims["confidence"], "band": sims["band"]})
    return pd.DataFrame(rows)


def score_pair(importers_4b: pd.DataFrame, registry: pd.DataFrame, ref: str, tin: str) -> dict[str, Any]:
    imp = importers_4b.fillna("").astype(str)
    imp = imp[imp["ref"] == ref]
    reg = registry.fillna("").astype(str)
    reg = reg[reg["tin"] == tin]
    if imp.empty or reg.empty:
        raise KeyError(f"no pair {ref} x {tin}")
    sims = pair_similarities(imp.iloc[0], reg.iloc[0])
    present = [k for k in WEIGHTS if sims[f"{k}_sim"] is not None]
    steps = [{"label": f"{k} similarity x {WEIGHTS[k]}", "value": _num(WEIGHTS[k] * sims[f'{k}_sim'], 3)} for k in present]
    steps.append({"label": "Combined confidence" + (" (re-weighted over the present fields)" if len(present) < 3 else ""), "value": sims["confidence"]})
    steps.append({"label": f"Band at the dial {DIAL['link']} / {DIAL['review']}", "value": sims["band"]})
    return {"ref": ref, "importer_id": str(imp.iloc[0]["importer_id"]), "tin": tin, "registry_name": str(reg.iloc[0]["legal_name"]), "weights": WEIGHTS, "dial": DIAL, **sims, "steps": steps}


def trackb_curve(scores: pd.DataFrame, sample: pd.DataFrame, dial: float = DIAL["review"]) -> dict[str, Any]:
    """Precision and recall by threshold on the labelled sample of track B (weighted back to the file's bands), and the three pairs nearest the dial."""
    best = scores.set_index("cust_id")
    s = sample.assign(score=sample["cust_id"].map(best["score"]).fillna(0.0), best=sample["cust_id"].map(best["reg_id"]).fillna(""), band=sample["cust_id"].map(best["band"]).fillna("no match"))
    s["is_link"] = (s["label"] == 1).to_numpy()
    # The sample is stratified by band, so every sampled pair stands for its band's share of the file: weight = band rows in the file / band rows in the sample.
    population = scores["band"].value_counts()
    sampled = s["band"].value_counts()
    weights = {band: float(population.get(band, 0)) / float(sampled.get(band, 1)) for band in population.index}
    w = s["band"].map(weights).fillna(1.0).to_numpy(dtype=float)
    links = float((w * s["is_link"].to_numpy()).sum())
    rows = []
    for t in np.round(np.arange(0.50, 1.0001, 0.05), 2):
        predicted = (s["score"] >= t).to_numpy()
        tp = float((w * (predicted & s["is_link"].to_numpy())).sum())
        kept = float((w * predicted).sum())
        rows.append({"threshold": float(t), "pairs": int(predicted.sum()), "pairs_weighted": _num(kept, 0), "precision": _num(tp / kept if kept else float("nan"), 4),
                     "recall": _num(tp / links if links else float("nan"), 4)})
    nearest = s.assign(gap=(s["score"] - dial).abs()).sort_values(["gap", "cust_id"]).head(3)
    return {"dial": float(dial), "sample_pairs": int(len(s)), "links_in_sample": int(s["is_link"].sum()), "weighted": True,
            "band_weights": {band: _num(v, 3) for band, v in sorted(weights.items())}, "rows": rows,
            "least_sure": [{"cust_id": c, "reg_id": r, "score": _num(v, 4)} for c, r, v in zip(nearest["cust_id"], nearest["reg_id"], nearest["score"])]}


# --------------------------------------------------------------------------- 4B · the four lists (ADD-L), in four_lists.py

# --------------------------------------------------------------------------- 4B · networks

def _graph(network: dict[str, Any]) -> nx.Graph:
    graph = nx.Graph()
    for node in network["nodes"]:
        graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in network["edges"]:
        graph.add_edge(edge["source"], edge["target"], kind=edge["kind"])
    return graph


def _number_side(imp: Any, numbers: pd.DataFrame | None) -> tuple[float, float, bool]:
    """Imports and import VAT paid over twelve months on the lines that bear VAT, per tax number used to clear (ADD-L L.3.3); the row's own values without a number."""
    tin = imp.tin_customs
    if not tin or numbers is None:
        return float(imp.import_value_12m_lcu), float(imp.import_vat_paid_12m_lcu), False
    per = numbers["imports_12m"].get(tin, float("nan")), numbers["import_vat_paid_12m"].get(tin, float("nan"))
    return float(per[0]), float(per[1]), True


def four_counts(network: dict[str, Any], importers_4b: pd.DataFrame, importers: pd.DataFrame, returns: pd.DataFrame, registry: pd.DataFrame,
                numbers: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per 4B importer: the consignees (every party clearing under its tax ID: other names plus the consignee records), the addresses and brokers behind them,
    turnover over imports and import VAT deducted over paid, both on the tax-number basis (numbers_4b: lines that bear VAT, last twelve months)."""
    graph = _graph(network)
    reg_all = importers.fillna("").astype(str)
    by_tin = reg_all[reg_all["tin"] != ""].groupby("tin")["importer_id"].apply(list)
    address_of = reg_all.set_index("importer_id")["address_line"]
    broker_of = reg_all.set_index("importer_id")["default_broker_id"]
    books = four_lists.returns_by_number(returns)
    tins = set(registry["tin"].astype(str))
    per_number = None if numbers is None else numbers.assign(tin_customs=numbers["tin_customs"].astype(str)).set_index("tin_customs")
    rows = []
    for imp in importers_4b.fillna("").astype(str).itertuples(index=False):
        names = [i for i in by_tin.get(imp.tin_customs, []) if i != imp.importer_id] if imp.tin_customs else []
        consignees = [n for n in graph.neighbors(imp.importer_id) if graph.nodes[n].get("kind") == "consignee"] if imp.importer_id in graph else []
        group = [imp.importer_id, *names]
        addresses = {address_of.get(i, "") for i in group} - {""}
        brokers = {broker_of.get(i, "") for i in group} - {""}
        imports, paid, has_number = _number_side(imp, per_number)
        known = imp.tin_customs in tins and float(books["filed_12m"].get(imp.tin_customs, 0)) > 0  # a number that filed no return in twelve months declared nothing
        turnover = float(books["sales_12m"].get(imp.tin_customs)) if known else float("nan")
        deducted = float(books["import_vat_deducted_12m"].get(imp.tin_customs)) if known else float("nan")
        ratio = turnover / imports if imports and turnover == turnover else float("nan")
        booked = deducted / paid if has_number and paid and deducted == deducted else float("nan")
        clearing = len(names) + len(consignees)  # the deck's "consignees": every party clearing under the tax ID (other names, plus the consignee records)
        community = graph.nodes[imp.importer_id].get("community", -1) if imp.importer_id in graph else -1
        flag = bool(clearing >= HUB_RULE["consignees"] and len(addresses) == HUB_RULE["addresses"] and ratio == ratio and ratio < HUB_RULE["turnover"])
        # the window of each count (data-v13): names_under_tin reads the register over all 36 months; names_12m the importer codes clearing under the
        # number on the lines that bear VAT over the last twelve months (numbers_4b.names_under_number, the deck's count); the flag reads the first, unchanged
        names_12m = int(per_number["names_under_number"].get(imp.tin_customs, 0)) if per_number is not None and imp.tin_customs else 0
        rows.append({"ref": imp.ref, "importer_id": imp.importer_id, "tin_customs": imp.tin_customs, "names_under_tin": len(names), "names_12m": names_12m, "consignee_nodes": len(consignees),
                     "consignees": clearing, "addresses": len(addresses), "brokers": len(brokers), "imports_12m": round(imports, 0),
                     "sales_12m": _num(turnover, 0), "turnover_ratio": _num(ratio, 3), "community": int(community), "flag": int(flag),
                     "names": " ".join(sorted(names)), "import_vat_booked": _num(booked, 3)})
    return pd.DataFrame(rows)


def count_case(table: pd.DataFrame, ref: str) -> dict[str, Any]:
    rows = table[table["ref"] == ref]
    if rows.empty:
        raise KeyError(f"no importer {ref}")
    r = {k: _num(v) for k, v in rows.iloc[0].to_dict().items()}
    r["rule"] = HUB_RULE
    r["steps"] = [{"label": "Consignees: the names declaring under the tax ID (all 36 months), plus the consignee records", "value": r["consignees"]},
                  {"label": "Names clearing under the number in the last twelve months", "value": r.get("names_12m")}, {"label": "Distinct addresses behind them", "value": r["addresses"]},
                  {"label": "Distinct brokers", "value": r["brokers"]}, {"label": "Turnover declared / imports (per tax number, lines that bear VAT)", "value": r["turnover_ratio"]},
                  {"label": "Import VAT deducted ÷ paid", "value": r.get("import_vat_booked")}]
    return r


def components(network: dict[str, Any], top: int = 10) -> list[dict[str, Any]]:
    """Connected groups of importers linked through shared addresses, directors or phones, highest degree first."""
    graph = _graph(network)
    keep = {n for n, d in graph.nodes(data=True) if d.get("kind") in ("importer", "address", "director", "phone")}  # a broker links every client: not a shared field
    sub = graph.subgraph(keep)
    out = []
    for comp in nx.connected_components(sub):
        importers = sorted(n for n in comp if sub.nodes[n].get("kind") == "importer")
        if len(importers) < 2:
            continue
        shared = sorted({f"{sub.nodes[n]['kind']}:{sub.nodes[n].get('label', n)}" for n in comp if sub.nodes[n].get("kind") != "importer" and sub.degree(n) >= 2})
        out.append({"importers": importers, "size": len(importers), "degree": int(sum(sub.degree(n) for n in importers)), "shared": shared[:12]})
    out.sort(key=lambda c: (-c["degree"], -c["size"], c["importers"][0]))
    for k, comp in enumerate(out[:top], 1):
        comp["id"] = k
    return out[:top]


# --------------------------------------------------------------------------- loading

FEATURE_COLUMNS = ["line_id", "importer_id", "broker_id", "exporter_id", "period_month", "month", "hs8", "hs6", "chapter", "origin", "consignment_country", "regime", "office",
                   "duty_rate", "preference_claim", "customs_value_lcu", "net_kg", "importer_tenure_months", "new_importer", "random_draw", "control_type", "outcome",
                   "duty_recovered_lcu", "value_per_kg", "peer_median_used", "peer_spread_used", "peer_level_used", "robust_z", "share_of_median", "text_code_disagreement",
                   "code_drift_score", "exporter_importers_12m", "weight_per_unit_dev", "broker_flagged_share_h1", "importer_controlled_h1", "importer_hit_rate_h1",
                   "learned_score", "oddness_score", "importer_cluster"]


def read_features(data: str | Path) -> pd.DataFrame:
    return pd.read_csv(Path(data) / "features_lines.csv", usecols=FEATURE_COLUMNS, dtype={"hs8": str, "hs6": str, "chapter": str, "control_type": str, "outcome": str}, low_memory=False)


def read_csv(data: str | Path, name: str, **kwargs: Any) -> pd.DataFrame | None:
    path = Path(data) / f"{name}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=kwargs.pop("dtype", None) or {"hs8": str, "hs6": str, "chapter": str, "tin": str, "tin_customs": str, "phone": str, "cust_id": str, "reg_id": str},
                       keep_default_na=kwargs.pop("keep_default_na", True), **kwargs)


def read_json(data: str | Path, name: str) -> Any:
    return json.loads((Path(data) / f"{name}.json").read_text(encoding="utf-8"))
