import { AlertCircle, ArrowRight, ArrowDownUp, LoaderCircle } from 'lucide-react'

export function LoadingState() {
  return <div className="loading-state" role="status"><LoaderCircle className="spin" size={25} /><strong>Bringing your finances into focus</strong><span>Loading all your transactions…</span></div>
}

export function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  return <div className="error-state" role="alert"><AlertCircle size={22} /><div><strong>We couldn’t update your transactions</strong><p>{message}</p></div><button className="button secondary" onClick={retry}>Try again</button></div>
}

export function EmptyState({ filtered = false, onAdd }: { filtered?: boolean; onAdd?: () => void }) {
  return <div className="empty-state"><span className="empty-icon"><ArrowDownUp size={27} /></span><h3>{filtered ? 'No matching transactions' : 'Your next chapter starts here'}</h3><p>{filtered ? 'Try a different search or clear your filters.' : 'Add your first transaction to see your financial picture take shape.'}</p>{onAdd && !filtered && <button className="button secondary" onClick={onAdd}>Add a transaction <ArrowRight size={16} /></button>}</div>
}
