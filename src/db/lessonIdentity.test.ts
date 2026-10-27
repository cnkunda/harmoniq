import { describe, expect, it } from 'vitest'

import {
  dedupeLessonRows,
  lessonIdentityKey,
  lessonIdentityKeyFromRow,
  lessonShouldReplace,
  normalizeSourceUrl,
} from './lessonIdentity'

describe('normalizeSourceUrl', () => {
  it('reduces YouTube URLs to a stable video id', () => {
    expect(normalizeSourceUrl('https://www.youtube.com/watch?v=Cx3QmqV2pHg&list=RDCx3QmqV2pHg')).toBe(
      'youtube:Cx3QmqV2pHg',
    )
    expect(normalizeSourceUrl('https://youtu.be/Cx3QmqV2pHg?t=30')).toBe('youtube:Cx3QmqV2pHg')
  })

  it('returns empty for missing values', () => {
    expect(normalizeSourceUrl(null)).toBe('')
    expect(normalizeSourceUrl('   ')).toBe('')
  })
})

describe('lessonIdentityKey', () => {
  it('prefers the source URL when present', () => {
    const key = lessonIdentityKey({
      song_title: 'Never',
      artist: 'Nonso Amadi',
      source_url: 'https://www.youtube.com/watch?v=Cx3QmqV2pHg',
    })
    expect(key).toBe('url:youtube:Cx3QmqV2pHg')
  })

  it('uses normalized title and artist for legacy rows without a URL', () => {
    const key = lessonIdentityKey({ song_title: '  Never ', artist: 'Nonso  Amadi' })
    expect(key).toBe('meta:never|nonso amadi')
  })

  it('falls back to the source URL for generic metadata', () => {
    const key = lessonIdentityKey({
      song_title: 'YouTube video',
      artist: 'Unknown artist',
      source_url: 'https://www.youtube.com/watch?v=Cx3QmqV2pHg',
    })
    expect(key).toBe('url:youtube:Cx3QmqV2pHg')
  })

  it('falls back to the job id for anonymous uploads', () => {
    const key = lessonIdentityKey(
      { song_title: 'Uploaded track', artist: 'Unknown artist' },
      'job-abc',
    )
    expect(key).toBe('job:job-abc')
  })
})

describe('lessonShouldReplace', () => {
  it('matches the same URL', () => {
    expect(
      lessonShouldReplace(
        { song_title: 'Never', artist: 'Nonso Amadi', source_url: 'https://youtu.be/aaa111' },
        { song_title: 'Never (Live)', artist: 'Nonso Amadi', source_url: 'https://youtu.be/aaa111' },
      ),
    ).toBe(true)
  })

  it('keeps different URLs separate even with identical metadata', () => {
    expect(
      lessonShouldReplace(
        { song_title: 'Never', artist: 'Nonso Amadi', source_url: 'https://youtu.be/aaa111' },
        { song_title: 'Never', artist: 'Nonso Amadi', source_url: 'https://youtu.be/bbb222' },
      ),
    ).toBe(false)
  })

  it('migrates a legacy metadata row when the incoming row has a URL', () => {
    expect(
      lessonShouldReplace(
        { song_title: 'Never', artist: 'Nonso Amadi' },
        { song_title: 'Never', artist: 'Nonso Amadi', source_url: 'https://youtu.be/aaa111' },
      ),
    ).toBe(true)
  })

  it('replaces a metadata row when the incoming row also has no URL', () => {
    expect(
      lessonShouldReplace(
        { song_title: 'Never', artist: 'Nonso Amadi' },
        { song_title: 'Never', artist: 'Nonso Amadi' },
      ),
    ).toBe(true)
  })

  it('does not replace a URL row with an anonymous upload of the same title', () => {
    expect(
      lessonShouldReplace(
        { song_title: 'Never', artist: 'Nonso Amadi', source_url: 'https://youtu.be/aaa111' },
        { song_title: 'Never', artist: 'Nonso Amadi' },
      ),
    ).toBe(false)
  })
})

