import { describe, expect, it, vi } from 'vitest'

import type { SongSuggestion } from './suggestSongs'
import { startOnboardingAnalyses } from './startOnboardingAnalyses'
import type { TrackAnalysisJobInput } from '@/src/analysis/trackedAnalysisJobs'

const SONGS: SongSuggestion[] = [
  { title: 'Song A', artist: 'Artist A', youtubeUrl: 'https://youtu.be/a', vibe: 'blues' },
  { title: 'Song B', artist: 'Artist B', youtubeUrl: 'https://youtu.be/b', vibe: 'rock' },
]

describe('startOnboardingAnalyses', () => {
  it('submits and tracks every selected song', async () => {
    const submit = vi.fn(async ({ youtube_url }: { youtube_url: string }) => `job-${youtube_url.slice(-1)}`)
    const track = vi.fn(async (_input: TrackAnalysisJobInput) => {})
    const progress: Array<[number, number]> = []

    const outcome = await startOnboardingAnalyses(SONGS, {
      submit,
      track,
      onProgress: (completed, total) => progress.push([completed, total]),
    })

    expect(outcome.failed).toEqual([])
    expect(outcome.started.map((row) => row.jobId)).toEqual(['job-a', 'job-b'])
    expect(submit).toHaveBeenNthCalledWith(1, { youtube_url: 'https://youtu.be/a' })
    expect(submit).toHaveBeenNthCalledWith(2, { youtube_url: 'https://youtu.be/b' })
    expect(track).toHaveBeenNthCalledWith(1, {
      jobId: 'job-a',
      sourceKind: 'youtube',
      sourceRef: 'https://youtu.be/a',
      title: 'Song A',
      artist: 'Artist A',
    })
    expect(progress).toEqual([
      [1, 2],
      [2, 2],
    ])
  })

  it('continues after one submission fails', async () => {
    const submit = vi
      .fn<({ youtube_url }: { youtube_url: string }) => Promise<string>>()
      .mockRejectedValueOnce(new Error('backend down'))
      .mockResolvedValueOnce('job-b')
    const track = vi.fn(async (_input: TrackAnalysisJobInput) => {})

    const outcome = await startOnboardingAnalyses(SONGS, { submit, track })

    expect(outcome.started.map((row) => row.song.title)).toEqual(['Song B'])
    expect(outcome.failed.map((row) => row.song.title)).toEqual(['Song A'])
    expect(track).toHaveBeenCalledTimes(1)
  })

  it('reports every song when submissions all fail', async () => {
    const submit = vi.fn(async () => {
      throw new Error('offline')
    })
    const track = vi.fn(async (_input: TrackAnalysisJobInput) => {})

    const outcome = await startOnboardingAnalyses(SONGS, { submit, track })

    expect(outcome.started).toEqual([])
    expect(outcome.failed).toHaveLength(2)
    expect(track).not.toHaveBeenCalled()
  })
})
