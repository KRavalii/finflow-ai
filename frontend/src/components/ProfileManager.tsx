import { useState, type FormEvent } from 'react'
import { isDemoMode } from '../demo'
import { createProfile, updateProfile } from '../api/profiles'
import { useProfiles } from '../hooks/ProfilesContext'

export default function ProfileManager() {
  const { profiles, reload, migrationPending } = useProfiles()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [names, setNames] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function change(action: () => Promise<unknown>) {
    setBusy(true); setError('')
    try { await action(); await reload() } catch { setError('Unable to save profile. Your transactions have not been changed.') }
    finally { setBusy(false) }
  }
  function add(event: FormEvent) {
    event.preventDefault()
    void change(async () => { await createProfile(name.trim()); setName('') })
  }
  if (isDemoMode()) return null
  return <div className="profile-management">
    <button className="button secondary" disabled={migrationPending} onClick={() => setOpen(!open)} aria-expanded={open}>Manage profiles</button>
    {open && <section className="panel profile-manager" aria-label="Manage profiles"><h2>Financial profiles</h2>
      <p>Keep each person’s finances separate. Archived profiles retain their transactions and are read-only.</p>
      <fieldset disabled={busy}><legend className="sr-only">Profile settings</legend>
        {profiles.map(profile => <div className="profile-row" key={profile.id}>
          <label>{profile.name}{profile.archived_at ? ' (archived)' : ''}<input aria-label={`Name for ${profile.name}`} required maxLength={100} value={names[profile.id] ?? profile.name} onChange={event => setNames({ ...names, [profile.id]: event.target.value })} /></label>
          <button disabled={!(names[profile.id] ?? profile.name).trim()} onClick={() => void change(() => updateProfile(profile.id, { name: (names[profile.id] ?? profile.name).trim() }))}>Rename {profile.name}</button>
          {!profile.is_default && <button onClick={() => void change(() => updateProfile(profile.id, { archived: !profile.archived_at }))}>{profile.archived_at ? 'Restore' : 'Archive'} {profile.name}</button>}
        </div>)}
        <form onSubmit={add}><label>New profile name<input required maxLength={100} value={name} onChange={event => setName(event.target.value)} placeholder="Mom, Dad, Brother, Friends…" /></label><button disabled={!name.trim()} type="submit">Create profile</button></form>
      </fieldset>{error && <p role="alert">{error}</p>}
      <button onClick={() => setOpen(false)}>Close profiles</button>
    </section>}
  </div>
}
