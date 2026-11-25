from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, require_admin
from app.db.models import CallLog, Company, Match, Student, User
from app.db.session import SessionLocal, get_db
from app.schemas.schemas import CompanyConversionMetric, DashboardSummaryOut
from app.services.vapi_service import build_voice_session, finalize_call_log

router = APIRouter(tags=["Dashboard & Browser Voice Simulator"])


@router.get("/dashboard/summary", response_model=DashboardSummaryOut)
def get_dashboard_summary(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_students = db.query(Student).count()
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    active_drives = len(companies)
    total_matches = db.query(Match).count()
    all_calls = db.query(CallLog).all()
    calls_placed = len(all_calls)

    answered = sum(1 for c in all_calls if c.call_status == "COMPLETED")
    interested = sum(1 for c in all_calls if c.student_outcome == "INTERESTED")
    answer_rate = round((answered / calls_placed) * 100, 1) if calls_placed else 0.0
    interested_rate = round((interested / answered) * 100, 1) if answered else 0.0

    metrics: list[CompanyConversionMetric] = []
    for comp in companies:
        comp_matches = db.query(Match).filter(Match.company_id == comp.id).count()
        comp_calls = [c for c in all_calls if c.company_id == comp.id]
        c_placed = len(comp_calls)
        c_answered = sum(1 for c in comp_calls if c.call_status == "COMPLETED")
        c_interested = sum(1 for c in comp_calls if c.student_outcome == "INTERESTED")
        conv_rate = round((c_interested / c_answered) * 100, 1) if c_answered else 0.0
        metrics.append(
            CompanyConversionMetric(
                company_id=comp.id,
                company_name=comp.company_name,
                role=comp.role,
                matched_count=comp_matches,
                calls_placed=c_placed,
                answered_count=c_answered,
                interested_count=c_interested,
                conversion_rate=conv_rate,
            )
        )

    return DashboardSummaryOut(
        total_students=total_students,
        active_drives=active_drives,
        total_matches=total_matches,
        calls_placed=calls_placed,
        answer_rate=answer_rate,
        interested_rate=interested_rate,
        company_metrics=metrics,
    )


@router.websocket("/simulator/voice/{match_id}")
async def browser_voice_simulator(
    websocket: WebSocket,
    match_id: int,
    token: str = Query(...),
):
    """Free browser-based voice simulator WebSocket (Web Speech API <-> FastAPI <-> LangChain)."""
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        role = payload.get("role", "STUDENT")
    except Exception:
        await websocket.close(code=4001)
        return

    db = SessionLocal()
    call_log: CallLog | None = None
    started_at = datetime.now(timezone.utc)
    session = None

    try:
        session, match = build_voice_session(db, match_id=match_id)
        if role == "STUDENT" and match.student.user_id != user_id:
            await websocket.close(code=4003)
            return

        await websocket.accept()
        call_log = CallLog(
            match_id=match.id,
            student_id=match.student_id,
            company_id=match.company_id,
            twilio_call_sid=None,
            call_status="IN_PROGRESS",
            student_outcome="UNKNOWN",
        )
        db.add(call_log)
        db.commit()
        db.refresh(call_log)

        greeting = session.opening_greeting()
        await websocket.send_text(
            json.dumps(
                {
                    "type": "ai_reply",
                    "text": greeting,
                    "transcript": session.get_transcript(),
                    "call_log_id": call_log.id,
                }
            )
        )

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "user_speech":
                utterance = str(msg.get("text") or "").strip()
                reply = session.respond(utterance)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "ai_reply",
                            "text": reply,
                            "transcript": session.get_transcript(),
                        }
                    )
                )
            elif msg_type == "end_call":
                duration = int((datetime.now(timezone.utc) - started_at).total_seconds())
                updated = finalize_call_log(
                    db=db,
                    call_log=call_log,
                    transcript=session.get_transcript(),
                    call_status="COMPLETED",
                    duration_sec=max(1, duration),
                )
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "call_ended",
                            "outcome": updated.student_outcome,
                            "link_sent": updated.link_sent,
                            "duration_sec": updated.duration_sec,
                            "transcript": updated.transcript,
                        }
                    )
                )
                break
    except WebSocketDisconnect:
        if call_log and session and call_log.call_status != "COMPLETED":
            transcript = session.get_transcript()
            if len(session.transcript_lines) <= 1:
                # Client disconnected immediately (e.g., StrictMode remount) before any conversation turn
                db.delete(call_log)
                db.commit()
            else:
                duration = int((datetime.now(timezone.utc) - started_at).total_seconds())
                finalize_call_log(
                    db=db,
                    call_log=call_log,
                    transcript=transcript,
                    call_status="COMPLETED",
                    duration_sec=max(1, duration),
                )
    finally:
        db.close()
