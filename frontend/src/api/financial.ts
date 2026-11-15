import axios from 'axios'
import { api } from './transactions'
import type { AssistantResponse, FinancialSummary, ReportingRange } from '../types/financial'

export async function fetchSummary(period: ReportingRange, signal?: AbortSignal): Promise<FinancialSummary> {
  return (await api.get<FinancialSummary>('/summary', { params: period, signal })).data
}

export async function askAssistant(query: string, period: ReportingRange, signal?: AbortSignal): Promise<AssistantResponse> {
  return (await api.post<AssistantResponse>('/assistant/query', { query, ...period }, { signal })).data
}

export function financialError(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.data?.detail?.code === 'exchange_rates_unavailable') return 'A required exchange rate is unavailable. Totals are hidden to avoid incomplete or misleading results. Retry or choose another conversion policy.'
  if (axios.isAxiosError(error) && error.response?.status === 422) return 'Check your dates and question. The start date must be on or before the end date; questions must contain 1 to 500 characters.'
  if (axios.isAxiosError(error) && error.response?.status === 503) return 'The database is temporarily unavailable. Please try again.'
  return 'Unable to load financial insights. Check that FastAPI is running and try again.'
}
