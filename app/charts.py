"""Plotly figure builders. Each returns an HTML fragment (no <html>, no plotly.js).

plotly.js is loaded once in base.html, so fragments use include_plotlyjs=False.
Colours and layout defaults live only here.
"""
from __future__ import annotations

import plotly.graph_objects as go
from plotly.io import to_html

from screening.analysis import (
    NEGATIVE,
    OPT_OUT,
    PENDING,
    POSITIVE,
    AnalysisResult,
    GroupStats,
)

_ORDER = [POSITIVE, NEGATIVE, OPT_OUT, PENDING]
_LABELS = {
    POSITIVE: "Positive",
    NEGATIVE: "Negative",
    OPT_OUT: "Opt-out",
    PENDING: "Pending",
}
_COLORS = {
    POSITIVE: "#2e7d32",
    NEGATIVE: "#c62828",
    OPT_OUT: "#f9a825",
    PENDING: "#90a4ae",
}


def _fragment(fig: go.Figure) -> str:
    fig.update_layout(
        margin=dict(l=50, r=20, t=55, b=60),
        height=380,
        template="plotly_white",
        legend=dict(orientation="h", y=-0.2),
    )
    return to_html(
        fig,
        full_html=False,
        include_plotlyjs=False,
        config={"displayModeBar": False},
    )


def _empty(message: str) -> str:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=15))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _fragment(fig)


def decision_breakdown(result: AnalysisResult) -> str:
    counts = result.overall.counts
    if result.total_records == 0:
        return _empty("No screening decisions found")
    fig = go.Figure(
        go.Bar(
            x=[_LABELS[k] for k in _ORDER],
            y=[counts.get(k, 0) for k in _ORDER],
            marker_color=[_COLORS[k] for k in _ORDER],
        )
    )
    fig.update_layout(title="Screening decisions", yaxis_title="Conclusions")
    return _fragment(fig)


def rejection_reasons(result: AnalysisResult, n: int = 10) -> str:
    items = result.top_rejection_reasons(n)
    if not items:
        return _empty("No rejection reasons found")
    labels, values = zip(*items)
    fig = go.Figure(
        go.Bar(
            x=list(values),
            y=[label.capitalize() for label in labels],
            orientation="h",
            marker_color=_COLORS[NEGATIVE],
        )
    )
    fig.update_layout(
        title=f"Top {len(items)} rejection reasons", xaxis_title="Occurrences"
    )
    fig.update_yaxes(autorange="reversed")
    return _fragment(fig)


def by_group(groups: dict[str, GroupStats], title: str, limit: int = 15) -> str:
    ordered = sorted(groups.items(), key=lambda kv: kv[1].total, reverse=True)[:limit]
    if not ordered:
        return _empty("No data")
    names = [name for name, _ in ordered]
    fig = go.Figure()
    for decision in _ORDER:
        fig.add_bar(
            name=_LABELS[decision],
            x=names,
            y=[stats.counts.get(decision, 0) for _, stats in ordered],
            marker_color=_COLORS[decision],
        )
    fig.update_layout(
        barmode="stack",
        title=title,
        yaxis_title="Conclusions",
        xaxis_tickangle=-30,
    )
    return _fragment(fig)
