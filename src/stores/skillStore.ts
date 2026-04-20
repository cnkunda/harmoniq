import { create } from 'zustand'

import { applySessionMutation as persistSessionMutation, getAllSkillNodes } from '@/src/db/client'
import type { SkillNodeRow, SkillSessionMutationRow } from '@/src/db/types'

export interface SkillStoreState {
  nodes: SkillNodeRow[]
  /** Loads skill_nodes from SQLite (native) or in-memory mirror (web). */
  loadFromDb: () => Promise<void>
  /** Commit 63: persist technique EMA + rolling history after Review. */
  applySessionMutation: (updates: SkillSessionMutationRow[]) => Promise<void>
}

export const useSkillStore = create<SkillStoreState>((set) => ({
  nodes: [],

  loadFromDb: async () => {
    const rows = await getAllSkillNodes()
    set({ nodes: rows })
  },

  applySessionMutation: async (updates) => {
    await persistSessionMutation(updates)
    const rows = await getAllSkillNodes()
    set({ nodes: rows })
  },
}))
