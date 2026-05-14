/**
 * Session phase store for commit #83.
 * 
 * Tracks current phase, step within phase, and phase completion status
 * for the 4-phase pedagogical model: Orient → Isolate → Apply → Reflect.
 */

import type { SessionStep } from '@/src/constants/sessionFlow'
import type { SessionPhase } from '@/src/constants/sessionPhases'
import {
    getNextPhase,
    getPhaseFirstStep,
    getPhaseForStep,
    getPreviousPhase
} from '@/src/constants/sessionPhases'
import { create } from 'zustand'

interface PhaseCompletion {
  /** Whether the phase has been completed */
  completed: boolean
  /** Timestamp when phase was completed */
  completedAt: string | null
  /** Number of steps completed in this phase */
  stepsCompleted: number
}

interface SessionPhaseState {
  /** Current active phase */
  currentPhase: SessionPhase | null
  /** Current step within the phase (session step name) */
  currentStepWithinPhase: SessionStep | null
  /** Completion status for each phase */
  phaseCompletion: Record<SessionPhase, PhaseCompletion>
  
  /** Actions */
  setCurrentPhase: (phase: SessionPhase | null) => void
  setCurrentStepWithinPhase: (step: SessionStep | null) => void
  advanceToNextPhase: () => void
  goToPreviousPhase: () => void
  markPhaseCompleted: (phase: SessionPhase) => void
  resetPhaseCompletion: (phase: SessionPhase) => void
  resetAllPhaseCompletion: () => void
  syncPhaseFromStep: (step: SessionStep) => void
}

export const useSessionPhaseStore = create<SessionPhaseState>((set, get) => ({
  currentPhase: null,
  currentStepWithinPhase: null,
  phaseCompletion: {
    orient: { completed: false, completedAt: null, stepsCompleted: 0 },
    isolate: { completed: false, completedAt: null, stepsCompleted: 0 },
    apply: { completed: false, completedAt: null, stepsCompleted: 0 },
    refine: { completed: false, completedAt: null, stepsCompleted: 0 },
    reflect: { completed: false, completedAt: null, stepsCompleted: 0 },
  },

  setCurrentPhase: (phase) => set({ currentPhase: phase }),

  setCurrentStepWithinPhase: (step) => set({ currentStepWithinPhase: step }),

  advanceToNextPhase: () => {
    const { currentPhase, phaseCompletion } = get()
    if (!currentPhase) return

    // Mark current phase as completed
    const now = new Date().toISOString()
    set({
      phaseCompletion: {
        ...phaseCompletion,
        [currentPhase]: {
          ...phaseCompletion[currentPhase],
          completed: true,
          completedAt: now,
        },
      },
    })

    // Advance to next phase
    const nextPhase = getNextPhase(currentPhase)
    if (nextPhase) {
      const firstStep = getPhaseFirstStep(nextPhase)
      set({
        currentPhase: nextPhase,
        currentStepWithinPhase: firstStep,
      })
    }
  },

  goToPreviousPhase: () => {
    const { currentPhase } = get()
    if (!currentPhase) return

    const previousPhase = getPreviousPhase(currentPhase)
    if (previousPhase) {
      const firstStep = getPhaseFirstStep(previousPhase)
      set({
        currentPhase: previousPhase,
        currentStepWithinPhase: firstStep,
      })
    }
  },

  markPhaseCompleted: (phase) => {
    const { phaseCompletion } = get()
    const now = new Date().toISOString()
    set({
      phaseCompletion: {
        ...phaseCompletion,
        [phase]: {
          ...phaseCompletion[phase],
          completed: true,
          completedAt: now,
        },
      },
    })
  },

  resetPhaseCompletion: (phase) => {
    const { phaseCompletion } = get()
    set({
      phaseCompletion: {
        ...phaseCompletion,
        [phase]: {
          completed: false,
          completedAt: null,
          stepsCompleted: 0,
        },
      },
    })
  },

  resetAllPhaseCompletion: () => {
    set({
      phaseCompletion: {
        orient: { completed: false, completedAt: null, stepsCompleted: 0 },
        isolate: { completed: false, completedAt: null, stepsCompleted: 0 },
        apply: { completed: false, completedAt: null, stepsCompleted: 0 },
        refine: { completed: false, completedAt: null, stepsCompleted: 0 },
        reflect: { completed: false, completedAt: null, stepsCompleted: 0 },
      },
      currentPhase: null,
      currentStepWithinPhase: null,
    })
  },

  syncPhaseFromStep: (step) => {
    const phase = getPhaseForStep(step)
    set({
      currentPhase: phase,
      currentStepWithinPhase: step,
    })
  },
}))
