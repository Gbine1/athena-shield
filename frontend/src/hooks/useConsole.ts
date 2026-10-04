import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../services/api'
import type { AthenaResult, ChatResult, Comparison, Decision, GuardResult, HealthState, SecurityEvent } from '../types/api'
import { newSession, primaryEngine } from '../utils/format'

export function useConsole() {
  const [health, setHealth] = useState<HealthState>({ backend: 'checking', guard: 'checking', ready: false, missing: [] })
  const [events, setEvents] = useState<SecurityEvent[]>([])
  const [serverEvents, setServerEvents] = useState<SecurityEvent[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ athena?: AthenaResult; guard?: GuardResult; input: string } | null>(null)
  const [chat, setChat] = useState<ChatResult | null>(null)
  const [sessionId, setSessionId] = useState(newSession)
  const [turns, setTurns] = useState<Comparison[]>([])
  const [backendEncoding, setBackendEncoding] = useState<string | null>(null)
  const locked = useRef(false)
  const mounted = useRef(true)
  const [logsError, setLogsError] = useState(false)

  const refreshLogs = useCallback(async () => {
    try {
      const r = await api.getLogs()
      if (!mounted.current) return
      setLogsError(false)
      setServerEvents(r.events.filter(e => e.audit).map(e => ({ id: e.audit!.request_id, time: Date.parse(e.ts.replace(' UTC', 'Z').replace(' ', 'T')), decision: e.audit!.decision, risk: e.audit!.risk_score, engine: e.kind === 'response' ? 'Response shield' : 'Athena', categories: e.audit!.categories, detail: `${e.kind === 'response' ? 'Output' : 'Prompt'} screening · metadata-only audit record`, latency: e.audit!.athena_latency_ms, origin: 'server' })))
    } catch { if (mounted.current) setLogsError(true) }
  }, [])

  useEffect(() => {
    mounted.current = true
    let checking = false
    let guardChecking = false
    async function poll() {
      if (checking) return
      checking = true
      const [h, r] = await Promise.allSettled([api.healthCheck(), api.readiness()])
      if (mounted.current) setHealth(old => ({ ...old, backend: h.status === 'fulfilled' && h.value.status === 'ok' ? 'online' : 'offline', ready: r.status === 'fulfilled' && r.value.ready, checkedAt: Date.now() }))
      checking = false
    }
    async function pollGuard() {
      if (guardChecking) return
      guardChecking = true
      try {
        const r = await api.guardHealth()
        if (mounted.current) setHealth(old => ({ ...old, missing: r.missing_config, guard: r.missing_config.some(x => x === 'GUARD_URL' || x === 'GUARD_TOKEN') ? 'unconfigured' : r.guard.ok ? 'online' : 'offline' }))
      } catch { if (mounted.current) setHealth(old => ({ ...old, guard: 'offline' })) }
      guardChecking = false
    }
    void poll(); void pollGuard(); void refreshLogs()
    void api.getPresets().then(r => { const preset = r.presets.find(p => p.id === 'encoding'); if (mounted.current && preset) setBackendEncoding(preset.turns[0]) }).catch(() => {})
    const timer = window.setInterval(() => { void poll(); void refreshLogs() }, 10000)
    const guardTimer = window.setInterval(pollGuard, 30000)
    return () => { mounted.current = false; window.clearInterval(timer); window.clearInterval(guardTimer) }
  }, [refreshLogs])

  function record(r: AthenaResult) {
    const significant = r.findings.find(f => ['high', 'critical', 'medium'].includes(f.severity)) || r.findings[0]
    const event: SecurityEvent = { id: r.request_id, time: Date.now(), decision: r.decision, risk: r.risk_score, engine: primaryEngine(r), categories: r.findings.map(f => f.category), detail: significant?.description || 'All required screening checks cleared.', latency: r.latency_ms, result: r, origin: 'browser' }
    setEvents(old => [event, ...old.filter(x => x.id !== event.id)].slice(0, 200))
  }
  async function perform(name: string, fn: () => Promise<void>) {
    if (locked.current) return
    locked.current = true; setBusy(name); setError('')
    try { await fn(); void refreshLogs() }
    catch (e) { setError(api.errorMessage(e)) }
    finally { locked.current = false; setBusy(null) }
  }
  const analyze = (text: string, mode: 'compare' | 'guard' | 'chat' = 'compare') => perform(mode, async () => {
    setResult(null); setChat(null)
    if (mode === 'guard') {
      const r = await api.guardOnly(text)
      setResult({ guard: r.guard, input: text })
      // Error/partial verdicts do not become successful security events.
      if (r.guard.ok && r.guard.status === 'complete') setEvents(old => [{ id: r.guard.request_id || crypto.randomUUID(), time: Date.now(), decision: (r.guard.allowed ? 'ALLOW' : 'BLOCK') as Decision, risk: null, engine: 'SecureAI Guard', categories: r.guard.flags || [], detail: 'Raw prompt screened by SecureAI Guard only.', latency: r.guard.latency_ms ?? undefined, origin: 'browser' as const }, ...old].slice(0, 200))
    } else if (mode === 'chat') {
      const r = await api.chatAthena(text)
      setChat(r); setResult({ athena: r.prompt_check, guard: r.prompt_check.guard_result, input: text }); record(r.prompt_check)
      if (r.response_check) setEvents(old => [{ id: r.response_check!.request_id, time: Date.now(), decision: r.response_check!.decision, risk: r.response_check!.risk_score, engine: 'Response shield', categories: r.response_check!.categories, detail: r.response_check!.blocked ? 'Model output withheld after response screening.' : 'Model output passed response screening.', origin: 'browser' as const }, ...old].slice(0, 200))
    } else {
      const r = await api.compareGuard(text)
      setResult({ athena: r.athena, guard: r.guard_only, input: text }); record(r.athena)
    }
  })
  const sendTurn = (text: string) => perform('session', async () => {
    const r = await api.compareGuard(text, sessionId)
    setTurns(old => [...old, r].slice(-10)); record(r.athena)
  })
  const reset = () => perform('reset', async () => {
    await api.resetSession(sessionId); setTurns([]); setSessionId(newSession())
  })
  const clearResult = () => { setResult(null); setChat(null); setError('') }
  return { health, events, serverEvents, busy, error, setError, result, chat, sessionId, turns, backendEncoding, logsError, analyze, sendTurn, reset, clearResult, clearEvents: () => setEvents([]), refreshLogs }
}
export type ConsoleState = ReturnType<typeof useConsole>
