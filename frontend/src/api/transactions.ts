import axios from 'axios'
import type { Transaction, TransactionInput } from '../types/transaction'
import type { ReportingRange } from '../types/financial'

export const api = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, ''),
  timeout: 15000,
})

// The existing API returns arrays, with no count or filter metadata. Traverse
// every page before reporting totals or applying client-side filters.
export async function fetchTransactions(signal?: AbortSignal, options: ReportingRange = {}): Promise<Transaction[]> {
  const result: Transaction[] = []
  const limit = 100
  for (let offset = 0; ; offset += limit) {
    const { data } = await api.get<Transaction[]>('/transactions', { params: { offset, limit, ...options }, signal })
    if (!Array.isArray(data)) throw new Error('The server returned an unexpected transaction response.')
    result.push(...data)
    if (data.length < limit) break
  }
  return [...new Map(result.map(item => [item.id, item])).values()]
}

export const createTransaction = (input: TransactionInput) => api.post<Transaction>('/transactions', input)
export const updateTransaction = (id: number, input: TransactionInput) => api.put<Transaction>(`/transactions/${id}`, input, { params: input.profile_id === undefined ? {} : { profile_id: input.profile_id } })
export const deleteTransaction = (id: number, profileId?: number) => api.delete(`/transactions/${id}`, { params: profileId === undefined ? {} : { profile_id: profileId } })

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response?.data?.detail?.code === 'demo_read_only') return 'This fictional public demo is read-only.'
    if (error.response?.status === 409) return typeof error.response.data?.detail === 'string' ? error.response.data.detail : error.response.data?.detail?.message || 'This operation is unavailable for the selected profile.'
    if (error.response?.status === 503) return 'The database is temporarily unavailable. Please try again.'
    if (error.response?.status === 404) return 'This transaction no longer exists. Refresh your transactions and try again.'
    if (error.response?.status === 422) {
      const detail = error.response.data?.detail
      if (Array.isArray(detail)) {
        if (detail.some((item: { type?: string; loc?: (string | number)[] }) => item.type === 'extra_forbidden' && item.loc?.at(-1) === 'currency')) {
          return 'The running backend is outdated and does not accept transaction currencies. Restart FastAPI from this project using backend/run_dev.py, then retry. Keep the original currency selected.'
        }
        return detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.slice(1).join('.') || 'Form'}: ${item.msg || 'Invalid value'}`).join('. ')
      }
      return 'Please check the transaction fields and try again.'
    }
    if (!error.response) return 'Unable to reach the backend. Check that FastAPI is running, then try again.'
    return 'The request could not be completed. Please try again.'
  }
  return 'Something went wrong while loading transactions. Please try again.'
}
