from screening.analysis import (
    NEGATIVE,
    OPT_OUT,
    PENDING,
    POSITIVE,
    DecisionRecord,
    analyze,
    analyze_assessments,
    assessment_records_from_api,
    classify_decision,
    normalize_reason,
    record_from_search_item,
)


def _record(decision="NegativeDecision", job="Backend Engineer", step="PreScreening",
            summary="Does not meet the minimum years of experience.", hitl=False,
            slug="p", human_decision="", application_date=""):
    return DecisionRecord(
        person_slug=slug,
        application_id="a",
        job_id="1",
        job_title=job,
        step_name=step,
        step_category=step,
        raw_decision=decision,
        decision=classify_decision(decision),
        summary=summary,
        explanation="",
        needs_human_review=hitl,
        human_raw_decision=human_decision,
        application_date=application_date,
    )


def test_classify_decision_maps_known_and_falls_back_to_pending():
    assert classify_decision("PositiveDecision") == POSITIVE
    assert classify_decision("NegativeDecision") == NEGATIVE
    assert classify_decision("OptOutNoAnswer") == OPT_OUT
    assert classify_decision("NegativeConclusion") == NEGATIVE
    assert classify_decision(None) == PENDING
    assert classify_decision("Something else") == PENDING


def test_normalize_reason_collapses_and_takes_first_sentence():
    assert normalize_reason("  Too   junior.\nHas 1 year. Needs 3.") == "too junior"
    assert normalize_reason("") == ""
    assert normalize_reason(None) == ""


def test_analyze_groups_and_tallies_reasons():
    records = [
        _record("NegativeDecision"),
        _record("NegativeDecision"),
        _record("PositiveDecision", summary="Strong Python background."),
        _record("OptOutNoAnswer", job="Data Analyst", summary=""),
    ]
    result = analyze(records)

    assert result.total_records == 4
    assert result.overall.counts[NEGATIVE] == 2
    assert result.overall.counts[POSITIVE] == 1
    assert result.overall.counts[OPT_OUT] == 1
    assert result.overall.negative_rate == 2 / 3

    assert result.rejection_reasons["does not meet the minimum years of experience"] == 2
    assert result.top_positive_signals(1) == [("strong python background", 1)]

    assert set(result.by_job) == {"Backend Engineer", "Data Analyst"}
    assert result.by_step["PreScreening"].counts[NEGATIVE] == 2


def test_analyze_counts_human_review_flag():
    result = analyze([_record(hitl=True), _record(hitl=False)])
    assert result.needs_human_review == 1


def test_analyze_agreement_compares_human_verdict():
    result = analyze([
        _record("NegativeDecision", human_decision="NegativeDecision"),  # agree
        _record("PositiveDecision", human_decision="NegativeDecision"),  # override
        _record("PositiveDecision"),  # no human verdict -> not counted
    ])
    assert result.agreement.reviewed == 2
    assert result.agreement.agree == 1
    assert result.agreement.disagree == 1
    assert result.agreement.agreement_rate == 0.5
    assert result.agreement.confusion[(POSITIVE, NEGATIVE)] == 1


def test_analyze_opt_out_breakdown_by_type_and_step():
    result = analyze([
        _record("OptOutNoAnswer", step="PreScreening"),
        _record("OptOutDeclineToTalkWithAI", step="AIVoiceInterview"),
        _record("OptOutNoAnswer", step="AIVoiceInterview"),
    ])
    assert result.opt_out_by_type["OptOutNoAnswer"] == 2
    assert result.opt_out_by_type["OptOutDeclineToTalkWithAI"] == 1
    assert result.opt_out_by_step["AIVoiceInterview"] == 2


