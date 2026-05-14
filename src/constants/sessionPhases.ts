/**
 * Session phase definitions for commit #83.
 *
 * 5-phase pedagogical model mapped to the linear session step order:
 * - Orient  (listen    — hear the target sound)
 * - Isolate (study     — break it down and understand)
 * - Refine  (slow      — slow practice to build muscle memory)
 * - Apply   (play      — play with the band)
 * - Reflect (review    — honest specific feedback)
 */

import { type SessionStep } from "@/src/constants/sessionFlow";

/** The 5 session phases in step order. */
export const SESSION_PHASES = [
  "orient",
  "isolate",
  "refine",
  "apply",
  "reflect",
] as const;
export type SessionPhase = (typeof SESSION_PHASES)[number];

/** Steps that belong to each phase. */
export const PHASE_STEPS: Record<SessionPhase, SessionStep[]> = {
  orient: ["listen"],
  isolate: ["study"],
  refine: ["slow"],
  apply: ["play"],
  reflect: ["review"],
};

/** Phase index for each session step. Pre-flight steps (tune, warmup, mood-check, musical-tolerance) are not in phases. */
export const PHASE_FOR_STEP: Record<SessionStep, SessionPhase | null> = {
  tune: null,
  "musical-tolerance": null,
  listen: "orient",
  study: "isolate",
  slow: "refine",
  play: "apply",
  review: "reflect",
};

/** Voice coach narration copy for phase transitions. */
export const PHASE_TRANSITION_COPY: Record<
  SessionPhase,
  {
    enter: string;
    description: string;
  }
> = {
  orient: {
    enter: "Let's start by hearing the target sound.",
    description:
      "Listen carefully to the melody and rhythm to get familiar with the music.",
  },
  isolate: {
    enter: "Now let's break it down and understand each part.",
    description: "Study the notes and play them slowly to build muscle memory.",
  },
  refine: {
    enter: "",
    description: "",
  },
  apply: {
    enter: "Time to play along with the band.",
    description: "Apply what you've learned by playing with the backing track.",
  },
  reflect: {
    enter: "Let's review your performance.",
    description: "Review your accuracy and identify areas for improvement.",
  },
};

/** Minimum completion conditions for advancing to the next phase. */
export const PHASE_COMPLETION_CONDITIONS: Record<
  SessionPhase,
  {
    minSteps: number;
    description: string;
  }
> = {
  orient: {
    minSteps: 1,
    description: "Listen to the full track at least once",
  },
  isolate: {
    minSteps: 1,
    description: "Complete at least one study or slow practice session",
  },
  refine: {
    minSteps: 0,
    description: "",
  },
  apply: {
    minSteps: 1,
    description: "Play along with the backing track at least once",
  },
  reflect: {
    minSteps: 1,
    description: "Review your performance",
  },
};

/** Get the phase for a given session step. Returns null for pre-flight steps. */
export function getPhaseForStep(step: SessionStep): SessionPhase | null {
  return PHASE_FOR_STEP[step] ?? null;
}

/** Get the index of a phase in SESSION_PHASES. */
export function getPhaseIndex(phase: SessionPhase): number {
  return SESSION_PHASES.indexOf(phase);
}
