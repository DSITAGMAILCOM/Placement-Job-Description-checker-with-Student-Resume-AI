import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.security import get_current_user, require_admin
from app.db.models import CallLog, Match, Student, User
from app.db.session import get_db
from app.schemas.schemas import CallLogOut, CallTriggerRequest, CallTriggerResult
from app.services.vapi_service import (
    build_vapi_overrides,
    finalize_call_log,
    get_vapi_preflight_status,
    handle_vapi_webhook_event,
    trigger_outbound_vapi_call,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Outbound Calling & Vapi"])


class WebCallCompleteRequest(BaseModel):
    transcript: str = ""
    duration_sec: int = 1


def _serialize_call_log(c: CallLog) -> CallLogOut:
    return CallLogOut(
        id=c.id,
        match_id=c.match_id,
        student_id=c.student_id,
        student_name=c.student.user.name,
        company_id=c.company_id,
        company_name=c.company.company_name,
        company_role=c.company.role,
        twilio_call_sid=c.twilio_call_sid,
        call_status=c.call_status,
        student_outcome=c.student_outcome,
        transcript=c.transcript,
        duration_sec=c.duration_sec,
        link_sent=c.link_sent,
        called_at=c.called_at,
    )


@router.get("/calls/preflight")
def calls_preflight(_: User = Depends(require_admin)):
    """Return Vapi readiness diagnostics for the Admin UI."""
    return get_vapi_preflight_status()


@router.post("/calls/trigger", response_model=list[CallTriggerResult])
def trigger_calls(
    payload: CallTriggerRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Match).options(
        joinedload(Match.student).joinedload(Student.user),
        joinedload(Match.resume),
        joinedload(Match.company),
    )

    if payload.match_id is not None:
        query = query.filter(Match.id == payload.match_id)
    elif payload.match_ids:
        query = query.filter(Match.id.in_(payload.match_ids))
    elif payload.company_id is not None:
        query = query.filter(
            Match.company_id == payload.company_id,
            Match.fit_score >= payload.min_fit_score,
            Match.match_status == "PENDING_CALL",
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide match_id, match_ids, or company_id to trigger outbound Vapi calls.",
        )

    matches = query.all()
    if not matches:
        raise HTTPException(status_code=404, detail="No eligible matches found to call.")

    results: list[CallTriggerResult] = []
    for match in matches:
        if not match.student.call_consent:
            results.append(
                CallTriggerResult(
                    match_id=match.id,
                    student_name=match.student.user.name,
                    phone=match.student.phone,
                    status="SKIPPED_NO_CONSENT",
                    error="Student has not opted in to automated calls.",
                )
            )
            continue

        call_log = CallLog(
            match_id=match.id,
            student_id=match.student_id,
            company_id=match.company_id,
            call_status="INITIATED",
            student_outcome="UNKNOWN",
        )
        db.add(call_log)
        db.flush()

        try:
            vapi_call_id = trigger_outbound_vapi_call(db=db, match=match, call_log=call_log)
            call_log.twilio_call_sid = vapi_call_id
            match.match_status = "CALLED"
            db.commit()
            results.append(
                CallTriggerResult(
                    match_id=match.id,
                    student_name=match.student.user.name,
                    phone=match.student.phone,
                    status="INITIATED",
                    twilio_call_sid=vapi_call_id,
                )
            )
        except Exception as exc:
            call_log.call_status = "FAILED"
            db.commit()
            results.append(
                CallTriggerResult(
                    match_id=match.id,
                    student_name=match.student.user.name,
                    phone=match.student.phone,
                    status="FAILED",
                    error=str(exc),
                )
            )

    return results


@router.get("/vapi/web-config/{match_id}")
def get_vapi_web_call_config(
    match_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a CallLog and return Vapi Web SDK config with injected Resume + JD overrides."""
    match = (
        db.query(Match)
        .options(joinedload(Match.student))
        .filter(Match.id == match_id)
        .first()
    )
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")
    if current_user.role == "STUDENT" and match.student.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    call_log = CallLog(
        match_id=match.id,
        student_id=match.student_id,
        company_id=match.company_id,
        call_status="IN_PROGRESS",
        student_outcome="UNKNOWN",
    )
    db.add(call_log)
    db.commit()
    db.refresh(call_log)

    overrides, _ = build_vapi_overrides(db, match_id=match_id, call_log_id=call_log.id)
    return {
        "publicKey": settings.VAPI_PUBLIC_KEY,
        "assistantId": settings.VAPI_ASSISTANT_ID,
        "assistantOverrides": overrides,
        "callLogId": call_log.id,
    }


@router.post("/vapi/web-call-complete/{call_log_id}")
def complete_vapi_web_call(
    call_log_id: int,
    payload: WebCallCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Finalize a browser Vapi Web Call transcript and classify student outcome."""
    call_log = (
        db.query(CallLog)
        .options(joinedload(CallLog.student))
        .filter(CallLog.id == call_log_id)
        .first()
    )
    if not call_log:
        raise HTTPException(status_code=404, detail="Call log not found.")
    if current_user.role == "STUDENT" and call_log.student.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    if call_log.call_status == "COMPLETED" and call_log.transcript:
        return {
            "outcome": call_log.student_outcome,
            "link_sent": call_log.link_sent,
            "duration_sec": call_log.duration_sec,
            "transcript": call_log.transcript,
        }

    updated = finalize_call_log(
        db=db,
        call_log=call_log,
        transcript=payload.transcript,
        call_status="COMPLETED",
        duration_sec=max(1, payload.duration_sec),
    )
    return {
        "outcome": updated.student_outcome,
        "link_sent": updated.link_sent,
        "duration_sec": updated.duration_sec,
        "transcript": updated.transcript,
    }


@router.post("/vapi/webhook")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Vapi server events (status-update, end-of-call-report)."""
    payload = await request.json()
    return handle_vapi_webhook_event(db=db, payload=payload)


@router.get("/calls/logs", response_model=list[CallLogOut])
def list_call_logs(
    company_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(CallLog).options(
        joinedload(CallLog.student).joinedload(Student.user),
        joinedload(CallLog.company),
    )

    if current_user.role == "STUDENT":
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if not student:
            return []
        query = query.filter(CallLog.student_id == student.id)
    elif company_id is not None:
        query = query.filter(CallLog.company_id == company_id)

    logs = query.order_by(CallLog.called_at.desc()).all()
    return [_serialize_call_log(c) for c in logs]