def test_analyze_decisions_over_time_buckets_by_iso_week():
    result = analyze([
        _record("PositiveDecision", application_date="2026-08-03T09:00:00Z"),
        _record("NegativeDecision", application_date="2026-08-04T09:00:00Z"),
        _record("PositiveDecision", application_date="2026-08-17T09:00:00Z"),
        _record("PositiveDecision", application_date=""),  # undated -> skipped
    ])
    buckets = dict(result.decisions_over_time)
    assert list(buckets) == sorted(buckets)  # chronological
    assert len(buckets) == 2
    first_week = result.decisions_over_time[0][1]
    assert first_week[POSITIVE] == 1 and first_week[NEGATIVE] == 1


_RAW_ASSESSMENTS = {
    "alice-001": [
        {
            "ID": "as-1",
            "Type": "technical_assessment",
            "Status": "completed",
            "AssessmentScore": 82,
            "AssessmentDetails": {"PassingScore": 70, "DifficultyLevel": "Intermediate"},
            "AssessedAt": "2026-01-02T00:00:00Z",
        },
        {
            "ID": "as-2",
            "Type": "technical_assessment",
            "Status": "completed",
            "AssessmentScore": 60,
            "AssessmentDetails": {"PassingScore": 70},
        },
    ],
    "bob-002": [
        {
            "ID": "as-3",
            "Type": "language_assessment",
            "Status": "pending",
            "AssessmentScore": None,
            "AssessmentDetails": None,
        }
    ],
    "carol-003": [],
}


def test_assessment_records_join_job_and_read_details_defensively():
    records = assessment_records_from_api(
        _RAW_ASSESSMENTS,
        {"alice-001": {"job_id": "1", "job_title": "Backend Engineer"}},
    )
    assert len(records) == 3
    alice = [r for r in records if r.person_slug == "alice-001"]
    assert alice[0].job_title == "Backend Engineer"
    assert alice[0].passed is True
    assert alice[1].passed is False
    bob = next(r for r in records if r.person_slug == "bob-002")
    assert bob.score is None
    assert bob.passed is None
    assert bob.job_title == ""


def test_analyze_assessments_aggregates_by_type():
    analysis = analyze_assessments(assessment_records_from_api(_RAW_ASSESSMENTS))

    assert analysis.total_records == 3
    assert analysis.candidates == 2  # carol-003 has no assessments

    tech = analysis.by_type["technical_assessment"]
    assert tech.total == 2
    assert tech.completed == 2
    assert tech.mean_score == 71
    assert tech.min_score == 60 and tech.max_score == 82
    assert tech.pass_rate == 0.5

    lang = analysis.by_type["language_assessment"]
    assert lang.scores == []
    assert lang.mean_score is None
    assert lang.pass_rate is None
    assert lang.status_counts["pending"] == 1


def test_analyze_assessments_splits_by_decision_and_flags_disagreements():
    records = assessment_records_from_api(
        _RAW_ASSESSMENTS,
        {
            "alice-001": {"job_id": "1", "job_title": "Backend Engineer"},
            "bob-002": {"job_id": "1", "job_title": "Backend Engineer"},
        },
    )
    # alice passed one (82) and failed one (60); Paul rejected her -> one disagreement
    analysis = analyze_assessments(
        records, {"alice-001": NEGATIVE, "bob-002": POSITIVE}
    )

    assert analysis.scores_by_decision[NEGATIVE] == [82, 60]
    assert analysis.by_job["Backend Engineer"].total == 3  # alice x2 + bob x1
    assert analysis.by_job["Backend Engineer"].graded == 2  # bob's is pending

    assert len(analysis.disagreements) == 1
    d = analysis.disagreements[0]
    assert d.kind == "rejected_but_passed"
    assert d.person_slug == "alice-001"
    assert d.score == 82


def test_record_from_search_item_extracts_fields(load_fixture):
    page = load_fixture("applications_search_page1.json")
    item = page["data"]["JobApplications"][0]
    record = record_from_search_item(item)
    assert record.person_slug == "alice-001"
    assert record.job_title == "Backend Engineer"
    assert record.step_category == "AIVoiceInterview"
    assert record.decision == NEGATIVE
    assert record.needs_human_review is True
