import json
import logging
import re
from typing import Literal, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.schemas import ParsedResumeData

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class MatchReasoningOutput(BaseModel):
    missing_skills: list[str] = Field(
        default_factory=list,
        description="Important skills required in the JD that are absent from the student's resume.",
    )
    match_pitch: str = Field(
        ...,
        description="Concise 2-sentence personalized calling pitch explaining why the student's skills and projects fit this role.",
    )
    llm_alignment_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="0-100 technical alignment score between resume and JD.",
    )


class CallOutcomeClassification(BaseModel):
    outcome: Literal["INTERESTED", "NOT_INTERESTED", "CALL_BACK", "UNKNOWN"]
    reason: str = ""


def _get_llm(fast: bool = False, json_mode: bool = False):
    """Build primary Groq LLM client with optional Gemini fallback."""
    model_name = settings.GROQ_FAST_MODEL if fast else settings.GROQ_REASONING_MODEL
    kwargs: dict = {}
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

    primary = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=model_name,
        temperature=0.15 if json_mode else 0.4,
        max_tokens=2048 if not fast else (512 if json_mode else 220),
        **kwargs,
    )
    if settings.GEMINI_API_KEY and not json_mode:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            fallback = ChatGoogleGenerativeAI(
                google_api_key=settings.GEMINI_API_KEY,
                model="gemini-2.0-flash",
                temperature=0.3,
            )
            return primary.with_fallbacks([fallback])
        except Exception as exc:
            logger.warning("Gemini fallback init failed: %s", exc)
            return primary
    return primary


def _invoke_json_model(
    schema: type[T],
    system_prompt: str,
    human_prompt: str,
    fast: bool = False,
) -> T:
    """Invoke Groq in strict JSON object mode and parse into a Pydantic model without tool-calling."""
    llm = _get_llm(fast=fast, json_mode=True)
    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]
    )
    raw = str(response.content).strip()
    # Strip markdown code fences if a model wraps JSON in ```json ... ```
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
    data = json.loads(raw)
    return schema.model_validate(data)


def extract_resume_structure(raw_text: str) -> ParsedResumeData:
    """Use LangChain + Groq JSON mode to extract skills, projects, and education from resume text."""
    system_prompt = (
        "You are an expert technical recruiter. Extract the candidate's technical & soft skills, "
        "notable projects (short 1-line descriptions), education entries, and a 2-sentence summary "
        "from the raw resume text. Only include facts explicitly present in the resume.\n"
        "Respond ONLY with a valid JSON object containing these exact keys:\n"
        '{"skills": ["..."], "projects": ["..."], "education": ["..."], "summary": "..."}'
    )
    human_prompt = f"Resume text:\n{raw_text[:10000]}"
    try:
        return _invoke_json_model(ParsedResumeData, system_prompt, human_prompt, fast=False)
    except Exception as exc:
        logger.warning("extract_resume_structure LLM failed, using fallback: %s", exc)
        common_keywords = [
            "Python", "Java", "C++", "JavaScript", "TypeScript", "React", "Node.js",
            "FastAPI", "Django", "SQL", "PostgreSQL", "Docker", "Kubernetes", "AWS",
            "Azure", "Redis", "gRPC", "Git", "Machine Learning", "LangChain", "HTML", "CSS",
        ]
        lower_text = raw_text.lower()
        found = [kw for kw in common_keywords if kw.lower() in lower_text]
        return ParsedResumeData(skills=found, projects=[], education=[], summary="")


def generate_match_reasoning(
    student_name: str,
    branch: str | None,
    cgpa: float,
    parsed_skills: dict | list | None,
    resume_text: str,
    company_name: str,
    role: str,
    jd_text: str,
    vector_score: int,
) -> MatchReasoningOutput:
    """Identify missing skills and generate a 2-sentence personalized calling pitch."""
    system_prompt = (
        "You are a campus placement AI advisor. Given a student's profile/resume and a company job description, "
        "evaluate how well the student fits the role and respond ONLY with a valid JSON object with these exact keys:\n"
        '{\n'
        '  "missing_skills": ["skill1", "skill2"],\n'
        '  "match_pitch": "Exactly 2 natural spoken sentences in second person addressing the student (e.g. Your project on...). Never write in first person as the student.",\n'
        '  "llm_alignment_score": 85\n'
        '}'
    )
    human_prompt = (
        f"Student: {student_name} (Branch: {branch or 'N/A'}, CGPA: {cgpa})\n"
        f"Extracted Resume Data: {parsed_skills or {}}\n"
        f"Resume Excerpt:\n{resume_text[:5000]}\n\n"
        f"Company: {company_name} — Role: {role}\n"
        f"Semantic Similarity Score: {vector_score}/100\n"
        f"Job Description:\n{jd_text[:5000]}"
    )
    try:
        return _invoke_json_model(MatchReasoningOutput, system_prompt, human_prompt, fast=False)
    except Exception as exc:
        logger.warning("generate_match_reasoning LLM failed, using fallback: %s", exc)
        pitch = (
            f"Hi {student_name}, your technical background aligns strongly with {company_name}'s {role} opening. "
            "Based on your resume skills and eligibility, you are a great fit and can register for this drive now."
        )
        return MatchReasoningOutput(
            missing_skills=[],
            match_pitch=pitch,
            llm_alignment_score=vector_score,
        )


