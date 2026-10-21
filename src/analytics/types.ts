/** Typed event contract for local-only practice analytics (Commit 161). */

export type AnalyticsEventType =
  | 'session_start'
  | 'session_complete'
  | 'session_step_progress'
  | 'session_abandon'
  | 'play_along_start'
  | 'play_along_complete'
  | 'play_along_discard'
  | 'feature_usage'
  | 'correction_made'
  | 'jam_complete'

export type AnalyticsFeature = 'practice_insights' | 'analytics_export'

export type AnalyticsFeedbackType = 'chord_correction' | 'note_correction' | 'wrong_chord'

export type AnalyticsEventPayloads = {
  session_start: {
    song_title: string | null
    step: string
  }
  session_complete: {
    song_title: string | null
    duration_sec: number
    final_step: string
    started_at: string
  }
  session_step_progress: {
    from_step: string
    to_step: string
    elapsed_sec: number
  }
  session_abandon: {
    song_title: string | null
    duration_sec: number
    last_step: string
  }
  play_along_start: {
    tempo_bpm: number | null
  }
  play_along_complete: {
    duration_sec: number
    tempo_bpm: number | null
    reason: 'done' | 'silence'
  }
  play_along_discard: {
    duration_sec: number
  }
  feature_usage: {
    feature: AnalyticsFeature
    event_count?: number
  }
  correction_made: {
    job_id: string
    feedback_type: AnalyticsFeedbackType
    event_index: number
  }
  jam_complete: {
    duration_sec: number
    track_id: string | null
    track_label: string | null
    inferred_scale_label: string | null
  }
}

type AnalyticsEventFor<T extends AnalyticsEventType> = {
  type: T
  payload: AnalyticsEventPayloads[T]
  id?: string
  timestamp?: string
}

/** Discriminated union accepted by `emit()`. */
export type AnalyticsEvent = {
  [T in AnalyticsEventType]: AnalyticsEventFor<T>
}[AnalyticsEventType]

export type NormalizedAnalyticsEvent = {
  [T in AnalyticsEventType]: {
    type: T
    payload: AnalyticsEventPayloads[T]
    id: string
    timestamp: string
  }
}[AnalyticsEventType]
