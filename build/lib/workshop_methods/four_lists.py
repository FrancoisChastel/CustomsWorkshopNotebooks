"""ADD-L: Breakout 4B v2, one import followed through both administrations, the four lists.

Five questions in order; a trader goes on the list of the first question it fails:
  1 · Known to tax?          the match class of sprint 1 (exact, validated probable, unresolved, known exception)
  2 · Filing?                fewer than five of the last six monthly VAT returns
  3 · Imports in its books?  import VAT deducted on the returns / import VAT paid at the border, below one half
  4 · Sold?                  sales over twelve months / imports over twelve months, below 1; ranked by VAT at stake, cut at capacity
  5 · Whose goods?           the four counts per tax number (sprint 3, in sprints.four_counts)

The last twelve months are declaration periods 25-36 and the last twelve VAT periods; the lines that bear
VAT are regime home_use or warehouse_out; VAT is 10%. Every function reads participant tables only; the
reference implementation is data/reference/lists_4b.py and these functions reproduce its answer key.

Plain words -> technical: the four lists -> a sequential rule-based segmentation; the sector's usual
sales over imports -> the sector median of the sales-to-imports ratio; VAT at stake -> the VAT on the margin
the sector's usual ratio implies, net of what was declared.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

VAT_RATE = 0.10
MONTHS = 36
WINDOW_MONTHS = 12                      # declaration periods 25-36, VAT periods 2025-10..2026-09
LAST_RETURNS = 6                        # the last six monthly returns: 2026-04..2026-09
FILED_MIN = 5                           # filing: at least five of the last six
SECTOR_FILED_MIN = 10                   # the sector usual reads numbers with at least 10 of 12 returns filed
BOOKED_LINE = 0.5                       # imports in its books: deducted / paid at least one half
SALES_LINE = 1.0                        # sold: sales / imports at least 1
CAPACITY = 3                            # desk audits the unit can open this quarter (a lever, 1..10)
CAPACITY_RANGE = (1, 10)
VAT_BEARING = ("home_use", "warehouse_out")
DIAL = {"link": 0.90, "review": 0.70}
MIN_CLASS_LINES = 30                    # under 30 random-draw lines a class of the join audit shows its counts, never a hit rate or a lift (ADD-K K.8 item 8)
TOO_FEW = "too few lines"
AUDIT_CLASSES = ("linked", "no number", "one character off", "unknown number")
CLASSES = ("exact", "validated probable", "unresolved", "known exception")
# A written rule that links a record without the recipe (a branch, a broker's own number, a group company, a
# re-registration): ref -> (tax number, the rule). None of the 25 needs one in this lab.
KNOWN_EXCEPTIONS: dict[str, tuple[str, str]] = {}
LISTS = ("1 not known to tax", "2 not filing", "3 import not booked", "4 desk audit, ranked by VAT at stake",
         "4b below imports, beyond capacity", "5 consistent for now")
QUESTIONS = ("Known to tax?", "Filing?", "Imports in its books?", "Sold?")
NUMBER_COLUMNS = ["tin_customs", "imports_12m", "import_vat_paid_12m", "names_under_number"]
LIST_COLUMNS = ["ref", "importer_id", "tin_customs", "sector", "match_class", "tin_tax", "names_under_number", "imports_12m", "import_vat_paid_12m",
                "returns_filed_last6", "import_vat_deducted_12m", "booked", "sales_12m", "sales_ratio", "sector_usual", "question", "list", "reason",
                "vat_at_stake", "rank"]


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or (isinstance(value, str) and not value.strip())


def _get(series: pd.Series, key: Any, default: float = float("nan")) -> float:
    return float(series.get(key, default)) if not _blank(key) else default


# --------------------------------------------------------------------------- the two sides, per tax number

def vat_lines(declarations: pd.DataFrame, months: int = MONTHS) -> pd.DataFrame:
    """The declaration lines that bear VAT (home use, warehouse release) in the last twelve months."""
    first = months - WINDOW_MONTHS + 1
    return declarations[(declarations["period_month"] >= first) & declarations["regime"].isin(VAT_BEARING)]


def number_table(declarations: pd.DataFrame) -> pd.DataFrame:
    """numbers_4b.csv: one row per tax number used to clear, with its imports, the import VAT paid and the names clearing under it."""
    lines = vat_lines(declarations)
    tin = lines["tin_customs"]
    lines = lines[tin.notna() & (tin.astype(str).str.strip() != "")]
    g = lines.groupby("tin_customs")
    out = pd.DataFrame({"imports_12m": g["customs_value_lcu"].sum(), "import_vat_paid_12m": g["vat_lcu"].sum(), "names_under_number": g["importer_id"].nunique()})
    return out.rename_axis("tin_customs").reset_index()[NUMBER_COLUMNS]


def return_periods(returns: pd.DataFrame) -> tuple[list[str], list[str]]:
    """The last twelve and the last six VAT periods of the returns."""
    periods = sorted(returns["period"].astype(str).unique())
    return periods[-WINDOW_MONTHS:], periods[-LAST_RETURNS:]


def returns_by_number(returns: pd.DataFrame) -> pd.DataFrame:
    """Per registered number, over the last twelve periods: returns filed, sales, import VAT deducted; and returns filed in the last six."""
    last12, last6 = return_periods(returns)
    period = returns["period"].astype(str)
    window = returns[period.isin(last12)]
    g = window.groupby(window["tin"].astype(str))
    out = pd.DataFrame({"filed_12m": g["filed"].sum(), "sales_12m": g["sales_lcu"].sum(), "import_vat_deducted_12m": g["import_vat_credit_lcu"].sum()})
    recent = returns[period.isin(last6)]
    out["returns_filed_last6"] = recent.groupby(recent["tin"].astype(str))["filed"].sum().reindex(out.index)
    return out.rename_axis("tin")


def compared_numbers(numbers: pd.DataFrame, returns: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """The numbers both sides know, filing at least 10 of 12 returns with import VAT paid: booked, sales ratio and the register's sector."""
    per = numbers.set_index("tin_customs")
    joined = per.join(returns_by_number(returns), how="inner")
    joined = joined[(joined["import_vat_paid_12m"] > 0) & (joined["filed_12m"] >= SECTOR_FILED_MIN)]
    sector = registry.assign(tin=registry["tin"].astype(str)).set_index("tin")["sector"]
    return joined.assign(booked=joined["import_vat_deducted_12m"] / joined["import_vat_paid_12m"], sales_ratio=joined["sales_12m"] / joined["imports_12m"],
                         sector=sector.reindex(joined.index).to_numpy())


