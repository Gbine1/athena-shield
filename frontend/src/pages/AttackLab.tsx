import { useState } from 'react'
import { ArrowRight, Braces, FileSearch, Fingerprint, FlaskConical, Layers3, Play, ScanLine, ShieldCheck } from 'lucide-react'
import type { ConsoleState } from '../hooks/useConsole'
import { encoded, obfuscations, scenarios } from '../data/demoScenarios'
import { ComparisonPanel, ResultDetails } from '../components/Results'
import { Eyebrow, LearningNote, PageHeading, Processing } from '../components/ui'
import { SessionWorkbench } from './Session'

const icons = [ScanLine, FileSearch, Layers3, Fingerprint]
export default function AttackLab({ state: s, initial = 'normalization', openAnalyzer }: { state: ConsoleState; initial?: string; openAnalyzer: (text: string) => void }) {
  const [selected, setSelected] = useState(initial)
  const [variant, setVariant] = useState(0)
  const scenario = scenarios.find(x => x.id === selected) || scenarios[0]
  const text = selected === 'normalization' ? obfuscations[variant].text : selected === 'encoding' ? s.backendEncoding || encoded : scenario.text
  const current = s.result?.input === text ? s.result : null
  return <><PageHeading eyebrow="ATTACK LAB" title="Make the invisible, visible." description="Explore four findings with synthetic scenarios and real backend decisions." action={<span className="subtle-pill"><FlaskConical size={13}/>Controlled environment</span>}/><div className="scenario-grid">{scenarios.map((item, i) => { const Icon = icons[i]; return <button className={`scenario-card ${selected === item.id ? 'selected' : ''}`} key={item.id} onClick={() => setSelected(item.id)} disabled={!!s.busy}><div className="scenario-card-top"><span className="scenario-icon"><Icon size={21}/></span><span className="mono">/{item.number}</span></div><h2>{item.title}</h2><p>{item.short}</p><div><span className="tiny-dot"/>{item.engine}<ArrowRight size={13}/></div></button> })}</div>
    {selected === 'session' ? <SessionWorkbench state={s}/> : <><section className="panel lab-workbench"><div className="lab-workbench-heading"><div><Eyebrow>{scenario.engine.toUpperCase()}</Eyebrow><h2>{scenario.title}</h2><p>{scenario.description}</p></div><span className={`evidence-status ${scenario.evidenceType}`}><ShieldCheck size={13}/>{scenario.evidence}</span></div>{selected === 'normalization' && <div className="segmented-control" aria-label="Obfuscation variant">{obfuscations.map((v, i) => <button aria-pressed={variant === i} key={v.label} disabled={!!s.busy} className={variant === i ? 'selected' : ''} onClick={() => setVariant(i)}>{v.label}</button>)}</div>}<div className="lab-payload"><div><span><Braces size={13}/>SYNTHETIC TEST INPUT</span><span>BLUE-ORBIT</span></div><pre>{text}</pre></div><div className="lab-run-row"><span><span className="tiny-dot"/>Select a scenario, then run to measure the result.</span><div><button className="button secondary" disabled={!!s.busy} onClick={() => openAnalyzer(text)}>Open in analyzer<ArrowRight size={14}/></button><button className="button primary" disabled={!!s.busy} onClick={() => void s.analyze(text)}><Play size={14}/>Run comparison</button></div></div></section>{selected === 'encoding' && <LearningNote>Encoding results depend on the exact payload. Newer team tests also found encodings the Guard correctly blocked. This comparison reports the actual response.</LearningNote>}{selected === 'context' && <LearningNote>Athena recognizes analytical intent, but REVIEW holds execution. A Guard block is never silently overridden.</LearningNote>}{s.busy && s.busy !== 'session' ? <Processing busy={s.busy}/> : <><ComparisonPanel guard={current?.guard} athena={current?.athena}/>{current?.athena && <ResultDetails key={current.athena.request_id} result={current.athena}/>}</>}</>}
  </>
}
