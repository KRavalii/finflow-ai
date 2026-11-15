import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { createProfile, fetchProfiles, updateProfile } from './api/profiles'
import { createTransaction, fetchTransactions } from './api/transactions'
import { askAssistant, fetchSummary } from './api/financial'
import { summaryFixture } from './test/financialFixtures'
import { records } from './test/fixtures'
import type { Profile } from './types/profile'
import type { Transaction } from './types/transaction'

vi.mock('./api/profiles', () => ({ fetchProfiles: vi.fn(), createProfile: vi.fn(), updateProfile: vi.fn() }))
vi.mock('./api/transactions', () => ({ fetchTransactions: vi.fn(), createTransaction: vi.fn(), updateTransaction: vi.fn(), deleteTransaction: vi.fn(), errorMessage: () => 'Request failed' }))
vi.mock('./api/financial', () => ({ fetchSummary: vi.fn(), askAssistant: vi.fn(), financialError: () => 'Rates unavailable' }))
vi.mock('./components/Charts', () => ({ default: () => <div>Charts</div> }))

const profiles: Profile[] = [
  { id: 1, name: 'My Profile', is_default: true, created_at: '2026-11-13', archived_at: null },
  { id: 2, name: 'Mom', is_default: false, created_at: '2026-11-13', archived_at: null },
  { id: 3, name: 'Dad', is_default: false, created_at: '2026-11-13', archived_at: '2026-11-13' },
]
const scopeSelect = () => screen.getByRole('combobox', { name: 'Financial profile' })

beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); window.history.replaceState({}, '', '/')
  vi.mocked(fetchProfiles).mockResolvedValue(profiles)
  vi.mocked(fetchTransactions).mockImplementation(async (_signal, options) => [{ ...records[0], description: options?.profile_id === 2 ? 'Mom groceries' : 'My groceries' }])
  vi.mocked(fetchSummary).mockResolvedValue(summaryFixture)
  vi.mocked(askAssistant).mockResolvedValue({ provider: 'rule_based', status: 'answered', message: 'Mom answer', summary: summaryFixture, intent: 'summary' })
})

