export interface Profile {
  id: number
  name: string
  created_at: string
  is_default: boolean
  archived_at: string | null
}
export type ProfileSelection = number | 'all'
