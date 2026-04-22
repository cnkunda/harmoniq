/**
 * Types for transcription pipeline data structures (ChordTimeline, SoloNotes, etc.)
 * These mirror the backend Pydantic models in backend/app/schemas.py
 */

export interface ChordEvent {
  timestamp: number
  chord: string
  confidence: number
}

export interface ChordTimeline {
  events: ChordEvent[]
}

export interface SoloNote {
  start_time: number
  duration: number
  pitch: number
  velocity?: number
}

export interface SoloNotes {
  notes: SoloNote[]
}
