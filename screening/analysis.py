"""Pure analysis over screening decisions. No I/O, no framework imports.

`DecisionRecord` is the normalized unit: one AI conclusion on one candidate at one
pipeline step. `analyze()` turns a stream of them into the numbers the UI shows.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

POSITIVE = "positive"
NEGATIVE = "negative"
OPT_OUT = "opt_out"
PENDING = "pending"

_DECISION_MAP = {
    "PositiveDecision": POSITIVE,
    "NegativeDecision": NEGATIVE,
    "OptOutNoAnswer": OPT_OUT,
    "OptOutDeclineToTalkWithAI": OPT_OUT,
    "OptOutDeclineToContinueApplication": OPT_OUT,
    # the *Conclusion spelling also appears in some payloads
    "PositiveConclusion": POSITIVE,
    "NegativeConclusion": NEGATIVE,
}

_UNKNOWN_JOB = "Unknown job"
_UNKNOWN_STEP = "Unknown step"


def classify_decision(raw: str | None) -> str:
    if not raw:
        return PENDING
    return _DECISION_MAP.get(raw, PENDING)


def normalize_reason(text: str | None) -> str:
    """Collapse a free-text summary/explanation to a comparable phrase.

    Whitespace-collapsed, first sentence only, lowercased, trailing period dropped.
    Deliberately simple; swap in real clustering later if the reason text is noisy.
    """
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return text.rstrip(".").strip().lower()


@dataclass(frozen=True)
class DecisionRecord:
    person_slug: str
    application_id: str
    job_id: str
    job_title: str
    step_name: str
    step_category: str
    decision: str
    raw_decision: str
    summary: str
    explanation: str
    needs_human_review: bool

    @property
    def job_key(self) -> str:
        return self.job_title or self.job_id or _UNKNOWN_JOB

    @property
    def step_key(self) -> str:
        return self.step_category or self.step_name or _UNKNOWN_STEP

    @property
    def reason_text(self) -> str:
        return normalize_reason(self.summary) or normalize_reason(self.explanation)


@dataclass
class GroupStats:
    total: int = 0
    counts: Counter = field(default_factory=Counter)
    rejection_reasons: Counter = field(default_factory=Counter)

    @property
    def decided(self) -> int:
        return self.counts[POSITIVE] + self.counts[NEGATIVE]

    @property
    def negative_rate(self) -> float:
        return self.counts[NEGATIVE] / self.decided if self.decided else 0.0

    def top_rejection_reasons(self, n: int = 5) -> list[tuple[str, int]]:
        return self.rejection_reasons.most_common(n)


@dataclass
class AnalysisResult:
    total_records: int
    overall: GroupStats
    by_job: dict[str, GroupStats]
    by_step: dict[str, GroupStats]
    rejection_reasons: Counter
    positive_signals: Counter
    needs_human_review: int

    def top_rejection_reasons(self, n: int = 10) -> list[tuple[str, int]]:
        return self.rejection_reasons.most_common(n)

    def top_positive_signals(self, n: int = 10) -> list[tuple[str, int]]:
        return self.positive_signals.most_common(n)


# -- record extraction (pure dict -> DecisionRecord) ------------------------


def record_from_search_item(item: dict[str, Any]) -> DecisionRecord:
    """From one ApplicationSearchListData row (current step only)."""
    app = item.get("Application") or {}
    person = item.get("Person") or {}
    job = item.get("Job") or {}
    return DecisionRecord(
        person_slug=person.get("PersonSlug", ""),
        application_id=str(app.get("ID") or job.get("JobPositionID") or ""),
        job_id=str(job.get("PaulsjobJobID") or ""),
        job_title=job.get("JobPositionTitle") or "",
        step_name=item.get("StepName") or "",
        step_category=item.get("StepCategory") or "",
        raw_decision=item.get("PaulDecision") or "",
        decision=classify_decision(item.get("PaulDecision")),
        summary=item.get("PaulDecisionSummary") or "",
        explanation=item.get("Comment") or "",
        needs_human_review=bool(item.get("HumanReview")),
    )


def records_from_detail(detail: dict[str, Any]) -> Iterable[DecisionRecord]:
    """From one DetailedJobApplication: one record per JobStepAssignmentHistory entry."""
    person = detail.get("Person") or {}
    job_pos = detail.get("JobPosition") or {}
    app_id = str(detail.get("ID") or "")
    job_title = job_pos.get("Title") or job_pos.get("title") or ""
    for entry in detail.get("JobStepAssignmentHistory") or []:
        raw = entry.get("PaulDecision") or ""
        yield DecisionRecord(
            person_slug=person.get("PersonSlug", ""),
            application_id=app_id,
            job_id=str(entry.get("PaulsjobJobID") or detail.get("PaulsjobJobID") or ""),
            job_title=job_title,
            step_name=entry.get("StepName") or "",
            step_category=entry.get("StepCategory") or "",
            raw_decision=raw,
            decision=classify_decision(raw),
            summary=entry.get("PaulDecisionSummary") or "",
            explanation=entry.get("PaulDecisionExplanation") or "",
            needs_human_review=bool(entry.get("HumanReview")),
        )


# -- aggregation ----------------------------------------------------------


def analyze(records: Iterable[DecisionRecord]) -> AnalysisResult:
    records = list(records)
    overall = GroupStats()
    by_job: dict[str, GroupStats] = defaultdict(GroupStats)
    by_step: dict[str, GroupStats] = defaultdict(GroupStats)
    rejection_reasons: Counter = Counter()
    positive_signals: Counter = Counter()
    needs_human_review = 0

    for record in records:
        job = by_job[record.job_key]
        step = by_step[record.step_key]
        for group in (overall, job, step):
            group.total += 1
            group.counts[record.decision] += 1

        if record.needs_human_review:
            needs_human_review += 1

        if record.decision == NEGATIVE:
            reason = record.reason_text
            if reason:
                rejection_reasons[reason] += 1
                job.rejection_reasons[reason] += 1
                step.rejection_reasons[reason] += 1
        elif record.decision == POSITIVE:
            signal = normalize_reason(record.summary)
            if signal:
                positive_signals[signal] += 1

    return AnalysisResult(
        total_records=len(records),
        overall=overall,
        by_job=dict(by_job),
        by_step=dict(by_step),
        rejection_reasons=rejection_reasons,
        positive_signals=positive_signals,
        needs_human_review=needs_human_review,
    )
