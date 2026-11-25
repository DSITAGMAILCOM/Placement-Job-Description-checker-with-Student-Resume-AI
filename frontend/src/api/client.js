import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_BASE_URL,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('placecall_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export function getSimulatorWsUrl(matchId) {
  const token = localStorage.getItem('placecall_token') || ''
  const envWs = import.meta.env.VITE_WS_BASE_URL
  if (envWs) {
    return `${envWs}/api/v1/simulator/voice/${matchId}?token=${encodeURIComponent(token)}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v1/simulator/voice/${matchId}?token=${encodeURIComponent(token)}`
}
