import { useFocusEffect } from '@react-navigation/native'
import * as Linking from 'expo-linking'
import { useRouter } from 'expo-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Platform, ScrollView, Switch, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ErrorBanner } from '@/components/ErrorBanner'
import { TabViewport } from '@/components/TabViewport'
import { getDiscoveryRecommendations } from '@/src/api/discovery'
import {
  createSpotifyPlaybackBridge,
  isSpotifyPlaybackBridgeSkipped,
  type SpotifyPlaybackBridgeError,
} from '@/src/audio/spotifyPlaybackBridge'
import { getAppPref, getLessonByJobId, listLessonsJournal, listSessionsJournal } from '@/src/db/client'
import { PREF_SPOTIFY_CLIENT_SESSION } from '@/src/db/schema'
import type { LessonListRow } from '@/src/db/types'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useSkillStore } from '@/src/stores/skillStore'
import type { DiscoverySuggestion, LessonJSON, SpotifyPlaybackStatePayload } from '@/src/types'
import { lessonStemUrl, stemRelPathToPlaybackUri } from '@/src/utils/lessonAudio'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import type { AlphaTabSurfaceRef } from '@/types/tabMessage'

function spotifySearchUrls(query: string): string[] {
  const q = encodeURIComponent(query)
  if (Platform.OS === 'web') {
    return [`https://open.spotify.com/search/${q}`]
  }
  return [`spotify:search:${q}`, `https://open.spotify.com/search/${q}`]
}

function spotifyBannerProps(error: SpotifyPlaybackBridgeError): { message: string; variant: 'warning' | 'error' } {
  if (error.code === 'inactive_playback') return { message: error.message, variant: 'warning' }
  return { message: error.message, variant: 'error' }
}

