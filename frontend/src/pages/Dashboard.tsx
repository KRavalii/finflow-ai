import { useProfiles, profileOptions } from '../hooks/ProfilesContext'
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownLeft, ArrowRight, ArrowUpRight, Plus, Wallet } from 'lucide-react'
import { useTransactions } from '../hooks/TransactionsContext'
import { filterTransactions, decimalMoney } from '../utils/finance'
import { useCurrency, reportingOptions } from '../hooks/CurrencyContext'
import { fetchSummary, financialError } from '../api/financial'
import type { FinancialSummary } from '../types/financial'
import ConversionNotice from '../components/ConversionNotice'
import { emptyFilters } from '../types/transaction'
import TransactionTable from '../components/TransactionTable'
import { TransactionDialog } from '../components/TransactionDialog'
import { EmptyState, ErrorState, LoadingState } from '../components/Feedback'

const Charts = lazy(() => import('../components/Charts'))

export default function Dashboard({ analyticsOnly = false }: { analyticsOnly?: boolean }) {
  const { transactions, loading, error, refresh } = useTransactions()
  const { selected: profileSelection, writable } = useProfiles()
  const { currency, policy } = useCurrency()
  const [period, setPeriod] = useState('')
  const [adding, setAdding] = useState(false)
  const [notice, setNotice] = useState('')
  const [report, setReport] = useState<FinancialSummary | null>(null)
  const [reportLoading, setReportLoading] = useState(true)
  const [reportError, setReportError] = useState('')
  const months = useMemo(() => [...new Set(transactions.map(item => item.transaction_date.slice(0, 7)))].sort().map(month => ({ month })), [transactions])
  const selected = useMemo(() => transactions.filter(item => !period || item.transaction_date.startsWith(period)), [transactions, period])
  useEffect(() => {
    const request = new AbortController()
    setReportLoading(true); setReportError(''); setReport(null)
    const lastDay = period ? new Date(Number(period.slice(0, 4)), Number(period.slice(5)), 0).getDate() : 0
    const dates = period ? { start_date: `${period}-01`, end_date: `${period}-${lastDay}` } : {}
    fetchSummary({ ...dates, ...reportingOptions(currency, policy), ...profileOptions(profileSelection) }, request.signal)
      .then(value => { if (!request.signal.aborted) setReport(value) })
      .catch(error => { if (!request.signal.aborted) setReportError(financialError(error)) })
      .finally(() => { if (!request.signal.aborted) setReportLoading(false) })
    return () => request.abort()
  }, [period, currency, policy, transactions, profileSelection])
  const recent = useMemo(() => filterTransactions(selected, emptyFilters).slice(0, 5), [selected])
  const categories = [...new Set(transactions.map(item => item.category))].sort()
  return <>
    <div className="page-heading"><div><span className="eyebrow">YOUR MONEY, IN FOCUS</span><h1>{analyticsOnly ? 'The bigger picture.' : 'Financial overview.'}</h1><p>{analyticsOnly ? 'Understand your patterns. Make your next move with confidence.' : 'A little perspective for your next big decision.'}</p></div><button className="button primary" disabled={!writable} onClick={() => setAdding(true)}><Plus size={17} />Add transaction</button></div>
    {notice && <div className="success-message" role="status">{notice}<button className="text-button" onClick={() => setNotice('')}>Dismiss</button></div>}
    <div className="section-toolbar"><div className="section-label"><span className="live-dot" />{period ? 'Monthly snapshot' : 'All-time snapshot'}</div><label className="period-select"><span className="sr-only">Reporting period</span><select value={period} onChange={e => setPeriod(e.target.value)}><option value="">All time</option>{[...months].reverse().map(month => <option key={month.month} value={month.month}>{new Date(`${month.month}-01T12:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</option>)}</select></label></div>
    {error && <ErrorState message={error} retry={() => void refresh()} />}
    {reportError && <ErrorState message={reportError} retry={() => void refresh()} />}
    {loading || reportLoading || (report && (report.currency !== currency || (report.rate_policy || 'historical') !== policy)) ? <LoadingState /> : !error && !reportError && report && <>
      <div className="stats-grid">
        <section className="stat-card"><div className="stat-top"><span>Total income</span><span className="stat-icon income"><ArrowDownLeft size={19} /></span></div><strong className="stat-value">{decimalMoney(report.income, currency)}</strong><span className="stat-foot">Money coming in <span>{selected.filter(item => item.transaction_type === 'income').length} transactions</span></span></section>
        <section className="stat-card"><div className="stat-top"><span>Total expenses</span><span className="stat-icon expense"><ArrowUpRight size={19} /></span></div><strong className="stat-value">{decimalMoney(report.expenses, currency)}</strong><span className="stat-foot">Money going out <span>{selected.filter(item => item.transaction_type === 'expense').length} transactions</span></span></section>
        <section className="stat-card balance-card"><div className="stat-top"><span>Net balance</span><span className="stat-icon"><Wallet size={19} /></span></div><strong className="stat-value">{decimalMoney(report.net_balance, currency)}</strong><span className="stat-foot">Income minus expenses<span>Selected period</span></span></section>
      </div>
      <ConversionNotice summary={report} />
      <Suspense fallback={<div className="chart-empty" role="status">Loading analytics…</div>}><Charts summary={report} /></Suspense>
      {!analyticsOnly && <section className="panel recent-panel"><div className="panel-heading"><div><h2>Recent transactions</h2><p>Your latest financial activity, at a glance</p></div><Link to="/transactions" className="text-link">View all <ArrowRight size={15} /></Link></div>{recent.length ? <TransactionTable items={recent} /> : <EmptyState filtered={!!period} onAdd={writable ? () => setAdding(true) : undefined} />}</section>}
      {analyticsOnly && <div className="insight-note"><Wallet size={19} /><p>These charts reflect {selected.length} transaction{selected.length !== 1 ? 's' : ''} in the selected period. Totals include all API pages and use the transaction date.</p></div>}
    </>}
    {adding && <TransactionDialog categories={categories} onClose={() => setAdding(false)} onSaved={message => { setAdding(false); setNotice(message); void refresh() }} />}
  </>
}
