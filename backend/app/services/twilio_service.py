from html import escape
import logging
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy.orm import Session, joinedload
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, Gather, VoiceResponse

from app.core.config import settings
from app.db.models import CallLog, Match, Resume, Student
from app.services.ai_engine import VoiceAgentSession, classify_call_transcript
from app.services.notification_service import dispatch_registration_link

logger = logging.getLogger(__name__)

# In-memory active session store for Gather-mode calls keyed by call_log_id
_gather_sessions: dict[int, VoiceAgentSession] = {}


def validate_twilio_signature(request: Request, form_params: dict[str, str]) -> bool:
    """Validate Twilio X-Twilio-Signature header against PUBLIC_BASE_URL."""
    if not settings.VALIDATE_TWILIO_SIGNATURE:
        return True
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        return False

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    # Reconstruct external URL using PUBLIC_BASE_URL because ngrok terminates TLS
    query = str(request.url.query)
    full_url = f"{settings.PUBLIC_BASE_URL}{request.url.path}"
    if query:
        full_url = f"{full_url}?{query}"

    if validator.validate(full_url, form_params, signature):
        return True
    # Fallback to raw request.url in case local proxy forwards exact host
    return validator.validate(str(request.url), form_params, signature)


def build_voice_session(db: Session, match_id: int) -> tuple[VoiceAgentSession, Match]:
    """Load match + student + resume + other company matches and create a VoiceAgentSession."""
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


def get_or_create_gather_session(db: Session, match_id: int, call_log_id: int) -> VoiceAgentSession:
    if call_log_id not in _gather_sessions:
        session, _ = build_voice_session(db, match_id)
        _gather_sessions[call_log_id] = session
    return _gather_sessions[call_log_id]


def pop_gather_session(call_log_id: int) -> VoiceAgentSession | None:
    return _gather_sessions.pop(call_log_id, None)


def _clean_phone(raw_phone: str) -> str:
    return "".join(ch for ch in raw_phone.strip() if ch.isdigit() or ch == "+")


def get_twilio_preflight_status() -> dict:
    """Inspect Twilio account readiness (owned From numbers, verified Caller IDs, trial status, PUBLIC_BASE_URL)."""
    configured_from = settings.caller_number
    result = {
        "account_type": "Unknown",
        "configured_from": configured_from,
        "owned_numbers": [],
        "verified_numbers": [],
        "from_number_valid": False,
        "public_base_url": settings.PUBLIC_BASE_URL,
        "issues": [],
    }
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        acc = client.api.accounts(settings.TWILIO_ACCOUNT_SID).fetch()
        result["account_type"] = acc.type
        bal = client.api.accounts(settings.TWILIO_ACCOUNT_SID).balance.fetch()
        result["balance"] = f"{bal.balance} {bal.currency}"

        owned = [n.phone_number for n in client.incoming_phone_numbers.list()]
        verified = [c.phone_number for c in client.outgoing_caller_ids.list()]
        result["owned_numbers"] = owned
        result["verified_numbers"] = verified
        result["from_number_valid"] = bool(configured_from and configured_from in owned)

        if float(bal.balance or 0) <= 0:
            result["issues"].append(
                f"Twilio account balance is {bal.balance} {bal.currency}. Twilio blocks custom webhook URLs on $0.00 unactivated trial accounts (the onboarding From number +17372212163 only works with webhooks.twilio.com). Claim your free Trial balance & Twilio number in Twilio Console (or upgrade)."
            )
        if not owned:
            result["issues"].append(
                "No Twilio phone number is provisioned in your Twilio Console. Claim a free Trial number in Twilio Console -> Phone Numbers -> Manage -> Buy a number, and put it in .env as PHONE_NUMBER."
            )
        elif not result["from_number_valid"]:
            result["issues"].append(
                f"Configured PHONE_NUMBER ({configured_from}) is not owned by your Twilio account. Set PHONE_NUMBER in .env to one of: {', '.join(owned)}."
            )
        if acc.type == "Trial" and not verified:
            result["issues"].append(
                "Twilio Trial accounts can only dial Verified Caller IDs. Verify your student/test phone number in Twilio Console -> Phone Numbers -> Manage -> Verified Caller IDs."
            )
    except Exception as exc:
        result["issues"].append(f"Could not connect to Twilio API: {exc}")
    return result


