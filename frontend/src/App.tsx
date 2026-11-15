import { ProfilesProvider, useProfiles } from './hooks/ProfilesContext'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { TransactionsProvider } from './hooks/TransactionsContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Assistant from './pages/Assistant'
import { CurrencyProvider } from './hooks/CurrencyContext'

function Workspace() {
  const { selected, migrationPending } = useProfiles()
  return <TransactionsProvider key={migrationPending ? 'legacy' : selected}><Routes><Route element={<Layout />}><Route index element={<Dashboard />} /><Route path="transactions" element={<Transactions />} /><Route path="analytics" element={<Dashboard analyticsOnly />} /><Route path="assistant" element={<Assistant />} /><Route path="*" element={<div className="empty-state"><h1>Page not found</h1><p>Let’s get back to your financial overview.</p><Link className="button primary" to="/">Back to overview</Link></div>} /></Route></Routes></TransactionsProvider>
}

export default function App() {
  return <BrowserRouter><CurrencyProvider><ProfilesProvider><Workspace /></ProfilesProvider></CurrencyProvider></BrowserRouter>
}
