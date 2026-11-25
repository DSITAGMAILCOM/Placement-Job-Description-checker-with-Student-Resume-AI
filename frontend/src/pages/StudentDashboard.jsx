import { useCallback, useEffect, useState } from 'react'
import {
  Briefcase,
  CheckCircle2,
  ExternalLink,
  FileText,
  Mail,
  Phone,
  Sparkles,
  Upload,
  UserCheck,
} from 'lucide-react'
import { api } from '../api/client'
import Navbar from '../components/Navbar'
import TranscriptModal from '../components/TranscriptModal'
import VapiWebCallModal from '../components/VapiWebCallModal'
import { useAuth } from '../context/AuthContext'

export default function StudentDashboard() {
  const { user, refreshUser } = useAuth()
  const [profile, setProfile] = useState({
    phone: '',
    branch: 'CSE',
    cgpa: '8.00',
    graduation_year: '2027',
    call_consent: true,
  })
  const [savingProfile, setSavingProfile] = useState(false)
  const [profileMsg, setProfileMsg] = useState('')

  const [resume, setResume] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState('')

  const [matches, setMatches] = useState([])
  const [callLogs, setCallLogs] = useState([])
  const [simulatorMatch, setSimulatorMatch] = useState(null)
  const [selectedLog, setSelectedLog] = useState(null)
  const [emailStatusMsg, setEmailStatusMsg] = useState('')
  const [sendingEmailId, setSendingEmailId] = useState(null)

  useEffect(() => {
    if (user?.student) {
      setProfile({
        phone: user.student.phone || '',
        branch: user.student.branch || 'CSE',
        cgpa: String(user.student.cgpa ?? '0.00'),
        graduation_year: String(user.student.graduation_year ?? '2027'),
        call_consent: Boolean(user.student.call_consent),
      })
    }
  }, [user])

  const loadData = useCallback(async () => {
    try {
      const [resResume, resMatches, resLogs] = await Promise.all([
        api.get('/resumes/active'),
        api.get('/matches'),
        api.get('/calls/logs'),
      ])
      setResume(resResume.data)
      setMatches(resMatches.data || [])
      setCallLogs(resLogs.data || [])
    } catch {
      // ignore initial empty errors
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleSaveProfile = async (e) => {
    e.preventDefault()
    setSavingProfile(true)
    setProfileMsg('')
    try {
      await api.put('/students/profile', {
        phone: profile.phone,
        branch: profile.branch,
        cgpa: Number(profile.cgpa),
        graduation_year: Number(profile.graduation_year),
        call_consent: profile.call_consent,
      })
      await refreshUser()
      setProfileMsg('Profile saved!')
    } catch (err) {
      setProfileMsg(err.response?.data?.detail || 'Failed to update profile.')
    } finally {
      setSavingProfile(false)
    }
  }

  const handleResumeUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg('')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const { data } = await api.post('/resumes/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResume(data)
      setUploadMsg('Resume parsed and embedded successfully!')
    } catch (err) {
      setUploadMsg(err.response?.data?.detail || 'Resume upload failed.')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleSendMatchEmail = async (matchId) => {
    setSendingEmailId(matchId)
    setEmailStatusMsg('')
    try {
      const { data } = await api.post('/matches/send-email', { match_id: matchId })
      const res = data?.[0]
      if (res?.status === 'SENT') {
        setEmailStatusMsg(`Sent full match & JD details to ${res.email}`)
      } else {
        setEmailStatusMsg(res?.error || 'Could not send email.')
      }
    } catch (err) {
      setEmailStatusMsg(err.response?.data?.detail || 'Failed to send email.')
    } finally {
      setSendingEmailId(null)
    }
  }

  const parsed = resume?.parsed_skills || {}
  const skills = Array.isArray(parsed) ? parsed : parsed.skills || []
  const projects = !Array.isArray(parsed) ? parsed.projects || [] : []

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {/* Top Row: Profile + Resume */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Student Profile */}
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center gap-2.5">
              <UserCheck className="h-5 w-5 text-indigo-600" />
              <h2 className="text-lg font-semibold text-slate-900">Student Profile & Opt-In</h2>
            </div>

            <form onSubmit={handleSaveProfile} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-600">
                    Phone (E.164 format)
                  </label>
                  <input
                    type="text"
                    required
                    value={profile.phone}
                    onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
                    placeholder="+919876543210"
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-600">Branch</label>
                  <input
                    type="text"
                    required
                    value={profile.branch}
                    onChange={(e) =>
                      setProfile({ ...profile, branch: e.target.value.toUpperCase() })
                    }
                    placeholder="CSE"
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-600">CGPA</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="10"
                    required
                    value={profile.cgpa}
                    onChange={(e) => setProfile({ ...profile, cgpa: e.target.value })}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-600">
                    Graduation Year
                  </label>
                  <input
                    type="number"
                    min="2020"
                    max="2035"
                    required
                    value={profile.graduation_year}
                    onChange={(e) => setProfile({ ...profile, graduation_year: e.target.value })}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <label className="flex items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={profile.call_consent}
                  onChange={(e) => setProfile({ ...profile, call_consent: e.target.checked })}
                  className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                />
                <span>Opt in to automated AI placement calls & registration alerts</span>
              </label>

              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-emerald-700">{profileMsg}</span>
                <button
                  type="submit"
                  disabled={savingProfile}
                  className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50"
                >
                  {savingProfile ? 'Saving...' : 'Save Profile'}
                </button>
              </div>
            </form>
          </section>

          {/* Active PDF Resume */}
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <FileText className="h-5 w-5 text-indigo-600" />
                <h2 className="text-lg font-semibold text-slate-900">Active Resume (PDF)</h2>
              </div>
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-slate-800">
                <Upload className="h-4 w-4" />
                <span>{uploading ? 'Parsing PDF...' : 'Upload PDF Resume'}</span>
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  disabled={uploading}
                  onChange={handleResumeUpload}
                  className="hidden"
                />
              </label>
            </div>

            {uploadMsg && (
              <div className="mb-3 rounded-xl bg-indigo-50 px-3.5 py-2 text-xs font-medium text-indigo-800">
                {uploadMsg}
              </div>
            )}

            {resume ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-3">
                  <div>
                    <p className="text-sm font-semibold text-emerald-950">{resume.file_name}</p>
                    <p className="text-xs text-emerald-700">
                      Uploaded {new Date(resume.created_at).toLocaleString()}
                    </p>
                  </div>
                  <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                </div>

                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Extracted Skills ({skills.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {skills.length > 0 ? (
                      skills.map((skill, idx) => (
                        <span
                          key={idx}
                          className="rounded-lg bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700"
                        >
                          {skill}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-slate-500">No skills extracted.</span>
                    )}
                  </div>
                </div>

                {projects.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Highlighted Projects
                    </p>
                    <ul className="list-inside list-disc space-y-1 text-xs text-slate-700">
                      {projects.slice(0, 4).map((p, idx) => (
                        <li key={idx}>{p}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 py-10 text-center">
                <FileText className="mb-2 h-8 w-8 text-slate-300" />
                <p className="text-sm font-medium text-slate-700">No active resume uploaded yet</p>
                <p className="mt-1 text-xs text-slate-500">
                  Upload your PDF resume so PlaceCall AI can match you with company drives.
                </p>
              </div>
            )}
          </section>
        </div>

        {/* Matched Drives */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <Sparkles className="h-5 w-5 text-indigo-600" />
              <h2 className="text-lg font-semibold text-slate-900">Your Matched Company Drives</h2>
            </div>
            {emailStatusMsg && (
              <span className="text-xs font-medium text-indigo-700">{emailStatusMsg}</span>
            )}
          </div>

          {matches.length === 0 ? (
            <p className="text-sm text-slate-500">
              No matched company drives yet. Once your resume is uploaded and an Admin runs matching,
              eligible companies will appear here.
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {matches.map((m) => (
                <div
                  key={m.id}
                  className="flex flex-col justify-between rounded-2xl border border-slate-200 p-5 transition hover:border-indigo-300"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="text-base font-bold text-slate-900">{m.company_name}</h3>
                        <p className="text-sm font-medium text-slate-600">
                          {m.company_role} {m.company_ctc ? `• ${m.company_ctc}` : ''}
                        </p>
                      </div>
                      <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-bold text-indigo-800">
                        {m.fit_score}% Fit
                      </span>
                    </div>

                    {m.match_pitch && (
                      <p className="mt-3 rounded-xl bg-slate-50 p-3 text-xs leading-relaxed text-slate-700">
                        {m.match_pitch}
                      </p>
                    )}

                    {m.missing_skills?.length > 0 && (
                      <div className="mt-3 flex flex-wrap items-center gap-1.5">
                        <span className="text-[11px] font-medium text-amber-700">
                          Skills to brush up:
                        </span>
                        {m.missing_skills.map((sk, idx) => (
                          <span
                            key={idx}
                            className="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800"
                          >
                            {sk}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
                    <span className="text-xs font-medium text-slate-500">
                      Status: <strong className="text-slate-800">{m.match_status}</strong>
                      {m.company_deadline ? ` • Due ${m.company_deadline}` : ''}
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleSendMatchEmail(m.id)}
                        disabled={sendingEmailId === m.id}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50"
                      >
                        <Mail className="h-3.5 w-3.5" />
                        {sendingEmailId === m.id ? 'Sending...' : 'Email Details'}
                      </button>
                      <button
                        onClick={() => setSimulatorMatch(m)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-700"
                      >
                        <Phone className="h-3.5 w-3.5" />
                        Talk to AI (Vapi)
                      </button>
                      {m.registration_url && (
                        <a
                          href={m.registration_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
                        >
                          Register <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Call History */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2.5">
            <Briefcase className="h-5 w-5 text-indigo-600" />
            <h2 className="text-lg font-semibold text-slate-900">Your Call History</h2>
          </div>
          {callLogs.length === 0 ? (
            <p className="text-sm text-slate-500">No AI placement calls logged yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="py-2.5 pr-4">Company</th>
                    <th className="py-2.5 pr-4">Status</th>
                    <th className="py-2.5 pr-4">Outcome</th>
                    <th className="py-2.5 pr-4">Duration</th>
                    <th className="py-2.5 pr-4">Link Sent</th>
                    <th className="py-2.5">Transcript</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {callLogs.map((log) => (
                    <tr key={log.id}>
                      <td className="py-3 pr-4 font-medium text-slate-900">
                        {log.company_name} ({log.company_role})
                      </td>
                      <td className="py-3 pr-4 text-xs">{log.call_status}</td>
                      <td className="py-3 pr-4">
                        <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700">
                          {log.student_outcome}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-xs text-slate-600">
                        {log.duration_sec ?? 0}s
                      </td>
                      <td className="py-3 pr-4 text-xs">{log.link_sent ? 'Yes' : 'No'}</td>
                      <td className="py-3">
                        <button
                          onClick={() => setSelectedLog(log)}
                          className="text-xs font-semibold text-indigo-600 hover:underline"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>

      {simulatorMatch && (
        <VapiWebCallModal
          match={simulatorMatch}
          onClose={() => setSimulatorMatch(null)}
          onCallFinished={() => loadData()}
        />
      )}
      {selectedLog && (
        <TranscriptModal log={selectedLog} onClose={() => setSelectedLog(null)} />
      )}
    </div>
  )
}
