import type { AthenaResult, Decision, GuardResult } from '../types/api'
export const time = (value: number) => new Date(value).toLocaleTimeString('en-GB', { hour12: false })
export const decisionLabel = (decision: Decision | 'ERROR' | 'IDLE') => ({ ALLOW: 'Allowed', BLOCK: 'Blocked', WARN: 'Warning', REVIEW: 'Review', SAFE_ANALYSIS: 'Safe analysis', ERROR: 'Unavailable', IDLE: 'Awaiting input' })[decision]
export const guardDecision = (g: GuardResult): Decision | 'ERROR' => !g.ok || g.status !== 'complete' ? 'ERROR' : g.allowed ? 'ALLOW' : 'BLOCK'
export const riskLevel = (n: number) => n >= 85 ? 'Critical' : n >= 65 ? 'High' : n >= 30 ? 'Moderate' : 'Low'
export const riskTone = (n: number) => n >= 65 ? 'red' : n >= 30 ? 'amber' : 'green'
export const engineNames: Record<string, string> = { encoding_shield: 'Encoding', normalization_shield: 'Normalization', context_adjudicator: 'Context', session_shield: 'Session', local_detector: 'Local detector', guard: 'SecureAI Guard', policy: 'Policy', response_shield: 'Response shield' }
export const primaryEngine = (r: AthenaResult) => {
  const sources = r.findings.map(f => f.source)
  for (const name of ['session_shield', 'context_adjudicator', 'normalization_shield', 'encoding_shield', 'policy', 'guard', 'local_detector']) if (sources.includes(name)) return engineNames[name]
  return 'SecureAI Guard'
}
export const newSession = () => 'ui-' + crypto.randomUUID()
export const safeErrorCode = (code?: string | null) => code && /^[a-z_0-9]+$/.test(code) ? code.replaceAll('_', ' ') : 'Service unavailable'
