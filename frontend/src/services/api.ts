import type { AthenaResult, AuditEvent, ChatResult, Comparison, GuardResult, Preset } from '../types/api'

// In Vite, requests stay same-origin. The configured public backend URL is the
// proxy target. A separately hosted production build may use the absolute URL.
const configured = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const base = import.meta.env.DEV || !configured || ['localhost', '127.0.0.1'].includes(location.hostname) ? '' : configured
export class ApiError extends Error { constructor(public code: string, public status?: number) { super(code); this.name = 'ApiError' } }
export async function request<T>(path: string, body?: unknown, timeout = 190000): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(base + path, { method: body === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json' }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}), signal: controller.signal })
    const data = await response.json().catch(() => null)
    if (!response.ok) throw new ApiError(response.status === 429 ? 'rate_limited' : response.status === 422 ? 'invalid_request' : response.status === 413 ? 'request_too_large' : typeof data?.error === 'string' && /^[a-z_]+$/.test(data.error) ? data.error : 'request_failed', response.status)
    if (!data || typeof data !== 'object') throw new ApiError('invalid_response')
    return data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(error instanceof DOMException && error.name === 'AbortError' ? 'timeout' : 'backend_unavailable')
  } finally { window.clearTimeout(timer) }
}
const payload = (text: string, session_id?: string) => ({ text, ...(session_id ? { session_id } : {}) })
export const checkAthena = (text: string, sid?: string) => request<AthenaResult>('/api/v1/athena/check', payload(text, sid))
export const compareGuard = (text: string, sid?: string) => request<Comparison>('/api/v1/demo/compare', payload(text, sid))
export const guardOnly = (text: string) => request<{ guard: GuardResult }>('/api/guard-only', { text })
export const chatAthena = (text: string, sid?: string) => request<ChatResult>('/api/v1/athena/chat', payload(text, sid))
export const resetSession = (sid: string) => request<{ ok: boolean }>('/api/v1/athena/reset', { session_id: sid })
export const healthCheck = () => request<{ status: string }>('/health', undefined, 5000)
export const guardHealth = () => request<{ guard: { ok: boolean }; missing_config: string[] }>('/api/health', undefined, 25000)
export const getPresets = () => request<{ presets: Preset[] }>('/api/presets', undefined, 6000)
export const getLogs = () => request<{ events: AuditEvent[]; counts?: { total: number; blocked: number; allowed: number }; owner?: string; email_enabled?: boolean }>('/api/logs', undefined, 6000)
export const setAlertEmail = (email: string) => request<{ ok: boolean; owner: string }>('/api/alert-email', { email })
export const emailLog = (email?: string) => request<{ ok: boolean; sent_to?: string | null; events?: number; note?: string | null; error?: string }>('/api/email-log', { email: email ?? '' }, 20000)
export async function readiness() {
  try { return await request<{ ready: boolean; missing_config: string[] }>('/ready', undefined, 5000) }
  catch (e) { if (e instanceof ApiError && e.status === 503) return { ready: false, missing_config: [] }; throw e }
}
export const errorMessage = (error: unknown) => {
  const code = error instanceof ApiError ? error.code : 'request_failed'
  const messages: Record<string, string> = { backend_unavailable: 'Athena API is offline. Start the backend and try again.', timeout: 'The request timed out. Its outcome is unknown; refresh or reset the session before retrying.', rate_limited: 'The service is rate limited. Wait before running another analysis.', invalid_request: 'Check your input. Prompts must contain 1–3,999 characters.', request_too_large: 'This request is too large. Shorten the prompt.', session_capacity: 'Session capacity reached. Wait for an inactive session to expire.', invalid_response: 'The backend returned an unexpected response. Please retry.', request_failed: 'The request could not be completed. Check the backend and try again.' }
  return messages[code] || 'The request could not be completed. Please retry.'
}
