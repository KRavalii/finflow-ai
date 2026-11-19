import { useProfiles } from '../hooks/ProfilesContext'
import { isDemoMode } from '../demo'
import ProfileManager from './ProfileManager'
import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { ArrowUpRight, ArrowDownUp, Bot, ChartNoAxesCombined, ChevronRight, CircleDollarSign, LayoutDashboard, Menu, RefreshCw, X } from 'lucide-react'
import { useTransactions } from '../hooks/TransactionsContext'
import { useCurrency, currencies, type Currency, type RatePolicy } from '../hooks/CurrencyContext'

export default function Layout() {
  const { profiles, selected, select, label, migrationPending, writable } = useProfiles()
  const [open, setOpen] = useState(false)
  const navigation = useRef<HTMLElement>(null)
  const menuButton = useRef<HTMLButtonElement>(null)
  const { pathname } = useLocation()
  const { loading, error, refresh } = useTransactions()
  const { currency, policy, setCurrency, setPolicy } = useCurrency()
  const title = pathname === '/transactions' ? 'Transactions' : pathname === '/analytics' ? 'Analytics' : pathname === '/assistant' ? 'AI Assistant' : 'Overview'
  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    navigation.current?.querySelector<HTMLElement>('nav a')?.focus()
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
      if (event.key === 'Tab') {
        const elements = navigation.current?.querySelectorAll<HTMLElement>('a, button:not(:disabled)')
        if (!elements?.length) return
        const first = elements[0]
        const last = elements[elements.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }
    }
    window.addEventListener('keydown', close)
    return () => { window.removeEventListener('keydown', close); document.body.style.overflow = previousOverflow; menuButton.current?.focus() }
  }, [open])
  return <div className="app-shell">
    <a href="#main-content" className="skip-link">Skip to content</a>
    {open && <button tabIndex={-1} className="nav-overlay" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside ref={navigation} className={`sidebar ${open ? 'is-open' : ''}`}>
      <a href="/" className="brand"><span className="brand-mark"><ChartNoAxesCombined size={23} /></span>finflow<span className="brand-ai">AI</span></a>
      <button className="icon-button nav-close" aria-label="Close navigation" onClick={() => setOpen(false)}><X size={20} /></button>
      <p className="nav-caption">WORKSPACE</p>
      <nav aria-label="Main navigation">
        <NavLink to="/" end><LayoutDashboard size={19} />Overview</NavLink>
        <NavLink to="/transactions"><ArrowDownUp size={19} />Transactions</NavLink>
        <NavLink to="/analytics"><ChartNoAxesCombined size={19} />Analytics</NavLink>
        <NavLink to="/assistant"><Bot size={19} />AI Assistant</NavLink>
      </nav>
      <div className="sidebar-note"><span className="note-icon"><CircleDollarSign size={22} /></span><h3>A little clarity.<br />A lot of possibility.</h3><p>Know where your money goes. Make room for what matters.</p><span className="note-line" /></div>
      <div className="sidebar-footer"><span className="avatar">F</span><div><strong>Personal workspace</strong><span>Your finances, in focus</span></div><ArrowUpRight size={17} /></div>
    </aside>
    <div className="main-shell" inert={open ? true : undefined}>
      <header className="topbar">
        <div className="breadcrumb"><button ref={menuButton} className="icon-button menu-toggle" aria-label="Open navigation" aria-expanded={open} onClick={() => setOpen(true)}><Menu size={21} /></button><span>Workspace</span><ChevronRight size={14} /><strong>{title}</strong></div>
        <div className="top-actions"><label className="reporting-select profile-select"><span className="sr-only">Financial profile</span><select disabled={migrationPending} value={selected ?? ''} onChange={event => select(event.target.value === 'all' ? 'all' : Number(event.target.value))}>{migrationPending ? <option value="">My Profile</option> : <>{profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}{profile.archived_at ? ' (archived)' : ''}</option>)}<option value="all">All Profiles (including archived)</option></>}</select></label><ProfileManager /><span className={`connection ${error ? 'offline' : ''}`}><i />{error ? 'Connection issue' : loading ? 'Syncing data' : 'Data synced'}</span><label className="reporting-select currency-select"><span className="sr-only">Reporting currency</span><select value={currency} onChange={event => setCurrency(event.target.value as Currency)}>{currencies.map(code => <option key={code}>{code}</option>)}</select></label><label className="reporting-select policy-select"><span className="sr-only">Conversion policy</span><select value={policy} onChange={event => setPolicy(event.target.value as RatePolicy)}><option value="historical">Historical rates</option><option value="latest">Latest valuation</option></select></label><button className="icon-button refresh-button" aria-label="Refresh transactions" disabled={loading} onClick={() => void refresh()}><RefreshCw size={17} className={loading ? 'spin' : ''} /></button><span className="avatar light">F</span></div>
      </header>
      <main id="main-content" tabIndex={-1}>{isDemoMode() && <p role="status" className="demo-banner">Public demo: all financial data is fictional. Editing is disabled.</p>}{migrationPending && <p role="status">Profiles require approved database migration 0003. Existing finances remain available.</p>}<p className="profile-scope">{label}{!writable && (isDemoMode() ? ' ? Read-only demo' : ' ? Read-only view. Select an active profile to add a transaction.')}</p><Outlet /></main>
      <footer className="page-footer"><span>FinFlow AI · A clearer financial picture</span><span>Reporting in {currency}; originals preserved</span></footer>
    </div>
  </div>
}
