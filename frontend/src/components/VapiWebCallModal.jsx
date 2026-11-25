import { useEffect, useRef, useState } from 'react'
import Vapi from '@vapi-ai/web'
import { Mic, MicOff, Phone, PhoneOff, Send, Volume2, X } from 'lucide-react'
import { api } from '../api/client'

export default function VapiWebCallModal({ match, onClose, onCallFinished }) {
  const [status, setStatus] = useState('idle') // idle | connecting | active | ended | error
  const [messages, setMessages] = useState([])
  const [muted, setMuted] = useState(false)
  const [assistantSpeaking, setAssistantSpeaking] = useState(false)
  const [volumeLevel, setVolumeLevel] = useState(0)
  const [textInput, setTextInput] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [summary, setSummary] = useState(null)
  const [elapsed, setElapsed] = useState(0)

  const vapiRef = useRef(null)
  const callLogIdRef = useRef(null)
  const messagesRef = useRef([])
  const startTimeRef = useRef(null)
  const finalizedRef = useRef(false)
  const bottomRef = useRef(null)
  const onCallFinishedRef = useRef(onCallFinished)

  useEffect(() => {
    onCallFinishedRef.current = onCallFinished
  }, [onCallFinished])

  useEffect(() => {
    messagesRef.current = messages
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (status !== 'active') return
    const id = setInterval(() => setElapsed((prev) => prev + 1), 1000)
    return () => clearInterval(id)
  }, [status])

  const finalizeCall = async () => {
    if (finalizedRef.current || !callLogIdRef.current) return
    finalizedRef.current = true
    const transcript = messagesRef.current
      .map((m) => `${m.sender === 'ai' ? 'AI' : 'Student'}: ${m.text}`)
      .join('\n')
    const durationSec = startTimeRef.current
      ? Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000))
      : Math.max(1, elapsed)

    try {
      const { data } = await api.post(`/vapi/web-call-complete/${callLogIdRef.current}`, {
        transcript,
        duration_sec: durationSec,
      })
      setSummary(data)
      if (onCallFinishedRef.current) onCallFinishedRef.current(data)
    } catch {
      // still show ended state
    }
    setStatus('ended')
  }

  useEffect(() => {
    return () => {
      if (vapiRef.current) {
        try {
          vapiRef.current.stop()
        } catch {
          // ignore
        }
      }
    }
  }, [])

  const startCall = async () => {
    setErrorMsg('')
    setStatus('connecting')
    finalizedRef.current = false
    setMessages([])

    try {
      const { data } = await api.get(`/vapi/web-config/${match.id}`)
      callLogIdRef.current = data.callLogId

      const vapi = new Vapi(data.publicKey)
      vapiRef.current = vapi

      vapi.on('call-start', () => {
        startTimeRef.current = Date.now()
        setStatus('active')
      })

      vapi.on('speech-start', () => setAssistantSpeaking(true))
      vapi.on('speech-end', () => setAssistantSpeaking(false))
      vapi.on('volume-level', (vol) => setVolumeLevel(vol))

      vapi.on('message', (msg) => {
        if (msg?.type === 'transcript' && msg?.transcriptType === 'final' && msg?.transcript) {
          const sender = msg.role === 'assistant' ? 'ai' : 'student'
          setMessages((prev) => [...prev, { sender, text: msg.transcript }])
        }
      })

      vapi.on('call-end', () => {
        setAssistantSpeaking(false)
        finalizeCall()
      })

      vapi.on('error', (err) => {
        setErrorMsg(err?.message || err?.error?.message || 'Vapi call encountered an error.')
        setStatus('error')
      })

      await vapi.start(data.assistantId, data.assistantOverrides)
    } catch (err) {
      setErrorMsg(
        err.response?.data?.detail || err.message || 'Could not start Vapi Web Call.'
      )
      setStatus('error')
    }
  }

  const toggleMute = () => {
    if (!vapiRef.current) return
    const next = !muted
    vapiRef.current.setMuted(next)
    setMuted(next)
  }

  const endCall = async () => {
    if (vapiRef.current) {
      try {
        await vapiRef.current.stop()
      } catch {
        // ignore
      }
    }
    await finalizeCall()
  }

  const sendTextMessage = (e) => {
    e.preventDefault()
    const cleaned = textInput.trim()
    if (!cleaned || !vapiRef.current || status !== 'active') return
    setMessages((prev) => [...prev, { sender: 'student', text: cleaned }])
    vapiRef.current.send({
      type: 'add-message',
      message: { role: 'user', content: cleaned },
      triggerResponseEnabled: true,
    })
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
              Vapi AI Voice Call • University Placement Agent
            </p>
            <h3 className="text-lg font-semibold">
              {match.company_name} — {match.company_role}
            </h3>
            <p className="text-xs text-indigo-100">
              {match.student_name} • Fit Score {match.fit_score}% • {formatTimer(elapsed)}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-indigo-100 transition hover:bg-indigo-500 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
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

        {/* Body */}
        <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-4">
          {status === 'idle' && (
            <div className="flex flex-col items-center justify-center space-y-4 py-8 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
                <Phone className="h-8 w-8" />
              </div>
              <div className="max-w-md space-y-1">
                <h4 className="text-base font-bold text-slate-900">
                  Ready to Call via Vapi Voice AI
                </h4>
                <p className="text-xs leading-relaxed text-slate-600">
                  Click below to start a live two-way voice call using your microphone. Vapi already
                  has <strong>{match.student_name}&apos;s</strong> resume and{' '}
                  <strong>{match.company_name}&apos;s</strong> full JD loaded.
                </p>
              </div>
              <button
                type="button"
                onClick={startCall}
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
              >
                <Phone className="h-4 w-4" />
                Start Vapi Voice Call
              </button>
            </div>
          )}

          {status === 'connecting' && (
            <p className="py-8 text-center text-sm text-slate-600">
              Connecting microphone to Vapi University Placement Agent...
            </p>
          )}

          {errorMsg && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
              {errorMsg}
            </div>
          )}

          {status === 'active' && (
            <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-900">
              <div className="flex items-center gap-2">
                <Volume2
                  className={`h-4 w-4 ${assistantSpeaking ? 'animate-pulse text-emerald-600' : 'text-slate-500'}`}
                />
                <span>
                  {assistantSpeaking
                    ? 'Vapi AI is speaking...'
                    : 'Listening to your microphone...'}
                </span>
              </div>
              <span className="font-mono text-[11px] text-emerald-700">
                Audio {Math.round(volumeLevel * 100)}%
              </span>
            </div>
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
                <div className="mb-1 text-[11px] font-semibold opacity-75">
                  {m.sender === 'ai' ? 'Vapi Placement AI' : match.student_name}
                </div>
                <p className="leading-relaxed">{m.text}</p>
              </div>
            </div>
          ))}

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

        {/* Footer Controls */}
        <div className="border-t border-slate-200 bg-white p-4">
          {status === 'active' ? (
            <div className="space-y-3">
              <form onSubmit={sendTextMessage} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={toggleMute}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                    muted
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-slate-100 text-slate-800 hover:bg-slate-200'
                  }`}
                >
                  {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                  <span>{muted ? 'Muted' : 'Mic On'}</span>
                </button>
                <input
                  type="text"
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder="Or type a message to Vapi AI..."
                  className="flex-1 rounded-xl border border-slate-300 px-3.5 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={!textInput.trim()}
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
                End Vapi Call & Save Transcript
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
