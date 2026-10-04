import { useEffect, useState } from 'react'
import { BellRing, ChevronRight, Download, Mail, Radio, RotateCw, Save, Search, Trash2 } from 'lucide-react'
import type { ConsoleState } from '../hooks/useConsole'
import type { SecurityEvent } from '../types/api'
import { riskTone, time } from '../utils/format'
import { Badge, Empty, PageHeading } from '../components/ui'
import { emailLog, getLogs, setAlertEmail } from '../services/api'

function AlertSettings() {
  const [email, setEmail] = useState(''), [enabled, setEnabled] = useState(false)
  const [counts, setCounts] = useState<{ total: number; blocked: number } | null>(null)
  const [status, setStatus] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { void (async () => { try { const r = await getLogs(); if (r.owner) setEmail(r.owner); setEnabled(!!r.email_enabled); if (r.counts) setCounts(r.counts) } catch { /* backend offline */ } })() }, [])
  async function save() { setBusy(true); try { const r = await setAlertEmail(email); setStatus(r.owner ? `Alerts will be sent to ${r.owner}` : 'Owner cleared') } catch { setStatus('Could not save') } finally { setBusy(false) } }
  async function send() { setBusy(true); setStatus('Sending…'); try { const r = await emailLog(email); setStatus(r.ok ? `Log emailed to ${r.sent_to}` : (r.note || r.error || 'Email not sent')) } catch { setStatus('Could not send') } finally { setBusy(false) } }
  return <section className="panel alert-settings">
    <div className="alert-settings-head">
      <div className="alert-settings-title"><BellRing size={16} /><div><h3>Alerts &amp; email digest</h3><p className="muted small">The owner is emailed the moment an attack is blocked. {enabled ? <span className="tone-green">SMTP connected.</span> : <span className="muted">Add SMTP in .env to actually send.</span>}</p></div></div>
      {counts && <div className="alert-counts"><span><strong>{counts.total}</strong> events</span><span className="tone-red"><strong>{counts.blocked}</strong> blocked</span></div>}
    </div>
    <div className="alert-settings-row">
      <input type="email" aria-label="Owner email" placeholder="owner@example.com" value={email} onChange={e => setEmail(e.target.value)} />
      <button className="button secondary" disabled={busy} onClick={save}><Save size={15} />Save owner</button>
      <button className="button secondary" disabled={busy} onClick={send}><Mail size={15} />Email me the log</button>
      {status && <span className="mono tiny muted">{status}</span>}
    </div>
  </section>
}

export default function Events({ state: s, inspectEvent }: { state: ConsoleState; inspectEvent: (e: SecurityEvent) => void }) {
  const [filter, setFilter] = useState('ALL'), [engine, setEngine] = useState('All engines'), [query, setQuery] = useState(''), [source, setSource] = useState<'browser' | 'server'>('browser')
  const all = source === 'browser' ? s.events : s.serverEvents
  const events = all.filter(e => (filter === 'ALL' || e.decision === filter) && (engine === 'All engines' || e.engine === engine) && `${e.engine} ${e.detail} ${e.categories.join(' ')} ${e.id}`.toLowerCase().includes(query.toLowerCase()))
  function exportEvents() { const content = events.map(({ result: _result, ...metadata }) => metadata); const url = URL.createObjectURL(new Blob([JSON.stringify(content, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = 'athena-events.json'; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000) }
  return <><PageHeading eyebrow="EVENT STREAM" title="Every decision leaves a signal." description="A live, readable trail of security decisions. Evidence, without the noise." action={<button className="button secondary" disabled={!events.length} onClick={exportEvents}><Download size={15}/>Export metadata</button>}/><AlertSettings/><section className="panel event-console"><div className="terminal-toolbar"><span><Radio size={15}/><strong>athena</strong><span className="muted">/ security-events</span></span><div className="source-switch"><button className={source === 'browser' ? 'selected' : ''} onClick={() => setSource('browser')}>Browser session</button><button className={source === 'server' ? 'selected' : ''} onClick={() => setSource('server')}>Backend audit</button></div></div><div className="events-controls"><div className="decision-filters">{['ALL', 'BLOCK', 'REVIEW', 'WARN', 'ALLOW', 'SAFE_ANALYSIS'].map(f => <button key={f} onClick={() => setFilter(f)} className={filter === f ? 'selected' : ''}>{f === 'SAFE_ANALYSIS' ? 'SAFE ANALYSIS' : f}</button>)}</div><div className="events-controls-right"><select aria-label="Filter by engine" value={engine} onChange={e => setEngine(e.target.value)}>{['All engines', ...new Set(all.map(e => e.engine))].map(e => <option key={e}>{e}</option>)}</select><button className="icon-button" title={source === 'browser' ? 'Clear browser events' : 'Refresh backend audit'} aria-label={source === 'browser' ? 'Clear browser events' : 'Refresh backend audit'} onClick={() => source === 'browser' ? s.clearEvents() : void s.refreshLogs()}>{source === 'browser' ? <Trash2 size={15}/> : <RotateCw size={15}/>}</button></div></div><div className="event-search"><Search size={14}/><input aria-label="Search events" placeholder="Filter by engine, category, reason or request ID…" value={query} onChange={e => setQuery(e.target.value)}/><span className="mono">{events.length} EVENTS</span></div><div className="event-table-wrap"><table className="event-table"><thead><tr><th>TIME</th><th>DECISION</th><th>RISK</th><th>ENGINE / CATEGORY</th><th>DETAIL</th><th/></tr></thead><tbody>{events.map(e => <tr key={e.id}><td className="mono">{time(e.time)}</td><td><Badge decision={e.decision} compact/></td><td><span className={`mono ${e.risk !== null ? `tone-${riskTone(e.risk)}` : 'muted'}`}>{e.risk !== null ? String(e.risk).padStart(2, '0') : '—'}</span></td><td><strong>{e.engine}</strong><span className="table-category">{e.categories.length ? e.categories.join(' · ').replaceAll('_', ' ') : 'clear'}</span></td><td><p>{e.detail}</p><span className="mono tiny muted">{e.id}{e.latency != null && ` · ${e.latency} ms`}</span></td><td>{e.result && <button className="icon-button" aria-label="Inspect event" onClick={() => inspectEvent(e)}><ChevronRight size={15}/></button>}</td></tr>)}</tbody></table>{!events.length && <Empty title={source === 'server' && s.logsError ? 'Backend audit unavailable' : query || filter !== 'ALL' || engine !== 'All engines' ? 'No matching signals.' : 'Listening for your first analysis.'} text={source === 'server' && s.logsError ? 'Start the backend to load its metadata-only audit records.' : 'Run an analysis or change the filters. Only actual screening responses appear here.'} icon={<Radio size={25}/>}/>}</div><div className="console-footer"><span className="mono"><span className="tiny-dot"/>{source === 'browser' ? 'IN-MEMORY · CURRENT BROWSER SESSION' : 'METADATA ONLY · REFRESHES EVERY 10s'}</span><span>Payloads are excluded from exported logs.</span></div></section></>
}
