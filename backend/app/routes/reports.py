from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import current_membership
from ..utils import maturity_level
from ..services.questions import questions_for
from ..services.insights import calculate_growth_insights
from .dashboard import get_completed_diagnostic

router = APIRouter(prefix="/reports", tags=["reports"])

NEXT_STEPS = {
    "support": ["Use AI to draft first replies, then edit", "Summarise long ticket threads before escalating", "Never paste customer details into public chatbots"],
    "engineering": ["Use a code assistant for tests and refactors", "Review every AI suggestion before merging", "Keep secrets and customer data out of prompts"],
    "sales": ["Draft outreach emails with AI and personalise them", "Summarise call notes into CRM updates", "Check AI-written claims before sending"],
    "manager": ["Agree an AI usage policy with your team", "Pick one workflow per quarter to improve with AI", "Track time saved, not tool licences"],
}


@router.get("/me")
def my_report(m: models.Membership = Depends(current_membership), db: Session = Depends(get_db)):
    expected_questions = questions_for(m.job_role, m.seniority)
    completed = get_completed_diagnostic(db, m)
    raw_answered_count = db.query(models.Response).filter_by(membership_id=m.id).count()

    if completed is not None:
        avg = completed["score"]
        flags = completed["flags"]
        completed_responses = completed["responses"]
        insights = calculate_growth_insights(completed_responses, expected_questions)
        return {
            "name": m.user.name,
            "organization": m.org.name,
            "answered": raw_answered_count,
            "average_score": round(avg, 2) if avg is not None else None,
            "level": maturity_level(avg),
            "risks": flags,
            "next_steps": NEXT_STEPS.get(m.job_role, NEXT_STEPS["manager"]),
            "growth_insights": insights,
        }

    return {
        "name": m.user.name,
        "organization": m.org.name,
        "answered": raw_answered_count,
        "average_score": None,
        "level": maturity_level(None),
        "risks": [],
        "next_steps": NEXT_STEPS.get(m.job_role, NEXT_STEPS["manager"]),
        "growth_insights": None,
    }