def sector_usual_table(numbers: pd.DataFrame, returns: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """sector_usual_4b.csv: the median of sales / imports by registry sector over the numbers compared (not rounded)."""
    g = compared_numbers(numbers, returns, registry).groupby("sector")["sales_ratio"]
    return pd.DataFrame({"sector_usual": g.median(), "numbers": g.size()}).rename_axis("sector").reset_index()


# --------------------------------------------------------------------------- sprint 1: the four match classes

def classify(pair: Any, dial_link: float = DIAL["link"], dial_review: float = DIAL["review"]) -> tuple[str, str | None, str]:
    """One of the 25 against the register: (class, the tax number it links to or None, the basis in plain words)."""
    if pair.ref in KNOWN_EXCEPTIONS:
        tin, rule = KNOWN_EXCEPTIONS[pair.ref]
        return "known exception", tin, f"a written rule links it: {rule}"
    if str(pair.exact_status) == "matched":
        return "exact", str(pair.tin_customs), "the customs number joins the register as typed"
    confidence = float(pair.confidence)
    if confidence >= dial_link:
        return "validated probable", str(pair.best_tin), f"confidence {confidence:.2f}, at or above the {dial_link:.2f} line"
    if confidence >= dial_review:
        return "unresolved", None, f"confidence {confidence:.2f}, between {dial_review:.2f} and {dial_link:.2f}: unresolved until a person decides"
    return "unresolved", None, f"confidence {confidence:.2f}, below the {dial_review:.2f} line"


def match_classes(pairs: pd.DataFrame, dial_link: float = DIAL["link"], dial_review: float = DIAL["review"]) -> dict[str, Any]:
    """The size of each class and one row per importer (the `match_classes` op)."""
    rows = []
    for pair in pairs.itertuples(index=False):
        cls, tin, basis = classify(pair, dial_link, dial_review)
        rows.append({"ref": pair.ref, "importer_id": pair.importer_id, "class": cls, "tin_tax": tin, "confidence": float(pair.confidence), "basis": basis})
    sizes = {cls: sum(r["class"] == cls for r in rows) for cls in CLASSES}
    return {"dial_link": dial_link, "dial_review": dial_review, "classes": sizes, "rows": rows}


# --------------------------------------------------------------------------- sprint 2: the four lists

def _first_failed(cls: str, filed: float, booked: float, ratio: float) -> int:
    """The question the trader fails first (5 = consistent for now). A number with no return counts as filing none."""
    if cls == "unresolved":
        return 1
    if (0.0 if _blank(filed) else filed) < FILED_MIN:
        return 2
    if booked < BOOKED_LINE:
        return 3
    if ratio < SALES_LINE:
        return 4
    return 5


def vat_at_stake(question: int, imports: float, sales: float, usual: float) -> float:
    """Lists 1 and 2: the VAT on the margin (import VAT was paid at the border); lists 3 and 4: the VAT on the sales the sector's usual ratio implies, net of the
    sales declared; floored at 0."""
    if question in (1, 2):
        value = VAT_RATE * imports * (usual - 1)
    elif question in (3, 4):
        value = VAT_RATE * (imports * usual - sales)
    else:
        value = 0.0
    return float("nan") if value != value else max(0.0, value)


def _list_row(imp: Any, pair: Any, numbers: pd.DataFrame, books: pd.DataFrame, usual: pd.Series, dial_link: float, dial_review: float) -> dict[str, Any]:
    """One importer through the four questions: number-level values where it has a tax number, its own row's values otherwise."""
    cls, tin_tax, basis = classify(pair, dial_link, dial_review)
    tin = None if _blank(imp.tin_customs) else str(imp.tin_customs)
    imports = _get(numbers["imports_12m"], tin) if tin else float(imp.import_value_12m_lcu)
    paid = _get(numbers["import_vat_paid_12m"], tin) if tin else float(imp.import_vat_paid_12m_lcu)
    names = int(numbers["names_under_number"].get(tin, 1)) if tin else 1
    filed, sales, deducted = (_get(books[c], tin_tax) for c in ("returns_filed_last6", "sales_12m", "import_vat_deducted_12m"))
    booked = deducted / paid if paid else float("nan")
    ratio = sales / imports if imports else float("nan")
    sector_usual = _get(usual, imp.sector)
    question = _first_failed(cls, filed, booked, ratio)
    return {"ref": imp.ref, "importer_id": imp.importer_id, "tin_customs": tin, "sector": imp.sector, "match_class": cls, "tin_tax": tin_tax, "names_under_number": names,
            "imports_12m": imports, "import_vat_paid_12m": paid, "returns_filed_last6": filed, "import_vat_deducted_12m": deducted, "booked": booked,
            "sales_12m": sales, "sales_ratio": ratio, "sector_usual": sector_usual, "question": question,
            "vat_at_stake": vat_at_stake(question, imports, sales, sector_usual), "basis": basis}


def reason(row: dict[str, Any], capacity: int) -> str:
    """One plain sentence with the number that decided the list."""
    q = row["question"]
    if q == 1:
        side = "no tax number on the declaration" if not row["tin_customs"] else f"the declared number {row['tin_customs']} is not in the register"
        return f"{side}; best register candidate at {row['basis'].removeprefix('confidence ')}"
    if q == 2:
        return f"filed {int(row['returns_filed_last6'] or 0)} of the last 6 returns"
    if q == 3:
        return f"import VAT deducted is {row['booked']:.0%} of the import VAT paid at the border, under one half"
    if q == 4:
        beyond = "" if row["rank"] <= capacity else f"; rank {row['rank']} by VAT at stake, beyond the capacity of {capacity}"
        return f"sales are {row['sales_ratio']:.2f} times imports, under 1{beyond}"
    return f"filed {int(row['returns_filed_last6'])} of 6, import VAT booked at {row['booked']:.0%}, sales {row['sales_ratio']:.2f} times imports"


def _ranked(rows: list[dict[str, Any]], capacity: int) -> list[dict[str, Any]]:
    """List 4 ranked by VAT at stake (ties by ref), cut at the capacity; every row gets its list and its reason."""
    sold = sorted((r for r in rows if r["question"] == 4), key=lambda r: (-(r["vat_at_stake"] if r["vat_at_stake"] == r["vat_at_stake"] else -1.0), r["ref"]))
    rank = {r["ref"]: k for k, r in enumerate(sold, 1)}
    out = []
    for r in rows:
        k = rank.get(r["ref"])
        name = LISTS[3] if k is not None and k <= capacity else LISTS[4] if k is not None else LISTS[{1: 0, 2: 1, 3: 2, 5: 5}[r["question"]]]
        filled = {**r, "rank": k, "list": name}
        out.append({**filled, "reason": reason(filled, capacity)})
    return out


def lists_table(importers_4b: pd.DataFrame, pairs: pd.DataFrame, numbers: pd.DataFrame, returns: pd.DataFrame, sector_usual: pd.DataFrame,
                capacity: int = CAPACITY, dial_link: float = DIAL["link"], dial_review: float = DIAL["review"]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The 25 through the four questions: one row per importer (LIST_COLUMNS) and the totals per list (importers, imports, VAT at stake)."""
    per_number = numbers.assign(tin_customs=numbers["tin_customs"].astype(str)).set_index("tin_customs")
    books = returns_by_number(returns)
    usual = sector_usual.set_index("sector")["sector_usual"]
    by_ref = {p.ref: p for p in pairs.itertuples(index=False)}
    rows = [_list_row(imp, by_ref[imp.ref], per_number, books, usual, dial_link, dial_review) for imp in importers_4b.itertuples(index=False)]
    table = pd.DataFrame(_ranked(rows, capacity))
    table["rank"] = table["rank"].astype("Int64")
    totals = pd.DataFrame([{"list": name, "importers": int((table["list"] == name).sum()), "imports_12m": float(table.loc[table["list"] == name, "imports_12m"].sum()),
                            "vat_at_stake": float(table.loc[table["list"] == name, "vat_at_stake"].sum())} for name in LISTS])
    return table[LIST_COLUMNS], totals


def list_case(table: pd.DataFrame, ref: str) -> dict[str, Any]:
    """One importer's row with the four questions in order: the value, the line, the answer (questions after the first 'no' are not asked)."""
    rows = table[table["ref"] == ref]
    if rows.empty:
        raise KeyError(f"no importer {ref}")
    r = rows.iloc[0].to_dict()
    checks = [(QUESTIONS[0], r["match_class"] if r["tin_tax"] is None else f"{r['match_class']}: {r['tin_tax']}", "exact, or validated at the dial", r["question"] != 1),
              (QUESTIONS[1], r["returns_filed_last6"], f"{FILED_MIN} of {LAST_RETURNS}", (r["returns_filed_last6"] or 0) >= FILED_MIN),
              (QUESTIONS[2], r["booked"], "one half", r["booked"] >= BOOKED_LINE),
              (QUESTIONS[3], r["sales_ratio"], "1", r["sales_ratio"] >= SALES_LINE)]
    steps, failed = [], False
    for question, value, line, passed in checks:
        steps.append({"question": question, "value": value if not failed else None, "line": line, "answer": "not asked" if failed else "yes" if passed else "no"})
        failed = failed or not passed
    formula = ("0.10 × imports × (sector usual − 1)" if r["question"] in (1, 2) else "0.10 × (imports × sector usual − sales)" if r["question"] in (3, 4) else "none: consistent for now")
    return {**r, "rank": None if pd.isna(r["rank"]) else int(r["rank"]), "steps": steps, "vat_formula": formula}


def lists_key(importers_4b: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """The facilitator key importers_4b_lists.csv: the existing columns of importers_4b.csv, then the 14 columns of ADD-L L.2."""
    added = ["match_class", "tin_tax", "names_under_number", "imports_12m", "import_vat_paid_12m", "returns_filed_last6", "import_vat_deducted_12m", "booked",
             "sales_12m", "sales_ratio", "sector_usual", "list", "reason", "vat_at_stake"]
    values = table.set_index("ref")[added].reindex(importers_4b["ref"]).reset_index(drop=True)
    numeric = [c for c in added if c not in ("match_class", "tin_tax", "list", "reason", "names_under_number", "returns_filed_last6")]
    values = values.assign(**{c: values[c].astype(float).round(3) for c in numeric}, returns_filed_last6=values["returns_filed_last6"].astype("Int64"))
    return pd.concat([importers_4b.reset_index(drop=True), values], axis=1)


# --------------------------------------------------------------------------- the population figures of the deck (L.5)

def one_off(tin: str, registered: set[str]) -> str | None:
    """A registered number one character away: one substitution, or one swap of neighbours."""
    for other in registered:
        if len(other) != len(tin):
            continue
        diff = [i for i in range(len(tin)) if tin[i] != other[i]]
        if len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and tin[diff[0]] == other[diff[1]] and tin[diff[1]] == other[diff[0]]):
            return other
    return None


def join_status(importers: pd.DataFrame, registry: pd.DataFrame) -> pd.Series:
    """The exact join for every importer: linked, no number, one character off or unknown number (by importer_id)."""
    registered = set(registry["tin"].astype(str))

    def status(tin: Any) -> str:
        if _blank(tin):
            return "no number"
        tin = str(tin)
        if tin in registered:
            return "linked"
        return "one character off" if one_off(tin, registered) else "unknown number"

    return importers.set_index("importer_id")["tin"].map(status)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return centre - half, centre + half


def join_audit(importers: pd.DataFrame, registry: pd.DataFrame, features: pd.DataFrame) -> dict[str, Any]:
    """L.5 lines 1-3: per join status, importers, share of the last twelve months' value, and the months 19-36 random draw with its lift (95% range)."""
    status = join_status(importers, registry)
    lines = features.assign(join=features["importer_id"].map(status))
    last = lines[lines["period_month"] > MONTHS - WINDOW_MONTHS]
    total = float(last["customs_value_lcu"].sum())
    draw = lines[(lines["period_month"] > MONTHS // 2) & (lines["random_draw"] == 1)]
    hit = (draw["outcome"] == "finding").to_numpy()
    base = float(hit.mean())
    out: dict[str, Any] = {"base_h2": base}
    for name in ("linked", "no number", "one character off", "unknown number"):
        mine = (draw["join"] == name).to_numpy()
        n, k = int(mine.sum()), int((mine & hit).sum())
        lo, hi = wilson(k, n) if n else (float("nan"), float("nan"))
        out[name] = {"importers": int((status == name).sum()), "value_share_last12": float(last.loc[last["join"] == name, "customs_value_lcu"].sum() / total),
                     "random_lines_h2": n, "findings": k, "hit": k / n if n else None, "lift": k / n / base if n else None,
                     "lift_lo": lo / base if n else None, "lift_hi": hi / base if n else None}
    return out


def audit_view(entry: dict[str, Any]) -> dict[str, Any]:
    """One class of the join audit as a page, a workbook or a report shows it: its counts always; its hit rate and its lift (95% range)
    only from MIN_CLASS_LINES random-draw lines, else `reading` says "too few lines" and the rates stay empty."""
    out = {k: entry[k] for k in ("importers", "value_share_last12", "random_lines_h2", "findings")}
    n = int(entry["random_lines_h2"])
    if n < MIN_CLASS_LINES:
        return {**out, "hit": None, "lift": None, "lift_lo": None, "lift_hi": None,
                "reading": f"{TOO_FEW}: {entry['findings']} finding{'s' if entry['findings'] != 1 else ''} on {n} random-draw line{'s' if n != 1 else ''}"}
    return {**out, "hit": entry["hit"], "lift": entry["lift"], "lift_lo": entry["lift_lo"], "lift_hi": entry["lift_hi"],
            "reading": f"{entry['findings']} of {n}, lift {entry['lift']:.1f} ({entry['lift_lo']:.1f}-{entry['lift_hi']:.1f})"}


def population_figures(numbers: pd.DataFrame, returns: pd.DataFrame, registry: pd.DataFrame, importers: pd.DataFrame) -> dict[str, Any]:
    """L.5 lines 4-7: import VAT booked, import VAT deducted without an import, filing, the sales line."""
    compared = compared_numbers(numbers, returns, registry)
    books = returns_by_number(returns)
    registered = set(registry["tin"].astype(str))
    known = set(numbers["tin_customs"].astype(str))
    without = books[(books["import_vat_deducted_12m"] > 0) & ~books.index.isin(known)]
    unlinked = [t for t in importers["tin"].dropna().astype(str).unique() if t.strip() and t not in registered]
    mistyped = {t for t in without.index if any(one_off(u, {t}) for u in unlinked)}
    per = numbers.assign(tin_customs=numbers["tin_customs"].astype(str)).set_index("tin_customs")
    importing = per[per.index.isin(registered)].join(books["returns_filed_last6"], how="left")
    late = importing["returns_filed_last6"].fillna(0) < FILED_MIN
    sector = compared.groupby("sector")["sales_ratio"].median()
    return {"import_vat": {"numbers_compared": int(len(compared)), "median_booked": float(compared["booked"].median()),
                           "within_5pct": float(compared["booked"].between(0.95, 1.05).mean()), "booked_under_half": int((compared["booked"] < BOOKED_LINE).sum()),
                           "booked_under_half_numbers": sorted(compared.index[compared["booked"] < BOOKED_LINE]),
                           "credit_without_import_taxpayers": int(len(without)), "credit_without_import_m": float(without["import_vat_deducted_12m"].sum() / 1e6),
                           "credit_without_import_that_are_a_mistyped_importer_number": int(len(mistyped))},
            "filing": {"registered_numbers_importing": int(len(importing)), "fewer_than_5_of_last_6": int(late.sum()), "their_imports_m": float(importing.loc[late, "imports_12m"].sum() / 1e6)},
            "sales_line": {"numbers": int(len(compared)), "median": float(compared["sales_ratio"].median()), "below_1": float((compared["sales_ratio"] < SALES_LINE).mean()),
                           "below_1_25": float((compared["sales_ratio"] < 1.25).mean()), "sector_median": {k: round(float(v), 3) for k, v in sector.items()}}}


def capacity_of(value: Any) -> int:
    """The capacity lever, checked: a whole number from 1 to 10."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer)) or float(value) != int(value):
        raise ValueError("capacity must be a whole number from 1 to 10")
    if not CAPACITY_RANGE[0] <= int(value) <= CAPACITY_RANGE[1]:
        raise ValueError("capacity must be a whole number from 1 to 10")
    return int(value)
