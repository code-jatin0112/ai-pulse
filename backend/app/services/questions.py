import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "questions.json")


SENIORITY_RANKS = {
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead": 4,
}


def load_questions():
    with open(_PATH) as f:
        return json.load(f)


def questions_for(job_role: str, seniority: str):
    """Common questions for everyone + questions for this job role, filtered by seniority."""
    user_rank = SENIORITY_RANKS.get(seniority.lower() if isinstance(seniority, str) else seniority, 0)
    result = []
    for q in load_questions():
        if q["roles"] != ["all"] and job_role not in q["roles"]:
            continue
        min_sen = q.get("min_seniority", "junior" if q.get("roles") != ["all"] else None)
        if min_sen and user_rank < SENIORITY_RANKS.get(min_sen, 1):
            continue
        result.append(q)
    return result

