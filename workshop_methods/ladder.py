"""The 1B ladder: a rule, distance from normal, an oddness score, a learning score.

Plain words -> technical: rule -> percentile threshold; distance from normal -> robust z-score;
oddness score -> anomaly score (isolation forest); learning score -> supervised model
(gradient boosting); the three reasons -> feature contributions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest

SIGNAL_NAMES = {
    "price_gap": "price below peers",
    "own_gap": "below its own history",
    "p_higher_duty_code": "description fits a dearer code",
    "doubtful_claim": "origin claim doubtful",
    "new_importer": "new importer",
    "changed_share": "often amended or withdrawn",
}


def step1_rule(ratio: pd.Series, percentile: float = 10.0) -> pd.Series:
    """Step 1: flag the lines in the bottom `percentile` of value against peers."""
    cut = np.nanpercentile(ratio, percentile)
    return ratio <= cut


def step2_distance(z: pd.Series, threshold: float = -2.5) -> pd.Series:
    """Step 2: flag lines more than `threshold` typical spreads below normal."""
    return z <= threshold


def step3_oddness(features: pd.DataFrame, seed: int = 0, n_reasons: int = 3) -> pd.DataFrame:
    """Step 3: an oddness score on all signals, with the signals that drove each score.

    Contributions are approximated by resetting one signal at a time to its median and measuring
    how much the oddness drops: a plain, explainable stand-in for feature attributions.
    """
    x = features.fillna(features.median())
    model = IsolationForest(n_estimators=300, random_state=seed).fit(x)
    score = -model.score_samples(x)
    contrib = {}
    for col in x.columns:
        reset = x.copy()
        reset[col] = x[col].median()
        contrib[col] = score - (-model.score_samples(reset))
    contrib = pd.DataFrame(contrib, index=x.index)
    reasons = contrib.apply(lambda r: [SIGNAL_NAMES.get(c, c) for c in r.sort_values(ascending=False).index[:n_reasons]], axis=1)
    return pd.DataFrame({"oddness": np.round(score, 4), "reasons": reasons}, index=x.index)


def learning_score(train: pd.DataFrame, target: pd.Series, apply_to: pd.DataFrame, seed: int = 0) -> tuple[pd.Series, pd.DataFrame]:
    """Step 4: a model trained on past inspection outcomes; returns scores and the three reasons."""
    model = GradientBoostingClassifier(random_state=seed, n_estimators=200, max_depth=3, learning_rate=0.05)
    fill = train.median()
    model.fit(train.fillna(fill), target)
    x = apply_to.fillna(fill)
    score = model.predict_proba(x)[:, 1]
    contrib = {}
    for col in x.columns:
        reset = x.copy()
        reset[col] = fill[col]
        contrib[col] = score - model.predict_proba(reset)[:, 1]
    contrib = pd.DataFrame(contrib, index=x.index)
    reasons = contrib.apply(
        lambda r: [{"signal": SIGNAL_NAMES.get(c, c), "contribution": round(float(r[c]), 3)} for c in r.sort_values(ascending=False).index[:3]],
        axis=1,
    )
    return pd.Series(np.round(score, 4), index=x.index), pd.DataFrame({"reasons": reasons})


def hit_rate_at_budget(score: pd.Series, outcome: pd.Series, budget: float = 0.05) -> float:
    """Share of findings among the top `budget` share of lines ranked by score."""
    k = max(1, int(round(len(score) * budget)))
    top = score.sort_values(ascending=False).index[:k]
    return float(outcome.loc[top].mean())
