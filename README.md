# PlaceCall AI

Automated campus placement matching and AI outbound voice calling platform built with **FastAPI**, **LangChain**, **Groq**, **PostgreSQL + pgvector (Neon)**, **Twilio Programmable Voice**, and **React + Vite + Tailwind CSS**.

## Project Structure

- `backend/` — FastAPI REST & WebSocket API, SQLAlchemy + pgvector models, PyMuPDF resume parser, local `all-MiniLM-L6-v2` embeddings, LangChain matching & voice agent, Twilio webhooks.
- `frontend/` — React + Vite + Tailwind CSS SPA for Student Portal, Admin Drive Manager, Match Runner, Call Logs, Analytics Dashboard, and free Browser Voice Call Simulator.

## Running Locally

### 1. Backend (FastAPI)

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8080
```

### 2. Frontend (React + Vite)

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

### 3. Live Twilio Calls (Optional)

1. Replace `PHONE_NUMBER` (or set `TWILIO_PHONE_NUMBER`) in `.env` with your real Twilio trial phone number in E.164 format (e.g. `+1...`).
2. Start ngrok pointing to port 8000 (`ngrok http 8000 --url=skeptic-droop-endurable.ngrok-free.dev`).
3. Ensure `SMTP_EMAIL` and `SMTP_APP_PASSWORD` are set in `.env` for automatic registration link emails.
4. Set `TWILIO_VOICE_MODE=gather` in `.env` if ConversationRelay is not enabled on your Twilio trial account.
