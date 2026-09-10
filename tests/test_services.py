import dataclasses

from app import services
from screening.analysis import NEGATIVE, analyze, analyze_assessments


class _FakeClient:
    correlation_id = "fake-corr"

    def __init__(self, *_args, **_kwargs):
        pass

    def iter_applications(self, *_args, **_kwargs):
        yield {
            "StepCategory": "PreScreening",
            "StepName": "Pre-Screening",
            "PaulDecision": "NegativeDecision",
            "PaulDecisionSummary": "Too junior.",
            "HumanReview": False,
            "Application": {"ID": "JP-1"},
            "Person": {"PersonSlug": "p1"},
            "Job": {"PaulsjobJobID": 1, "JobPositionTitle": "Backend Engineer"},
        }

    def iter_assessments(self, person_slugs, **_kwargs):
        for slug in person_slugs:
            yield slug, [
                {
                    "ID": "as-1",
                    "Type": "technical_assessment",
                    "Status": "completed",
                    "AssessmentScore": 90,
                    "AssessmentDetails": {"PassingScore": 70},
                }
            ]


def test_load_decision_records_uses_cache_on_second_call(config, monkeypatch):
    monkeypatch.setattr(services, "ScreeningClient", _FakeClient)

    records, meta = services.load_decision_records(config, deep=False)
    assert meta["source"] == "api"
    assert len(records) == 1

    records2, meta2 = services.load_decision_records(config, deep=False)
    assert meta2["source"] == "cache"
    assert analyze(records2).overall.counts[NEGATIVE] == 1


def test_load_assessment_records_joins_job_and_caches(config, monkeypatch):
    monkeypatch.setattr(services, "ScreeningClient", _FakeClient)

    records, meta = services.load_assessment_records(config)
    assert meta["source"] == "api"
    assert meta["candidates_queried"] == 1
    assert records[0].job_title == "Backend Engineer"
    assert analyze_assessments(records).by_type["technical_assessment"].pass_rate == 1.0

    _, meta2 = services.load_assessment_records(config)
    assert meta2["source"] == "cache"


def test_demo_mode_loads_bundled_dataset(config):
    demo_config = dataclasses.replace(config, demo_mode=True)

    records, meta = services.load_decision_records(demo_config)
    assert meta["source"] == "demo"
    assert len(records) > 0

    a_records, a_meta = services.load_assessment_records(demo_config)
    assert a_meta["source"] == "demo"
    analysis = analyze_assessments(a_records)
    assert analysis.total_records > 0
    assert analysis.by_type  # at least one assessment type present