export default function DiscoverScreen() {
  const router = useRouter()
  const tabRef = useRef<AlphaTabSurfaceRef>(null)
  const loadSkills = useSkillStore((s) => s.loadFromDb)
  const nodes = useSkillStore((s) => s.nodes)
  const lesson = useLessonStore((s) => s.lesson)

  // Recommendations state
  const [suggestions, setSuggestions] = useState<DiscoverySuggestion[]>([])
  const [recsLoading, setRecsLoading] = useState(false)
  const [recsError, setRecsError] = useState<string | null>(null)

  // Library/Listening mode state
  const [libraryLessons, setLibraryLessons] = useState<LessonListRow[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string>('')
  const [selectedLesson, setSelectedLesson] = useState<LessonJSON | null>(null)
  const [libraryLoading, setLibraryLoading] = useState(true)
  const [libraryLoadError, setLibraryLoadError] = useState<string | null>(null)
  const [tabReady, setTabReady] = useState(false)
  const [followAlong, setFollowAlong] = useState(true)
  const [clientSession, setClientSession] = useState<string>('')
  const [playbackState, setPlaybackState] = useState<SpotifyPlaybackStatePayload | null>(null)
  const [bridgeError, setBridgeError] = useState<SpotifyPlaybackBridgeError | null>(null)

  const playbackSkipped = isSpotifyPlaybackBridgeSkipped()

  const loadRecommendations = useCallback(async () => {
    setRecsLoading(true)
    setRecsError(null)
    try {
      // Get mastered job IDs from session history
      const sessions = await listSessionsJournal()
      const masteredJobIds = sessions.slice(0, 5).map(s => s.job_id).filter((id): id is string => Boolean(id))

      // Get all lessons from library (database) - like listening tab
      const libraryRows = await listLessonsJournal()

      if (masteredJobIds.length === 0 && libraryRows.length === 0) {
        setSuggestions([])
        return
      }

      const skillNodesPayload = nodes.map(n => ({
        id: n.id,
        label: n.label,
        score: n.score,
      }))

      // Fetch full lessons from database using getLessonByJobId
      const libraryLessonsPayload = await Promise.all(
        libraryRows.map(row => getLessonByJobId(row.job_id))
      )

      const validLibraryLessons = libraryLessonsPayload.filter((l): l is NonNullable<typeof l> => l !== null)

      const response = await getDiscoveryRecommendations({
        mastered_job_ids: masteredJobIds,
        library_lessons: validLibraryLessons,
        skill_nodes: skillNodesPayload,
        limit: 5,
        min_similarity: 0.3,
      })

      setSuggestions(response.suggestions)
    } catch (e) {
      setRecsError('Failed to load recommendations')
      console.error('Discovery error:', e)
    } finally {
      setRecsLoading(false)
    }
  }, [nodes])

  const loadLibrary = useCallback(() => {
    setLibraryLoading(true)
    setLibraryLoadError(null)
    void listLessonsJournal()
      .then((rows) => {
        setLibraryLessons(rows)
        const first = rows[0]?.job_id ?? ''
        setSelectedJobId((prev) => prev || first)
      })
      .catch((e) => setLibraryLoadError(e instanceof Error ? e.message : 'Could not load analyzed songs.'))
      .finally(() => setLibraryLoading(false))
  }, [])

  useFocusEffect(
    useCallback(() => {
      void loadSkills()
      void loadRecommendations()
      loadLibrary()
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [loadLibrary])
  )

  // Load Spotify client session
  useEffect(() => {
    let cancelled = false
    void getAppPref(PREF_SPOTIFY_CLIENT_SESSION).then((value) => {
      if (cancelled) return
      setClientSession((value ?? '').trim())
    })
    return () => {
      cancelled = true
    }
  }, [])

  // Load selected lesson when job ID changes
  useEffect(() => {
    let cancelled = false
    if (!selectedJobId) {
      setSelectedLesson(null)
      return () => {
        cancelled = true
      }
    }
    setLibraryLoadError(null)
    setTabReady(false)
    void getLessonByJobId(selectedJobId)
      .then((lesson) => {
        if (cancelled) return
        if (!lesson) {
          setLibraryLoadError('Could not load this analyzed song.')
          setSelectedLesson(null)
          return
        }
        setSelectedLesson(lesson)
      })
      .catch((e) => {
        if (cancelled) return
        setSelectedLesson(null)
        setLibraryLoadError(e instanceof Error ? e.message : 'Could not load this analyzed song.')
      })
    return () => {
      cancelled = true
    }
  }, [selectedJobId])

  // Reset bridge error when selection or follow mode changes
  useEffect(() => {
    setBridgeError(null)
    setPlaybackState(null)
  }, [selectedJobId, followAlong])

  // Spotify playback bridge
  useEffect(() => {
    const tab = tabRef.current
    if (!tab || !tabReady || !followAlong || playbackSkipped) {
      tab?.setStemPlaybackActive(false)
      return
    }
    if (!clientSession) {
      setBridgeError({
        code: 'disconnected',
        message: 'Connect Spotify in Settings before using follow mode.',
      })
      return
    }
    const bridge = createSpotifyPlaybackBridge({
      clientSession,
      tab,
      onPlaybackState: setPlaybackState,
      onError: setBridgeError,
    })
    bridge.start()
    return () => {
      bridge.stop()
    }
  }, [clientSession, followAlong, playbackSkipped, tabReady])

  const handleAnalyze = (suggestion: DiscoverySuggestion) => {
    // Navigate to add-song with the job_id for one-tap analysis
    // Note: This is a one-tap deep-link to analyze, not directly to session play
    // The lesson must be loaded from the analyze job before entering session flow
    router.push({
      pathname: '/add-song',
      params: { jobId: suggestion.job_id },
    })
  }

  // Derived values for tab viewport
  const section = selectedLesson?.sections?.[0]
  const tabs = useMemo(() => readSectionTabPayloads(section), [section])
  const gp5Base64 = tabs.full ?? tabs.skeleton ?? tabs.alt ?? null
  const audioSrc = useMemo(() => {
    const rel = selectedLesson?.stems?.guitar
    if (!rel || typeof rel !== 'string') return null
    return stemRelPathToPlaybackUri(rel) ?? lessonStemUrl(rel)
  }, [selectedLesson?.stems?.guitar])

  const listenOnSpotify = useCallback(async () => {
    if (!selectedLesson) return
    const title = selectedLesson.song_title?.trim() ?? ''
    const artist = selectedLesson.artist?.trim() ?? ''
    const query = [artist, title].filter(Boolean).join(' ').trim()
    if (!query) {
      setLibraryLoadError('This lesson is missing song metadata for Spotify search.')
      return
    }
    const urls = spotifySearchUrls(query)
    for (const url of urls) {
      try {
        await Linking.openURL(url)
        return
      } catch {
        // Try next URL variant.
      }
    }
    setLibraryLoadError('Could not open Spotify on this device.')
  }, [selectedLesson])

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-6 py-6" contentContainerStyle={{ paddingBottom: 36 }}>
        <Text className="font-serif text-3xl text-cream">Discover</Text>
        <Text className="mt-2 font-sans text-sm text-muted-brown">
          Song recommendations and your library — play along with Spotify while tabs follow in real time.
        </Text>

        {recsError && <ErrorBanner message={recsError} variant="error" className="mt-4" />}

        {/* Recommendations Section */}
        <View className="mt-6 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Recommended songs</Text>
          {recsLoading ? <Text className="mt-3 font-sans text-sm text-muted-brown">Loading recommendations…</Text> : null}
          {!recsLoading && suggestions.length === 0 ? (
            <Text className="mt-3 font-sans text-sm text-muted-brown">
              Complete more lessons to get personalized recommendations
            </Text>
          ) : (
            <View className="mt-3 gap-2">
              {suggestions.map((suggestion) => (
                <AnimatedPressable
                  key={suggestion.job_id}
                  onPress={() => handleAnalyze(suggestion)}
                  haptic="light"
                  className="rounded-lg border border-wood-600/45 bg-wood-900/40 px-3 py-2.5"
                >
                  <Text className="font-sans-medium text-sm text-cream">{suggestion.song_title || 'Unknown Song'}</Text>
                  <Text className="mt-0.5 font-sans text-xs text-muted-brown">
                    {suggestion.artist || 'Unknown Artist'}
                  </Text>
                  {suggestion.reasonLabel && (
                    <Text className="mt-2 font-sans text-xs text-cream/70 leading-relaxed">
                      {suggestion.reasonLabel}
                    </Text>
                  )}
                </AnimatedPressable>
              ))}
            </View>
          )}
        </View>

        {/* Library / Listening Mode Section */}
        {libraryLoadError ? <ErrorBanner message={libraryLoadError} variant="error" className="mt-4" /> : null}
        {playbackSkipped ? (
          <ErrorBanner
            message="Spotify playback polling is disabled via HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1."
            detail="The tab still loads in static study mode."
            variant="info"
            className="mt-4"
            dismissible={false}
          />
        ) : null}
        {bridgeError ? (
          <ErrorBanner
            message={spotifyBannerProps(bridgeError).message}
            variant={spotifyBannerProps(bridgeError).variant}
            className="mt-4"
            dismissible={false}
          />
        ) : null}

        <View className="mt-6 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">Your Library</Text>
          <Text className="mt-1 font-sans text-xs text-muted-brown">
            Select a song to view tabs and enable Spotify follow-along
          </Text>
          {libraryLoading ? <Text className="mt-3 font-sans text-sm text-muted-brown">Loading songs…</Text> : null}
          {!libraryLoading && libraryLessons.length === 0 ? (
            <Text className="mt-3 font-sans text-sm text-muted-brown">
              No analyzed songs yet. Add one first from Home or Library.
            </Text>
          ) : (
            <View className="mt-3 gap-2">
              {libraryLessons.slice(0, 10).map((row) => {
                const selected = row.job_id === selectedJobId
                return (
                  <AnimatedPressable
                    key={row.job_id}
                    onPress={() => setSelectedJobId(row.job_id)}
                    haptic="light"
                    className={`rounded-lg border px-3 py-2.5 ${
                      selected ? 'border-amber-accent bg-amber-accent/15' : 'border-wood-600/45 bg-wood-900/40'
                    }`}
                  >
                    <Text className={`font-sans-medium text-sm ${selected ? 'text-amber-light' : 'text-cream'}`}>
                      {row.song_title?.trim() || 'Untitled lesson'}
                    </Text>
                    <Text className="mt-0.5 font-sans text-xs text-muted-brown">
                      {row.artist?.trim() || 'Unknown artist'}
                    </Text>
                  </AnimatedPressable>
                )
              })}
            </View>
          )}
        </View>

        {/* Spotify Controls */}
        <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
          <View className="flex-row items-center justify-between gap-3">
            <View className="flex-1 pr-2">
              <Text className="font-sans-medium text-sm text-cream">Follow along</Text>
              <Text className="mt-1 font-sans text-xs text-muted-brown">
                Sync tab cursor to Spotify playback position.
              </Text>
            </View>
            <Switch value={followAlong} onValueChange={setFollowAlong} disabled={playbackSkipped} />
          </View>
          <AnimatedPressable
            onPress={() => void listenOnSpotify()}
            haptic="medium"
            className="mt-4 rounded-lg bg-amber-accent/90 px-4 py-3"
          >
            <Text className="text-center font-sans-medium text-sm text-wood-900">Listen on Spotify</Text>
          </AnimatedPressable>
          <Text className="mt-2 font-sans text-[11px] text-muted-brown">
            This opens Spotify search for the selected song. Harmoniq never starts/stops Spotify playback.
          </Text>
          {playbackState ? (
            <Text className="mt-3 font-sans text-xs text-cream">
              Now tracking:{' '}
              <Text className="font-sans-medium text-amber-light">
                {playbackState.track_name?.trim() || 'Unknown track'}
              </Text>{' '}
              {playbackState.artists?.length ? `· ${playbackState.artists.join(', ')}` : ''} ·{' '}
              {playbackState.is_playing ? 'Playing' : 'Paused'}
            </Text>
          ) : null}
        </View>

        {/* Tab Viewport */}
        <View className="mt-4 h-[340px] w-full">
          <TabViewport
            ref={tabRef}
            gp5Base64={gp5Base64}
            audioSrc={audioSrc}
            renderPreset="listen"
            runtimeDiagnosticsEnabled={false}
            readOnlyFollowMode
            onReady={() => setTabReady(true)}
            onError={(message) => setLibraryLoadError(message)}
            style={{ flex: 1, height: '100%', width: '100%' }}
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}
