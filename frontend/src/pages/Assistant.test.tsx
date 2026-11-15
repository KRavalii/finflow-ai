import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Assistant from './Assistant'
import { askAssistant, fetchSummary } from '../api/financial'
import { summaryFixture } from '../test/financialFixtures'

vi.mock('../api/financial', () => ({ fetchSummary: vi.fn(), askAssistant: vi.fn(), financialError: () => 'Financial service unavailable.' }))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchSummary).mockResolvedValue(summaryFixture)
  vi.mocked(askAssistant).mockResolvedValue({ provider: 'rule_based', status: 'answered', intent: 'expenses', message: 'Total expenses: $127.55. Reporting period: all recorded dates.', summary: summaryFixture })
})

describe('local financial assistant', () => {
  it.each(['summarise my finances', 'summarize my finances', 'give me a financial summary'])('displays a complete financial summary for "%s"', async question => {
    vi.mocked(askAssistant).mockResolvedValue({
      provider: 'rule_based', status: 'answered', intent: 'summary', summary: summaryFixture,
      message: 'Financial summary (USD). Income: $1,000.10. Expenses: $127.55. Net balance (income minus expenses): $872.55. Top spending categories: Food: $125.25; Travel: $2.30. Reporting period: all recorded dates.',
    })
    render(<Assistant />)
    await userEvent.type(screen.getByLabelText('Your question'), question)
    await userEvent.click(screen.getByRole('button', { name: 'Ask assistant' }))
    await waitFor(() => expect(screen.getByRole('log', { name: 'Assistant conversation' })).toHaveTextContent('Financial summary (USD)'))
    const conversation = screen.getByRole('log', { name: 'Assistant conversation' })
    for (const text of ['Income: $1,000.10', 'Expenses: $127.55', 'Net balance (income minus expenses): $872.55', 'Food: $125.25', 'Reporting period: all recorded dates']) expect(conversation).toHaveTextContent(text)
    expect(askAssistant).toHaveBeenCalledWith(question, {}, expect.any(AbortSignal))
  })
  it('offers a financial summary suggestion', async () => {
    render(<Assistant />)
    await userEvent.click(screen.getByRole('button', { name: 'Summarize my finances' }))
    expect(screen.getByLabelText('Your question')).toHaveValue('Summarize my finances')
  })
  it('explains missing financial data in the summary response', async () => {
    vi.mocked(askAssistant).mockResolvedValue({ provider: 'rule_based', status: 'no_data', intent: 'summary', summary: { ...summaryFixture, income: '0.00', expenses: '0.00', net_balance: '0.00', transaction_count: 0 }, message: 'Income: $0.00. Expenses: $0.00. Net balance: $0.00. No transactions are recorded. Reporting period: 2026-01-01 through 2026-01-31.' })
    render(<Assistant />)
    await userEvent.type(screen.getByLabelText('Your question'), 'summarise my finances')
    await userEvent.click(screen.getByRole('button', { name: 'Ask assistant' }))
    await waitFor(() => expect(screen.getByRole('log')).toHaveTextContent('No transactions are recorded'))
    expect(screen.getByRole('log')).toHaveTextContent('2026-01-01 through 2026-01-31')
  })
  it('shows database summary totals and local-only mode', async () => {
    render(<Assistant />)
    expect(await screen.findByText('$872.55')).toBeInTheDocument()
    expect(screen.getByText('$1,000.10')).toBeInTheDocument()
    expect(screen.getByText('Free · Rule-based')).toBeInTheDocument()
    expect(fetchSummary).toHaveBeenCalledWith({}, expect.any(AbortSignal))
  })
  it('uses a loading state rather than showing fake totals', async () => {
    let finish!: (value: typeof summaryFixture) => void
    vi.mocked(fetchSummary).mockReturnValue(new Promise(resolve => { finish = resolve }))
    render(<Assistant />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading financial summary')
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    await act(async () => finish(summaryFixture))
    expect(await screen.findByText('$872.55')).toBeInTheDocument()
  })
  it('makes an explicit empty state when no transactions exist', async () => {
    vi.mocked(fetchSummary).mockResolvedValue({ ...summaryFixture, income: '0.00', expenses: '0.00', net_balance: '0.00', transaction_count: 0, spending_by_category: [], monthly_trends: [], insights: { top_spending_categories: [], month_over_month: null } })
    render(<Assistant />)
    expect(await screen.findByText(/No transactions in this period/)).toBeInTheDocument()
  })
  it('shows a suggested question and uses the local API response', async () => {
    render(<Assistant />)
    await screen.findByText('$872.55')
    await userEvent.click(screen.getByRole('button', { name: 'What are my total expenses?' }))
    expect(screen.getByLabelText('Your question')).toHaveValue('What are my total expenses?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask assistant' }))
    expect(await screen.findByText('Total expenses: $127.55. Reporting period: all recorded dates.')).toBeInTheDocument()
    expect(askAssistant).toHaveBeenCalledWith('What are my total expenses?', {}, expect.any(AbortSignal))
    expect(screen.getByLabelText('Your question')).toHaveValue('')
    await userEvent.click(screen.getByRole('button', { name: 'Clear conversation' }))
    expect(screen.queryByText('Total expenses: $127.55. Reporting period: all recorded dates.')).not.toBeInTheDocument()
  })
  it('does not reinterpret unsupported queries or invent an answer', async () => {
    vi.mocked(askAssistant).mockResolvedValue({ provider: 'rule_based', status: 'unsupported', intent: null, summary: null, message: 'Please ask about supported financial totals.' })
    render(<Assistant />)
    await userEvent.type(screen.getByLabelText('Your question'), 'Predict my income next year')
    await userEvent.click(screen.getByRole('button', { name: 'Ask assistant' }))
    expect(await screen.findByText('Please ask about supported financial totals.')).toBeInTheDocument()
  })
  it('applies selected dates to both the summary and assistant request', async () => {
    render(<Assistant />)
    await screen.findByText('$872.55')
    await userEvent.type(screen.getByLabelText('Start date'), '2026-10-01')
    await userEvent.type(screen.getByLabelText('End date'), '2026-10-31')
    await userEvent.click(screen.getByRole('button', { name: 'Apply dates' }))
    await waitFor(() => expect(fetchSummary).toHaveBeenLastCalledWith({ start_date: '2026-10-01', end_date: '2026-10-31' }, expect.any(AbortSignal)))
    await userEvent.click(screen.getByRole('button', { name: 'How did expenses change?' }))
    await userEvent.click(screen.getByRole('button', { name: 'Ask assistant' }))
    await waitFor(() => expect(askAssistant).toHaveBeenCalledWith('How did expenses change?', { start_date: '2026-10-01', end_date: '2026-10-31' }, expect.any(AbortSignal)))
  })
  it('rejects reversed dates before sending them to the API', async () => {
    render(<Assistant />)
    await screen.findByText('$872.55')
    await userEvent.type(screen.getByLabelText('Start date'), '2026-11-30')
    await userEvent.type(screen.getByLabelText('End date'), '2026-10-01')
    await userEvent.click(screen.getByRole('button', { name: 'Apply dates' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('start date must be on or before')
    expect(fetchSummary).toHaveBeenCalledTimes(1)
  })
  it('recovers a failed summary request through retry', async () => {
    vi.mocked(fetchSummary).mockRejectedValueOnce(new Error('offline'))
    render(<Assistant />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Financial service unavailable')
    await userEvent.click(screen.getByRole('button', { name: 'Retry summary' }))
    expect(await screen.findByText('$872.55')).toBeInTheDocument()
  })
  it('preserves the question on failure and prevents duplicate submissions while pending', async () => {
    let fail!: (error: Error) => void
    vi.mocked(askAssistant).mockReturnValueOnce(new Promise((_, reject) => { fail = reject }))
    render(<Assistant />)
    await userEvent.type(screen.getByLabelText('Your question'), 'What is my net balance?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask assistant' }))
    expect(screen.getByRole('button', { name: 'Calculating…' })).toBeDisabled()
    await act(async () => fail(new Error('offline')))
    expect(await screen.findByRole('alert')).toHaveTextContent('Financial service unavailable')
    expect(screen.getByLabelText('Your question')).toHaveValue('What is my net balance?')
    expect(askAssistant).toHaveBeenCalledTimes(1)
  })
  it('aborts summary loading on navigation away', () => {
    vi.mocked(fetchSummary).mockReturnValue(new Promise(() => {}))
    const { unmount } = render(<Assistant />)
    const signal = vi.mocked(fetchSummary).mock.calls[0][1]
    unmount()
    expect(signal?.aborted).toBe(true)
  })
})
