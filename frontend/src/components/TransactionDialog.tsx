import { useProfiles } from '../hooks/ProfilesContext'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { LoaderCircle, X } from 'lucide-react'
import { createTransaction, deleteTransaction, errorMessage, updateTransaction } from '../api/transactions'
import type { Transaction, TransactionInput } from '../types/transaction'
import { money, toMinor, today, validateTransaction } from '../utils/finance'
import { useCurrency, currencies, type Currency } from '../hooks/CurrencyContext'

function Dialog({ title, children, onClose, busy }: { title: string; children: ReactNode; onClose: () => void; busy: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const dialog = ref.current
    dialog?.showModal()
    return () => { dialog?.close(); previous?.focus() }
  }, [])
  return <dialog ref={ref} className="modal" aria-labelledby="dialog-title" onCancel={event => { event.preventDefault(); if (!busy) close.current() }}>
    <div className="modal-header"><div><span className="eyebrow">YOUR FINANCES</span><h2 id="dialog-title">{title}</h2></div><button className="icon-button" aria-label="Close dialog" disabled={busy} onClick={onClose}><X size={21} /></button></div>{children}
  </dialog>
}

export function TransactionDialog({ transaction, categories, onClose, onSaved }: { transaction?: Transaction; categories: string[]; onClose: () => void; onSaved: (message: string) => void }) {
  const { selected, writable } = useProfiles()
  const { currency } = useCurrency()
  const [form, setForm] = useState<TransactionInput>(transaction ? { description: transaction.description, amount: transaction.amount, category: transaction.category, transaction_type: transaction.transaction_type, transaction_date: transaction.transaction_date, currency: transaction.currency || 'USD' } : { description: '', amount: '', category: '', transaction_type: 'expense', transaction_date: today(), currency })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const change = (key: keyof TransactionInput, value: string) => setForm(current => ({ ...current, [key]: value }))
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!writable) { setError('Select an active profile to change transactions.'); return }
    const validation = validateTransaction(form)
    if (validation) { setError(validation); return }
    setBusy(true)
    setError(null)
    try {
      const input = { ...form, ...(typeof selected === 'number' && { profile_id: selected }), description: form.description.trim(), category: form.category.trim() }
      if (transaction) await updateTransaction(transaction.id, input)
      else await createTransaction(input)
      onSaved(transaction ? 'Transaction updated successfully.' : 'Transaction added successfully.')
    } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <Dialog title={transaction ? 'Edit transaction' : 'Add transaction'} onClose={onClose} busy={busy}><form onSubmit={submit}>
    <fieldset disabled={busy} className="form-fields"><legend className="sr-only">Transaction details</legend>
      <div className="type-picker" role="group" aria-label="Transaction type">{(['expense', 'income'] as const).map(type => <button type="button" key={type} aria-pressed={form.transaction_type === type} className={form.transaction_type === type ? 'selected' : ''} onClick={() => change('transaction_type', type)}>{type === 'income' ? '↓ Income' : '↑ Expense'}</button>)}</div>
      <label>Description<input autoFocus required maxLength={500} value={form.description} onChange={e => change('description', e.target.value)} placeholder="What was this transaction for?" /></label>
      <label>Original currency<select value={form.currency} onChange={event => change('currency', event.target.value as Currency)}>{currencies.map(code => <option key={code}>{code}</option>)}</select></label>
      <div className="form-grid"><div className="amount-field"><label htmlFor="transaction-amount">Amount ({form.currency})</label><input id="transaction-amount" required inputMode="decimal" value={form.amount} onChange={e => change('amount', e.target.value)} placeholder="0.00" aria-describedby="amount-hint" /><small id="amount-hint">Original amount, up to 2 decimal places. Reporting conversions never change it.</small></div><label>Date<input type="date" required value={form.transaction_date} onChange={e => change('transaction_date', e.target.value)} /></label></div>
      <label>Category<input required maxLength={100} list="transaction-categories" value={form.category} onChange={e => change('category', e.target.value)} placeholder="Choose or enter a category" /><datalist id="transaction-categories">{categories.map(category => <option key={category} value={category} />)}</datalist></label>
    </fieldset>
    {error && <div className="form-error" role="alert">{error}</div>}
    <div className="modal-footer"><button type="button" className="button secondary" disabled={busy} onClick={onClose}>Cancel</button><button className="button primary" disabled={busy}>{busy && <LoaderCircle size={16} className="spin" />}{busy ? 'Saving…' : transaction ? 'Save changes' : 'Add transaction'}</button></div>
  </form></Dialog>
}

export function DeleteDialog({ transaction, onClose, onDeleted }: { transaction: Transaction; onClose: () => void; onDeleted: (message: string) => void }) {
  const { selected, writable } = useProfiles()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function remove() {
    if (!writable) return
    setBusy(true)
    setError(null)
    try { await deleteTransaction(transaction.id, typeof selected === 'number' ? selected : undefined); onDeleted('Transaction deleted successfully.') }
    catch (error) { setError(errorMessage(error)); setBusy(false) }
  }
  return <Dialog title="Delete this transaction?" busy={busy} onClose={onClose}><div className="delete-body"><p>You’re about to delete <strong>{transaction.description}</strong> for <strong>{money(toMinor(transaction.amount), transaction.currency || 'USD')} ({transaction.currency || 'USD'})</strong>. This cannot be undone.</p>{error && <div role="alert" className="form-error">{error}</div>}</div><div className="modal-footer"><button className="button secondary" disabled={busy} onClick={onClose}>Keep transaction</button><button className="button destructive" disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Delete transaction'}</button></div></Dialog>
}
