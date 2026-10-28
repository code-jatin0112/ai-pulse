import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import current_membership
from ..services.questions import questions_for, load_questions
from ..services.scoring import score_open_answer, AIServiceError, AIValidationError

logger = logging.getLogger("ai_pulse.diagnostic")
router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])


class AnswerIn(BaseModel):
    question_id: str
    answer: str


class SubmitIn(BaseModel):
    answers: list[AnswerIn]


@router.get("/questions")
def get_questions(m: models.Membership = Depends(current_membership)):
    qs = questions_for(m.job_role, m.seniority)
    # don't leak scoring points to the client
    return [
        {k: v for k, v in q.items() if k != "points"} | (
            {"options": [o["text"] for o in q["options"]]} if q["type"] == "mcq" else {}
        )
        for q in qs
    ]


MAX_ANSWER_LENGTH = 5000
MAX_ANSWERS_COUNT = 50


@router.post("/submit")
def submit(body: SubmitIn, m: models.Membership = Depends(current_membership), db: Session = Depends(get_db)):
    if len(body.answers) > MAX_ANSWERS_COUNT:
        raise HTTPException(422, f"Submission contains too many answers (maximum {MAX_ANSWERS_COUNT})")

    # 1. Determine assigned questions for this exact employee
    expected_questions = questions_for(m.job_role, m.seniority)
    expected_map = {q["id"]: q for q in expected_questions}
    expected_qids = set(expected_map.keys())

    # 2. Check for duplicate question IDs in submission
    seen_qids = set()
    duplicates = set()
    for a in body.answers:
        if a.question_id in seen_qids:
            duplicates.add(a.question_id)
        seen_qids.add(a.question_id)

    if duplicates:
        raise HTTPException(422, f"Duplicate question IDs submitted: {sorted(duplicates)}")

    # 3. Check for exact match with expected questions
    missing = expected_qids - seen_qids
    extra = seen_qids - expected_qids
    if missing or extra:
        errors = []
        if missing:
            errors.append(f"Missing required questions: {sorted(missing)}")
        if extra:
            errors.append(f"Ineligible or unknown questions for your role/seniority: {sorted(extra)}")
        raise HTTPException(422, "; ".join(errors))

    # 4. Validate answer content for all questions (non-blank, length limits, MCQ options)
    answer_by_qid = {a.question_id: a.answer for a in body.answers}

    for q in expected_questions:
        qid = q["id"]
        raw_ans = answer_by_qid[qid]
        if not raw_ans or not str(raw_ans).strip():
            raise HTTPException(422, f"Blank answer for question '{qid}'")
        if len(str(raw_ans)) > MAX_ANSWER_LENGTH:
            raise HTTPException(422, f"Answer for question '{qid}' exceeds maximum length of {MAX_ANSWER_LENGTH} characters")

        if q["type"] == "mcq":
            valid_options = {o["text"] for o in q["options"]}
            if raw_ans not in valid_options:
                raise HTTPException(422, f"Invalid option '{raw_ans}' for question '{qid}'")

    # All validation passed! No LLM call or DB modification was performed yet.
    # 5. Score answers and construct Response objects in memory
    new_responses = []
    for q in expected_questions:
        qid = q["id"]
        ans = answer_by_qid[qid]
        resp = models.Response(membership_id=m.id, question_id=qid, answer=ans)

        if q["type"] == "mcq":
            option = next(o for o in q["options"] if o["text"] == ans)
            score = float(option["points"])
            if not (1.0 <= score <= 5.0):
                raise HTTPException(502, f"Configured score {score} for '{qid}' is out of valid 1-5 range")
            resp.score = score
        else:
            try:
                result = score_open_answer(q["text"], ans.strip())
            except (AIServiceError, AIValidationError) as exc:
                logger.error("AI scoring failed: %s", type(exc).__name__)
                raise HTTPException(502, "AI scoring service temporarily unavailable. Please try again.")
            except Exception as exc:
                logger.error("Unexpected error during AI scoring: %s", type(exc).__name__)
                raise HTTPException(502, "AI scoring service temporarily unavailable. Please try again.")

            resp.score = result["score"]
            resp.reason = result["reason"]
            resp.flags = result["flags"]

        new_responses.append(resp)

    # 6. Atomic replacement in a single database transaction
    try:
        db.query(models.Response).filter_by(membership_id=m.id).delete(synchronize_session="fetch")
        for resp in new_responses:
            db.add(resp)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"saved": len(new_responses)}


@router.delete("/me")
def delete_my_diagnostic(m: models.Membership = Depends(current_membership), db: Session = Depends(get_db)):
    """Deletes all diagnostic responses, scores, reasons, and risks for the authenticated membership.

    Scoped strictly to the authenticated organization membership. Idempotent and executed in a single transaction.
    """
    deleted_count = (
        db.query(models.Response)
        .filter_by(membership_id=m.id)
        .delete(synchronize_session="fetch")
    )
    db.commit()
    return {"status": "ok", "deleted": deleted_count}

