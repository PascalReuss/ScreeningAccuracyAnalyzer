"""Generate deterministic demo data for the UI without touching the Paulsjob API.

Writes two files next to this script:

  applications.json  - list[ApplicationSearchListData]  (one current step per applicant)
  assessments.json   - {person_slug: list[Assessment]}   (structured assessments)

The shapes match what ``screening.analysis`` reads, so ``SCREENING_DEMO=1`` renders
the real dashboards. Re-run after changing the knobs below:

    python demo/generate.py --persons 60
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random

HERE = pathlib.Path(__file__).parent

JOBS = [
    (12345, "Backend Engineer"),
    (12346, "Frontend Engineer"),
    (12347, "Data Analyst"),
    (12348, "Product Designer"),
    (12349, "Customer Success Manager"),
]

STEPS = [
    ("Pre-Screening", "PreScreening"),
    ("Prescreening Questions", "PreScreening"),
    ("AI Voice Interview", "AIVoiceInterview"),
    ("Human Interview", "HumanInterview"),
    ("Recruiting Day", "RecruitingDay"),
    ("Rejected", "Rejected"),
]

# reused verbatim so the "top rejection reasons" tally is meaningful
REJECTION_REASONS = [
    "Does not meet the minimum years of experience.",
    "Missing a mandatory certification for the role.",
    "Salary expectation is well above the band.",
    "No relevant industry background.",
    "Weak communication during the screening call.",
    "Not available within the required start window.",
    "Location does not match the on-site requirement.",
]
POSITIVE_SIGNALS = [
    "Meets all mandatory requirements; strong technical background.",
    "Excellent communication and clear motivation for the role.",
    "Relevant industry experience and a good culture fit.",
    "Exceeds the experience bar and available immediately.",
]
OPT_OUT_DECISIONS = [
    "OptOutNoAnswer",
    "OptOutDeclineToTalkWithAI",
    "OptOutDeclineToContinueApplication",
]

ASSESSMENT_TYPES = [
    ("technical_assessment", 70, ["Python", "SQL", "System design"]),
    ("language_assessment", 60, ["Comprehension", "Fluency", "Grammar"]),
    ("cognitive_assessment", 65, ["Logical reasoning", "Numerical", "Verbal"]),
    ("culture_fit", 50, ["Collaboration", "Ownership", "Communication"]),
]

FIRST = [
    "Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace", "Heidi", "Ivan",
    "Judy", "Mallory", "Niaj", "Olivia", "Peggy", "Rupert", "Sybil", "Trent",
    "Uma", "Victor", "Wendy", "Xavier", "Yara", "Zane", "Nora", "Liam", "Mia",
]
LAST = [
    "Adams", "Baker", "Clark", "Diaz", "Evans", "Fisher", "Gomez", "Hughes",
    "Ivanov", "Jones", "Klein", "Lopez", "Meyer", "Novak", "Owens", "Patel",
]


def _decision_for(step_category: str, rng: random.Random) -> tuple[str, str, str]:
    """Return (PaulDecision, summary, comment) weighted by pipeline step."""
    roll = rng.random()
    if step_category == "Rejected":
        return "NegativeDecision", rng.choice(REJECTION_REASONS), ""
    if step_category == "PreScreening":
        neg, opt = 0.45, 0.10
    elif step_category in ("AIVoiceInterview", "HumanInterview"):
        neg, opt = 0.30, 0.12
    else:
        neg, opt = 0.20, 0.05

    if roll < neg:
        return "NegativeDecision", rng.choice(REJECTION_REASONS), ""
    if roll < neg + opt:
        return rng.choice(OPT_OUT_DECISIONS), "", "Candidate opted out."
    if roll < neg + opt + 0.30:
        return "", "", ""  # pending / not concluded yet
    return "PositiveDecision", rng.choice(POSITIVE_SIGNALS), ""


def build(persons: int, seed: int) -> tuple[list[dict], dict[str, list[dict]]]:
    rng = random.Random(seed)
    applications: list[dict] = []
    assessments: dict[str, list[dict]] = {}

    for i in range(1, persons + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        slug = f"{first.lower()}-{last.lower()}-{i:03d}"
        job_id, job_title = rng.choice(JOBS)
        step_name, step_category = rng.choice(STEPS)
        decision, summary, comment = _decision_for(step_category, rng)

        # a human reviews ~45% of conclusions; they mostly confirm Paul but
        # overturn a decided conclusion ~22% of the time
        human_review = rng.random() < 0.45
        human_decision = ""
        if human_review and decision in ("PositiveDecision", "NegativeDecision"):
            if rng.random() < 0.78:
                human_decision = decision
            else:
                human_decision = (
                    "NegativeDecision"
                    if decision == "PositiveDecision"
                    else "PositiveDecision"
                )

        # spread applications across ~3 months so the timeline has shape
        month = 7 + (i % 3)
        day = (i * 5) % 27 + 1

        applications.append(
            {
                "StepName": step_name,
                "StepCategory": step_category,
                "HumanReview": human_review,
                "HumanDecision": human_decision,
                "AgentReview": rng.random() < 0.15,
                "PaulDecision": decision,
                "PaulDecisionSummary": summary,
                "Comment": comment,
                "Application": {
                    "ID": f"JP-{2000 + i}",
                    "ApplicationDate": f"2026-{month:02d}-{day:02d}T09:00:00Z",
                },
                "Person": {"PersonSlug": slug, "FullName": f"{first} {last}"},
                "Job": {"PaulsjobJobID": job_id, "JobPositionTitle": job_title},
            }
        )

        # ~75% of candidates have at least one assessment
        if rng.random() < 0.75:
            picked = rng.sample(ASSESSMENT_TYPES, k=rng.randint(1, 3))
            rows: list[dict] = []
            # nudge scores up for candidates the AI liked
            bias = 12 if decision == "PositiveDecision" else (-10 if decision == "NegativeDecision" else 0)
            for j, (a_type, passing, skills) in enumerate(picked, start=1):
                completed = rng.random() < 0.85
                score = max(0, min(100, round(rng.gauss(66 + bias, 14)))) if completed else None
                rows.append(
                    {
                        "ID": f"as-{i:03d}-{j}",
                        "Type": a_type,
                        "Status": "completed" if completed else "pending",
                        "AssessmentScore": score,
                        "AssessmentDetails": {
                            "PassingScore": passing,
                            "SkillsEvaluated": skills,
                            "DifficultyLevel": rng.choice(["Easy", "Intermediate", "Hard"]),
                            "TimeSpentMinutes": rng.randint(20, 75),
                        },
                        "AssessedAt": f"2026-08-{(i % 27) + 1:02d}T14:00:00Z",
                    }
                )
            assessments[slug] = rows

    return applications, assessments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persons", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    applications, assessments = build(args.persons, args.seed)
    (HERE / "applications.json").write_text(
        json.dumps(applications, indent=2), "utf-8"
    )
    (HERE / "assessments.json").write_text(
        json.dumps(assessments, indent=2), "utf-8"
    )
    with_assess = sum(1 for v in assessments.values() if v)
    total_rows = sum(len(v) for v in assessments.values())
    print(
        f"wrote {len(applications)} applications, "
        f"{total_rows} assessments across {with_assess} candidates"
    )


if __name__ == "__main__":
    main()
