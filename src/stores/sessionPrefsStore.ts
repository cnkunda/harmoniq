import { create } from 'zustand'

import { getAppPref, setAppPref } from '@/src/db/client'
import {
  PREF_HOME_PRACTICE_MODE,
  PREF_LISTEN_NUDGE_DISMISSED,
  PREF_SESSION_INCLUDE_LISTEN,
  PREF_SESSION_MIC_CALIBRATION_JSON,
  PREF_SESSION_MIC_PROFILE_ID,
  PREF_SESSION_SKIP_TUNE,
} from '@/src/db/schema'

export type MicCalibrationProfileId = 'quiet-acoustic' | 'electric-unplugged'

/** Commit 164: Home hero mode — practice one song vs follow a generated plan. */
export type HomePracticeMode = 'single' | 'plan'

export const MIC_CALIBRATION_PROFILES: MicCalibrationProfileId[] = ['quiet-acoustic', 'electric-unplugged']

type CalibrationMap = Partial<Record<MicCalibrationProfileId, number>>

function isProfileId(s: string): s is MicCalibrationProfileId {
  return s === 'quiet-acoustic' || s === 'electric-unplugged'
}

function parseCalibrationJson(raw: string | null): CalibrationMap {
  if (!raw?.trim()) return {}
  try {
    const o = JSON.parse(raw) as unknown
    if (!o || typeof o !== 'object' || Array.isArray(o)) return {}
    const out: CalibrationMap = {}
    for (const id of MIC_CALIBRATION_PROFILES) {
      const v = (o as Record<string, unknown>)[id]
      if (typeof v === 'number' && Number.isFinite(v) && v >= 0) out[id] = v
    }
    return out
  } catch {
    return {}
  }
}

function serializeCalibrationJson(map: CalibrationMap): string {
  return JSON.stringify(map)
}

function currentLocalDayKey(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export type SessionPrefsState = {
  hydrated: boolean
  skipTuneStep: boolean
  activeMicProfile: MicCalibrationProfileId
  calibrationGateRmsByProfile: CalibrationMap
  /** `"1"` = include `/session/listen` at session start; `"0"` = go straight to Study (default). */
  includeListenStep: boolean
  /** Dismissed-date keys for the "Listen first" first-run nudge. */
  listenNudgeDismissed: Record<string, true>
  /** Commit 164: `single` = practice a song, `plan` = follow a plan (default). */
  homePracticeMode: HomePracticeMode

  hydrate: () => Promise<void>
  setSkipTuneStep: (skip: boolean) => Promise<void>
  setActiveMicProfile: (id: MicCalibrationProfileId) => Promise<void>
  setCalibrationGateForProfile: (id: MicCalibrationProfileId, gateRms: number) => Promise<void>
  setIncludeListenStep: (include: boolean) => Promise<void>
  setHomePracticeMode: (mode: HomePracticeMode) => Promise<void>
  dismissListenNudge: () => Promise<void>
  /** Gate threshold stored for the active mic profile (after calibration); null if none. */
  getActiveNoiseGateThresholdRms: () => number | null
  /** True if the nudge was dismissed today (or ever). */
  isListenNudgeDismissed: () => boolean
}

export const useSessionPrefsStore = create<SessionPrefsState>((set, get) => ({
  hydrated: false,
  skipTuneStep: false,
  activeMicProfile: 'quiet-acoustic',
  calibrationGateRmsByProfile: {},
  includeListenStep: false,
  listenNudgeDismissed: {},
  homePracticeMode: 'plan',

  hydrate: async () => {
    const [skipRaw, profileRaw, calRaw, includeRaw, modeRaw] = await Promise.all([
      getAppPref(PREF_SESSION_SKIP_TUNE),
      getAppPref(PREF_SESSION_MIC_PROFILE_ID),
      getAppPref(PREF_SESSION_MIC_CALIBRATION_JSON),
      getAppPref(PREF_SESSION_INCLUDE_LISTEN),
      getAppPref(PREF_HOME_PRACTICE_MODE),
    ])
    const skipTuneStep = skipRaw === '1'
    const activeMicProfile =
      typeof profileRaw === 'string' && isProfileId(profileRaw) ? profileRaw : 'quiet-acoustic'
    const calibrationGateRmsByProfile = parseCalibrationJson(calRaw)
    const dismissedRaw = await getAppPref(`${PREF_LISTEN_NUDGE_DISMISSED}${currentLocalDayKey()}`)
    const listenNudgeDismissed: Record<string, true> = {}
    if (dismissedRaw === '1') listenNudgeDismissed[currentLocalDayKey()] = true
    set({
      hydrated: true,
      skipTuneStep,
      activeMicProfile,
      calibrationGateRmsByProfile,
      includeListenStep: includeRaw === '1',
      listenNudgeDismissed,
      homePracticeMode: modeRaw === 'single' ? 'single' : 'plan',
    })
  },

  setSkipTuneStep: async (skip) => {
    await setAppPref(PREF_SESSION_SKIP_TUNE, skip ? '1' : '0')
    set({ skipTuneStep: skip })
  },

  setActiveMicProfile: async (id) => {
    await setAppPref(PREF_SESSION_MIC_PROFILE_ID, id)
    set({ activeMicProfile: id })
  },

  setCalibrationGateForProfile: async (id, gateRms) => {
    const nextMap: CalibrationMap = { ...get().calibrationGateRmsByProfile, [id]: gateRms }
    await setAppPref(PREF_SESSION_MIC_CALIBRATION_JSON, serializeCalibrationJson(nextMap))
    set({ calibrationGateRmsByProfile: nextMap })
  },

  setIncludeListenStep: async (include) => {
    await setAppPref(PREF_SESSION_INCLUDE_LISTEN, include ? '1' : '0')
    set({ includeListenStep: include })
  },

  setHomePracticeMode: async (mode) => {
    await setAppPref(PREF_HOME_PRACTICE_MODE, mode)
    set({ homePracticeMode: mode })
  },

  dismissListenNudge: async () => {
    const key = currentLocalDayKey()
    await setAppPref(`${PREF_LISTEN_NUDGE_DISMISSED}${key}`, '1')
    set((state) => ({ listenNudgeDismissed: { ...state.listenNudgeDismissed, [key]: true } }))
  },

  getActiveNoiseGateThresholdRms: () => {
    const { activeMicProfile, calibrationGateRmsByProfile } = get()
    const v = calibrationGateRmsByProfile[activeMicProfile]
    return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null
  },

  isListenNudgeDismissed: () => {
    const { listenNudgeDismissed } = get()
    return Boolean(listenNudgeDismissed[currentLocalDayKey()])
  },
}))
