/**
 * Daily lick rotation — deterministic Slonimsky pattern selection for the home screen.
 *
 * Picks one pattern per day (seeded by YYYYMMDD) and manages dismissal state
 * via app preferences. The selected pattern is auto-inserted into the licks
 * table on first daily view.
 */

import { getAppPref, insertLickRow, setAppPref } from '@/src/db/client'
import { PREF_DAILY_LICK_DISMISSED } from '@/src/db/schema'
import type { LickInsertInput } from '@/src/db/types'
import {
  dailySeedFromDate,
  generateDailyWarmup,
  type SlonimskyPattern,
} from '@/src/music/slonimskyGenerator'

export interface DailyLick {
  id: string
  name: string
  description: string
  pattern: SlonimskyPattern
  date: string
}

/**
 * Get today's daily lick.
 * Deterministic: always returns the same lick for the same date.
 */
export function getDailyLick(date?: Date): DailyLick {
  const d = date ?? new Date()
  const seed = dailySeedFromDate(d)
  const result = generateDailyWarmup(seed)
  const isoDate = d.toISOString().slice(0, 10)
  return {
    id: `daily-lick-${isoDate}`,
    name: result.pattern.name,
    description: result.pattern.description,
    pattern: result.pattern,
    date: isoDate,
  }
}

/** Storage key e.g. "daily_lick_dismissed_2026-07-17". */
export function getDailyLickKey(date?: Date): string {
  const d = date ?? new Date()
  return `${PREF_DAILY_LICK_DISMISSED}${d.toISOString().slice(0, 10)}`
}

/**
 * Check whether today's lick has been dismissed.
 */
export async function isDailyLickDismissed(date?: Date): Promise<boolean> {
  const key = getDailyLickKey(date)
  const val = await getAppPref(key)
  return val === '1'
}

/**
 * Mark today's lick as dismissed so it won't show again.
 */
export async function dismissDailyLick(date?: Date): Promise<void> {
  const key = getDailyLickKey(date)
  await setAppPref(key, '1')
}

/**
 * Persist today's daily lick to the licks table.
 * Safe to call multiple times — insert is idempotent (upsert by convention).
 */
export async function persistDailyLick(date?: Date): Promise<void> {
  const lick = getDailyLick(date)
  const input: LickInsertInput = {
    id: lick.id,
    song_title: 'Daily Lick',
    artist: 'Slonimsky',
    key: null,
    scale: null,
    position: null,
    tab_gp5_base64: '',
    audio_segment_path: null,
    stems_json: null,
    coach_oneliner: lick.description,
    technique_tags: lick.pattern.techniqueTags,
    user_annotations: [],
    date_saved: lick.date,
  }
  try {
    await insertLickRow(input)
  } catch (e) {
    // Lick already inserted (duplicate id) — this is expected on subsequent daily views
    console.log('[DailyLick] already persisted for', lick.date)
  }
}
