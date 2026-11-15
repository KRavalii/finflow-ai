import type { Transaction } from '../types/transaction'

// Fixtures are used only in tests. The application never supplies sample records.
export const records: Transaction[] = [
  { id: 1, description: 'Paycheck', amount: '1000.10', category: 'Work', transaction_type: 'income', transaction_date: '2026-10-01', created_at: '2026-10-01T12:00:00Z' },
  { id: 2, description: 'Groceries', amount: '125.25', category: 'Food', transaction_type: 'expense', transaction_date: '2026-10-02', created_at: '2026-10-02T12:00:00Z' },
  { id: 3, description: 'Bus ticket', amount: '2.30', category: 'Travel', transaction_type: 'expense', transaction_date: '2026-11-01', created_at: '2026-11-01T12:00:00Z' },
]
