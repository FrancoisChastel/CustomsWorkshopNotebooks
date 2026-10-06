"""Display helpers for the Colab notebooks: the steps in plain words, styled tables, charts in the
workshop colours, the finding sentence, hints and the locked reveal.

Every analysis cell follows the same order (Brief 0): the question as understood, the steps,
the table or chart, then the finding sentence. Code stays folded under the cell title.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import zlib
from typing import Any

import pandas as pd

COLORS = {
    "navy": "#0E2F5A", "navy2": "#1A4278", "light": "#F5F7FA", "ink": "#3C4A5E", "accent": "#1F6FC2",
    "amber": "#C98A1C", "card": "#FDFDFC", "border": "#D9E0EA", "tint": "#E9EEF5", "muted": "#6A7686",
    "pale": "#9FC3EA", "soft": "#D6E2F0",
}
LABEL = "IMF · Data and AI for Customs"
MAX_COLUMNS = 8  # tables stay readable on a phone screen
HINTS_USED: dict[str, int] = {}  # analysis_id -> highest hint level shown, read in the debrief
_KDF_ROUNDS = 200_000


def _display(obj: Any) -> None:
    try:
        from IPython.display import display
    except ImportError:  # plain Python: print instead
        print(obj if not hasattr(obj, "data") else obj.data)
        return
    display(obj)


def _markdown(text: str) -> None:
    try:
        from IPython.display import Markdown
    except ImportError:
        print(text)
        return
    _display(Markdown(text))


def use_style() -> None:
    """Matplotlib in the workshop colours: accent for the main series, muted for the rest."""
    import matplotlib as mpl
    from cycler import cycler

    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
        "axes.edgecolor": COLORS["border"], "axes.labelcolor": COLORS["ink"], "axes.titlecolor": COLORS["navy"],
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": COLORS["tint"],
        "axes.prop_cycle": cycler(color=[COLORS["accent"], COLORS["muted"], COLORS["pale"], COLORS["navy2"]]),
        "xtick.color": COLORS["ink"], "ytick.color": COLORS["ink"], "figure.dpi": 100, "figure.figsize": (8.6, 4.2),
    })


def chart(title: str, height: float = 4.2):
    """A figure no wider than 900 px whose title states the finding; returns (figure, axes)."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.6, height))
    ax.set_title(title)
    fig.text(0.01, 0.01, LABEL, fontsize=7, color=COLORS["muted"])
    return fig, ax


def steps(question: str, *plain_steps: str) -> None:
    """The question as understood, then the steps in plain words."""
    lines = [f"**Question.** {question}"] + [f"{i}. {step}" for i, step in enumerate(plain_steps, 1)]
    _markdown("\n\n".join(lines[:1]) + "\n\n" + "\n".join(lines[1:]))


def finding(sentence: str) -> str:
    """The sentence every analysis cell ends with, built from the data."""
    _markdown(f"**Finding.** {sentence}")
    return sentence


def show(frame: pd.DataFrame, formats: dict[str, str] | None = None, highlight: pd.Series | None = None, max_rows: int = 20):
    """A styled table of at most eight columns; rows in `highlight` (a boolean Series) are amber."""
    if frame.shape[1] > MAX_COLUMNS:
        raise ValueError(f"{frame.shape[1]} columns: keep tables to {MAX_COLUMNS} so they read on a phone")
    view = frame.head(max_rows)
    styler = view.style.format(formats or {}, na_rep="–").set_table_styles([
        {"selector": "th", "props": [("background-color", COLORS["tint"]), ("color", COLORS["navy"]), ("text-align", "left")]},
        {"selector": "td", "props": [("color", COLORS["ink"])]},
    ])
    if highlight is not None:
        marked = highlight.reindex(view.index).fillna(False).astype(bool)
        styler = styler.apply(lambda row: [f"background-color: {COLORS['amber']}33" if bool(marked.loc[row.name]) else "" for _ in row], axis=1)
    _display(styler)
    return styler


def hint(level: int, hints: tuple[str, ...] | list[str], analysis_id: str) -> None:
    """Prints hints H1..H`level`; hints are the method being taught, counted and never penalised."""
    level = max(0, min(int(level), len(hints)))
    if level:
        HINTS_USED[analysis_id] = max(HINTS_USED.get(analysis_id, 0), level)
        _markdown("\n\n".join(f"**H{i}.** {text}" for i, text in enumerate(hints[:level], 1)))


# --------------------------------------------------------------------------- the locked reveal

def _key(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.strip().encode("utf-8"), salt, _KDF_ROUNDS, dklen=32)


def _stream(key: bytes, size: int) -> bytes:
    blocks = (hashlib.sha256(key + i.to_bytes(8, "big")).digest() for i in range(size // 32 + 1))
    return b"".join(blocks)[:size]


def seal(code: str, payload: Any, salt: bytes | None = None) -> dict[str, str]:
    """Encrypt the reveal with the facilitator's code (used when the notebooks are built)."""
    salt = salt if salt is not None else os.urandom(16)
    key = _key(code, salt)
    plain = zlib.compress(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"), 9)
    cipher = bytes(a ^ b for a, b in zip(plain, _stream(key, len(plain))))
    mac = hmac.new(key, cipher, hashlib.sha256).hexdigest()
    return {"salt": base64.b64encode(salt).decode(), "data": base64.b64encode(cipher).decode(), "mac": mac}


def unseal(code: str, sealed: dict[str, str]) -> Any | None:
    """The reveal when the code is right; None (and nothing printed) otherwise."""
    if not code or not code.strip():
        return None
    key = _key(code, base64.b64decode(sealed["salt"]))
    cipher = base64.b64decode(sealed["data"])
    if not hmac.compare_digest(hmac.new(key, cipher, hashlib.sha256).hexdigest(), sealed["mac"]):
        return None
    plain = bytes(a ^ b for a, b in zip(cipher, _stream(key, len(cipher))))
    return json.loads(zlib.decompress(plain).decode("utf-8"))
