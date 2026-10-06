"""2B: trader segments, broker scorecard, networks, and the three regimes (warehouse, transit, parcels)."""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


# --------------------------------------------------------------------------- segments and brokers

def trader_profile(declarations: pd.DataFrame) -> pd.DataFrame:
    """Per importer: 12-month import value and a compliance score (0 = clean, higher = worse)."""
    imp = declarations[declarations["flow"] == "import"]
    last12 = imp[imp["month"] > str(pd.Period(imp["month"].max(), freq="M") - 12)]
    g = imp.groupby("trader_ref")
    inspected = g["inspected"].sum().clip(lower=1)
    out = pd.DataFrame({
        "import_value_12m": last12.groupby("trader_ref")["customs_value_lcu"].sum(),
        "findings_per_inspection": g["inspection_outcome"].apply(lambda s: (s == "finding").sum()) / inspected,
        "amended_share": g["status"].apply(lambda s: (s == "amended").mean()),
        "queries_upheld": g["valuation_query"].apply(lambda s: (s == "upheld").sum()),
        "main_broker": g["broker_id"].agg(lambda s: s.value_counts().index[0]),
    }).fillna({"import_value_12m": 0})
    out["compliance_score"] = (out["findings_per_inspection"] + out["amended_share"] + 0.05 * out["queries_upheld"]).round(3)
    return out


def broker_scorecard(declarations: pd.DataFrame) -> pd.DataFrame:
    """Five measures per broker, with the share of its clients that had a finding."""
    imp = declarations[declarations["flow"] == "import"]
    flagged_traders = set(imp.loc[imp["inspection_outcome"] == "finding", "trader_ref"])
    g = imp.groupby("broker_id")
    out = pd.DataFrame({
        "clients": g["trader_ref"].nunique(),
        "lines": g.size(),
        "flagged_client_share": g["trader_ref"].apply(lambda s: np.mean([t in flagged_traders for t in s.unique()])).round(3),
        "amendment_rate": g["status"].apply(lambda s: (s == "amended").mean()).round(3),
        "queries_upheld_rate": g["valuation_query"].apply(lambda s: (s == "upheld").mean()).round(4),
        "mean_release_hours": g["release_hours"].mean().round(1),
    })
    peers = out["flagged_client_share"].median()
    out["vs_peer_median"] = (out["flagged_client_share"] - peers).round(3)
    return out.sort_values("flagged_client_share", ascending=False)


def segments(profile: pd.DataFrame, broker_share: pd.Series | None = None, k: int = 4, seed: int = 0, broker_weight: float = 2.0) -> pd.DataFrame:
    """k-means on value and compliance (and optionally the broker's flagged share): four tiles.

    Each column is standardised; the broker column then counts `broker_weight` times, so the
    risk axis (compliance + weighted broker share) shows what the broker adds.
    """
    cols = {"log_value": np.log1p(profile["import_value_12m"]), "compliance": profile["compliance_score"]}
    if broker_share is not None:
        cols["broker_flagged_share"] = profile["main_broker"].map(broker_share).fillna(0)
    x = StandardScaler().fit_transform(pd.DataFrame(cols))
    if broker_share is not None:
        x[:, 2] *= broker_weight
    model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(x)
    return profile.assign(segment=model.labels_, risk_axis=x[:, 1:].sum(axis=1).round(3))


# --------------------------------------------------------------------------- networks

def build_graph(network: dict) -> nx.Graph:
    graph = nx.Graph()
    for node in network["nodes"]:
        graph.add_node(node["id"], kind=node["kind"], label=node.get("label", node["id"]))
    for edge in network["edges"]:
        graph.add_edge(edge["source"], edge["target"], kind=edge["kind"])
    return graph


def hubs(graph: nx.Graph, kind: str | None = None, top: int = 10) -> pd.DataFrame:
    rows = [{"node": n, "kind": d["kind"], "degree": graph.degree(n)} for n, d in graph.nodes(data=True) if kind is None or d["kind"] == kind]
    return pd.DataFrame(rows).sort_values("degree", ascending=False).head(top).reset_index(drop=True)


def shared_address_clusters(consignees: pd.DataFrame, min_size: int = 6) -> pd.DataFrame:
    """Groups of consignees cleared under one TIN that share one address."""
    g = consignees.groupby(["trader_ref", "address_id"]).size().reset_index(name="consignees")
    return g[g["consignees"] >= min_size].sort_values("consignees", ascending=False)


# --------------------------------------------------------------------------- regimes

def warehouse_gaps(stock: pd.DataFrame, flag: float = 0.08) -> pd.DataFrame:
    gap = stock["opening_stock_lcu"] + stock["entered_lcu"] - stock["exited_lcu"] - stock["declared_stock_lcu"]
    out = stock.assign(gap_lcu=gap.round(0), gap_share=(gap / stock["entered_lcu"]).round(3))
    out["flag"] = out["gap_share"] > flag
    return out


def transit_performance(transit: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    as_of = as_of or pd.to_datetime(transit["opened_at"]).max()
    opened = pd.to_datetime(transit["opened_at"])
    closed = pd.to_datetime(transit["closed_at"])
    hours = (closed - opened).dt.total_seconds() / 3600
    overdue = closed.isna() & ((as_of - opened).dt.total_seconds() / 3600 > transit["deadline_hours"])
    frame = transit.assign(hours=hours, over_norm=hours / transit["route_norm_hours"], open_past_deadline=overdue)
    g = frame.groupby("operator_ref")
    return pd.DataFrame({
        "movements": g.size(), "closure_rate": g["closed_at"].apply(lambda s: s.notna().mean()).round(3),
        "median_hours_vs_norm": g["over_norm"].median().round(2), "open_past_deadline": g["open_past_deadline"].sum(),
    }).sort_values("closure_rate")


def parcel_splitting(parcels: pd.DataFrame, de_minimis: float = 2000.0, min_count: int = 6, near: float = 0.9) -> pd.DataFrame:
    near_max = parcels["max_value_lcu"] >= near * de_minimis
    frame = parcels.assign(near_threshold=near_max & (parcels["consignments"] >= min_count))
    g = frame.groupby("consignee_id")
    return pd.DataFrame({
        "months": g.size(), "months_flagged": g["near_threshold"].sum(), "mean_consignments": g["consignments"].mean().round(1),
        "max_value_lcu": g["max_value_lcu"].max(),
    }).sort_values(["months_flagged", "mean_consignments"], ascending=False)
