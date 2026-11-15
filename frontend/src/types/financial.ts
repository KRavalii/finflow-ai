import type { Currency, RatePolicy } from '../hooks/CurrencyContext'
export interface ReportingRange { profile_id?: number | 'all'; start_date?: string; end_date?: string; reporting_currency?: Currency; rate_policy?: RatePolicy }
export interface RateQuote { base: Currency; quote: Currency; rate: string; requested_date: string | null; rate_date: string; fetched_at: string; cache_hit: boolean; source: string }
export interface CategorySpending { category: string; total: string; share_percent: string }
export interface MonthComparison {
  current_month: string; previous_month: string
  current_income: string; previous_income: string; income_change: string; income_change_percent: string | null
  current_expenses: string; previous_expenses: string; expense_change: string; expense_change_percent: string | null
  current_transaction_count: number; previous_transaction_count: number; note: string
}
export interface FinancialSummary {
  profile_id?: number | 'all' | null
  profile_name?: string
  period: ReportingRange & { as_of: string; partial_months: boolean }
  currency: Currency
  rate_policy?: RatePolicy
  rates?: RateQuote[]
  conversion_policy?: string
  income: string; expenses: string; net_balance: string; transaction_count: number
  spending_by_category: CategorySpending[]
  monthly_trends: { month: string; income: string; expenses: string; net_balance: string; transaction_count: number }[]
  insights: { top_spending_categories: CategorySpending[]; month_over_month: MonthComparison | null }
}
export interface AssistantResponse {
  provider: 'rule_based'
  status: 'answered' | 'no_data' | 'unsupported'
  intent: string | null
  message: string
  summary: FinancialSummary | null
}
