import { describe, expect, it } from 'vitest'
import { analytics, filterTransactions, money, toMinor, totals, validateTransaction } from './finance'
import { records } from '../test/fixtures'
import { emptyFilters } from '../types/transaction'

describe('financial calculations', () => {
  it('formats exact cents in USD, Indian grouping, and AED without Number overflow', () => {
    expect(money(123456789n, 'INR')).toBe('₹12,34,567.89')
    expect(money(-123456n, 'USD')).toBe('-$1,234.56')
    expect(money(123456n, 'AED').replace(/\u00a0/g, ' ')).toBe('AED 1,234.56')
    expect(money(999999999999999999n, 'INR')).toBe('₹9,99,99,99,99,99,99,999.99')
  })
  it('never adds mixed original currencies without backend conversions', () => {
    const mixed = [{ ...records[0], currency: 'INR' as const }]
    expect(() => totals(mixed)).toThrow('Exchange rates unavailable')
    expect(totals([{ ...mixed[0], reporting_currency: 'USD', converted_amount: '12.50' }]).income).toBe(1250n)
  })
  it('sums exact cents and formats negative balances', () => {
    expect(toMinor('0.10') + toMinor('0.20')).toBe(30n)
    expect(totals(records)).toEqual({ income: 100010n, expense: 12755n, balance: 87255n })
    expect(money(-12345n)).toBe('-$123.45')
  })
  it('preserves precision above the safe Number aggregate range', () => {
    expect(money(toMinor('999999999999.99') * 100n)).toBe('$99,999,999,999,999.00')
  })
  it('combines search, type, category and inclusive date bounds', () => {
    expect(filterTransactions(records, { ...emptyFilters, search: 'GRO', type: 'expense', category: 'Food', from: '2026-10-02', to: '2026-10-02' }).map(item => item.id)).toEqual([2])
    expect(filterTransactions(records, emptyFilters).map(item => item.id)).toEqual([3, 2, 1])
  })
  it('aggregates real transaction dates and expense categories', () => {
    const result = analytics(records)
    expect(result.months.map(month => [month.month, month.income, month.expense])).toEqual([['2026-10', 1000.1, 125.25], ['2026-11', 0, 2.3]])
    expect(result.categories.map(category => [category.name, category.cents])).toEqual([['Food', 12525n], ['Travel', 230n]])
  })
  it('handles an empty dataset without invented values', () => {
    expect(totals([])).toEqual({ income: 0n, expense: 0n, balance: 0n })
    expect(analytics([])).toEqual({ months: [], categories: [] })
  })
  it.each(['0', '-1', '1.234', 'NaN', '1000000000000.00'])('rejects invalid amount %s', amount => {
    expect(validateTransaction({ ...records[0], amount })).toMatch(/positive amount/)
  })
  it('rejects blank text and invalid dates', () => {
    expect(validateTransaction({ ...records[0], description: '   ' })).toMatch(/Description/)
    expect(validateTransaction({ ...records[0], transaction_date: '2026-02-30' })).toMatch(/valid transaction date/)
    expect(validateTransaction(records[0])).toBeNull()
  })
})
