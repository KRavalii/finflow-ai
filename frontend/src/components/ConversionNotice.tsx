import type { FinancialSummary } from '../types/financial'

export default function ConversionNotice({ summary }: { summary: FinancialSummary }) {
  const dates = [...new Set((summary.rates || []).map(rate => rate.rate_date))].sort()
  return <p className="conversion-notice">Reporting in {summary.currency}. {summary.rate_policy === 'latest' ? 'Latest-rate valuation' : 'Historical transaction-date conversion'}; each transaction is rounded half-up before totals.
    {dates.length ? ` Published rate dates: ${dates.length > 4 ? `${dates[0]} through ${dates[dates.length - 1]}` : dates.join(', ')}.` : ' No exchange rate required.'}
    {summary.rates?.some(rate => rate.requested_date && rate.requested_date !== rate.rate_date) && ' A prior published rate was used (maximum 7-day lookback).'}
  </p>
}
