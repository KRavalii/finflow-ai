import { useProfiles, profileOptions } from './ProfilesContext'
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import axios from 'axios'
import { errorMessage, fetchTransactions } from '../api/transactions'
import type { Transaction } from '../types/transaction'
import { useCurrency } from './CurrencyContext'

interface DataContext {
  transactions: Transaction[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}
const Context = createContext<DataContext | null>(null)

export function TransactionsProvider({ children }: { children: ReactNode }) {
  const { selected } = useProfiles()
  const { currency, policy } = useCurrency()
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)
  const refresh = useCallback(async () => {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    setLoading(true)
    setError(null)
    try {
      const items = await fetchTransactions(request.signal, { reporting_currency: currency, rate_policy: policy, ...profileOptions(selected) })
      if (!request.signal.aborted) setTransactions(items)
    } catch (error) {
      if (!request.signal.aborted && !axios.isCancel(error)) setError(errorMessage(error))
    } finally {
      if (!request.signal.aborted) setLoading(false)
    }
  }, [currency, policy, selected])
  useEffect(() => { void refresh(); return () => controller.current?.abort() }, [refresh])
  return <Context.Provider value={{ transactions, loading, error, refresh }}>{children}</Context.Provider>
}

export function useTransactions() {
  const value = useContext(Context)
  if (!value) throw new Error('TransactionsProvider is required')
  return value
}
