import { useEffect, useRef, useState } from 'react'
import { Mic, MicOff, PhoneOff, Send, Volume2, VolumeX, X } from 'lucide-react'
import { getSimulatorWsUrl } from '../api/client'

export default function VoiceSimulatorModal({ match, onClose, onCallFinished }) {
  const [status, setStatus] = useState('connecting') // connecting | active | ended | error
  const [messages, setMessages] = useState([])
  const [listening, setListening] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [muted, setMuted] = useState(false)
  const [textInput, setTextInput] = useState('')
  const [summary, setSummary] = useState(null)
  const [speechSupported, setSpeechSupported] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  const wsRef = useRef(null)
  const recognitionRef = useRef(null)
  const bottomRef = useRef(null)
  const onCallFinishedRef = useRef(onCallFinished)
  const mutedRef = useRef(muted)

  useEffect(() => {
    onCallFinishedRef.current = onCallFinished
  }, [onCallFinished])

  useEffect(() => {
    mutedRef.current = muted
    if (muted) window.speechSynthesis?.cancel()
  }, [muted])

  useEffect(() => {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition
    setSpeechSupported(Boolean(SpeechRec))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (status !== 'active') return
    const id = setInterval(() => setElapsed((prev) => prev + 1), 1000)
    return () => clearInterval(id)
  }, [status])

  const speakText = (text) => {
    if (mutedRef.current || !('speechSynthesis' in window) || !text) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'en-IN'
    utterance.rate = 1.02
    window.speechSynthesis.speak(utterance)
  }

  useEffect(() => {
    let cancelled = false
    const ws = new WebSocket(getSimulatorWsUrl(match.id))
    wsRef.current = ws

    ws.onopen = () => {
      if (cancelled) return
      setStatus('active')
      setThinking(true)
    }

    ws.onmessage = (event) => {
      if (cancelled) return
      const data = JSON.parse(event.data)
      if (data.type === 'ai_reply') {
        setThinking(false)
        setMessages((prev) => [...prev, { sender: 'ai', text: data.text }])
        speakText(data.text)
      } else if (data.type === 'call_ended') {
        setThinking(false)
        setStatus('ended')
        setSummary(data)
        if (onCallFinishedRef.current) onCallFinishedRef.current(data)
      }
    }

    ws.onerror = () => {
      if (cancelled) return
      setStatus('error')
      setThinking(false)
    }

    ws.onclose = () => {
      window.speechSynthesis?.cancel()
      recognitionRef.current?.stop()
    }

    return () => {
      cancelled = true
      window.speechSynthesis?.cancel()
      recognitionRef.current?.stop()
      if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    }
  }, [match.id])

  const sendUtterance = (text) => {
    const cleaned = text.trim()
    if (!cleaned || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setMessages((prev) => [...prev, { sender: 'student', text: cleaned }])
    setThinking(true)
    wsRef.current.send(JSON.stringify({ type: 'user_speech', text: cleaned }))
  }

  const toggleMic = () => {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRec) return

    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return
    }

    window.speechSynthesis?.cancel()
    const rec = new SpeechRec()
    rec.lang = 'en-IN'
    rec.interimResults = false
    rec.maxAlternatives = 1

    rec.onresult = (event) => {
      const spoken = event.results[0][0].transcript
      setListening(false)
      sendUtterance(spoken)
    }
    rec.onerror = () => setListening(false)
    rec.onend = () => setListening(false)

    recognitionRef.current = rec
    setListening(true)
    rec.start()
  }

  const endCall = () => {
    window.speechSynthesis?.cancel()
    recognitionRef.current?.stop()
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      setThinking(true)
      wsRef.current.send(JSON.stringify({ type: 'end_call' }))
    } else {
      onClose()
    }
  }

  const handleTextSubmit = (e) => {
    e.preventDefault()
    if (!textInput.trim()) return
    sendUtterance(textInput)
    setTextInput('')
  }

  const formatTimer = (sec) => {
    const m = String(Math.floor(sec / 60)).padStart(2, '0')
    const s = String(sec % 60).padStart(2, '0')
    return `${m}:${s}`
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between bg-indigo-600 px-5 py-4 text-white">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-indigo-100">
              Interactive AI Voice Call Simulator
            </p>
            <h3 className="text-lg font-semibold">
              {match.company_name} — {match.company_role}
            </h3>
            <p className="text-xs text-indigo-100">
              Calling {match.student_name} • Fit Score {match.fit_score}% • {formatTimer(elapsed)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMuted((m) => !m)}
              title={muted ? 'Unmute AI voice' : 'Mute AI voice'}
              className="rounded-lg p-1.5 text-indigo-100 transition hover:bg-indigo-500 hover:text-white"
            >
              {muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
            </button>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-indigo-100 transition hover:bg-indigo-500 hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* JD & Resume Match Context Strip */}
        <div className="border-b border-slate-200 bg-indigo-50/70 px-5 py-2.5 text-xs text-slate-700">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>
              <strong>CTC:</strong> {match.company_ctc || 'N/A'} •{' '}
              <strong>Deadline:</strong> {match.company_deadline || 'Check portal'}
            </span>
            {match.missing_skills?.length > 0 && (
              <span className="text-amber-800">
                <strong>Skill Gaps:</strong> {match.missing_skills.join(', ')}
              </span>
            )}
          </div>
        </div>

        {/* Transcript Chat */}
        <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-4">
          {status === 'connecting' && (
            <p className="text-center text-sm text-slate-500">Connecting to PlaceCall AI...</p>
          )}
          {status === 'error' && (
            <p className="rounded-lg bg-red-50 p-3 text-center text-sm text-red-700">
              WebSocket connection failed. Ensure the FastAPI backend is running.
            </p>
          )}

          {messages.map((m, idx) => (
            <div
              key={idx}
              className={`flex ${m.sender === 'student' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm shadow-sm ${
                  m.sender === 'student'
                    ? 'bg-indigo-600 text-white'
                    : 'border border-slate-200 bg-white text-slate-800'
                }`}
              >
                <div className="mb-1 flex items-center justify-between gap-3 text-[11px] font-semibold opacity-75">
                  <span className="flex items-center gap-1">
                    {m.sender === 'ai' && <Volume2 className="h-3 w-3" />}
                    {m.sender === 'ai' ? 'PlaceCall AI' : match.student_name}
                  </span>
                  {m.sender === 'ai' && (
                    <button
                      type="button"
                      onClick={() => speakText(m.text)}
                      className="underline hover:opacity-100"
                    >
                      Play Audio
                    </button>
                  )}
                </div>
                <p className="leading-relaxed">{m.text}</p>
              </div>
            </div>
          ))}

          {thinking && status === 'active' && (
            <div className="flex justify-start">
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-xs text-slate-500">
                PlaceCall AI is speaking...
              </div>
            </div>
          )}

          {summary && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
              <p className="font-semibold">Call Completed & Classified</p>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                <div>
                  <span className="text-emerald-700">Outcome:</span>{' '}
                  <strong className="block">{summary.outcome}</strong>
                </div>
                <div>
                  <span className="text-emerald-700">Duration:</span>{' '}
                  <strong className="block">{summary.duration_sec}s</strong>
                </div>
                <div>
                  <span className="text-emerald-700">Link Sent:</span>{' '}
                  <strong className="block">{summary.link_sent ? 'Yes' : 'Logged / No SMTP'}</strong>
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Controls */}
        <div className="border-t border-slate-200 bg-white p-4">
          {status === 'active' ? (
            <div className="space-y-3">
              {/* Quick Student Prompts */}
              <div className="flex flex-wrap gap-1.5">
                {[
                  'Tell me all details about the JD and why I match',
                  'What is the package and deadline?',
                  'Yes, please send the registration link!',
                ].map((q) => (
                  <button
                    key={q}
                    type="button"
                    disabled={thinking}
                    onClick={() => sendUtterance(q)}
                    className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-medium text-slate-700 transition hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>

              <form onSubmit={handleTextSubmit} className="flex items-center gap-2">
                {speechSupported && (
                  <button
                    type="button"
                    onClick={toggleMic}
                    className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                      listening
                        ? 'animate-pulse bg-rose-600 text-white'
                        : 'bg-slate-100 text-slate-800 hover:bg-slate-200'
                    }`}
                  >
                    {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                    <span>{listening ? 'Listening...' : 'Speak'}</span>
                  </button>
                )}
                <input
                  type="text"
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder={
                    speechSupported
                      ? 'Click Speak or type your response...'
                      : 'Type student response (e.g., Tell me about the JD)'
                  }
                  className="flex-1 rounded-xl border border-slate-300 px-3.5 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={!textInput.trim() || thinking}
                  className="inline-flex items-center gap-1 rounded-xl bg-indigo-600 px-3.5 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>

              <button
                type="button"
                onClick={endCall}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-700"
              >
                <PhoneOff className="h-4 w-4" />
                End Call & Classify Outcome
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="w-full rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
