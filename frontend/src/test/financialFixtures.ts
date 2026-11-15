import type { FinancialSummary } from '../types/financial'

// Test-only aggregate fixtures, never imported by production code.
export const summaryFixture: FinancialSummary = {
  period: { as_of: '2026-11-12', partial_months: true }, currency: 'USD',
  income: '1000.10', expenses: '127.55', net_balance: '872.55', transaction_count: 3,
  spending_by_category: [{ category: 'Food', total: '125.25', share_percent: '98.20' }, { category: 'Travel', total: '2.30', share_percent: '1.80' }],
  monthly_trends: [], insights: { top_spending_categories: [{ category: 'Food', total: '125.25', share_percent: '98.20' }], month_over_month: null },
}
