"""Employee-facing AI Growth Insights service.

Provides deterministic performance breakdowns across four core AI competency pillars,
identifying the employee's strongest area and lowest-scoring improvement priority.
"""
from typing import Any
from .. import models

# Question-to-competency mapping covering all 15 questions in questions.json
QUESTION_CATEGORY_MAP = {
    # Data Security & Governance
    "common-policy": "data_security",
    "common-data": "data_security",
    "mgr-policy": "data_security",
    # Output Verification & Quality Control
    "common-review": "output_verification",
    "eng-review": "output_verification",
    # Adoption & Frequency
    "common-freq": "adoption_frequency",
    "mgr-adoption": "adoption_frequency",
    # Applied Role Workflow Impact
    "common-open": "practical_application",
    "sup-drafts": "practical_application",
    "sup-escalation": "practical_application",
    "eng-assistant": "practical_application",
    "eng-arch": "practical_application",
    "sales-outreach": "practical_application",
    "sales-crm": "practical_application",
    "mgr-open": "practical_application",
}

CATEGORIES = {
    "data_security": {
        "name": "Data Security & Policy Compliance",
        "description": "Safe handling of customer and confidential data, and following organizational AI usage rules.",
        "recommendation": "Establish a habit of redacting customer and confidential details before prompting, and review approved AI tool guidelines.",
    },
    "output_verification": {
        "name": "Output Verification & Quality Review",
        "description": "Critical evaluation, fact-checking, and testing of AI outputs before applying them to work.",
        "recommendation": "Treat all AI output as an unverified draft: fact-check claims, verify sources, and add tests before shipping code or decisions.",
    },
    "adoption_frequency": {
        "name": "Adoption & Daily Habit",
        "description": "Regularity and integration of AI tools into day-to-day work habits.",
        "recommendation": "Identify 1–2 routine daily tasks (such as drafting first-pass emails or summarising meeting notes) to build consistent AI leverage.",
    },
    "practical_application": {
        "name": "Practical Workflow Impact",
        "description": "Applying AI to concrete role-specific tasks to achieve measurable productivity and quality gains.",
        "recommendation": "Develop and refine reusable role-specific prompt templates to streamline complex, multi-step job tasks.",
    },
}

# Tie-breaking rules:
# Strongest: Prioritize concrete practical impact, then verification, then security, then adoption.
TIE_BREAKER_STRONGEST = [
    "practical_application",
    "output_verification",
    "data_security",
    "adoption_frequency",
]

# Improvement (Weakest): Prioritize data security risk first, then output review, then practical impact, then adoption.
TIE_BREAKER_IMPROVEMENT = [
    "data_security",
    "output_verification",
    "practical_application",
    "adoption_frequency",
]


def get_question_category(qid: str) -> str:
    """Returns the competency category for a question ID.

    Raises KeyError if the question has no explicit category mapping,
    or ValueError if the mapped category is unrecognized.
    """
    if qid not in QUESTION_CATEGORY_MAP:
        raise KeyError(f"Question '{qid}' does not have an explicit competency category mapping")
    category = QUESTION_CATEGORY_MAP[qid]
    if category not in CATEGORIES:
        raise ValueError(f"Category '{category}' for question '{qid}' is not recognized")
    return category


def calculate_growth_insights(
    responses: list[models.Response],
    expected_questions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Calculates deterministic growth insights for a completed diagnostic.

    Returns None if the diagnostic is incomplete, missing, or corrupted.
    """
    if not responses or not expected_questions:
        return None

    expected_qids = {q["id"] for q in expected_questions}
    response_map = {r.question_id: r for r in responses if r.score is not None}

    # Must contain responses with valid numeric scores for every assigned question
    if not expected_qids.issubset(response_map.keys()):
        return None

    # Group scores into categories
    category_scores: dict[str, list[float]] = {cat: [] for cat in CATEGORIES}
    for qid in expected_qids:
        cat_key = get_question_category(qid)
        resp = response_map[qid]
        score = float(resp.score)
        # Bounded between 1.0 and 5.0
        clamped_score = max(1.0, min(5.0, score))
        category_scores[cat_key].append(clamped_score)

    breakdown = []
    category_averages: dict[str, float] = {}

    for cat_key, scores in category_scores.items():
        if not scores:
            continue
        avg = round(sum(scores) / len(scores), 1)
        # Ensure within 1.0 to 5.0
        avg = max(1.0, min(5.0, avg))
        category_averages[cat_key] = avg
        meta = CATEGORIES[cat_key]
        breakdown.append({
            "key": cat_key,
            "name": meta["name"],
            "score": avg,
            "description": meta["description"],
            "question_count": len(scores),
        })

    if not category_averages:
        return None

    # Determine strongest area with deterministic tie-breaking
    max_score = max(category_averages.values())
    top_candidates = [k for k, s in category_averages.items() if s == max_score]
    strongest_key = next((k for k in TIE_BREAKER_STRONGEST if k in top_candidates), top_candidates[0])

    # Determine improvement area with deterministic tie-breaking
    min_score = min(category_averages.values())
    bottom_candidates = [k for k, s in category_averages.items() if s == min_score]
    improvement_key = next((k for k in TIE_BREAKER_IMPROVEMENT if k in bottom_candidates), bottom_candidates[0])

    strongest_meta = CATEGORIES[strongest_key]
    improvement_meta = CATEGORIES[improvement_key]

    return {
        "breakdown": breakdown,
        "strongest_area": {
            "key": strongest_key,
            "name": strongest_meta["name"],
            "score": category_averages[strongest_key],
        },
        "improvement_area": {
            "key": improvement_key,
            "name": improvement_meta["name"],
            "score": category_averages[improvement_key],
            "recommendation": improvement_meta["recommendation"],
        },
    }
