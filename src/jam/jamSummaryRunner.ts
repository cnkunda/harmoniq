import {
  buildPlayerProfileFromSkillNodes,
  loadLearningContextFromPrefs,
  parseTasteProfileJson,
} from '@/src/api/analyze'
import {
  submitJamSummary,
  type JamPersonaChoice,
  type JamPhraseMetrics,
  type JamSummaryBundle,
  type JamSummaryPersona,
  type JamSummaryRequestBody,
} from '@/src/api/jam'
import { getAppPref, getAllSkillNodes, setAppPref, updateJamSnapshotSummary } from '@/src/db/client'
import { PREF_JAM_SUMMARY_PERSONA, PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'
import type { JamSnapshotRow } from '@/src/db/types'

export const DEFAULT_JAM_PERSONA_CHOICE: JamPersonaChoice = 'encouraging'

export function personaChoiceToBackend(choice: JamPersonaChoice): JamSummaryPersona {
  return choice === 'technical' ? 'transcriber' : 'learner'
}

export function parseJamPersonaChoice(raw: string | null): JamPersonaChoice {
  return raw === 'technical' ? 'technical' : 'encouraging'
}

export async function loadJamPersonaChoice(): Promise<JamPersonaChoice> {
  return parseJamPersonaChoice(await getAppPref(PREF_JAM_SUMMARY_PERSONA))
}

export async function saveJamPersonaChoice(choice: JamPersonaChoice): Promise<void> {
  await setAppPref(PREF_JAM_SUMMARY_PERSONA, choice)
}

export function parseStoredPhrases(raw: string | null): JamPhraseMetrics[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) {
      console.warn('[JamSummary] phrases_json is not an array')
      return []
    }
    return parsed as JamPhraseMetrics[]
  } catch (error) {
    console.warn('[JamSummary] could not parse phrases_json', error)
    return []
  }
}

export type JamSummaryRequestContext = {
  duration_seconds: number
  pitch_class_weight_map: Record<string, number>
  inferred_scale_label: string | null
  inference_confidence: 'low' | 'medium' | 'high' | null
  track_id: string | null
  track_label: string | null
  track_key: string | null
  track_bpm: number | null
  phrases: JamPhraseMetrics[]
  personaChoice: JamPersonaChoice
  weak_areas: readonly string[]
  previous_jam_count?: number
}

export function requestJamSummary(context: JamSummaryRequestContext): JamSummaryRequestBody {
  return {
    duration_seconds: context.duration_seconds,
    pitch_class_weight_map: context.pitch_class_weight_map,
    inferred_scale_label: context.inferred_scale_label,
    inference_confidence: context.inference_confidence,
    track_id: context.track_id,
    track_label: context.track_label,
    track_key: context.track_key,
    track_bpm: context.track_bpm,
    phrases: context.phrases,
    player_level: 'intermediate',
    persona: personaChoiceToBackend(context.personaChoice),
    previous_jam_count: context.previous_jam_count ?? 0,
    weak_areas: [...context.weak_areas],
  }
}

export async function persistJamSummary(
  snapshotId: string,
  request: JamSummaryRequestBody,
): Promise<JamSummaryBundle> {
  const response = await submitJamSummary(request)
  const bundle = response.bundle
  await updateJamSnapshotSummary(snapshotId, {
    summary_bundle_json: JSON.stringify(bundle),
    coach_summary: bundle.coach_summary || response.coach_summary,
    summary_status: 'ready',
  })
  return bundle
}

export async function markJamSummaryFailed(snapshotId: string, coachSummary: string): Promise<void> {
  await updateJamSnapshotSummary(snapshotId, {
    summary_bundle_json: null,
    coach_summary: coachSummary,
    summary_status: 'failed',
  })
}

export async function runJamSummary(
  snapshotId: string,
  request: JamSummaryRequestBody,
  fallbackSummary: string,
): Promise<JamSummaryBundle> {
  try {
    return await persistJamSummary(snapshotId, request)
  } catch (error) {
    console.error('[JamSummary] summary request failed', error)
    try {
      await markJamSummaryFailed(snapshotId, fallbackSummary)
    } catch (persistError) {
      console.error('[JamSummary] could not mark snapshot failed', persistError)
    }
    throw error
  }
}

async function loadCurrentWeakAreas(): Promise<string[]> {
  const [nodes, tasteRaw, learningCtx] = await Promise.all([
    getAllSkillNodes(),
    getAppPref(PREF_TASTE_PROFILE_JSON),
    loadLearningContextFromPrefs(),
  ])
  const profile = buildPlayerProfileFromSkillNodes(nodes, parseTasteProfileJson(tasteRaw), learningCtx)
  return profile?.weak_areas ?? []
}

export async function retryJamSummary(
  row: JamSnapshotRow,
  options?: { weakAreas?: readonly string[] },
): Promise<JamSummaryBundle> {
  const phrases = parseStoredPhrases(row.phrases_json)
  if (phrases.length === 0) {
    await updateJamSnapshotSummary(row.id, {
      summary_bundle_json: row.summary_bundle_json,
      coach_summary: row.coach_summary,
      summary_status: 'skipped',
    })
    throw new Error('This jam has no phrase data to analyze.')
  }

  const [personaChoice, weakAreas] = await Promise.all([
    loadJamPersonaChoice(),
    options?.weakAreas ? Promise.resolve([...options.weakAreas]) : loadCurrentWeakAreas(),
  ])

  const request = requestJamSummary({
    duration_seconds: row.duration_seconds,
    pitch_class_weight_map: row.pitch_class_weight_map ?? row.scale_position_map ?? {},
    inferred_scale_label: row.inferred_scale_label,
    inference_confidence: row.inference_confidence,
    track_id: row.track_id,
    track_label: row.track_label,
    track_key: row.track_key,
    track_bpm: row.track_bpm,
    phrases,
    personaChoice,
    weak_areas: weakAreas,
  })

  await updateJamSnapshotSummary(row.id, {
    summary_bundle_json: row.summary_bundle_json,
    coach_summary: row.coach_summary,
    summary_status: 'pending',
  })

  return runJamSummary(row.id, request, row.coach_summary)
}
