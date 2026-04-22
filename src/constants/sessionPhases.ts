/**
 * Session phase definitions for commit #83.
 * 
 * Restructures the linear session into a 4-phase pedagogical model:
 * - Orient (hear the target)
 * - Isolate (understand and break down)
 * - Apply (play with a responsive band)
 * - Reflect (honest specific feedback)
 */

import { type SessionStep } from '@/src/constants/sessionFlow'

/** The 4 session phases in order. */
export const SESSION_PHASES = ['orient', 'isolate', 'apply', 'reflect'] as const
export type SessionPhase = (typeof SESSION_PHASES)[number]

/** Steps that belong to each phase. */
export const PHASE_STEPS: Record<SessionPhase, SessionStep[]> = {
  orient: ['orient', 'listen'],
  isolate: ['study', 'slow'],
  apply: ['play'],
  reflect: ['review'],
}

/** Phase index for each session step. Pre-flight steps (tune, warmup, mood-check) are not in phases. */
export const PHASE_FOR_STEP: Record<SessionStep, SessionPhase | null> = {
  tune: null, // Pre-flight
  orient: 'orient',
  listen: 'orient',
  study: 'isolate',
  slow: 'isolate',
  play: 'apply',
  review: 'reflect',
}

/** Voice coach narration copy for phase transitions. */
export const PHASE_TRANSITION_COPY: Record<SessionPhase, {
  enter: string
  description: string
}> = {
  orient: {
    enter: "Let's start by hearing the target sound.",
    description: "Listen carefully to the melody and rhythm to get familiar with the music.",
  },
  isolate: {
    enter: "Now let's break it down and understand each part.",
    description: "Study the notes and play them slowly to build muscle memory.",
  },
  apply: {
    enter: "Time to play along with the band.",
    description: "Apply what you've learned by playing with the backing track.",
  },
  reflect: {
    enter: "Let's review your performance.",
    description: "Review your accuracy and identify areas for improvement.",
  },
}

/** Minimum completion conditions for advancing to the next phase. */
export const PHASE_COMPLETION_CONDITIONS: Record<SessionPhase, {
  minSteps: number
  description: string
}> = {
  orient: {
    minSteps: 1,
    description: "Listen to the full track at least once",
  },
  isolate: {
    minSteps: 1,
    description: "Complete at least one study or slow practice session",
  },
  apply: {
    minSteps: 1,
    description: "Play along with the backing track at least once",
  },
  reflect: {
    minSteps: 1,
    description: "Review your performance",
  },
}

/** Get the phase for a given session step. Returns null for pre-flight steps. */
export function getPhaseForStep(step: SessionStep): SessionPhase | null {
  return PHASE_FOR_STEP[step] ?? null
}

/** Get the index of a phase. */
export function getPhaseIndex(phase: SessionPhase): number {
  return SESSION_PHASES.indexOf(phase)
}

/** Get the next phase, or null if at the last phase. */
export function getNextPhase(currentPhase: SessionPhase): SessionPhase | null {
  const index = getPhaseIndex(currentPhase)
  if (index === -1 || index === SESSION_PHASES.length - 1) {
    return null
  }
  return SESSION_PHASES[index + 1]
}

/** Get the previous phase, or null if at the first phase. */
export function getPreviousPhase(currentPhase: SessionPhase): SessionPhase | null {
  const index = getPhaseIndex(currentPhase)
  if (index <= 0) {
    return null
  }
  return SESSION_PHASES[index - 1]
}

/** Get the first step of a phase. */
export function getPhaseFirstStep(phase: SessionPhase): SessionStep | null {
  const steps = PHASE_STEPS[phase]
  return steps.length > 0 ? steps[0] : null
}

/** Get the last step of a phase. */
export function getPhaseLastStep(phase: SessionPhase): SessionStep | null {
  const steps = PHASE_STEPS[phase]
  return steps.length > 0 ? steps[steps.length - 1] : null
}

/** Check if a step is the last step in its phase. */
export function isLastStepInPhase(step: SessionStep): boolean {
  const phase = getPhaseForStep(step)
  if (!phase) return false
  const lastStep = getPhaseLastStep(phase)
  return lastStep === step
}

/** Check if a step is the first step in its phase. */
export function isFirstStepInPhase(step: SessionStep): boolean {
  const phase = getPhaseForStep(step)
  if (!phase) return false
  const firstStep = getPhaseFirstStep(phase)
  return firstStep === step
}