describe('dedupeLessonRows', () => {
  it('keeps the newest row per song and reports the rest for deletion', () => {
    const rows = [
      {
        job_id: 'old',
        song_title: 'Never',
        artist: 'Nonso Amadi',
        analyzed_at: '2026-10-26T10:00:00.000Z',
        lesson_json: '{}',
      },
      {
        job_id: 'new',
        song_title: 'never',
        artist: 'nonso amadi',
        analyzed_at: '2026-10-27T11:00:00.000Z',
        lesson_json: '{}',
      },
      {
        job_id: 'other',
        song_title: 'Gravity',
        artist: 'John Mayer',
        analyzed_at: '2026-10-25T10:00:00.000Z',
        lesson_json: '{}',
      },
    ]

    const result = dedupeLessonRows(rows)

    expect(result.kept.map((row) => row.job_id).sort()).toEqual(['new', 'other'])
    expect(result.removedJobIds).toEqual(['old'])
  })

  it('keeps different recordings with the same metadata when URLs differ', () => {
    const rows = [
      {
        job_id: 'studio',
        song_title: 'Never',
        artist: 'Nonso Amadi',
        analyzed_at: '2026-10-26T10:00:00.000Z',
        lesson_json: JSON.stringify({ source_url: 'https://youtu.be/aaa111' }),
      },
      {
        job_id: 'live',
        song_title: 'Never',
        artist: 'Nonso Amadi',
        analyzed_at: '2026-10-27T11:00:00.000Z',
        lesson_json: JSON.stringify({ source_url: 'https://youtu.be/bbb222' }),
      },
    ]

    expect(dedupeLessonRows(rows).removedJobIds).toEqual([])
  })

  it('drops a legacy URL-less row once a URL row exists for the same song', () => {
    const rows = [
      {
        job_id: 'legacy',
        song_title: 'Never',
        artist: 'Nonso Amadi',
        analyzed_at: '2026-10-27T11:00:00.000Z',
        lesson_json: '{}',
      },
      {
        job_id: 'url',
        song_title: 'Never',
        artist: 'Nonso Amadi',
        analyzed_at: '2026-10-26T10:00:00.000Z',
        lesson_json: JSON.stringify({ source_url: 'https://youtu.be/aaa111' }),
      },
    ]

    const result = dedupeLessonRows(rows)

    expect(result.kept.map((row) => row.job_id)).toEqual(['url'])
    expect(result.removedJobIds).toEqual(['legacy'])
  })

  it('does not collapse anonymous uploads together', () => {
    const rows = [
      {
        job_id: 'upload-1',
        song_title: 'Uploaded track',
        artist: 'Unknown artist',
        analyzed_at: '2026-10-26T10:00:00.000Z',
        lesson_json: '{}',
      },
      {
        job_id: 'upload-2',
        song_title: 'Uploaded track',
        artist: 'Unknown artist',
        analyzed_at: '2026-10-27T11:00:00.000Z',
        lesson_json: '{}',
      },
    ]

    expect(dedupeLessonRows(rows).removedJobIds).toEqual([])
  })
})

describe('lessonIdentityKeyFromRow', () => {
  it('parses source_url from persisted JSON when metadata is generic', () => {
    const key = lessonIdentityKeyFromRow({
      job_id: 'job-1',
      song_title: 'YouTube video',
      artist: 'Unknown artist',
      analyzed_at: '2026-10-27T11:00:00.000Z',
      lesson_json: JSON.stringify({ source_url: 'https://youtu.be/Cx3QmqV2pHg' }),
    })
    expect(key).toBe('url:youtube:Cx3QmqV2pHg')
  })

  it('prefers source_url even when real metadata is present', () => {
    const key = lessonIdentityKeyFromRow({
      job_id: 'job-1',
      song_title: 'Never',
      artist: 'Nonso Amadi',
      analyzed_at: '2026-10-27T11:00:00.000Z',
      lesson_json: JSON.stringify({ source_url: 'https://youtu.be/Cx3QmqV2pHg' }),
    })
    expect(key).toBe('url:youtube:Cx3QmqV2pHg')
  })
})
