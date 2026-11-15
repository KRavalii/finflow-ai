import axios from 'axios'
import { isDemoMode } from '../demo'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { fetchProfiles } from '../api/profiles'
import type { Profile, ProfileSelection } from '../types/profile'

interface ProfilesState {
  profiles: Profile[]
  selected: ProfileSelection | undefined
  label: string
  ready: boolean
  writable: boolean
  error: string | null
  migrationPending: boolean
  select: (id: ProfileSelection) => void
  reload: () => Promise<void>
}
const Context = createContext<ProfilesState>({ profiles: [], selected: undefined, label: 'My Profile', ready: true,
  writable: true, error: null, migrationPending: false, select: () => {}, reload: async () => {} })

function saved(): ProfileSelection | undefined {
  try {
    const value = localStorage.getItem('finflow.profile')
    return value === 'all' ? 'all' : value && /^[1-9]\d*$/.test(value) ? Number(value) : undefined
  } catch { return undefined }
}
function persist(value: ProfileSelection) {
  try { localStorage.setItem('finflow.profile', String(value)) } catch { /* Selection works without storage. */ }
}

export function ProfilesProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [selected, setSelected] = useState<ProfileSelection | undefined>(saved)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [migrationPending, setMigrationPending] = useState(false)

  function accept(items: Profile[]) {
    const defaultProfile = items.find(item => item.is_default && !item.archived_at)
    if (!defaultProfile) throw new Error('Default profile is missing')
    setProfiles(items)
    setSelected(current => {
      const value = current === 'all' || items.some(item => item.id === current && !item.archived_at) ? current! : defaultProfile.id
      persist(value)
      return value
    })
    setError(null); setMigrationPending(false); setReady(true)
  }
  function fail(error: unknown) {
    if (axios.isAxiosError(error) && error.response?.data?.detail?.code === 'profiles_migration_required') {
      setProfiles([]); setSelected(undefined); setMigrationPending(true); setError(null); setReady(true)
    } else { setError('Unable to load profiles. Retry before viewing financial data.'); setReady(false) }
  }
  useEffect(() => {
    const controller = new AbortController()
    fetchProfiles(controller.signal).then(items => { if (!controller.signal.aborted) accept(items) })
      .catch(error => { if (!controller.signal.aborted) fail(error) })
    return () => controller.abort()
  }, [])
  async function reload() {
    try { accept(await fetchProfiles()) } catch (error) { fail(error) }
  }
  const profile = profiles.find(item => item.id === selected)
  const label = selected === 'all' ? 'All Profiles (including archived)' : profile?.name || 'My Profile'
  return <Context.Provider value={{ profiles, selected, label, ready, error, migrationPending,
    writable: !isDemoMode() && ready && selected !== 'all' && !profile?.archived_at,
    select: value => { setSelected(value); persist(value) }, reload }}>
    {error ? <div role="alert">{error}<button onClick={() => void reload()}>Retry profiles</button></div> : !ready ? <p role="status">Loading profiles…</p> : children}
  </Context.Provider>
}
export const useProfiles = () => useContext(Context)
export const profileOptions = (selected: ProfileSelection | undefined) => selected === undefined ? {} : { profile_id: selected }
