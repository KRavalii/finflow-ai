export type TransactionType = 'income' | 'expense'
import type { Currency } from '../hooks/CurrencyContext'
import type { RateQuote } from './financial'

export interface TransactionInput {
  description: string
  amount: string
  category: string
  transaction_type: TransactionType
  transaction_date: string
  profile_id?: number
  currency?: Currency
}

export interface Transaction extends TransactionInput {
  profile_name?: string | null
  id: number
  created_at: string
  converted_amount?: string | null
  reporting_currency?: Currency | null
  conversion?: RateQuote | null
  conversion_error?: { message: string } | null
}

export interface Filters {
  search: string
  type: '' | TransactionType
  category: string
  from: string
  to: string
}

export const emptyFilters: Filters = { search: '', type: '', category: '', from: '', to: '' }
