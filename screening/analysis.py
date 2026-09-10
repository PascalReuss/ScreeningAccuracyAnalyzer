"""Pure analysis over screening decisions. No I/O, no framework imports.

`DecisionRecord` is the normalized unit: one AI conclusion on one candidate at one
pipeline step. `analyze()` turns a stream of them into the numbers the UI shows.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping

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


def _period(date_str: str) -> str | None:
    """Bucket an ISO timestamp into an ISO week label (``2026-W32``).

    Falls back to the date prefix if the string does not parse; returns None
    when there is no date at all.
    """
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return date_str[:10] or None
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


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
    agent_review: bool = False
    human_raw_decision: str = ""
    application_date: str = ""

    @property
    def human_decision(self) -> str:
        """The human reviewer's verdict, classified like ``decision``.

        Empty ``human_raw_decision`` (no verdict recorded) classifies to
        ``PENDING``; callers compare agreement only when a verdict is present.
        """
        return classify_decision(self.human_raw_decision)

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
class AgreementStats:
    """AI vs. human/agent review of the same conclusion.

    ``reviewed`` counts conclusions that carry a human verdict to compare
    against; ``human_review_flag`` / ``agent_review_flag`` count the raw review
    flags regardless of whether a verdict was recorded.
    """

    human_review_flag: int = 0
    agent_review_flag: int = 0
    reviewed: int = 0
    agree: int = 0
    disagree: int = 0
    confusion: Counter = field(default_factory=Counter)  # (ai_decision, human_decision)

    @property
    def agreement_rate(self) -> float | None:
        return self.agree / self.reviewed if self.reviewed else None

    def confusion_rows(self) -> list[tuple[str, str, int]]:
        rows = [(ai, human, n) for (ai, human), n in self.confusion.items()]
        rows.sort(key=lambda r: r[2], reverse=True)
        return rows


@dataclass
class AnalysisResult:
    total_records: int
    overall: GroupStats
    by_job: dict[str, GroupStats]
    by_step: dict[str, GroupStats]
    rejection_reasons: Counter
    positive_signals: Counter
    needs_human_review: int
    agreement: AgreementStats = field(default_factory=AgreementStats)
    opt_out_by_type: Counter = field(default_factory=Counter)
    opt_out_by_step: Counter = field(default_factory=Counter)
    decisions_over_time: list[tuple[str, Counter]] = field(default_factory=list)

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
        agent_review=bool(item.get("AgentReview")),
        human_raw_decision=item.get("HumanDecision") or "",
        application_date=(app.get("ApplicationDate") or ""),
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
            agent_review=bool(entry.get("AgentReview")),
            human_raw_decision=entry.get("HumanDecision") or "",
            application_date=entry.get("StepDate") or detail.get("ApplicationDate") or "",
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
    agreement = AgreementStats()
    opt_out_by_type: Counter = Counter()
    opt_out_by_step: Counter = Counter()
    over_time: dict[str, Counter] = defaultdict(Counter)

    for record in records:
        job = by_job[record.job_key]
        step = by_step[record.step_key]
        for group in (overall, job, step):
            group.total += 1
            group.counts[record.decision] += 1

        if record.needs_human_review:
            needs_human_review += 1
            agreement.human_review_flag += 1
        if record.agent_review:
            agreement.agent_review_flag += 1
        if record.human_raw_decision:
            human = record.human_decision
            agreement.reviewed += 1
            agreement.confusion[(record.decision, human)] += 1
            if human == record.decision:
                agreement.agree += 1
            else:
                agreement.disagree += 1

        if record.decision == OPT_OUT:
            opt_out_by_type[record.raw_decision or "Unknown"] += 1
            opt_out_by_step[record.step_key] += 1

        period = _period(record.application_date)
        if period:
            over_time[period][record.decision] += 1

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
        agreement=agreement,
        opt_out_by_type=opt_out_by_type,
        opt_out_by_step=opt_out_by_step,
        decisions_over_time=sorted(
            (period, counts) for period, counts in over_time.items()
        ),
    )


# -- assessments ---------------------------------------------------------
#
# Structured assessments come from GET /company/person/{slug}/assessments, one
# call per candidate (there is no company-wide list). `AssessmentRecord` is the
# normalized unit: one Assessment for one candidate, with the job it was taken
# for joined back in. `AssessmentDetails` is schema-free (additionalProperties),
# so every key is read defensively.

_UNKNOWN_TYPE = "Unknown type"


def _as_float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class AssessmentRecord:
    person_slug: str
    job_id: str
    job_title: str
    assessment_id: str
    type: str
    status: str
    score: float | None
    passing_score: float | None
    assessed_at: str
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def type_key(self) -> str:
        return self.type or _UNKNOWN_TYPE

    @property
    def job_key(self) -> str:
        return self.job_title or self.job_id or _UNKNOWN_JOB

    @property
    def is_completed(self) -> bool:
        return self.status.lower() == "completed"

    @property
    def passed(self) -> bool | None:
        if self.score is None or self.passing_score is None:
            return None
        return self.score >= self.passing_score


@dataclass
class AssessmentTypeStats:
    total: int = 0
    completed: int = 0
    status_counts: Counter = field(default_factory=Counter)
    scores: list[float] = field(default_factory=list)
    graded: int = 0
    passed: int = 0

    @property
    def mean_score(self) -> float | None:
        return statistics.fmean(self.scores) if self.scores else None

    @property
    def min_score(self) -> float | None:
        return min(self.scores) if self.scores else None

    @property
    def max_score(self) -> float | None:
        return max(self.scores) if self.scores else None

    @property
    def pass_rate(self) -> float | None:
        return self.passed / self.graded if self.graded else None


@dataclass(frozen=True)
class AssessmentDisagreement:
    """One assessment result that contradicts the AI's screening decision."""

    person_slug: str
    job_title: str
    type: str
    score: float
    passing_score: float
    ai_decision: str
    kind: str  # "rejected_but_passed" | "advanced_but_failed"


