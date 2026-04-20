import { create } from 'zustand'

import { getAppPref, setAppPref } from '@/src/db/client'
import {
  PREF_SESSION_MIC_CALIBRATION_JSON,
  PREF_SESSION_MIC_PROFILE_ID,
  PREF_SESSION_SKIP_TUNE,
} from '@/src/db/schema'

export type MicCalibrationProfileId = 'quiet-acoustic' | 'electric-unplugged'

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

export type SessionPrefsState = {
  hydrated: boolean
  skipTuneStep: boolean
  activeMicProfile: MicCalibrationProfileId
  calibrationGateRmsByProfile: CalibrationMap

  hydrate: () => Promise<void>
  setSkipTuneStep: (skip: boolean) => Promise<void>
  setActiveMicProfile: (id: MicCalibrationProfileId) => Promise<void>
  setCalibrationGateForProfile: (id: MicCalibrationProfileId, gateRms: number) => Promise<void>
  /** Gate threshold stored for the active mic profile (after calibration); null if none. */
  getActiveNoiseGateThresholdRms: () => number | null
}

export const useSessionPrefsStore = create<SessionPrefsState>((set, get) => ({
  hydrated: false,
  skipTuneStep: false,
  activeMicProfile: 'quiet-acoustic',
  calibrationGateRmsByProfile: {},

  hydrate: async () => {
    const [skipRaw, profileRaw, calRaw] = await Promise.all([
      getAppPref(PREF_SESSION_SKIP_TUNE),
      getAppPref(PREF_SESSION_MIC_PROFILE_ID),
      getAppPref(PREF_SESSION_MIC_CALIBRATION_JSON),
    ])
    const skipTuneStep = skipRaw === '1'
    const activeMicProfile =
      typeof profileRaw === 'string' && isProfileId(profileRaw) ? profileRaw : 'quiet-acoustic'
    const calibrationGateRmsByProfile = parseCalibrationJson(calRaw)
    set({ hydrated: true, skipTuneStep, activeMicProfile, calibrationGateRmsByProfile })
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

  getActiveNoiseGateThresholdRms: () => {
    const { activeMicProfile, calibrationGateRmsByProfile } = get()
    const v = calibrationGateRmsByProfile[activeMicProfile]
    return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null
  },
}))
