import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  BarChart3,
  Building2,
  Mail,
  PhoneCall,
  PhoneOutgoing,
  Play,
  Plus,
  Sparkles,
  Users,
} from 'lucide-react'
import { api } from '../api/client'
import Navbar from '../components/Navbar'
import TranscriptModal from '../components/TranscriptModal'
import VapiWebCallModal from '../components/VapiWebCallModal'

export default function AdminDashboard() {
  const [tab, setTab] = useState('drives') // drives | matches | calls | students
  const [summary, setSummary] = useState(null)
  const [companies, setCompanies] = useState([])
  const [matches, setMatches] = useState([])
  const [callLogs, setCallLogs] = useState([])
  const [students, setStudents] = useState([])
  const [preflight, setPreflight] = useState(null)

  const [selectedCompanyId, setSelectedCompanyId] = useState('')
  const [minThreshold, setMinThreshold] = useState(70)
  const [busyAction, setBusyAction] = useState('')
  const [bannerMsg, setBannerMsg] = useState('')

  const [driveForm, setDriveForm] = useState({
    company_name: '',
    role: '',
    min_cgpa: '7.00',
    eligible_branches: 'CSE, IT, ECE',
    ctc: '12 LPA',
    deadline: '',
    registration_url: '',
    jd_text: '',
  })
  const [jdFile, setJdFile] = useState(null)

  const [simulatorMatch, setSimulatorMatch] = useState(null)
  const [selectedLog, setSelectedLog] = useState(null)

  const loadAll = useCallback(async () => {
    try {
      const [sumRes, compRes, matchRes, logRes, studRes, preRes] = await Promise.all([
        api.get('/dashboard/summary'),
        api.get('/companies'),
        api.get('/matches'),
        api.get('/calls/logs'),
        api.get('/students'),
        api.get('/calls/preflight'),
      ])
      setSummary(sumRes.data)
      setCompanies(compRes.data || [])
      setMatches(matchRes.data || [])
      setCallLogs(logRes.data || [])
      setStudents(studRes.data || [])
      setPreflight(preRes.data || null)
    } catch {
      // handled gracefully
    }
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const handleCreateDrive = async (e) => {
    e.preventDefault()
    setBusyAction('creating_drive')
    setBannerMsg('')
    try {
      const fd = new FormData()
      fd.append('company_name', driveForm.company_name)
      fd.append('role', driveForm.role)
      fd.append('min_cgpa', driveForm.min_cgpa || '0')
      fd.append('eligible_branches', driveForm.eligible_branches)
      if (driveForm.ctc) fd.append('ctc', driveForm.ctc)
      if (driveForm.deadline) fd.append('deadline', driveForm.deadline)
      if (driveForm.registration_url) fd.append('registration_url', driveForm.registration_url)
      fd.append('jd_text', driveForm.jd_text)
      if (jdFile) fd.append('jd_file', jdFile)

      await api.post('/companies', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setDriveForm({
        company_name: '',
        role: '',
        min_cgpa: '7.00',
        eligible_branches: 'CSE, IT, ECE',
        ctc: '12 LPA',
        deadline: '',
        registration_url: '',
        jd_text: '',
      })
      setJdFile(null)
      setBannerMsg('Company drive created and JD embedded into pgvector!')
      await loadAll()
    } catch (err) {
      setBannerMsg(err.response?.data?.detail || 'Failed to create company drive.')
    } finally {
      setBusyAction('')
    }
  }

  const handleRunMatch = async (companyId) => {
    setBusyAction(`match_${companyId}`)
    setBannerMsg('')
    try {
      const { data } = await api.post(`/companies/${companyId}/match`, {
        min_fit_score: Number(minThreshold),
      })
      setBannerMsg(`Matching complete: ${data.length} eligible candidate(s) ranked.`)
      setSelectedCompanyId(String(companyId))
      setTab('matches')
      await loadAll()
    } catch (err) {
      setBannerMsg(err.response?.data?.detail || 'Matching run failed.')
    } finally {
      setBusyAction('')
    }
  }

  const handleTriggerCall = async (payload, key) => {
    setBusyAction(key)
    setBannerMsg('')
    try {
      const { data } = await api.post('/calls/trigger', payload)
      const okCount = data.filter((r) => r.status === 'INITIATED').length
      const failCount = data.length - okCount
      const firstErr = data.find((r) => r.error)?.error
      setBannerMsg(
        `Triggered ${okCount} Vapi call(s).${failCount ? ` ${failCount} skipped/failed (${firstErr || ''}).` : ''}`
      )
      await loadAll()
    } catch (err) {
      setBannerMsg(err.response?.data?.detail || 'Failed to trigger Vapi call.')
    } finally {
      setBusyAction('')
    }
  }

  const handleSendEmail = async (payload, key) => {
    setBusyAction(key)
    setBannerMsg('')
    try {
      const { data } = await api.post('/matches/send-email', payload)
      const sentCount = data.filter((r) => r.status === 'SENT').length
      const failCount = data.length - sentCount
      const firstErr = data.find((r) => r.error)?.error
      const sentTo = data
        .filter((r) => r.status === 'SENT')
        .map((r) => r.email)
        .join(', ')
      setBannerMsg(
        `Sent ${sentCount} email(s)${sentTo ? ` (${sentTo})` : ''}.${
          failCount ? ` ${failCount} failed: ${firstErr || 'SMTP error'}` : ''
        }`
      )
    } catch (err) {
      setBannerMsg(err.response?.data?.detail || 'Failed to send match email.')
    } finally {
      setBusyAction('')
    }
  }

  const filteredMatches = selectedCompanyId
    ? matches.filter((m) => String(m.company_id) === String(selectedCompanyId))
    : matches

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {/* Analytics KPI Strip */}
        {summary && (
          <section className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
            {[
              { label: 'Total Students', value: summary.total_students },
              { label: 'Active Drives', value: summary.active_drives },
              { label: 'Matched Candidates', value: summary.total_matches },
              { label: 'Calls Placed', value: summary.calls_placed },
              { label: 'Answer Rate', value: `${summary.answer_rate}%` },
              { label: 'Interested Rate', value: `${summary.interested_rate}%` },
            ].map((kpi, idx) => (
              <div
                key={idx}
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <p className="text-xs font-medium text-slate-500">{kpi.label}</p>
                <p className="mt-1 text-2xl font-bold text-slate-900">{kpi.value}</p>
              </div>
            ))}
          </section>
        )}

        {bannerMsg && (
          <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm font-medium text-indigo-900">
            {bannerMsg}
          </div>
        )}

        {preflight && (
          <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 text-xs text-slate-800">
            <div className="flex items-center gap-2 font-semibold text-indigo-950">
              <AlertTriangle className="h-4 w-4 shrink-0 text-indigo-600" />
              <span>
                Vapi Voice AI Connected — Assistant: {preflight.assistant_name || 'University Placement Agent'} • Number: {preflight.phone_number || 'Configured'}
              </span>
            </div>
            {preflight.issues?.length > 0 && (
              <ul className="mt-1.5 list-inside list-disc space-y-1 text-slate-700">
                {preflight.issues.map((issue, idx) => (
                  <li key={idx}>{issue}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
          {[
            { id: 'drives', label: 'Company Drives & Matching', icon: Building2 },
            { id: 'matches', label: `Matched Candidates (${matches.length})`, icon: Sparkles },
            { id: 'calls', label: `Call Logs & Analytics (${callLogs.length})`, icon: PhoneCall },
            { id: 'students', label: `Students (${students.length})`, icon: Users },
          ].map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                onClick={() => setTab(item.id)}
                className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                  tab === item.id
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-white text-slate-700 hover:bg-slate-100'
                }`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            )
          })}
        </div>

        {/* TAB 1: Company Drives */}
        {tab === 'drives' && (
          <div className="grid gap-6 lg:grid-cols-5">
            {/* Create Drive Form */}
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
              <div className="mb-4 flex items-center gap-2">
                <Plus className="h-5 w-5 text-indigo-600" />
                <h2 className="text-lg font-semibold text-slate-900">New Company Drive</h2>
              </div>
              <form onSubmit={handleCreateDrive} className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <input
                    type="text"
                    required
                    placeholder="Company Name (e.g., Razorpay)"
                    value={driveForm.company_name}
                    onChange={(e) => setDriveForm({ ...driveForm, company_name: e.target.value })}
                    className="rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                  <input
                    type="text"
                    required
                    placeholder="Role (e.g., SDE Intern)"
                    value={driveForm.role}
                    onChange={(e) => setDriveForm({ ...driveForm, role: e.target.value })}
                    className="rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="10"
                    placeholder="Min CGPA"
                    value={driveForm.min_cgpa}
                    onChange={(e) => setDriveForm({ ...driveForm, min_cgpa: e.target.value })}
                    className="rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                  <input
                    type="text"
                    placeholder="CTC (e.g., 14 LPA)"
                    value={driveForm.ctc}
                    onChange={(e) => setDriveForm({ ...driveForm, ctc: e.target.value })}
                    className="rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                  <input
                    type="date"
                    value={driveForm.deadline}
                    onChange={(e) => setDriveForm({ ...driveForm, deadline: e.target.value })}
                    className="rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <input
                  type="text"
                  placeholder="Eligible Branches (e.g., CSE, IT, ECE)"
                  value={driveForm.eligible_branches}
                  onChange={(e) =>
                    setDriveForm({ ...driveForm, eligible_branches: e.target.value })
                  }
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
                <input
                  type="url"
                  placeholder="Registration URL (https://...)"
                  value={driveForm.registration_url}
                  onChange={(e) => setDriveForm({ ...driveForm, registration_url: e.target.value })}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
                <textarea
                  rows={4}
                  placeholder="Paste Job Description text (or upload a JD PDF below)..."
                  value={driveForm.jd_text}
                  onChange={(e) => setDriveForm({ ...driveForm, jd_text: e.target.value })}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                />
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-600">
                    Optional JD PDF
                  </label>
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    onChange={(e) => setJdFile(e.target.files?.[0] || null)}
                    className="w-full text-xs text-slate-600"
                  />
                </div>
                <button
                  type="submit"
                  disabled={busyAction === 'creating_drive'}
                  className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
                >
                  {busyAction === 'creating_drive' ? 'Creating & Embedding...' : 'Publish Company Drive'}
                </button>
              </form>
            </section>

            {/* Company Drives List */}
            <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold text-slate-900">Published Drives</h2>
                <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
                  Min Fit Threshold:
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={minThreshold}
                    onChange={(e) => setMinThreshold(e.target.value)}
                    className="w-16 rounded-lg border border-slate-300 px-2 py-1 text-xs"
                  />
                </label>
              </div>

              {companies.length === 0 ? (
                <p className="text-sm text-slate-500">No company drives published yet.</p>
              ) : (
                <div className="space-y-3">
                  {companies.map((c) => (
                    <div
                      key={c.id}
                      className="rounded-xl border border-slate-200 p-4 transition hover:border-indigo-200"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h3 className="font-bold text-slate-900">
                            {c.company_name} — {c.role}
                          </h3>
                          <p className="mt-0.5 text-xs text-slate-500">
                            Min CGPA: {c.min_cgpa} • Branches:{' '}
                            {c.eligible_branches?.length ? c.eligible_branches.join(', ') : 'All'} •
                            CTC: {c.ctc || 'N/A'} {c.deadline ? `• Due ${c.deadline}` : ''}
                          </p>
                        </div>
                        <button
                          onClick={() => handleRunMatch(c.id)}
                          disabled={busyAction === `match_${c.id}`}
                          className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50"
                        >
                          <Play className="h-3.5 w-3.5" />
                          {busyAction === `match_${c.id}` ? 'Matching...' : 'Run Hybrid Match'}
                        </button>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs text-slate-600">{c.jd_text}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        {/* TAB 2: Matches & Outbound Calling */}
        {tab === 'matches' && (
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <h2 className="text-lg font-semibold text-slate-900">Matched Candidates</h2>
                <select
                  value={selectedCompanyId}
                  onChange={(e) => setSelectedCompanyId(e.target.value)}
                  className="rounded-xl border border-slate-300 px-3 py-1.5 text-sm"
                >
                  <option value="">All Companies</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.company_name} — {c.role}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {filteredMatches.length > 0 && (
                  <button
                    onClick={() =>
                      handleSendEmail(
                        { match_ids: filteredMatches.map((m) => m.id) },
                        'batch_email'
                      )
                    }
                    disabled={busyAction === 'batch_email'}
                    className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
                  >
                    <Mail className="h-4 w-4" />
                    {busyAction === 'batch_email' ? 'Sending Emails...' : 'Send Email to All'}
                  </button>
                )}

                {selectedCompanyId && (
                  <button
                    onClick={() =>
                      handleTriggerCall(
                        { company_id: Number(selectedCompanyId), min_fit_score: Number(minThreshold) },
                        'batch_call'
                      )
                    }
                    disabled={busyAction === 'batch_call'}
                    className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
                  >
                    <PhoneOutgoing className="h-4 w-4" />
                    {busyAction === 'batch_call' ? 'Dialing via Vapi...' : 'Start Vapi Calls (Pending)'}
                  </button>
                )}
              </div>
            </div>

            {filteredMatches.length === 0 ? (
              <p className="text-sm text-slate-500">
                No matches found. Run Hybrid Matching on a company drive first.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="py-2.5 pr-4">Student</th>
                      <th className="py-2.5 pr-4">Company</th>
                      <th className="py-2.5 pr-4">Fit Score</th>
                      <th className="py-2.5 pr-4">AI Pitch & Missing Skills</th>
                      <th className="py-2.5 pr-4">Status</th>
                      <th className="py-2.5">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredMatches.map((m) => (
                      <tr key={m.id} className="align-top">
                        <td className="py-3 pr-4">
                          <p className="font-semibold text-slate-900">{m.student_name}</p>
                          <p className="text-xs text-slate-500">
                            {m.student_branch} • CGPA {m.student_cgpa} • {m.student_phone}
                          </p>
                        </td>
                        <td className="py-3 pr-4">
                          <p className="font-medium text-slate-800">{m.company_name}</p>
                          <p className="text-xs text-slate-500">{m.company_role}</p>
                        </td>
                        <td className="py-3 pr-4">
                          <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-bold text-indigo-800">
                            {m.fit_score}%
                          </span>
                        </td>
                        <td className="max-w-md py-3 pr-4 text-xs text-slate-700">
                          <p>{m.match_pitch}</p>
                          {m.missing_skills?.length > 0 && (
                            <p className="mt-1 text-amber-700">
                              Missing: {m.missing_skills.join(', ')}
                            </p>
                          )}
                        </td>
                        <td className="py-3 pr-4 text-xs font-semibold text-slate-700">
                          {m.match_status}
                        </td>
                        <td className="py-3">
                          <div className="flex flex-col gap-1.5">
                            <button
                              onClick={() =>
                                handleSendEmail({ match_id: m.id }, `email_${m.id}`)
                              }
                              disabled={busyAction === `email_${m.id}`}
                              className="inline-flex items-center justify-center gap-1 rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                            >
                              <Mail className="h-3.5 w-3.5" />
                              {busyAction === `email_${m.id}` ? 'Sending...' : 'Send Email'}
                            </button>
                            <button
                              onClick={() =>
                                handleTriggerCall({ match_id: m.id }, `call_${m.id}`)
                              }
                              disabled={busyAction === `call_${m.id}`}
                              className="inline-flex items-center justify-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                            >
                              <PhoneOutgoing className="h-3.5 w-3.5" />
                              Call Phone (Vapi)
                            </button>
                            <button
                              onClick={() => setSimulatorMatch(m)}
                              className="inline-flex items-center justify-center gap-1 rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
                            >
                              <PhoneCall className="h-3.5 w-3.5" />
                              Vapi Web Call
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {/* TAB 3: Call Logs & Per-Company Analytics */}
        {tab === 'calls' && (
          <div className="space-y-6">
            {summary?.company_metrics?.length > 0 && (
              <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="mb-4 flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-indigo-600" />
                  <h2 className="text-lg font-semibold text-slate-900">
                    Conversion Rate by Company
                  </h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                      <tr>
                        <th className="py-2 pr-4">Company</th>
                        <th className="py-2 pr-4">Matched</th>
                        <th className="py-2 pr-4">Calls Placed</th>
                        <th className="py-2 pr-4">Answered</th>
                        <th className="py-2 pr-4">Interested</th>
                        <th className="py-2">Conversion</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {summary.company_metrics.map((cm) => (
                        <tr key={cm.company_id}>
                          <td className="py-2.5 pr-4 font-medium">
                            {cm.company_name} ({cm.role})
                          </td>
                          <td className="py-2.5 pr-4">{cm.matched_count}</td>
                          <td className="py-2.5 pr-4">{cm.calls_placed}</td>
                          <td className="py-2.5 pr-4">{cm.answered_count}</td>
                          <td className="py-2.5 pr-4">{cm.interested_count}</td>
                          <td className="py-2.5 font-semibold text-indigo-700">
                            {cm.conversion_rate}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">Global Call Logs</h2>
              {callLogs.length === 0 ? (
                <p className="text-sm text-slate-500">No calls placed or simulated yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                      <tr>
                        <th className="py-2 pr-4">Student</th>
                        <th className="py-2 pr-4">Company</th>
                        <th className="py-2 pr-4">Status</th>
                        <th className="py-2 pr-4">Outcome</th>
                        <th className="py-2 pr-4">Duration</th>
                        <th className="py-2 pr-4">Link Sent</th>
                        <th className="py-2">Transcript</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {callLogs.map((log) => (
                        <tr key={log.id}>
                          <td className="py-2.5 pr-4 font-medium">{log.student_name}</td>
                          <td className="py-2.5 pr-4">
                            {log.company_name} ({log.company_role})
                          </td>
                          <td className="py-2.5 pr-4 text-xs">{log.call_status}</td>
                          <td className="py-2.5 pr-4">
                            <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700">
                              {log.student_outcome}
                            </span>
                          </td>
                          <td className="py-2.5 pr-4 text-xs">{log.duration_sec ?? 0}s</td>
                          <td className="py-2.5 pr-4 text-xs">{log.link_sent ? 'Yes' : 'No'}</td>
                          <td className="py-2.5">
                            <button
                              onClick={() => setSelectedLog(log)}
                              className="text-xs font-semibold text-indigo-600 hover:underline"
                            >
                              View Transcript
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        )}

        {/* TAB 4: Students Directory */}
        {tab === 'students' && (
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">Registered Students</h2>
            {students.length === 0 ? (
              <p className="text-sm text-slate-500">No students registered yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="py-2 pr-4">Name</th>
                      <th className="py-2 pr-4">Branch / CGPA</th>
                      <th className="py-2 pr-4">Phone</th>
                      <th className="py-2 pr-4">Call Consent</th>
                      <th className="py-2 pr-4">Resume</th>
                      <th className="py-2">Skills</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {students.map((s) => (
                      <tr key={s.id}>
                        <td className="py-2.5 pr-4">
                          <p className="font-semibold text-slate-900">{s.name}</p>
                          <p className="text-xs text-slate-500">{s.email}</p>
                        </td>
                        <td className="py-2.5 pr-4 text-xs">
                          {s.branch || 'N/A'} • {s.cgpa} CGPA
                        </td>
                        <td className="py-2.5 pr-4 text-xs">{s.phone}</td>
                        <td className="py-2.5 pr-4 text-xs">
                          {s.call_consent ? 'Opted In' : 'Opted Out'}
                        </td>
                        <td className="py-2.5 pr-4 text-xs">
                          {s.has_active_resume ? 'Active' : 'Missing'}
                        </td>
                        <td className="py-2.5 text-xs text-slate-600">
                          {s.parsed_skills?.slice(0, 6).join(', ') || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </main>

      {simulatorMatch && (
        <VapiWebCallModal
          match={simulatorMatch}
          onClose={() => setSimulatorMatch(null)}
          onCallFinished={() => loadAll()}
        />
      )}
      {selectedLog && (
        <TranscriptModal log={selectedLog} onClose={() => setSelectedLog(null)} />
      )}
    </div>
  )
}
