import { AxiosError } from 'axios'
import { describe, expect, it, vi } from 'vitest'
import { api, createTransaction, deleteTransaction, errorMessage, fetchTransactions, updateTransaction } from './transactions'
import { records } from '../test/fixtures'

describe('transaction API client', () => {
  it.each(['USD','INR','AED'] as const)('keeps the original %s currency in the Salary request payload', async currency => {
    const payload = { description:'Salary',amount:'300',category:'Salary',transaction_type:'income' as const,
      transaction_date:'2026-11-12',currency }
    const post = vi.spyOn(api,'post').mockResolvedValue({data:{...payload,id:1}})
    await createTransaction(payload)
    expect(post).toHaveBeenCalledWith('/transactions',payload)
  })
  it('explains an old running backend instead of stripping the currency field', () => {
    const stale = { isAxiosError:true,response:{status:422,data:{detail:[{type:'extra_forbidden',loc:['body','currency'],msg:'Extra inputs are not permitted'}]}} }
    expect(errorMessage(stale)).toContain('running backend is outdated')
    expect(errorMessage(stale)).toContain('run_dev.py')
  })
  it('traverses all API pages before exposing totals', async () => {
    const first = Array.from({ length: 100 }, (_, index) => ({ ...records[0], id: index + 1 }))
    const get = vi.spyOn(api, 'get').mockResolvedValueOnce({ data: first }).mockResolvedValueOnce({ data: [{ ...records[1], id: 101 }] })
    const items = await fetchTransactions()
    expect(items).toHaveLength(101)
    expect(get).toHaveBeenNthCalledWith(2, '/transactions', { params: { offset: 100, limit: 100 }, signal: undefined })
  })
  it('rejects incomplete data when a later page fails', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({ data: Array.from({ length: 100 }, (_, id) => ({ ...records[0], id })) }).mockRejectedValueOnce(new Error('offline'))
    await expect(fetchTransactions()).rejects.toThrow('offline')
  })
  it('passes cancellation and rejects malformed list responses', async () => {
    const signal = new AbortController().signal
    const get = vi.spyOn(api, 'get').mockResolvedValueOnce({ data: {} })
    await expect(fetchTransactions(signal)).rejects.toThrow('unexpected transaction response')
    expect(get).toHaveBeenCalledWith('/transactions', expect.objectContaining({ signal }))
  })
  it('uses the existing create, replace and delete contracts', async () => {
    const { id, created_at, ...input } = records[0]
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: records[0] })
    const put = vi.spyOn(api, 'put').mockResolvedValue({ data: records[0] })
    const remove = vi.spyOn(api, 'delete').mockResolvedValue({})
    await createTransaction(input)
    await updateTransaction(id, input)
    await deleteTransaction(id)
    expect(post).toHaveBeenCalledWith('/transactions', input)
    expect(put).toHaveBeenCalledWith('/transactions/1', input, { params: {} })
    expect(remove).toHaveBeenCalledWith('/transactions/1', { params: {} })
  })
  it('does not expose raw transport or database diagnostics', () => {
    expect(errorMessage(new AxiosError('SECRET_DATABASE_DIAGNOSTIC'))).toMatch(/Unable to reach/)
    expect(errorMessage(new Error('SECRET_DATABASE_DIAGNOSTIC'))).not.toContain('SECRET')
  })
})
