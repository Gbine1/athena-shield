import { useEffect, useRef } from 'react'
import { ArrowUpRight, Braces, CircleHelp, Eraser, Play, Shield, Sparkles } from 'lucide-react'
import type { ConsoleState } from '../hooks/useConsole'
import { encoded, obfuscations, research } from '../data/demoScenarios'
import { AnalysisEmpty, ChatResponse, ComparisonPanel, ResultDetails } from '../components/Results'
import { Eyebrow, PageHeading, Processing } from '../components/ui'

export default function Analyzer({ state: s, text, setText }: { state: ConsoleState; text: string; setText: (s: string) => void }) {
  const editor = useRef<HTMLTextAreaElement>(null)
  const count = [...text].length
  const valid = text.trim().length > 0 && count <= 3999
  const current = s.result?.input === text ? s.result : null
  useEffect(() => { editor.current?.focus({ preventScroll: true }) }, [])
  return <>
    <PageHeading eyebrow="LIVE ANALYZER" title="Look beyond the prompt." description="Compare the original Guard verdict with Athena’s deeper inspection." action={<span className="subtle-pill"><span className="tiny-dot"/>Live API comparison</span>}/>
    <section className="panel prompt-panel"><div className="editor-toolbar"><span><Braces size={16}/>PROMPT INPUT</span><span className="mono tiny">UTF-8<span className="toolbar-divider"/>PLAIN TEXT</span></div><textarea ref={editor} aria-label="Enter a prompt to inspect" placeholder="Enter a prompt to inspect…" value={text} onChange={e => setText(e.target.value)} disabled={!!s.busy} onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && valid && !s.busy) { e.preventDefault(); void s.analyze(text) } }} spellCheck={false}/><div className="editor-meta"><span><CircleHelp size={12}/>Your original input is preserved.</span><span className={`mono ${count > 3999 ? 'tone-red' : ''}`}>{count.toLocaleString()} / 3,999</span></div><div className="editor-actions"><div><button className="button primary" disabled={!valid || !!s.busy} onClick={() => void s.analyze(text)}><Sparkles size={15}/>Analyze with Athena<span className="shortcut">⌘ ↵</span></button><button className="button secondary" disabled={!valid || !!s.busy} onClick={() => void s.analyze(text, 'guard')}><Shield size={14}/>Guard only</button><button className="button quiet" disabled={!text || !!s.busy} onClick={() => { setText(''); s.clearResult(); editor.current?.focus() }}><Eraser size={14}/>Clear</button></div><button className="button quiet" disabled={!valid || !!s.busy} onClick={() => void s.analyze(text, 'chat')} title="Calls the LLM only after Athena and Guard permit the prompt; screens the response before delivery."><Play size={13}/>Screened chat<ArrowUpRight size={13}/></button></div></section>
    <div className="quick-prompts"><Eyebrow>TRY A SCENARIO</Eyebrow>{[{ label: 'Obfuscated instruction', text: obfuscations[0].text }, { label: 'Encoded payload', text: s.backendEncoding || encoded }, { label: 'Research quotation', text: research }, { label: 'Benign control', text: 'What is the capital of Ghana?' }].map(p => <button key={p.label} disabled={!!s.busy} onClick={() => { setText(p.text); s.clearResult() }}>{p.label}<ArrowUpRight size={12}/></button>)}</div>
    {s.busy && s.busy !== 'session' && s.busy !== 'reset' ? <Processing busy={s.busy}/> : <><div className="section-overline"><span>THE DIFFERENCE, SIDE BY SIDE</span><span>Original input → additional inspection</span></div><ComparisonPanel athena={current?.athena} guard={current?.guard}/>{current?.athena ? <ResultDetails key={current.athena.request_id} result={current.athena}/> : !current && <AnalysisEmpty/>}{s.chat && current?.athena && <ChatResponse result={s.chat}/>}</>}
  </>
}
