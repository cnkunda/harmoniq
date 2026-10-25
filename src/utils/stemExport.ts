import { STEM_KEYS, type StemKey } from '@/src/constants/stems'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'

/** Must match the backend 404 detail for missing/evicted stems. */
export const STEM_EXPORT_UNAVAILABLE_COPY =
  'Stems for this song are no longer available — they may have been cleaned up. Re-analyze the song to export again.'

export function buildStemsExportUrl(apiBaseUrl: string, jobId: string, stem?: StemKey | null): string {
  const base = `${apiBaseUrl.replace(/\/$/, '')}/jobs/${encodeURIComponent(jobId)}/stems`
  return stem ? `${base}?stem=${encodeURIComponent(stem)}` : base
}

export function stemExportFilename(base: string, stem?: StemKey | null): string {
  if (stem) return `${stem}.wav`
  const safe = base.replace(/[^\w.\-()+ ]+/g, '_').replace(/^[\s._]+|[\s._]+$/g, '').slice(0, 80)
  return `${safe || 'harmoniq'}-stems.zip`
}

/** The demo lesson and other bundled-only lessons have no backend job to export. */
export function isExportableJobId(jobId: string | null | undefined): jobId is string {
  return typeof jobId === 'string' && jobId.length > 0 && jobId !== DEMO_LESSON_JOB_ID
}

/** Stem keys that point at backend files (not `bundled://` assets). */
export function exportableStemKeys(stems: Record<string, string> | null | undefined): StemKey[] {
  if (!stems) return []
  return STEM_KEYS.filter((key) => {
    const value = stems[key]
    return typeof value === 'string' && value.trim().length > 0 && !value.trim().startsWith('bundled://')
  })
}

export function canExportStems(
  jobId: string | null | undefined,
  stems: Record<string, string> | null | undefined,
): boolean {
  return isExportableJobId(jobId) && exportableStemKeys(stems).length > 0
}