describe('financial profiles', () => {
  it('keeps demo browsing while disabling transaction and profile edits', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'true')
    try {
      render(<App />)
      await screen.findByText('My groceries')
      expect(screen.getByText(/all financial data is fictional/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Add transaction' })).toBeDisabled()
      expect(screen.queryByRole('button', { name: 'Manage profiles' })).not.toBeInTheDocument()
      await userEvent.selectOptions(scopeSelect(), '2')
      await screen.findByText('Mom groceries')
      await userEvent.click(screen.getByRole('link', { name: 'Transactions' }))
      expect(screen.getByRole('button', { name: 'Add transaction' })).toBeDisabled()
      expect(screen.queryByRole('button', { name: /Edit/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument()
      expect(createProfile).not.toHaveBeenCalled()
      expect(createTransaction).not.toHaveBeenCalled()
    } finally { vi.unstubAllEnvs() }
  })
  it('defaults to My Profile and sends backend scope for transactions and totals', async () => {
    render(<App />)
    await screen.findByText('My groceries')
    expect(scopeSelect()).toHaveValue('1')
    expect(fetchTransactions).toHaveBeenLastCalledWith(expect.any(AbortSignal), expect.objectContaining({ profile_id: 1 }))
    expect(fetchSummary).toHaveBeenLastCalledWith({ profile_id: 1 }, expect.any(AbortSignal))
    expect(localStorage.getItem('finflow.profile')).toBe('1')
  })

  it('keeps scope across navigation and refresh, with explicit combined read-only view', async () => {
    const view = render(<App />)
    await screen.findByText('My groceries')
    await userEvent.selectOptions(scopeSelect(), '2')
    await screen.findByText('Mom groceries')
    await userEvent.click(screen.getByRole('link', { name: 'Analytics' }))
    await waitFor(() => expect(fetchSummary).toHaveBeenLastCalledWith({ profile_id: 2 }, expect.any(AbortSignal)))
    expect(scopeSelect()).toHaveValue('2')
    view.unmount(); render(<App />)
    await waitFor(() => expect(scopeSelect()).toHaveValue('2'))
    await userEvent.selectOptions(scopeSelect(), 'all')
    await waitFor(() => expect(fetchSummary).toHaveBeenLastCalledWith({ profile_id: 'all' }, expect.any(AbortSignal)))
    expect(screen.getByRole('button', { name: 'Add transaction' })).toBeDisabled()
    expect(localStorage.getItem('finflow.profile')).toBe('all')
  })

  it.each(['999', '3', 'invalid'])('falls back safely from saved unavailable selection %s', async saved => {
    localStorage.setItem('finflow.profile', saved)
    render(<App />)
    await screen.findByText('My groceries')
    expect(scopeSelect()).toHaveValue('1')
    expect(fetchTransactions).toHaveBeenLastCalledWith(expect.any(AbortSignal), expect.objectContaining({ profile_id: 1 }))
  })

  it('preserves an explicitly saved All Profiles selection', async () => {
    localStorage.setItem('finflow.profile', 'all')
    render(<App />)
    await waitFor(() => expect(scopeSelect()).toHaveValue('all'))
    expect(screen.getByRole('button', { name: 'Add transaction' })).toBeDisabled()
  })

  it('cancels stale responses and closes transaction forms on profile switches', async () => {
    let finish!: (rows: Transaction[]) => void
    vi.mocked(fetchTransactions).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    render(<App />)
    await screen.findByRole('combobox', { name: 'Financial profile' })
    const originalSignal = vi.mocked(fetchTransactions).mock.calls[0][0]!
    await userEvent.click(screen.getByRole('button', { name: 'Add transaction' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await userEvent.selectOptions(scopeSelect(), '2')
    await screen.findByText('Mom groceries')
    expect(originalSignal.aborted).toBe(true)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await act(async () => finish([{ ...records[0], description: 'Stale private record' }]))
    expect(screen.queryByText('Stale private record')).not.toBeInTheDocument()
  })

  it('submits transactions with the selected concrete profile and original currency', async () => {
    window.history.replaceState({}, '', '/transactions'); localStorage.setItem('finflow.profile', '2')
    render(<App />); await screen.findByText('Mom groceries')
    await userEvent.click(screen.getByRole('button', { name: 'Add transaction' }))
    const dialog = within(screen.getByRole('dialog'))
    await userEvent.type(dialog.getByLabelText('Description'), 'Lunch')
    await userEvent.selectOptions(dialog.getByLabelText('Original currency'), 'INR')
    await userEvent.type(dialog.getByLabelText('Amount (INR)'), '80.00')
    await userEvent.type(dialog.getByLabelText('Category'), 'Food')
    await userEvent.click(dialog.getByRole('button', { name: 'Add transaction' }))
    expect(createTransaction).toHaveBeenCalledWith(expect.objectContaining({ profile_id: 2, currency: 'INR', amount: '80.00' }))
  })

  it('scopes assistant and currency conversion, clearing old conversations on switching', async () => {
    window.history.replaceState({}, '', '/assistant'); localStorage.setItem('finflow.profile', '2')
    render(<App />); await screen.findByRole('combobox', { name: 'Financial profile' })
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Reporting currency' }), 'INR')
    vi.mocked(fetchSummary).mockResolvedValue({ ...summaryFixture, currency: 'INR' })
    await userEvent.click(screen.getByRole('button', { name: 'Summarize my finances' }))
    await userEvent.click(screen.getByRole('button', { name: 'Ask assistant' }))
    await screen.findByText('Mom answer')
    expect(askAssistant).toHaveBeenCalledWith('Summarize my finances', { profile_id: 2, reporting_currency: 'INR' }, expect.any(AbortSignal))
    await userEvent.selectOptions(scopeSelect(), '1')
    expect(screen.queryByText('Mom answer')).not.toBeInTheDocument()
    await waitFor(() => expect(fetchSummary).toHaveBeenLastCalledWith({ profile_id: 1, reporting_currency: 'INR' }, expect.any(AbortSignal)))
  })

  it('creates, renames, archives, restores, and offers archived profiles read-only', async () => {
    render(<App />); await screen.findByText('My groceries')
    await userEvent.click(screen.getByRole('button', { name: 'Manage profiles' }))
    expect(screen.queryByRole('button', { name: 'Archive My Profile' })).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('New profile name'), 'Brother')
    await userEvent.click(screen.getByRole('button', { name: 'Create profile' }))
    await waitFor(() => expect(createProfile).toHaveBeenCalledWith('Brother'))
    const name = screen.getByLabelText('Name for Mom')
    await userEvent.clear(name); await userEvent.type(name, 'Mother')
    await userEvent.click(screen.getByRole('button', { name: 'Rename Mom' }))
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith(2, { name: 'Mother' }))
    await userEvent.click(screen.getByRole('button', { name: 'Archive Mom' }))
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith(2, { archived: true }))
    await userEvent.click(screen.getByRole('button', { name: 'Restore Dad' }))
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith(3, { archived: false }))
    await userEvent.click(screen.getByRole('button', { name: 'Close profiles' }))
    await userEvent.selectOptions(scopeSelect(), '3')
    expect(screen.getByRole('button', { name: 'Add transaction' })).toBeDisabled()
  })

  it('keeps existing finances usable while 0003 is pending', async () => {
    vi.mocked(fetchProfiles).mockRejectedValue({ isAxiosError: true, response: { data: { detail: { code: 'profiles_migration_required' } } } })
    render(<App />); await screen.findByText('My groceries')
    expect(scopeSelect()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Manage profiles' })).toBeDisabled()
    expect(fetchSummary).toHaveBeenLastCalledWith({}, expect.any(AbortSignal))
    expect(screen.getByText(/Profiles require approved database migration/)).toBeInTheDocument()
  })

  it('does not fetch finances when profile loading fails', async () => {
    vi.mocked(fetchProfiles).mockRejectedValue(new Error('offline'))
    render(<App />); await screen.findByRole('alert')
    expect(fetchTransactions).not.toHaveBeenCalled()
    expect(fetchSummary).not.toHaveBeenCalled()
  })
})
