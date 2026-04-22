/**
 * User feedback collection for coach redundancy perception (commit 90).
 * Tracks user perceptions of whether coach feedback feels repetitive.
 */

const FEEDBACK_KEY = 'harmoniq_coach_feedback'

export type CoachFeedbackRating = 'helpful' | 'repetitive' | 'neutral' | 'skipped'

export interface CoachFeedbackEntry {
  timestamp: number
  focus_area: string | null
  rating: CoachFeedbackRating
  session_count: number
}

/**
 * Record user feedback on coach feedback redundancy perception.
 */
export async function recordCoachFeedback(feedback: Omit<CoachFeedbackEntry, 'timestamp'>): Promise<void> {
  try {
    // @ts-expect-error - AsyncStorage may not be available in web builds
    const { AsyncStorage } = await import('@react-native-async-storage/async-storage')
    const raw = await AsyncStorage.getItem(FEEDBACK_KEY)
    const entries: CoachFeedbackEntry[] = raw ? JSON.parse(raw) : []
    entries.push({ ...feedback, timestamp: Date.now() })
    await AsyncStorage.setItem(FEEDBACK_KEY, JSON.stringify(entries))
  } catch {
    // Fallback to localStorage for web
    try {
      const raw = localStorage.getItem(FEEDBACK_KEY)
      const entries: CoachFeedbackEntry[] = raw ? JSON.parse(raw) : []
      entries.push({ ...feedback, timestamp: Date.now() })
      localStorage.setItem(FEEDBACK_KEY, JSON.stringify(entries))
    } catch {
      // Ignore errors
    }
  }
}

/**
 * Get all coach feedback entries.
 */
export async function getCoachFeedbackEntries(): Promise<CoachFeedbackEntry[]> {
  try {
    // @ts-expect-error - AsyncStorage may not be available in web builds
    const { AsyncStorage } = await import('@react-native-async-storage/async-storage')
    const raw = await AsyncStorage.getItem(FEEDBACK_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    try {
      const raw = localStorage.getItem(FEEDBACK_KEY)
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  }
}

/**
 * Calculate the percentage of feedback marked as "repetitive".
 * Used to measure effectiveness of focus area variation.
 */
export async function getRepetitiveFeedbackPercentage(): Promise<number> {
  const entries = await getCoachFeedbackEntries()
  if (entries.length === 0) return 0
  const repetitiveCount = entries.filter((e) => e.rating === 'repetitive').length
  return (repetitiveCount / entries.length) * 100
}

/**
 * Clear all coach feedback entries (useful for testing).
 */
export async function clearCoachFeedback(): Promise<void> {
  try {
    // @ts-expect-error - AsyncStorage may not be available in web builds
    const { AsyncStorage } = await import('@react-native-async-storage/async-storage')
    await AsyncStorage.removeItem(FEEDBACK_KEY)
  } catch {
    try {
      localStorage.removeItem(FEEDBACK_KEY)
    } catch {
      // Ignore errors
    }
  }
}
