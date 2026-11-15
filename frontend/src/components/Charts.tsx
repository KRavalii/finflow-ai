import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import type { FinancialSummary } from '../types/financial'
import { decimalMoney } from '../utils/finance'
import { currencyLocales } from '../hooks/CurrencyContext'

const colors = ['#23836a', '#72aa95', '#b2cdb5', '#d1b982', '#8e9eae', '#c8a4a4', '#a09fbd', '#ccd5d0']

export default function Charts({ summary }: { summary: FinancialSummary }) {
  const chartMoney = (value: unknown) => new Intl.NumberFormat(currencyLocales[summary.currency], { style: 'currency', currency: summary.currency }).format(Number(value))
  const tooltipMoney = (value: unknown, name: unknown, item: { payload?: Record<string, unknown> }) => {
    const row = item.payload
    const exact = row?.total ?? (name === 'Income' ? row?.exactIncome : row?.exactExpense)
    return exact !== undefined ? decimalMoney(String(exact), summary.currency) : chartMoney(value)
  }
  const data = {
    months: summary.monthly_trends.map(month => ({ month: month.month,
      label: new Date(`${month.month}-01T12:00:00`).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      income: Number(month.income), expense: Number(month.expenses), exactIncome: month.income, exactExpense: month.expenses,
    })),
    categories: summary.spending_by_category.map(category => ({ name: category.category, value: Number(category.total), total: category.total })),
  }
  return <div className="charts-grid">
    <section className="panel chart-panel" aria-labelledby="cash-flow-heading"><div className="panel-heading"><div><h2 id="cash-flow-heading">Income vs. expenses</h2><p>A clearer view of your cash flow over time</p></div><div className="chart-legend"><span><i className="income-dot" />Income</span><span><i className="expense-dot" />Expenses</span></div></div>
      {data.months.length ? <><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart accessibilityLayer data={data.months} barGap={5} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}><CartesianGrid vertical={false} stroke="#edf0ec" strokeDasharray="3 3" /><XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#7a867e', fontSize: 11 }} dy={9} minTickGap={18} /><YAxis axisLine={false} tickLine={false} tick={{ fill: '#7a867e', fontSize: 11 }} tickFormatter={value => chartMoney(value)} width={85} /><Tooltip formatter={tooltipMoney} cursor={{ fill: '#f3f6f3' }} contentStyle={{ border: '1px solid #e5eae5', borderRadius: 10, fontSize: 12 }} /><Bar name="Income" dataKey="income" fill="#23836a" radius={[4, 4, 0, 0]} maxBarSize={28} /><Bar name="Expenses" dataKey="expense" fill="#c9d7cd" radius={[4, 4, 0, 0]} maxBarSize={28} /></BarChart></ResponsiveContainer></div><details className="chart-details"><summary>View cash flow data</summary><div className="table-scroll"><table><caption className="sr-only">Monthly income and expenses in {summary.currency}</caption><thead><tr><th>Month</th><th>Income</th><th>Expenses</th></tr></thead><tbody>{data.months.map(month => <tr key={month.month}><td>{month.label}</td><td>{decimalMoney(month.exactIncome, summary.currency)}</td><td>{decimalMoney(month.exactExpense, summary.currency)}</td></tr>)}</tbody></table></div></details></> : <div className="chart-empty">Your cash flow chart will appear when you add transactions.</div>}
    </section>
    <section className="panel chart-panel spending-panel" aria-labelledby="spending-heading"><div className="panel-heading"><div><h2 id="spending-heading">Spending breakdown</h2><p>Where your money is going</p></div><span className="subtle-badge">By category</span></div>
      {data.categories.length ? <><div className="donut-wrap"><ResponsiveContainer width="100%" height="100%"><PieChart accessibilityLayer><Pie data={data.categories} dataKey="value" nameKey="name" innerRadius="67%" outerRadius="90%" paddingAngle={3} stroke="none">{data.categories.map((category, index) => <Cell key={category.name} fill={colors[index % colors.length]} />)}</Pie><Tooltip formatter={tooltipMoney} contentStyle={{ borderRadius: 10, fontSize: 12 }} /></PieChart></ResponsiveContainer><div className="donut-label"><span>Total expenses</span><strong>{decimalMoney(summary.expenses, summary.currency)}</strong></div></div><ul className="category-legend">{data.categories.map((category, index) => <li key={category.name}><span><i style={{ backgroundColor: colors[index % colors.length] }} />{category.name}</span><strong>{decimalMoney(category.total, summary.currency)}</strong></li>)}</ul></> : <div className="chart-empty">Add an expense to see your spending by category.</div>}
    </section>
  </div>
}
