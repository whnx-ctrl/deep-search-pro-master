import { get, set } from 'idb-keyval'
import { z } from 'zod'
import { SessionSchema, type Session } from '../types/workbench'
const KEY = 'deep-search-pro-history-v1'
export async function loadHistory(): Promise<Session[]> {
  const value = await get(KEY)
  if (value === undefined) return []
  return z.array(SessionSchema).parse(value)
}
export async function saveHistory(sessions: Session[]) {
  await set(KEY, JSON.parse(JSON.stringify(sessions)))
}
