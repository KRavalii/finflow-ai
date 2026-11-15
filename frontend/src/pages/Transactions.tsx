import { useProfiles } from '../hooks/ProfilesContext'
import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Plus, Search, SlidersHorizontal, X } from 'lucide-react'
import { useTransactions } from '../hooks/TransactionsContext'
import { emptyFilters, type Filters, type Transaction } from '../types/transaction'
import { filterTransactions, money, totals } from '../utils/finance'
import TransactionTable from '../components/TransactionTable'
import { DeleteDialog, TransactionDialog } from '../components/TransactionDialog'
import { EmptyState, ErrorState, LoadingState } from '../components/Feedback'
import { useCurrency } from '../hooks/CurrencyContext'

export default function Transactions() {
  const { transactions, loading, error, refresh } = useTransactions()
  const { writable } = useProfiles()
  const { currency } = useCurrency()
  const [filters, setFilters] = useState<Filters>(emptyFilters)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [editing, setEditing] = useState<Transaction | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Transaction | null>(null)
  const [notice, setNotice] = useState('')
  const categories = [...new Set(transactions.map(item => item.category))].sort()
  const filtered = useMemo(() => filterTransactions(transactions, filters), [transactions, filters])
  const summary = useMemo(() => { try { return totals(filtered, currency) } catch { return null } }, [filtered, currency])
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, pages)
  const offset = (currentPage - 1) * pageSize
  const hasFilters = Object.values(filters).some(Boolean)
  const changeFilter = (key: keyof Filters, value: string) => { setFilters(current => ({ ...current, [key]: value })); setPage(1) }
  function saved(message: string) { setEditing(null); setDeleting(null); setNotice(message); void refresh() }
  return <>
    <div className="page-heading"><div><span className="eyebrow">EVERY DETAIL, ALL IN ONE PLACE</span><h1>Your transactions.</h1><p>Keep track of what comes in and what goes out.</p></div><button className="button primary" disabled={!writable} onClick={() => setEditing('new')}><Plus size={17} />Add transaction</button></div>
    {notice && <div className="success-message" role="status">{notice}<button className="text-button" onClick={() => setNotice('')}>Dismiss</button></div>}
    <section className="panel transactions-panel" aria-label="Transaction management">
      <div className="filters"><div className="filter-heading"><SlidersHorizontal size={16} /><strong>Find a transaction</strong>{hasFilters && <button className="text-button" onClick={() => { setFilters(emptyFilters); setPage(1) }}><X size={13} />Clear filters</button>}</div>
        <div className="filter-row"><label className="search-field"><span className="sr-only">Search transactions</span><Search size={17} /><input placeholder="Search description or category…" value={filters.search} onChange={e => changeFilter('search', e.target.value)} /></label><label><span>Type</span><select value={filters.type} onChange={e => changeFilter('type', e.target.value)}><option value="">All types</option><option value="income">Income</option><option value="expense">Expense</option></select></label><label><span>Category</span><select value={filters.category} onChange={e => changeFilter('category', e.target.value)}><option value="">All categories</option>{categories.map(category => <option key={category}>{category}</option>)}</select></label><label><span>From</span><input type="date" value={filters.from} onChange={e => changeFilter('from', e.target.value)} /></label><label><span>To</span><input type="date" min={filters.from || undefined} value={filters.to} onChange={e => changeFilter('to', e.target.value)} /></label></div>
        {filters.from && filters.to && filters.from > filters.to && <p role="alert" className="filter-warning">The end date must be on or after the start date.</p>}
      </div>
      {error && <ErrorState message={error} retry={() => void refresh()} />}
      {loading ? <LoadingState /> : !error && <>
        <div className="results-summary"><span><strong>{filtered.length}</strong> transaction{filtered.length !== 1 ? 's' : ''}{hasFilters ? ' matching your filters' : ' in your workspace'}</span><span>Net total ({currency}) <strong>{summary ? money(summary.balance, currency) : 'Unavailable: missing exchange rates'}</strong></span></div>
        {filtered.length ? <TransactionTable items={filtered.slice(offset, offset + pageSize)} onEdit={writable ? setEditing : undefined} onDelete={writable ? setDeleting : undefined} /> : <EmptyState filtered={hasFilters} onAdd={writable ? () => setEditing('new') : undefined} />}
        <div className="pagination"><label>Rows per page<select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1) }}>{[10, 25, 50].map(size => <option key={size}>{size}</option>)}</select></label><span>{filtered.length ? `${offset + 1}–${Math.min(offset + pageSize, filtered.length)}` : '0'} of {filtered.length}</span><div><button className="icon-button" aria-label="Previous page" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={18} /></button><span>Page {currentPage} of {pages}</span><button className="icon-button" aria-label="Next page" disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}><ChevronRight size={18} /></button></div></div>
      </>}
    </section>
    {editing && <TransactionDialog transaction={editing === 'new' ? undefined : editing} categories={categories} onClose={() => setEditing(null)} onSaved={saved} />}
    {deleting && <DeleteDialog transaction={deleting} onClose={() => setDeleting(null)} onDeleted={saved} />}
  </>
}
