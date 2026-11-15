import { createContext, useContext, useState, type ReactNode } from 'react'

export type Currency = 'USD' | 'INR' | 'AED'
export type RatePolicy = 'historical' | 'latest'
export const currencies: Currency[] = ['USD', 'INR', 'AED']
export const currencyLocales = { USD: 'en-US', INR: 'en-IN', AED: 'en-AE' }
interface Preferences {
  currency: Currency; policy: RatePolicy
  setCurrency: (currency: Currency) => void; setPolicy: (policy: RatePolicy) => void
}
const Context = createContext<Preferences>({ currency: 'USD', policy: 'historical', setCurrency: () => {}, setPolicy: () => {} })

function saved(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function persist(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* Preferences still work without storage. */ }
}
export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, updateCurrency] = useState<Currency>(() => {
    const value = saved('finflow.currency')
    return currencies.includes(value as Currency) ? value as Currency : 'USD'
  })
  const [policy, updatePolicy] = useState<RatePolicy>(() => saved('finflow.ratePolicy') === 'latest' ? 'latest' : 'historical')
  return <Context.Provider value={{ currency, policy,
    setCurrency: value => { updateCurrency(value); persist('finflow.currency', value) },
    setPolicy: value => { updatePolicy(value); persist('finflow.ratePolicy', value) },
  }}>{children}</Context.Provider>
}
export const useCurrency = () => useContext(Context)
export const reportingOptions = (currency: Currency, policy: RatePolicy) => ({
  ...(currency !== 'USD' && { reporting_currency: currency }),
  ...(policy !== 'historical' && { rate_policy: policy }),
})
