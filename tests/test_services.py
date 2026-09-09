from app import services
from screening.analysis import NEGATIVE, analyze


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


def test_load_decision_records_uses_cache_on_second_call(config, monkeypatch):
    monkeypatch.setattr(services, "ScreeningClient", _FakeClient)

    records, meta = services.load_decision_records(config, deep=False)
    assert meta["source"] == "api"
    assert len(records) == 1

    records2, meta2 = services.load_decision_records(config, deep=False)
    assert meta2["source"] == "cache"
    assert analyze(records2).overall.counts[NEGATIVE] == 1
