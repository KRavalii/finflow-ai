import { AxiosError } from 'axios'
import { describe, expect, it, vi } from 'vitest'
import { api } from './transactions'
import { askAssistant, fetchSummary, financialError } from './financial'
import { summaryFixture } from '../test/financialFixtures'

describe('financial API', () => {
  it('fetches the read-only summary using validated date controls and cancellation', async () => {
    const signal = new AbortController().signal
    const get = vi.spyOn(api, 'get').mockResolvedValue({ data: summaryFixture })
    const period = { start_date: '2026-10-01', end_date: '2026-10-31' }
    expect(await fetchSummary(period, signal)).toEqual(summaryFixture)
    expect(get).toHaveBeenCalledWith('/summary', { params: period, signal })
  })
  it('sends only the question and reporting dates, never cached transactions', async () => {
    const response = { provider: 'rule_based', status: 'answered', message: 'Total expenses: $127.55.' }
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: response })
    expect(await askAssistant('What are my total expenses?', {})).toEqual(response)
    expect(post).toHaveBeenCalledWith('/assistant/query', { query: 'What are my total expenses?' }, { signal: undefined })
  })
  it('suppresses sensitive transport details in user-facing errors', () => {
    expect(financialError(new AxiosError('PRIVATE_ERROR'))).not.toContain('PRIVATE')
    expect(financialError(new Error('PRIVATE_ERROR'))).not.toContain('PRIVATE')
  })
})