@dataclass
class AssessmentAnalysis:
    total_records: int
    candidates: int
    by_type: dict[str, AssessmentTypeStats]
    all_scores: list[float]
    by_job: dict[str, AssessmentTypeStats] = field(default_factory=dict)
    scores_by_decision: dict[str, list[float]] = field(default_factory=dict)
    disagreements: list[AssessmentDisagreement] = field(default_factory=list)

    @property
    def mean_score(self) -> float | None:
        return statistics.fmean(self.all_scores) if self.all_scores else None


def _accumulate(stats: AssessmentTypeStats, record: AssessmentRecord) -> None:
    stats.total += 1
    stats.status_counts[record.status or "unknown"] += 1
    if record.is_completed:
        stats.completed += 1
    if record.score is not None:
        stats.scores.append(record.score)
    passed = record.passed
    if passed is not None:
        stats.graded += 1
        if passed:
            stats.passed += 1


def assessment_records_from_api(
    raw_by_slug: Mapping[str, Iterable[dict[str, Any]]],
    job_lookup: Mapping[str, Mapping[str, str]] | None = None,
) -> list[AssessmentRecord]:
    """Flatten ``{person_slug: Assessment[]}`` into records.

    ``job_lookup`` optionally maps a slug to ``{"job_id", "job_title"}`` so each
    assessment carries the job the candidate applied for (assessments themselves
    are not job-scoped in the API).
    """
    job_lookup = job_lookup or {}
    records: list[AssessmentRecord] = []
    for slug, assessments in raw_by_slug.items():
        job = job_lookup.get(slug) or {}
        for a in assessments or []:
            details = a.get("AssessmentDetails")
            if not isinstance(details, Mapping):
                details = {}
            records.append(
                AssessmentRecord(
                    person_slug=slug,
                    job_id=str(job.get("job_id") or ""),
                    job_title=job.get("job_title") or "",
                    assessment_id=str(a.get("ID") or ""),
                    type=a.get("Type") or "",
                    status=a.get("Status") or "",
                    score=_as_float(a.get("AssessmentScore")),
                    passing_score=_as_float(details.get("PassingScore")),
                    assessed_at=a.get("AssessedAt") or "",
                    details=dict(details),
                )
            )
    return records


def analyze_assessments(
    records: Iterable[AssessmentRecord],
    decision_by_slug: Mapping[str, str] | None = None,
) -> AssessmentAnalysis:
    """Aggregate assessment records.

    ``decision_by_slug`` maps a candidate slug to their classified screening
    decision (``POSITIVE`` / ``NEGATIVE`` / ...). When given, scores are also
    split by that decision and contradictions are collected: a rejected
    candidate who passed, or an advanced candidate who failed.
    """
    decision_by_slug = decision_by_slug or {}
    records = list(records)
    by_type: dict[str, AssessmentTypeStats] = defaultdict(AssessmentTypeStats)
    by_job: dict[str, AssessmentTypeStats] = defaultdict(AssessmentTypeStats)
    all_scores: list[float] = []
    candidates: set[str] = set()
    scores_by_decision: dict[str, list[float]] = defaultdict(list)
    disagreements: list[AssessmentDisagreement] = []

    for record in records:
        candidates.add(record.person_slug)
        _accumulate(by_type[record.type_key], record)
        _accumulate(by_job[record.job_key], record)
        if record.score is not None:
            all_scores.append(record.score)

        decision = decision_by_slug.get(record.person_slug)
        if decision and record.score is not None:
            scores_by_decision[decision].append(record.score)

        if decision in (POSITIVE, NEGATIVE) and record.passed is not None:
            if decision == NEGATIVE and record.passed:
                kind = "rejected_but_passed"
            elif decision == POSITIVE and not record.passed:
                kind = "advanced_but_failed"
            else:
                kind = ""
            if kind:
                disagreements.append(
                    AssessmentDisagreement(
                        person_slug=record.person_slug,
                        job_title=record.job_title,
                        type=record.type_key,
                        score=record.score,
                        passing_score=record.passing_score,
                        ai_decision=decision,
                        kind=kind,
                    )
                )

    disagreements.sort(key=lambda d: abs(d.score - d.passing_score), reverse=True)
    return AssessmentAnalysis(
        total_records=len(records),
        candidates=len(candidates),
        by_type=dict(by_type),
        all_scores=all_scores,
        by_job=dict(by_job),
        scores_by_decision=dict(scores_by_decision),
        disagreements=disagreements,
    )
