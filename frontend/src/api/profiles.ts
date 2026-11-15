import { api } from './transactions'
import type { Profile } from '../types/profile'

export async function fetchProfiles(signal?: AbortSignal): Promise<Profile[]> {
  return (await api.get<Profile[]>('/profiles', { params: { include_archived: true }, signal })).data
}
export async function createProfile(name: string): Promise<Profile> {
  return (await api.post<Profile>('/profiles', { name })).data
}
export async function updateProfile(id: number, patch: { name?: string; archived?: boolean }): Promise<Profile> {
  return (await api.patch<Profile>(`/profiles/${id}`, patch)).data
}
