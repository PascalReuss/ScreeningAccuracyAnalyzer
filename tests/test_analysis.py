from screening.analysis import (
    NEGATIVE,
    OPT_OUT,
    PENDING,
    POSITIVE,
    DecisionRecord,
    analyze,
    classify_decision,
    normalize_reason,
    record_from_search_item,
)


def _record(decision="NegativeDecision", job="Backend Engineer", step="PreScreening",
            summary="Does not meet the minimum years of experience.", hitl=False):
    return DecisionRecord(
        person_slug="p",
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


def test_record_from_search_item_extracts_fields(load_fixture):
    page = load_fixture("applications_search_page1.json")
    item = page["data"]["JobApplications"][0]
    record = record_from_search_item(item)
    assert record.person_slug == "alice-001"
    assert record.job_title == "Backend Engineer"
    assert record.step_category == "AIVoiceInterview"
    assert record.decision == NEGATIVE
    assert record.needs_human_review is True
