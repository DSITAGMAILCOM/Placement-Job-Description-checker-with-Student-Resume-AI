import { X } from 'lucide-react'

export default function TranscriptModal({ log, onClose }) {
  if (!log) return null

  const lines = (log.transcript || '')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="flex max-h-[85vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-900">
              Call Transcript — {log.company_name}
            </h3>
            <p className="text-xs text-slate-500">
              {log.student_name} • {log.company_role} • Duration: {log.duration_sec ?? 0}s
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-wrap gap-2 border-b border-slate-100 bg-slate-50 px-5 py-3 text-xs">
          <span className="rounded-full bg-slate-200 px-2.5 py-1 font-medium text-slate-800">
            Status: {log.call_status}
          </span>
          <span className="rounded-full bg-indigo-100 px-2.5 py-1 font-medium text-indigo-800">
            Outcome: {log.student_outcome}
          </span>
          <span className="rounded-full bg-emerald-100 px-2.5 py-1 font-medium text-emerald-800">
            Link Sent: {log.link_sent ? 'Yes' : 'No'}
          </span>
        </div>

        <div className="flex-1 space-y-2.5 overflow-y-auto p-5">
          {lines.length === 0 ? (
            <p className="text-sm text-slate-500">No transcript recorded for this call.</p>
          ) : (
            lines.map((line, i) => {
              const isAi = line.startsWith('AI:')
              return (
                <div
                  key={i}
                  className={`rounded-xl px-4 py-2.5 text-sm ${
                    isAi
                      ? 'border border-slate-200 bg-slate-50 text-slate-800'
                      : 'bg-indigo-50 text-indigo-950'
                  }`}
                >
                  {line}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
