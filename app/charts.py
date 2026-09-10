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
    AssessmentAnalysis,
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


def _fragment(fig: go.Figure, *, bottom: int = 60, legend_y: float = -0.2) -> str:
    fig.update_layout(
        margin=dict(l=50, r=20, t=55, b=bottom),
        height=380,
        template="plotly_white",
        legend=dict(orientation="h", y=legend_y),
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


def positive_signals(result: AnalysisResult, n: int = 10) -> str:
    items = result.top_positive_signals(n)
    if not items:
        return _empty("No positive signals found")
    labels, values = zip(*items)
    fig = go.Figure(
        go.Bar(
            x=list(values),
            y=[label.capitalize() for label in labels],
            orientation="h",
            marker_color=_COLORS[POSITIVE],
        )
    )
    fig.update_layout(
        title=f"Top {len(items)} positive signals", xaxis_title="Occurrences"
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
    return _fragment(fig, bottom=130, legend_y=-0.45)


_ASSESSMENT_COLOR = "#1565c0"


def assessment_scores(analysis: AssessmentAnalysis) -> str:
    """Mean score per assessment type, with min/max whiskers."""
    typed = [
        (name, stats)
        for name, stats in analysis.by_type.items()
        if stats.mean_score is not None
    ]
    typed.sort(key=lambda kv: kv[1].mean_score or 0, reverse=True)
    if not typed:
        return _empty("No scored assessments found")
    names = [name for name, _ in typed]
    means = [stats.mean_score for _, stats in typed]
    fig = go.Figure(
        go.Bar(
            x=names,
            y=means,
            marker_color=_ASSESSMENT_COLOR,
            error_y=dict(
                type="data",
                symmetric=False,
                array=[s.max_score - s.mean_score for _, s in typed],
                arrayminus=[s.mean_score - s.min_score for _, s in typed],
            ),
        )
    )
    fig.update_layout(
        title="Mean assessment score by type", yaxis_title="Score", xaxis_tickangle=-30
    )
    return _fragment(fig)


_OPT_OUT_LABELS = {
    "OptOutNoAnswer": "No answer",
    "OptOutDeclineToTalkWithAI": "Declined AI interview",
    "OptOutDeclineToContinueApplication": "Withdrew application",
}


def human_agreement(result: AnalysisResult) -> str:
    """Agree vs. disagree count over conclusions that carry a human verdict."""
    a = result.agreement
    if a.reviewed == 0:
        return _empty("No human-reviewed decisions to compare")
    fig = go.Figure(
        go.Bar(
            x=["Agree", "Disagree"],
            y=[a.agree, a.disagree],
            marker_color=[_COLORS[POSITIVE], _COLORS[NEGATIVE]],
        )
    )
    fig.update_layout(
        title="AI vs. human decision agreement", yaxis_title="Reviewed conclusions"
    )
    return _fragment(fig)


def opt_out_breakdown(result: AnalysisResult) -> str:
    items = result.opt_out_by_type.most_common()
    if not items:
        return _empty("No opt-outs recorded")
    labels = [_OPT_OUT_LABELS.get(k, k or "Unknown") for k, _ in items]
    fig = go.Figure(
        go.Bar(
            x=[v for _, v in items],
            y=labels,
            orientation="h",
            marker_color=_COLORS[OPT_OUT],
        )
    )
    fig.update_layout(title="Opt-out reasons", xaxis_title="Candidates")
    fig.update_yaxes(autorange="reversed")
    return _fragment(fig)


def decisions_over_time(result: AnalysisResult) -> str:
    buckets = result.decisions_over_time
    if not buckets:
        return _empty("No dated decisions")
    periods = [period for period, _ in buckets]
    fig = go.Figure()
    for decision in _ORDER:
        fig.add_bar(
            name=_LABELS[decision],
            x=periods,
            y=[counts.get(decision, 0) for _, counts in buckets],
            marker_color=_COLORS[decision],
        )
    fig.update_layout(
        barmode="stack", title="Decisions over time (ISO week)", yaxis_title="Conclusions"
    )
    return _fragment(fig)


def assessment_scores_by_decision(analysis: AssessmentAnalysis) -> str:
    """Score distribution split by the AI's screening decision."""
    data = [
        (decision, analysis.scores_by_decision.get(decision, []))
        for decision in _ORDER
    ]
    data = [(decision, scores) for decision, scores in data if scores]
    if not data:
        return _empty("No assessment scores linked to a decision")
    fig = go.Figure()
    for decision, scores in data:
        fig.add_box(
            y=scores,
            name=_LABELS[decision],
            marker_color=_COLORS[decision],
            boxmean=True,
        )
    fig.update_layout(
        title="Assessment score by AI decision", yaxis_title="Score", showlegend=False
    )
    return _fragment(fig)


def assessments_by_job(analysis: AssessmentAnalysis) -> str:
    typed = [
        (name, stats)
        for name, stats in analysis.by_job.items()
        if stats.mean_score is not None
    ]
    typed.sort(key=lambda kv: kv[1].mean_score or 0, reverse=True)
    if not typed:
        return _empty("No scored assessments to break down by job")
    fig = go.Figure(
        go.Bar(
            x=[name for name, _ in typed],
            y=[stats.mean_score for _, stats in typed],
            marker_color=_ASSESSMENT_COLOR,
            text=[
                f"{stats.pass_rate * 100:.0f}% pass" if stats.pass_rate is not None else ""
                for _, stats in typed
            ],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Mean assessment score by job", yaxis_title="Score", xaxis_tickangle=-30
    )
    return _fragment(fig)


def assessment_pass_rate(analysis: AssessmentAnalysis) -> str:
    """Pass rate per type (only types with a PassingScore in AssessmentDetails)."""
    typed = [
        (name, stats.pass_rate)
        for name, stats in analysis.by_type.items()
        if stats.pass_rate is not None
    ]
    typed.sort(key=lambda kv: kv[1], reverse=True)
    if not typed:
        return _empty("No assessments with a passing score")
    names, rates = zip(*typed)
    fig = go.Figure(
        go.Bar(
            x=[r * 100 for r in rates],
            y=list(names),
            orientation="h",
            marker_color=_COLORS[POSITIVE],
        )
    )
    fig.update_layout(title="Assessment pass rate by type", xaxis_title="Pass rate (%)")
    fig.update_xaxes(range=[0, 100])
    fig.update_yaxes(autorange="reversed")
    return _fragment(fig)
