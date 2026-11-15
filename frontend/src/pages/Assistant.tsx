import { useProfiles, profileOptions } from '../hooks/ProfilesContext'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Bot, LoaderCircle, RefreshCw, Send, Sparkles } from 'lucide-react'
import { askAssistant, fetchSummary, financialError } from '../api/financial'
import type { FinancialSummary, ReportingRange } from '../types/financial'
import { decimalMoney } from '../utils/finance'
import { useCurrency, reportingOptions } from '../hooks/CurrencyContext'
import ConversionNotice from '../components/ConversionNotice'

const suggestions = ['Summarize my finances', 'What are my total expenses?', 'What is my net balance?', 'What is my biggest spending category?', 'How did expenses change last month?']
interface Message { id: number; role: 'user' | 'assistant'; text: string }

export default function Assistant() {
  const { selected: profileSelection } = useProfiles()
  const { currency, policy } = useCurrency()
  const [dates, setDates] = useState({ start_date: '', end_date: '' })
  const [period, setPeriod] = useState<ReportingRange>({})
  const [summary, setSummary] = useState<FinancialSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [summaryError, setSummaryError] = useState('')
  const [revision, setRevision] = useState(0)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [asking, setAsking] = useState(false)
  const [queryError, setQueryError] = useState('')
  const request = useRef<AbortController | null>(null)
  const nextId = useRef(0)
  const questionInput = useRef<HTMLTextAreaElement>(null)
  const conversation = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setSummaryError('')
    setSummary(null)
    fetchSummary({ ...period, ...reportingOptions(currency, policy), ...profileOptions(profileSelection) }, controller.signal).then(value => {
      if (!controller.signal.aborted) setSummary(value)
    }).catch(error => {
      if (!controller.signal.aborted) setSummaryError(financialError(error))
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [period, revision, currency, policy, profileSelection])
  useEffect(() => { request.current?.abort(); setAsking(false); setMessages([]); setQueryError('') }, [currency, policy, profileSelection])
  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => {
    if (conversation.current) conversation.current.scrollTop = conversation.current.scrollHeight
  }, [messages, asking])

  function appendMessage(role: Message['role'], text: string) {
    const message: Message = { id: nextId.current++, role, text }
    setMessages(current => [...current, message].slice(-20))
  }

  function applyDates(event: FormEvent) {
    event.preventDefault()
    if (dates.start_date && dates.end_date && dates.start_date > dates.end_date) {
      setSummaryError('The start date must be on or before the end date.')
      return
    }
    setPeriod({ ...(dates.start_date && { start_date: dates.start_date }), ...(dates.end_date && { end_date: dates.end_date }) })
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const text = question.trim()
    if (!text || text.length > 500 || asking) return
    setAsking(true)
    setQueryError('')
    appendMessage('user', text)
    const controller = new AbortController()
    request.current = controller
    try {
      const answer = await askAssistant(text, { ...period, ...reportingOptions(currency, policy), ...profileOptions(profileSelection) }, controller.signal)
      if (!controller.signal.aborted) {
        appendMessage('assistant', answer.message)
        setQuestion('')
      }
    } catch (error) {
      if (!controller.signal.aborted) setQueryError(financialError(error))
    } finally { if (!controller.signal.aborted) { setAsking(false); questionInput.current?.focus() } }
  }

  return <>
    <div className="page-heading"><div><span className="eyebrow">CLARITY, ONE QUESTION AT A TIME</span><h1>Your financial assistant.</h1><p>Understand your recorded finances with straightforward, calculated answers.</p></div><span className="assistant-mode"><Sparkles size={15} />Free · Rule-based</span></div>
    <section className="panel assistant-summary" aria-labelledby="assistant-summary-title">
      <div className="panel-heading"><div><h2 id="assistant-summary-title">Your reporting snapshot</h2><p>Live database totals · USD · No transaction data is sent to an external service.</p></div><button className="icon-button" aria-label="Refresh financial summary" disabled={loading || asking} onClick={() => setRevision(value => value + 1)}><RefreshCw size={17} className={loading ? 'spin' : ''} /></button></div>
      <form className="assistant-date-controls" onSubmit={applyDates}><label>Start date<input type="date" value={dates.start_date} disabled={asking} onChange={event => setDates(value => ({ ...value, start_date: event.target.value }))} /></label><label>End date<input type="date" value={dates.end_date} disabled={asking} onChange={event => setDates(value => ({ ...value, end_date: event.target.value }))} /></label><button className="button secondary" disabled={asking}>Apply dates</button><button className="text-button" type="button" disabled={asking} onClick={() => { setDates({ start_date: '', end_date: '' }); setPeriod({}) }}>All time</button></form>
      {summaryError && <div className="assistant-error" role="alert">{summaryError}<button className="text-button" onClick={() => setRevision(value => value + 1)}>Retry summary</button></div>}
      {loading ? <div className="assistant-summary-loading" role="status"><LoaderCircle size={18} className="spin" />Loading financial summary…</div> : summary && <><div className="assistant-totals"><div><span>Income</span><strong>{decimalMoney(summary.income, summary.currency)}</strong></div><div><span>Expenses</span><strong>{decimalMoney(summary.expenses, summary.currency)}</strong></div><div><span>Net balance</span><strong>{decimalMoney(summary.net_balance, summary.currency)}</strong></div></div><ConversionNotice summary={summary} /><p className="assistant-period">Applied period: {summary.period.start_date || 'Beginning of records'} to {summary.period.end_date || 'All recorded dates'}. {summary.transaction_count} recorded transaction{summary.transaction_count !== 1 ? 's' : ''}.{summary.period.partial_months && ' May include partial calendar months.'}</p>{summary.transaction_count === 0 && <p className="assistant-no-data">No transactions in this period. Add transactions or select another period to explore your finances.</p>}</>}
    </section>
    <section className="panel assistant-panel" aria-labelledby="assistant-heading">
      <div className="panel-heading"><div><h2 id="assistant-heading"><Bot size={19} />Ask FinFlow</h2><p>Ask about totals, top categories, or changes between complete calendar months.</p></div><button className="text-button" disabled={asking || !messages.length} onClick={() => { setMessages([]); setQueryError('') }}>Clear conversation</button></div>
      <div className="assistant-guidance">Dates use America/Chicago. With date controls, ask without “this month” or “last month.” Monthly comparisons use complete calendar months and may extend before the selected start date.</div>
      <div className="assistant-suggestions" aria-label="Suggested questions">{suggestions.map(text => {
        const suggestedQuestion = period.start_date || period.end_date ? text.replace(' last month', '') : text
        return <button className="suggestion" key={text} disabled={asking} onClick={() => { setQuestion(suggestedQuestion); questionInput.current?.focus() }}>{suggestedQuestion}</button>
      })}</div>
      <div ref={conversation} className="assistant-messages" role="log" aria-label="Assistant conversation" aria-live="polite" aria-relevant="additions">
        {!messages.length && <div className="assistant-welcome"><span className="empty-icon"><Bot size={28} /></span><h3>A clearer picture starts with a question.</h3><p>Try a suggestion above. Answers are calculated from your transactions, with no paid AI account required.</p></div>}
        {messages.map(message => <article className={`assistant-message ${message.role}`} key={message.id}><strong>{message.role === 'user' ? 'You' : 'FinFlow Assistant'}</strong><p>{message.text}</p></article>)}
        {asking && <div className="assistant-thinking" role="status"><LoaderCircle className="spin" size={16} />Calculating your answer…</div>}
      </div>
      {queryError && <div className="assistant-error" role="alert">{queryError} Your question is preserved below; submit it again to retry.</div>}
      <form className="assistant-composer" onSubmit={submit}><label htmlFor="assistant-question">Your question</label><textarea id="assistant-question" ref={questionInput} rows={2} maxLength={500} required disabled={asking} value={question} placeholder="How much did I spend this month?" onChange={event => setQuestion(event.target.value)} /><div><span>{question.length}/500 · Answers use recorded transactions, not predictions.</span><button className="button primary" disabled={asking || !question.trim()}>{asking ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />}{asking ? 'Calculating…' : 'Ask assistant'}</button></div></form>
      <p className="assistant-footnote">This assistant cannot change transactions. Conversation history stays in this page’s memory and is cleared when you leave or reload.</p>
    </section>
  </>
}
