import type { Filters, Transaction, TransactionInput } from '../types/transaction'
import { currencyLocales, type Currency } from '../hooks/CurrencyContext'

// Never sum binary floating-point currency. BigInt also avoids aggregate overflow.
export function toMinor(amount: string): bigint {
  if (!/^\d+(\.\d{1,2})?$/.test(amount)) throw new Error('Invalid monetary value')
  const [whole, fraction = ''] = amount.split('.')
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
}

export function money(cents: bigint, currency: Currency = 'USD'): string {
  const absolute = cents < 0n ? -cents : cents
  const parts = new Intl.NumberFormat(currencyLocales[currency], { style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: 2 }).formatToParts(absolute / 100n)
  return `${cents < 0n ? '-' : ''}${parts.map(part => part.type === 'fraction' ? String(absolute % 100n).padStart(2, '0') : part.value).join('')}`
}

export function decimalMoney(value: string, currency: Currency = 'USD') {
  return money(toMinor(value.replace(/^-/, '')) * (value.startsWith('-') ? -1n : 1n), currency)
}

export function totals(transactions: Transaction[], currency: Currency = 'USD') {
  let income = 0n
  let expense = 0n
  for (const item of transactions) {
    const amount = item.converted_amount != null && item.reporting_currency === currency ? item.converted_amount
      : (item.currency || 'USD') === currency ? item.amount : null
    if (amount === null) throw new Error('Exchange rates unavailable; mixed currencies cannot be summed')
    if (item.transaction_type === 'income') income += toMinor(amount)
    else expense += toMinor(amount)
  }
  return { income, expense, balance: income - expense }
}

export function filterTransactions(items: Transaction[], filters: Filters) {
  const query = filters.search.trim().toLowerCase()
  return items.filter(item =>
    (!query || `${item.description} ${item.category}`.toLowerCase().includes(query)) &&
    (!filters.type || item.transaction_type === filters.type) &&
    (!filters.category || item.category === filters.category) &&
    (!filters.from || item.transaction_date >= filters.from) &&
    (!filters.to || item.transaction_date <= filters.to),
  ).sort((a, b) => b.transaction_date.localeCompare(a.transaction_date) || b.id - a.id)
}

export function analytics(items: Transaction[]) {
  const months = new Map<string, { income: bigint; expense: bigint }>()
  const categories = new Map<string, bigint>()
  for (const item of items) {
    const month = item.transaction_date.slice(0, 7)
    const aggregate = months.get(month) || { income: 0n, expense: 0n }
    aggregate[item.transaction_type] += toMinor(item.amount)
    months.set(month, aggregate)
    if (item.transaction_type === 'expense') categories.set(item.category, (categories.get(item.category) || 0n) + toMinor(item.amount))
  }
  return {
    months: [...months].sort(([a], [b]) => a.localeCompare(b)).map(([month, value]) => ({
      month,
      label: new Date(`${month}-01T12:00:00`).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      income: Number(value.income) / 100,
      expense: Number(value.expense) / 100,
    })),
    categories: [...categories].sort((a, b) => a[1] > b[1] ? -1 : a[1] < b[1] ? 1 : a[0].localeCompare(b[0])).map(([name, cents]) => ({ name, cents, value: Number(cents) / 100 })),
  }
}

export function dateLabel(value: string) {
  return new Date(`${value}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function today() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function validateTransaction(input: TransactionInput): string | null {
  if (input.currency && !['USD', 'INR', 'AED'].includes(input.currency)) return 'Choose USD, INR, or AED.'
  if (!input.description.trim() || input.description.trim().length > 500) return 'Description must contain 1 to 500 characters.'
  if (!input.category.trim() || input.category.trim().length > 100) return 'Category must contain 1 to 100 characters.'
  if (!/^\d{1,12}(\.\d{1,2})?$/.test(input.amount) || toMinor(input.amount) <= 0n) return 'Enter a positive amount with up to 12 integer digits and 2 decimal places.'
  if (!['income', 'expense'].includes(input.transaction_type)) return 'Choose income or expense.'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input.transaction_date) || Number.isNaN(Date.parse(input.transaction_date)) || new Date(`${input.transaction_date}T00:00:00Z`).toISOString().slice(0, 10) !== input.transaction_date) return 'Enter a valid transaction date.'
  return null
}
