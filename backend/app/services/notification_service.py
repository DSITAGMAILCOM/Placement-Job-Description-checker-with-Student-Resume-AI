from email.message import EmailMessage
from html import escape
import logging
import smtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_match_details_email(
    to_email: str,
    student_name: str,
    student_branch: str | None,
    student_cgpa: float | None,
    company_name: str,
    role: str,
    fit_score: int | None,
    match_pitch: str | None,
    matched_skills: list[str] | None,
    missing_skills: list[str] | None,
    ctc: str | None,
    deadline: str | None,
    registration_url: str | None,
    jd_text: str | None,
) -> tuple[bool, str | None]:
    """Send complete match analysis, JD summary, and registration link via Gmail SMTP."""
    if not settings.SMTP_EMAIL or not settings.SMTP_APP_PASSWORD:
        msg = "SMTP_EMAIL and SMTP_APP_PASSWORD are not configured in .env yet."
        logger.info("%s Skipped email to %s.", msg, to_email)
        return False, msg

    skills_str = ", ".join(matched_skills) if matched_skills else "See your uploaded resume"
    missing_str = ", ".join(missing_skills) if missing_skills else "None identified"
    score_str = f"{fit_score}%" if fit_score is not None else "Eligible"
    reg_display = registration_url or "Check the PlaceCall AI portal"
    jd_excerpt = (jd_text or "").strip()

    plain_body = (
        f"Hi {student_name},\n\n"
        f"You have matched with {company_name} for the {role} role! You can register for this company.\n\n"
        f"--- Match Analysis ---\n"
        f"Fit Score: {score_str}\n"
        f"Your Profile: Branch {student_branch or 'N/A'} | CGPA {student_cgpa if student_cgpa is not None else 'N/A'}\n"
        f"Why You Match: {match_pitch or 'Your skills and profile align with this drive.'}\n"
        f"Your Matched Skills: {skills_str}\n"
        f"Skills to Brush Up: {missing_str}\n\n"
        f"--- Drive Details ---\n"
        f"Company: {company_name}\n"
        f"Role: {role}\n"
        f"Package (CTC): {ctc or 'See portal'}\n"
        f"Registration Deadline: {deadline or 'See portal'}\n"
        f"Registration Link: {reg_display}\n\n"
        f"--- Full Job Description ---\n"
        f"{jd_excerpt}\n\n"
        "Best of luck!\n"
        "Campus Placement Cell (PlaceCall AI)"
    )

    html_reg = (
        f'<a href="{escape(registration_url)}" style="display:inline-block;padding:10px 18px;background:#4f46e5;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;">Register for {escape(company_name)}</a>'
        if registration_url
        else f"<span>{escape(reg_display)}</span>"
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#0f172a;line-height:1.5;">
      <div style="background:#4f46e5;color:#ffffff;padding:20px 24px;border-radius:12px 12px 0 0;">
        <h2 style="margin:0;font-size:20px;">{escape(company_name)} — {escape(role)}</h2>
        <p style="margin:6px 0 0;font-size:13px;opacity:0.9;">PlaceCall AI Match Score: <strong>{escape(score_str)}</strong> • You can register for this company</p>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;padding:24px;border-radius:0 0 12px 12px;background:#ffffff;">
        <p>Hi <strong>{escape(student_name)}</strong>,</p>
        <p>Based on your resume and database profile (<strong>{escape(student_branch or 'N/A')}</strong>, CGPA <strong>{student_cgpa if student_cgpa is not None else 'N/A'}</strong>), you are eligible and strongly matched for <strong>{escape(company_name)}</strong>.</p>

        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin:16px 0;">
          <p style="margin:0 0 8px;"><strong>Why You Match:</strong><br/>{escape(match_pitch or 'Your skills align with this drive.')}</p>
          <p style="margin:0 0 6px;font-size:13px;"><strong>Your Skills:</strong> {escape(skills_str)}</p>
          <p style="margin:0;font-size:13px;"><strong>Skills to Brush Up:</strong> {escape(missing_str)}</p>
        </div>

        <table style="width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;">
          <tr><td style="padding:6px 0;color:#64748b;">Package (CTC)</td><td style="padding:6px 0;font-weight:600;">{escape(ctc or 'See portal')}</td></tr>
          <tr><td style="padding:6px 0;color:#64748b;">Deadline</td><td style="padding:6px 0;font-weight:600;">{escape(deadline or 'See portal')}</td></tr>
          <tr><td style="padding:6px 0;color:#64748b;">Registration URL</td><td style="padding:6px 0;">{escape(reg_display)}</td></tr>
        </table>

        <div style="margin:20px 0;">{html_reg}</div>

        <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;"/>
        <p style="margin:0 0 6px;font-size:12px;font-weight:700;text-transform:uppercase;color:#64748b;">Full Job Description</p>
        <pre style="white-space:pre-wrap;font-family:Arial,sans-serif;font-size:12px;color:#334155;background:#f8fafc;padding:12px;border-radius:8px;border:1px solid #e2e8f0;">{escape(jd_excerpt)}</pre>
      </div>
    </div>
    """

    msg = EmailMessage()
    msg["Subject"] = f"[{score_str} Match] {company_name} — {role} Campus Drive"
    msg["From"] = settings.SMTP_EMAIL
    msg["To"] = to_email
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        app_password = settings.SMTP_APP_PASSWORD.replace(" ", "").strip()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(settings.SMTP_EMAIL.strip(), app_password)
            smtp.send_message(msg)
        return True, None
    except Exception as exc:
        logger.error("Failed to send SMTP email to %s: %s", to_email, exc)
        return False, str(exc)


def send_registration_email(
    to_email: str,
    student_name: str,
    company_name: str,
    role: str,
    ctc: str | None,
    deadline: str | None,
    registration_url: str | None,
) -> bool:
    """Send the placement drive registration link via Gmail SMTP."""
    ok, _ = send_match_details_email(
        to_email=to_email,
        student_name=student_name,
        student_branch=None,
        student_cgpa=None,
        company_name=company_name,
        role=role,
        fit_score=None,
        match_pitch="Great speaking with you on our PlaceCall AI placement call!",
        matched_skills=None,
        missing_skills=None,
        ctc=ctc,
        deadline=deadline,
        registration_url=registration_url,
        jd_text="",
    )
    return ok


def send_whatsapp_registration_link(
    to_phone: str,
    student_name: str,
    company_name: str,
    role: str,
    registration_url: str | None,
) -> bool:
    """Optionally send the registration link via Twilio WhatsApp Sandbox if configured."""
    if not settings.TWILIO_WHATSAPP_FROM or not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return False

    try:
        from twilio.rest import Client

        clean_to = "".join(ch for ch in to_phone.strip() if ch.isdigit() or ch == "+")
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        from_wa = (
            settings.TWILIO_WHATSAPP_FROM
            if settings.TWILIO_WHATSAPP_FROM.startswith("whatsapp:")
            else f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}"
        )
        to_wa = clean_to if clean_to.startswith("whatsapp:") else f"whatsapp:{clean_to}"
        body = (
            f"Hi {student_name}! Here is your registration link for {company_name} ({role}): "
            f"{registration_url or 'Check the PlaceCall AI portal'}"
        )
        client.messages.create(from_=from_wa, to=to_wa, body=body)
        return True
    except Exception as exc:
        logger.error("Failed to send WhatsApp message to %s: %s", to_phone, exc)
        return False


def dispatch_registration_link(
    to_email: str,
    to_phone: str,
    student_name: str,
    company_name: str,
    role: str,
    ctc: str | None,
    deadline: str | None,
    registration_url: str | None,
) -> bool:
    """Dispatch registration link over Email and/or WhatsApp. Returns True if at least one succeeded."""
    email_ok = send_registration_email(
        to_email=to_email,
        student_name=student_name,
        company_name=company_name,
        role=role,
        ctc=ctc,
        deadline=deadline,
        registration_url=registration_url,
    )
    wa_ok = send_whatsapp_registration_link(
        to_phone=to_phone,
        student_name=student_name,
        company_name=company_name,
        role=role,
        registration_url=registration_url,
    )
    return email_ok or wa_ok
