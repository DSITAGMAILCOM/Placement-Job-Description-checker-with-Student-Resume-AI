import logging

import httpx
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.models import CallLog, Match, Student
from app.services.ai_engine import VoiceAgentSession, classify_call_transcript
from app.services.notification_service import dispatch_registration_link

logger = logging.getLogger(__name__)


def clean_phone_e164(raw_phone: str) -> str:
    return "".join(ch for ch in raw_phone.strip() if ch.isdigit() or ch == "+")


def _vapi_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.VAPI_API_KEY}",
        "Content-Type": "application/json",
    }


def resolve_vapi_phone_number_id() -> tuple[str | None, str | None, str | None]:
    """Return (uuid, e164_number, provider) for the configured VAPI_PHONE_NUMBER_ID."""
    configured = settings.VAPI_PHONE_NUMBER_ID.strip()
    try:
        resp = httpx.get(
            f"{settings.VAPI_BASE_URL}/phone-number",
            headers=_vapi_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        numbers = resp.json() or []
        for item in numbers:
            if item.get("id") == configured or item.get("number") == clean_phone_e164(configured):
                return item.get("id"), item.get("number"), item.get("provider")
        if numbers:
            first = numbers[0]
            return first.get("id"), first.get("number"), first.get("provider")
    except Exception as exc:
        logger.warning("Failed to list Vapi phone numbers: %s", exc)
    return configured, settings.VAPI_PHONE_NUMBER, None


def get_vapi_preflight_status() -> dict:
    """Inspect Vapi phone number, assistant, and webhook configuration."""
    issues: list[str] = []
    phone_uuid, phone_num, provider = resolve_vapi_phone_number_id()
    assistant_name = None

    try:
        resp = httpx.get(
            f"{settings.VAPI_BASE_URL}/assistant/{settings.VAPI_ASSISTANT_ID}",
            headers=_vapi_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            assistant_name = resp.json().get("name")
        else:
            issues.append(f"Vapi assistant lookup failed ({resp.status_code}).")
    except Exception as exc:
        issues.append(f"Could not reach Vapi API: {exc}")

    if not phone_uuid:
        issues.append("No active Vapi phone number found.")
    elif provider == "vapi":
        issues.append(
            f"Free Vapi US number ({phone_num}) supports US/Canada (+1) PSTN calls only; "
            "for international (+91) numbers, use the Vapi Web Call button in the browser (works globally for free)."
        )

    return {
        "provider": "vapi",
        "assistant_id": settings.VAPI_ASSISTANT_ID,
        "assistant_name": assistant_name,
        "phone_number_id": phone_uuid,
        "phone_number": phone_num,
        "phone_provider": provider,
        "public_base_url": settings.PUBLIC_BASE_URL,
        "issues": issues,
    }


def build_vapi_overrides(db: Session, match_id: int, call_log_id: int | None = None) -> tuple[dict, Match]:
    """Build dynamic Vapi assistantOverrides injected with student resume + JD + other matches."""
    match = (
        db.query(Match)
        .options(
            joinedload(Match.student).joinedload(Student.user),
            joinedload(Match.resume),
            joinedload(Match.company),
        )
        .filter(Match.id == match_id)
        .first()
    )
    if not match:
        raise ValueError(f"Match {match_id} not found")

    other_matches = (
        db.query(Match)
        .options(joinedload(Match.company))
        .filter(
            Match.student_id == match.student_id,
            Match.id != match.id,
        )
        .order_by(Match.fit_score.desc())
        .limit(5)
        .all()
    )
    other_summary = "; ".join(
        f"{m.company.company_name} ({m.company.role}, fit {m.fit_score}%, CTC {m.company.ctc or 'N/A'})"
        for m in other_matches
    )

    student_name = match.student.user.name
    company_name = match.company.company_name
    role = match.company.role
    ctc = match.company.ctc or "Not specified in portal"
    deadline = str(match.company.deadline) if match.company.deadline else "Check placement portal"
    reg_url = match.company.registration_url or "Available on the PlaceCall AI portal"
    parsed_skills = match.resume.parsed_skills if match.resume else {}
    resume_excerpt = (match.resume.raw_text[:2500] if match.resume and match.resume.raw_text else "N/A")
    missing_skills = match.missing_skills or []
    pitch = match.match_pitch or (
        f"Your profile and technical skills align well with {company_name}'s {role} opening."
    )

    system_prompt = (
        "You are PlaceCall AI (University Placement Agent), a warm, natural-sounding campus placement voice assistant on a live phone call.\n"
        f"You are speaking directly with {student_name} (Branch: {match.student.branch or 'N/A'}, CGPA: {float(match.student.cgpa)}).\n"
        "You ALREADY have their parsed resume and the company's full Job Description below — DO NOT ask them to recite their resume or JD.\n\n"
        f"PRIMARY MATCHED COMPANY:\n"
        f"- Company: {company_name}\n"
        f"- Role: {role}\n"
        f"- Fit Score: {match.fit_score}%\n"
        f"- CTC / Package: {ctc}\n"
        f"- Registration Deadline: {deadline}\n"
        f"- Registration Link: {reg_url}\n"
        f"- Personalized Match Pitch: {pitch}\n"
        f"- Missing / Growth Skills: {missing_skills}\n"
        f"- Other Matched Companies for this student: {other_summary or 'None currently'}\n\n"
        f"STUDENT RESUME DETAILS:\n"
        f"- Parsed Data: {parsed_skills}\n"
        f"- Resume Text Excerpt:\n{resume_excerpt}\n\n"
        f"FULL JOB DESCRIPTION (ONLY SOURCE OF TRUTH):\n{match.company.jd_text[:4000]}\n\n"
        "CONVERSATION RULES:\n"
        "1. Speak naturally without markdown, bullet points, or emojis.\n"
        "2. Explain clearly why their resume & projects match this company, tell them 'You can register for this company', and share key JD details (role, CTC, skills, deadline) when asked.\n"
        "3. Keep normal replies concise (2-3 spoken sentences), and give a clear, complete summary when asked for the full JD.\n"
        "4. Stay strictly grounded in the JD and resume above; if asked something unavailable, direct them to the placement portal.\n"
        "5. Ask if they would like the registration link sent right away; if they say yes, confirm you will send it as soon as the call ends and politely wrap up."
    )

    first_message = (
        f"Hi {student_name}, this is PlaceCall AI calling from your Campus Placement Cell! "
        f"We analyzed your resume against {company_name}'s {role} drive and found a {match.fit_score} percent match, so you can register for this company right now. "
        "Would you like me to explain why you match and share the job description details, or send the registration link?"
    )

    overrides: dict = {
        "firstMessage": first_message,
        "model": {
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "toolIds": ["d1316b2b-4365-46be-8135-ae085203cf5d"],
            "messages": [{"role": "system", "content": system_prompt}],
        },
        "serverMessages": ["status-update", "end-of-call-report"],
    }
    if settings.PUBLIC_BASE_URL.startswith("https://"):
        overrides["server"] = {
            "url": f"{settings.PUBLIC_BASE_URL}{settings.API_V1_PREFIX}/vapi/webhook"
        }
    if call_log_id is not None:
        overrides["metadata"] = {"match_id": match.id, "call_log_id": call_log_id}

    return overrides, match


def build_voice_session(db: Session, match_id: int) -> tuple[VoiceAgentSession, Match]:
    """Load match + student + resume + other company matches for the WebSocket fallback simulator."""
    match = (
        db.query(Match)
        .options(
            joinedload(Match.student).joinedload(Student.user),
            joinedload(Match.resume),
            joinedload(Match.company),
        )
        .filter(Match.id == match_id)
        .first()
    )
    if not match:
        raise ValueError(f"Match {match_id} not found")

    other_matches = (
        db.query(Match)
        .options(joinedload(Match.company))
        .filter(Match.student_id == match.student_id, Match.id != match.id)
        .order_by(Match.fit_score.desc())
        .limit(5)
        .all()
    )
    other_summary = "; ".join(
        f"{m.company.company_name} ({m.company.role}, fit {m.fit_score}%, CTC {m.company.ctc or 'N/A'})"
        for m in other_matches
    )
    session = VoiceAgentSession(
        student_name=match.student.user.name,
        student_branch=match.student.branch,
        student_cgpa=float(match.student.cgpa),
        parsed_skills=match.resume.parsed_skills if match.resume else None,
        company_name=match.company.company_name,
        role=match.company.role,
        ctc=match.company.ctc,
        deadline=str(match.company.deadline) if match.company.deadline else None,
        registration_url=match.company.registration_url,
        match_pitch=match.match_pitch,
        missing_skills=match.missing_skills or [],
        jd_text=match.company.jd_text,
        other_matches_summary=other_summary,
    )
    return session, match


def trigger_outbound_vapi_call(db: Session, match: Match, call_log: CallLog) -> str:
    """Place an outbound PSTN phone call via Vapi POST /call API."""
    phone_uuid, _, _ = resolve_vapi_phone_number_id()
    if not phone_uuid:
        raise ValueError("VAPI_PHONE_NUMBER_ID is not configured.")

    to_phone = clean_phone_e164(match.student.phone)
    overrides, _ = build_vapi_overrides(db, match_id=match.id, call_log_id=call_log.id)

    payload = {
        "phoneNumberId": phone_uuid,
        "assistantId": settings.VAPI_ASSISTANT_ID,
        "customer": {
            "number": to_phone,
            "name": match.student.user.name,
        },
        "assistantOverrides": overrides,
    }

    resp = httpx.post(
        f"{settings.VAPI_BASE_URL}/call",
        headers=_vapi_headers(),
        json=payload,
        timeout=20,
    )
    if resp.status_code >= 400:
        try:
            err_body = resp.json()
            err_msg = err_body.get("message") or str(err_body)
        except Exception:
            err_msg = resp.text
        raise ValueError(f"Vapi call error ({resp.status_code}): {err_msg}")

    data = resp.json()
    return str(data.get("id"))


def finalize_call_log(
    db: Session,
    call_log: CallLog,
    transcript: str | None = None,
    call_status: str | None = None,
    duration_sec: int | None = None,
) -> CallLog:
    """Persist transcript, classify outcome via Groq LangChain, update Match, and dispatch registration link."""
    if transcript is not None and transcript.strip():
        call_log.transcript = transcript.strip()
    if call_status is not None:
        call_log.call_status = call_status
    if duration_sec is not None:
        call_log.duration_sec = duration_sec

    if call_log.call_status == "NO_ANSWER":
        call_log.student_outcome = "UNKNOWN"
    elif call_log.transcript:
        call_log.student_outcome = classify_call_transcript(call_log.transcript)

    match = (
        db.query(Match)
        .options(
            joinedload(Match.student).joinedload(Student.user),
            joinedload(Match.company),
        )
        .filter(Match.id == call_log.match_id)
        .first()
    )

    if match:
        if call_log.student_outcome == "INTERESTED":
            match.match_status = "REGISTERED"
            if not call_log.link_sent:
                sent = dispatch_registration_link(
                    to_email=match.student.user.email,
                    to_phone=match.student.phone,
                    student_name=match.student.user.name,
                    company_name=match.company.company_name,
                    role=match.company.role,
                    ctc=match.company.ctc,
                    deadline=str(match.company.deadline) if match.company.deadline else None,
                    registration_url=match.company.registration_url,
                )
                call_log.link_sent = sent
        elif call_log.student_outcome == "NOT_INTERESTED":
            match.match_status = "DISMISSED"
        elif call_log.call_status == "COMPLETED":
            match.match_status = "CALLED"

    db.commit()
    db.refresh(call_log)
    return call_log


def handle_vapi_webhook_event(db: Session, payload: dict) -> dict:
    """Process Vapi server events (status-update, end-of-call-report)."""
    message = payload.get("message") or payload
    msg_type = message.get("type")
    call_obj = message.get("call") or {}
    call_id = call_obj.get("id")

    metadata = (
        message.get("metadata")
        or call_obj.get("metadata")
        or (call_obj.get("assistantOverrides") or {}).get("metadata")
        or {}
    )
    call_log_id = metadata.get("call_log_id")

    call_log = None
    if call_log_id:
        call_log = db.query(CallLog).filter(CallLog.id == int(call_log_id)).first()
    if not call_log and call_id:
        call_log = db.query(CallLog).filter(CallLog.twilio_call_sid == str(call_id)).first()
    if not call_log:
        return {"status": "ignored"}

    if msg_type == "status-update":
        raw_status = str(message.get("status") or "").lower()
        status_map = {
            "queued": "INITIATED",
            "ringing": "RINGING",
            "in-progress": "IN_PROGRESS",
            "forwarding": "IN_PROGRESS",
            "ended": "COMPLETED",
        }
        if raw_status in status_map and call_log.call_status != "COMPLETED":
            call_log.call_status = status_map[raw_status]
            db.commit()
        return {"status": "ok"}

    if msg_type == "end-of-call-report":
        artifact = message.get("artifact") or {}
        transcript = message.get("transcript") or artifact.get("transcript") or ""
        if not transcript and artifact.get("messages"):
            lines = []
            for m in artifact["messages"]:
                role_label = "AI" if m.get("role") in {"assistant", "bot"} else "Student"
                content = m.get("message") or m.get("content") or ""
                if content:
                    lines.append(f"{role_label}: {content}")
            transcript = "\n".join(lines)

        duration_raw = message.get("durationSeconds") or call_obj.get("duration")
        duration_sec = int(round(float(duration_raw))) if duration_raw is not None else None
        ended_reason = str(message.get("endedReason") or "").lower()
        final_status = "NO_ANSWER" if "no-answer" in ended_reason or "busy" in ended_reason else "COMPLETED"

        finalize_call_log(
            db=db,
            call_log=call_log,
            transcript=transcript,
            call_status=final_status,
            duration_sec=duration_sec,
        )
        return {"status": "ok", "outcome": call_log.student_outcome}

    return {"status": "ignored"}
