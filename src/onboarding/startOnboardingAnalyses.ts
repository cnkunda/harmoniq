import type { TrackAnalysisJobInput } from '@/src/analysis/trackedAnalysisJobs'
import type { SongSuggestion } from '@/src/onboarding/suggestSongs'

export type OnboardingAnalysisDeps = {
  submit: (input: { youtube_url: string }) => Promise<string>
  track: (input: TrackAnalysisJobInput) => Promise<void>
  onProgress?: (completed: number, total: number) => void
}

export type OnboardingAnalysisOutcome = {
  started: Array<{ song: SongSuggestion; jobId: string }>
  failed: Array<{ song: SongSuggestion; error: unknown }>
}

/**
 * Submit each selected onboarding song as a background analysis job and add it
 * to the tracked-jobs store. Per-song failures are reported, not thrown.
 */
export async function startOnboardingAnalyses(
  songs: SongSuggestion[],
  deps: OnboardingAnalysisDeps,
): Promise<OnboardingAnalysisOutcome> {
  const started: OnboardingAnalysisOutcome['started'] = []
  const failed: OnboardingAnalysisOutcome['failed'] = []

  for (let index = 0; index < songs.length; index += 1) {
    const song = songs[index]!
    try {
      const jobId = await deps.submit({ youtube_url: song.youtubeUrl })
      try {
        await deps.track({
          jobId,
          sourceKind: 'youtube',
          sourceRef: song.youtubeUrl,
          title: song.title,
          artist: song.artist,
        })
      } catch (trackError) {
        console.warn('[onboarding] could not track analysis job', trackError)
      }
      started.push({ song, jobId })
    } catch (error) {
      failed.push({ song, error })
    }
    deps.onProgress?.(index + 1, songs.length)
  }

  return { started, failed }
}
