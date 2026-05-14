/**
 * Session phase store for commit #83.
 * 
 * Tracks current phase from the active session step.
 */

import type { SessionStep } from '@/src/constants/sessionFlow'
import type { SessionPhase } from '@/src/constants/sessionPhases'
import {
    getPhaseForStep,
} from '@/src/constants/sessionPhases'
import { create } from 'zustand'

interface SessionPhaseState {
  /** Current active phase */
  currentPhase: SessionPhase | null
  /** Current step within the phase */
  currentStepWithinPhase: SessionStep | null
  /** Sync phase from the current session step */
  syncPhaseFromStep: (step: SessionStep) => void
}

export const useSessionPhaseStore = create<SessionPhaseState>((set) => ({
  currentPhase: null,
  currentStepWithinPhase: null,

  syncPhaseFromStep: (step) => {
    const phase = getPhaseForStep(step)
    set({
      currentPhase: phase,
      currentStepWithinPhase: step,
    })
  },
}))