def classify_call_transcript(transcript: str) -> str:
    """Classify a completed call transcript into INTERESTED, NOT_INTERESTED, CALL_BACK, or UNKNOWN."""
    if not transcript or not transcript.strip():
        return "UNKNOWN"

    system_prompt = (
        "Classify the student's intent at the end of a campus placement phone call. "
        "Respond ONLY with a valid JSON object:\n"
        '{"outcome": "INTERESTED" | "NOT_INTERESTED" | "CALL_BACK" | "UNKNOWN", "reason": "..."}\n'
        "- INTERESTED: student wants to register, receive the link, or apply.\n"
        "- NOT_INTERESTED: student declines or says they do not want to apply.\n"
        "- CALL_BACK: student is busy right now or asks to be called later.\n"
        "- UNKNOWN: unclear, disconnected early, or no meaningful student response."
    )
    human_prompt = f"Transcript:\n{transcript[:6000]}"
    try:
        result = _invoke_json_model(CallOutcomeClassification, system_prompt, human_prompt, fast=True)
        return result.outcome
    except Exception as exc:
        logger.warning("classify_call_transcript LLM failed, using fallback: %s", exc)
        lower = transcript.lower()
        if any(w in lower for w in ["send the link", "yes", "interested", "sure", "register", "please send"]):
            return "INTERESTED"
        if any(w in lower for w in ["not interested", "no thanks", "don't want", "decline"]):
            return "NOT_INTERESTED"
        if any(w in lower for w in ["call back", "later", "busy"]):
            return "CALL_BACK"
        return "UNKNOWN"


class VoiceAgentSession:
    """Stateful conversational LangChain voice agent grounded in JD + Resume + other student matches."""

    def __init__(
        self,
        student_name: str,
        student_branch: str | None,
        student_cgpa: float,
        parsed_skills: dict | list | None,
        company_name: str,
        role: str,
        ctc: str | None,
        deadline: str | None,
        registration_url: str | None,
        match_pitch: str | None,
        missing_skills: list[str] | None,
        jd_text: str,
        other_matches_summary: str = "",
    ) -> None:
        self.student_name = student_name
        self.company_name = company_name
        self.role = role
        self.match_pitch = match_pitch or ""
        self.llm = _get_llm(fast=True, json_mode=False)

        system_content = (
            "You are PlaceCall AI, a friendly, natural-sounding campus placement assistant on a live phone call.\n"
            f"You are calling {student_name} (Branch: {student_branch or 'N/A'}, CGPA: {student_cgpa}).\n"
            f"Primary matched company: {company_name} for the {role} role.\n"
            f"Package (CTC): {ctc or 'Not specified in portal'}\n"
            f"Registration Deadline: {deadline or 'Check placement portal'}\n"
            f"Personalized Match Pitch: {self.match_pitch}\n"
            f"Student Parsed Skills & Projects: {parsed_skills or 'N/A'}\n"
            f"Missing Skills to note if asked: {missing_skills or []}\n"
            f"Other matched companies for this student: {other_matches_summary or 'None currently'}\n\n"
            f"Full Job Description (ONLY source of truth):\n{jd_text[:4500]}\n\n"
            "STRICT CONVERSATION RULES:\n"
            "1. Speak naturally like a real placement coordinator on a phone call (no bullet points, no markdown, no emojis).\n"
            "2. Keep regular turns concise (2 to 3 spoken sentences), unless the student asks for full job description details — then clearly summarize the role, CTC, tech stack/requirements, why their resume matches, missing skills if any, and deadline.\n"
            "3. Proactively explain why their resume & projects match this company and tell them they can register for this drive.\n"
            "4. Answer all questions strictly from the JD and database above; if a detail is not listed, politely direct them to the placement portal.\n"
            "5. Ask if they would like the registration link sent right away; if they agree, confirm you will send it as soon as the call ends."
        )
        self.history: list[BaseMessage] = [SystemMessage(content=system_content)]
        self.transcript_lines: list[str] = []

    def opening_greeting(self) -> str:
        """Generate the initial spoken greeting when the student answers the phone."""
        prompt_msg = (
            f"The student {self.student_name} just picked up the phone. Greet them warmly by name, "
            f"mention you're calling from the Campus Placement Cell about {self.company_name}'s {self.role} drive, "
            f"deliver the personalized pitch concisely, and ask if they'd like to hear details or get the registration link. "
            f"Keep it to 2 short spoken sentences."
        )
        return self._invoke_turn(prompt_msg, record_user=False)

    def respond(self, student_utterance: str) -> str:
        """Process a student's spoken turn and return a concise 1-2 sentence reply."""
        cleaned = student_utterance.strip()
        if not cleaned:
            return "Sorry, I didn't quite catch that. Could you repeat?"
        return self._invoke_turn(cleaned, record_user=True)

    def _invoke_turn(self, text: str, record_user: bool) -> str:
        if record_user:
            self.transcript_lines.append(f"Student: {text}")
        self.history.append(HumanMessage(content=text))
        try:
            ai_msg = self.llm.invoke(self.history)
            reply_text = str(ai_msg.content).strip()
        except Exception as exc:
            logger.warning("VoiceAgentSession LLM failed, using fallback: %s", exc)
            reply_text = (
                f"You're matched for {self.company_name}'s {self.role} drive based on your resume. "
                "Would you like me to send you the registration link?"
            )
        self.history.append(AIMessage(content=reply_text))
        self.transcript_lines.append(f"AI: {reply_text}")
        return reply_text

    def get_transcript(self) -> str:
        return "\n".join(self.transcript_lines)
