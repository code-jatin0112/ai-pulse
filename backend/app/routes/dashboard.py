from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import current_membership

from ..services.questions import questions_for
from ..utils import maturity_level

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MIN_COMPLETERS_THRESHOLD = 5


def get_completed_diagnostic(db: Session, membership: models.Membership) -> dict | None:
    """Checks whether a membership has completed their assigned diagnostic.

    Returns a dict with `score` and `flags` if completed, or None if incomplete.
    Deduplicates repeated responses by taking the latest submission per question.
    """
    expected_questions = questions_for(membership.job_role, membership.seniority)
    expected_qids = {q["id"] for q in expected_questions}
    if not expected_qids:
        return None

    responses = (
        db.query(models.Response)
        .filter_by(membership_id=membership.id)
        .order_by(models.Response.id.desc())
        .all()
    )

    # Deduplicate by question_id (latest response takes precedence)
    latest_by_qid = {}
    for r in responses:
        if r.question_id not in latest_by_qid:
            latest_by_qid[r.question_id] = r

    # Must have answered every assigned question with non-empty content
    if not expected_qids.issubset(latest_by_qid.keys()):
        return None

    for qid in expected_qids:
        ans = latest_by_qid[qid].answer
        if not ans or not str(ans).strip():
            return None

    scores = [
        latest_by_qid[qid].score
        for qid in expected_qids
        if latest_by_qid[qid].score is not None
    ]
    avg_score = sum(scores) / len(scores) if scores else None

    flags = sorted({
        f
        for qid in expected_qids
        for f in (latest_by_qid[qid].flags or [])
    })


    return {
        "membership_id": membership.id,
        "score": avg_score,
        "flags": flags,
    }


@router.get("")
def org_dashboard(org_id: int, m: models.Membership = Depends(current_membership), db: Session = Depends(get_db)):
    if m.role != "admin":
        raise HTTPException(403, "Admins only")
    if m.org_id != org_id:
        raise HTTPException(403, "Not authorized for this organization")

    org = db.get(models.Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    members = db.query(models.Membership).filter_by(org_id=org_id).all()
    departments = []
    all_flags = {}

    for dept in org.departments:
        dept_members = [x for x in members if x.department_id == dept.id]
        completed_diagnostics = []

        for dm in dept_members:
            comp = get_completed_diagnostic(db, dm)
            if comp is not None:
                completed_diagnostics.append(comp)

        completer_count = len(completed_diagnostics)

        # Privacy rule: Departments with fewer than 5 completed diagnostics
        # must be completely suppressed from dashboard analytics.
        if completer_count < MIN_COMPLETERS_THRESHOLD:
            continue

        valid_scores = [cd["score"] for cd in completed_diagnostics if cd["score"] is not None]
        avg = sum(valid_scores) / len(valid_scores) if valid_scores else None

        for cd in completed_diagnostics:
            for f in cd["flags"]:
                all_flags[f] = all_flags.get(f, 0) + 1

        departments.append({
            "department": dept.name,
            "employees": len(dept_members),
            "responded": completer_count,
            "average_score": round(avg, 2) if avg is not None else None,
            "level": maturity_level(avg),
        })

    return {
        "organization": org.name,
        "departments": departments,
        "top_risks": sorted(all_flags.items(), key=lambda kv: -kv[1])[:5],
    }