def trigger_outbound_twilio_call(match: Match, call_log: CallLog) -> str:
    """Place an outbound PSTN call via Twilio Programmable Voice API."""
    caller = settings.caller_number
    if not caller:
        raise ValueError("Twilio caller phone number (TWILIO_PHONE_NUMBER / PHONE_NUMBER) is not configured.")

    to_phone = _clean_phone(match.student.phone)
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    params = urlencode({"match_id": match.id, "call_log_id": call_log.id})
    webhook_url = f"{settings.PUBLIC_BASE_URL}{settings.API_V1_PREFIX}/twilio/voice-webhook?{params}"
    status_url = f"{settings.PUBLIC_BASE_URL}{settings.API_V1_PREFIX}/twilio/status-callback?{params}"

    try:
        call = client.calls.create(
            to=to_phone,
            from_=caller,
            url=webhook_url,
            method="POST",
            status_callback=status_url,
            status_callback_method="POST",
        )
        return call.sid
    except Exception as exc:
        msg = str(exc)
        if "limited parameter access" in msg.lower():
            raise ValueError(
                "Twilio rejected custom webhook parameters because this Trial account has $0.00 balance / no claimed Twilio number yet "
                "(Twilio's onboarding From number +17372212163 only works with webhooks.twilio.com demo URLs). "
                "Activate your Trial balance & claim a free Twilio number in Twilio Console, or use the Browser Voice Simulator."
            ) from exc
        raise


def build_initial_twiml(match_id: int, call_log_id: int, greeting: str) -> str:
    """Generate TwiML for ConversationRelay WebSocket or Gather fallback."""
    response = VoiceResponse()
    if settings.TWILIO_VOICE_MODE == "gather":
        action_url = (
            f"{settings.PUBLIC_BASE_URL}{settings.API_V1_PREFIX}/twilio/gather-turn/{match_id}"
            f"?call_log_id={call_log_id}"
        )
        gather = Gather(
            input="speech",
            language="en-IN",
            speech_timeout="auto",
            action=action_url,
            method="POST",
        )
        gather.say(greeting, voice="Polly.Aditi", language="en-IN")
        response.append(gather)
        response.say(
            "I did not hear a response. You can always check your matched companies on the PlaceCall AI portal. Goodbye!",
            voice="Polly.Aditi",
            language="en-IN",
        )
        return str(response)

    # Primary: Twilio ConversationRelay WebSocket
    ws_url = (
        f"{settings.ws_base_url}{settings.API_V1_PREFIX}/twilio/voice-stream/{match_id}"
        f"?call_log_id={call_log_id}"
    )
    connect = Connect()
    connect.conversation_relay(
        url=ws_url,
        welcome_greeting=greeting,
        language="en-IN",
    )
    response.append(connect)
    return str(response)


def build_gather_turn_twiml(match_id: int, call_log_id: int, reply_text: str) -> str:
    """Generate TwiML for subsequent Gather speech turns."""
    response = VoiceResponse()
    action_url = (
        f"{settings.PUBLIC_BASE_URL}{settings.API_V1_PREFIX}/twilio/gather-turn/{match_id}"
        f"?call_log_id={call_log_id}"
    )
    gather = Gather(
        input="speech",
        language="en-IN",
        speech_timeout="auto",
        action=action_url,
        method="POST",
    )
    gather.say(reply_text, voice="Polly.Aditi", language="en-IN")
    response.append(gather)
    response.say("Thank you for your time. Goodbye!", voice="Polly.Aditi", language="en-IN")
    return str(response)


def finalize_call_log(
    db: Session,
    call_log: CallLog,
    transcript: str | None = None,
    call_status: str | None = None,
    duration_sec: int | None = None,
) -> CallLog:
    """Persist transcript, classify outcome via LangChain, update Match, and dispatch link if INTERESTED."""
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
