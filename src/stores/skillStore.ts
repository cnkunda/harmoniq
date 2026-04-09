import { create } from 'zustand'

import { getAllSkillNodes } from '@/src/db/client'
import type { SkillNodeRow } from '@/src/db/types'

export interface SkillStoreState {
  nodes: SkillNodeRow[]
  /** Loads skill_nodes from SQLite (native) or in-memory mirror (web). */
  loadFromDb: () => Promise<void>
}

export const useSkillStore = create<SkillStoreState>((set) => ({
  nodes: [],

  loadFromDb: async () => {
    const rows = await getAllSkillNodes()
    set({ nodes: rows })
  },
}))
