/** Stable identity for analyzed songs so re-analyses replace library rows. */

export interface LessonIdentityFields {
  source_url?: string | null
  song_title?: string | null
  artist?: string | null
}

export interface LessonIdentityRow extends LessonIdentityFields {
  job_id: string
  analyzed_at: string
  lesson_json?: string | null
}

const GENERIC_TITLES = new Set(['unknown title', 'youtube video', 'uploaded track'])
const GENERIC_ARTISTS = new Set(['unknown artist', 'harmoniq ai'])

export function normalizeSongField(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase().replace(/\s+/g, ' ')
}

/** Extract a stable identifier from a YouTube or generic URL. */
export function normalizeSourceUrl(value: string | null | undefined): string {
  const raw = (value ?? '').trim()
  if (!raw) return ''
  const youtube = raw.match(/(?:youtu\.be\/|[?&]v=)([A-Za-z0-9_-]{6,})/)
  if (youtube) return `youtube:${youtube[1]}`
  try {
    const url = new URL(raw)
    url.hash = ''
    return url.toString().toLowerCase()
  } catch {
    return raw.toLowerCase().replace(/[?#].*$/, '')
  }
}

export function lessonSourceUrlKey(fields: LessonIdentityFields): string {
  const url = normalizeSourceUrl(fields.source_url)
  return url ? `url:${url}` : ''
}

/** Real title/artist key; empty for generic placeholders. */
export function lessonMetaKey(fields: LessonIdentityFields): string {
  const title = normalizeSongField(fields.song_title)
  const artist = normalizeSongField(fields.artist)
  const hasRealTitle = Boolean(title) && !GENERIC_TITLES.has(title)
  const hasRealArtist = Boolean(artist) && !GENERIC_ARTISTS.has(artist)
  return hasRealTitle || hasRealArtist ? `meta:${title}|${artist}` : ''
}

/**
 * Identity used to collapse duplicate library entries.
 *
 * The source URL wins when present so different recordings that share a
 * title/artist (live vs. studio) stay separate. Legacy rows without a URL use
 * real metadata, and anonymous uploads fall back to the job id.
 */
export function lessonIdentityKey(fields: LessonIdentityFields, jobId?: string | null): string {
  return lessonSourceUrlKey(fields) || lessonMetaKey(fields) || `job:${(jobId ?? '').trim()}`
}

/** Read fields from a persisted row, parsing lesson_json only when needed. */
export function lessonRowFields(row: LessonIdentityRow): LessonIdentityFields {
  let sourceUrl = row.source_url ?? null
  if (!sourceUrl && row.lesson_json) {
    try {
      const parsed = JSON.parse(row.lesson_json) as { source_url?: unknown }
      if (typeof parsed.source_url === 'string') sourceUrl = parsed.source_url
    } catch {
      // Malformed JSON is treated as missing source_url.
    }
  }
  return { source_url: sourceUrl, song_title: row.song_title, artist: row.artist }
}

export function lessonIdentityKeyFromRow(row: LessonIdentityRow): string {
  return lessonIdentityKey(lessonRowFields(row), row.job_id)
}

/**
 * Whether an incoming analysis should replace an existing library row.
 *
 * URL rows only match the same URL. An incoming URL row also replaces a
 * legacy row (no URL) with the same real metadata, which is how older
 * duplicates get migrated. Rows without a URL match on metadata.
 */
export function lessonShouldReplace(existing: LessonIdentityFields, incoming: LessonIdentityFields): boolean {
  const incomingUrl = lessonSourceUrlKey(incoming)
  const existingUrl = lessonSourceUrlKey(existing)
  if (incomingUrl) {
    if (existingUrl) return incomingUrl === existingUrl
    const incomingMeta = lessonMetaKey(incoming)
    return Boolean(incomingMeta && incomingMeta === lessonMetaKey(existing))
  }
  return lessonIdentityKey(existing) === lessonIdentityKey(incoming)
}

export interface DedupeLessonRowsResult<T> {
  kept: T[]
  removedJobIds: string[]
}

/**
 * Keep the newest row per identity. Runs once at DB init and on upsert, not on
 * read paths.
 */
export function dedupeLessonRows<T extends LessonIdentityRow>(rows: readonly T[]): DedupeLessonRowsResult<T> {
  const fieldsByJobId = new Map<string, LessonIdentityFields>()
  const newestByKey = new Map<string, T>()

  for (const row of rows) {
    const fields = lessonRowFields(row)
    fieldsByJobId.set(row.job_id, fields)
    const key = lessonIdentityKey(fields, row.job_id)
    const current = newestByKey.get(key)
    if (!current || row.analyzed_at > current.analyzed_at) newestByKey.set(key, row)
  }

  // Normalize duplicates across the legacy(meta) → URL migration: once a URL
  // row exists for a song, drop the ambiguous URL-less row.
  const metaKeysWithUrl = new Set<string>()
  for (const row of newestByKey.values()) {
    const fields = fieldsByJobId.get(row.job_id)!
    if (lessonSourceUrlKey(fields)) {
      const meta = lessonMetaKey(fields)
      if (meta) metaKeysWithUrl.add(meta)
    }
  }

  const kept = [...newestByKey.values()].filter((row) => {
    const fields = fieldsByJobId.get(row.job_id)!
    if (lessonSourceUrlKey(fields)) return true
    const meta = lessonMetaKey(fields)
    return !(meta && metaKeysWithUrl.has(meta))
  })
  const keptIds = new Set(kept.map((row) => row.job_id))
  return {
    kept,
    removedJobIds: rows.filter((row) => !keptIds.has(row.job_id)).map((row) => row.job_id),
  }
}
