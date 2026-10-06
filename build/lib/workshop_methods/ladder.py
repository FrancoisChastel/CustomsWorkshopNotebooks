"""The 1B ladder: a rule, distance from normal, an oddness score, a learning score.

Plain words -> technical: rule -> percentile threshold; distance from normal -> robust z-score;
oddness score -> anomaly score (isolation forest); learning score -> supervised model
(gradient boosting); the three reasons -> feature contributions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest

MIN_CONTRIBUTION = 0.005  # a signal that moves the score by less is not named as a reason

SIGNAL_NAMES = {
    "price_gap": "price below peers",
    "own_gap": "below its own history",
    "p_higher_duty_code": "description fits a dearer code",
    "doubtful_claim": "origin claim doubtful",
    "new_importer": "new importer",
    "changed_share": "often amended or withdrawn",
    # the worksheet's columns (worksheet_1b.json) and the notebook's six-signal table
    "price": "price below peers",
    "own_history": "below its own history",
    "description": "description fits a dearer code",
    "origin": "origin claim doubtful",
    "history": "often amended or withdrawn",
    "signal_price": "price below peers",
    "signal_description": "description fits a dearer code",
    "signal_origin": "origin claim doubtful",
}


def step1_rule(ratio: pd.Series, percentile: float = 10.0) -> pd.Series:
    """Step 1: flag the lines in the bottom `percentile` of value against peers."""
    cut = np.nanpercentile(ratio, percentile)
    return ratio <= cut


def step2_distance(z: pd.Series, threshold: float = -2.5) -> pd.Series:
    """Step 2: flag lines more than `threshold` typical spreads below normal."""
    return z <= threshold


def _contributions(predict, x: pd.DataFrame, reference: pd.Series) -> pd.DataFrame:
    """How much each signal moves a line's score, in plain terms: the average of what the score loses
    when the signal is set back to normal and what it gains when the signal alone is kept. Two
    signals that each explain the score (say price and description) both get credit this way.
    """
    score = predict(x)
    normal = pd.DataFrame([reference.to_numpy()] * len(x), columns=x.columns, index=x.index)
    baseline = predict(normal)
    out = {}
    for col in x.columns:
        without = x.copy()
        without[col] = reference[col]
        alone = normal.copy()
        alone[col] = x[col]
        out[col] = ((score - predict(without)) + (predict(alone) - baseline)) / 2
    return pd.DataFrame(out, index=x.index)


def _reasons(contrib: pd.DataFrame, n_reasons: int) -> pd.Series:
    """The signals that pushed each line's score up, strongest first; a signal that added nothing is no reason."""
    def pick(row: pd.Series) -> list[str]:
        ranked = row.sort_values(ascending=False)
        kept = [c for c in ranked.index[:n_reasons] if ranked[c] > MIN_CONTRIBUTION]
        return kept or [ranked.index[0]]
    return contrib.apply(pick, axis=1)


def step3_oddness(features: pd.DataFrame, seed: int = 0, n_reasons: int = 3, fit_on: pd.DataFrame | None = None) -> pd.DataFrame:
    """Step 3: an oddness score on all signals, with the signals that drove each score.

    `fit_on` holds the lines that define normal (all import lines); a line is odd when few of them
    look like it. Without it the lines in `features` define normal among themselves.
    Contributions average what the oddness loses when a signal is set back to its median and what
    it gains when that signal alone is kept: a plain, explainable stand-in for feature attributions.
    """
    base = features if fit_on is None else fit_on[features.columns]
    median = base.median()
    x = features.fillna(median)
    model = IsolationForest(n_estimators=300, random_state=seed).fit(base.fillna(median))
    score = -model.score_samples(x)
    contrib = _contributions(lambda frame: -model.score_samples(frame), x, median)
    reasons = _reasons(contrib, n_reasons).map(lambda cols: [SIGNAL_NAMES.get(c, c) for c in cols])
    return pd.DataFrame({"oddness": np.round(score, 4), "reasons": reasons}, index=x.index)


def learning_score(train: pd.DataFrame, target: pd.Series, apply_to: pd.DataFrame, seed: int = 0) -> tuple[pd.Series, pd.DataFrame]:
    """Step 4: a model trained on past inspection outcomes; returns scores and the three reasons."""
    model = GradientBoostingClassifier(random_state=seed, n_estimators=200, max_depth=3, learning_rate=0.05)
    fill = train.median()
    model.fit(train.fillna(fill), target)
    x = apply_to.fillna(fill)
    score = model.predict_proba(x)[:, 1]
    contrib = _contributions(lambda frame: model.predict_proba(frame)[:, 1], x, fill)
    picked = _reasons(contrib, 3)
    reasons = pd.Series(
        [[{"signal": SIGNAL_NAMES.get(c, c), "contribution": round(float(contrib.at[i, c]), 3)} for c in cols] for i, cols in picked.items()],
        index=x.index,
    )
    return pd.Series(np.round(score, 4), index=x.index), pd.DataFrame({"reasons": reasons})


def hit_rate_at_budget(score: pd.Series, outcome: pd.Series, budget: float = 0.05) -> float:
    """Share of findings among the top `budget` share of lines ranked by score."""
    k = max(1, int(round(len(score) * budget)))
    top = score.sort_values(ascending=False).index[:k]
    return float(outcome.loc[top].mean())
